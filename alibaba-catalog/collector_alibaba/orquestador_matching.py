"""
Orquesta Match Mode (Fase 2) para un candidato de Mercado Libre con demanda
confirmada: genera una query de búsqueda en Alibaba, abre esa búsqueda,
rankea los resultados contra el producto de ML (`matcher.py`), verifica el
`top_k` abriendo fichas individuales en orden, y persiste el resultado
completo (auditable) en `matching_alibaba` (ver `database/db.py`).

La lógica de decisión (`procesar_candidato_matching`) está separada de la
navegación real, igual que `orquestador_demanda_ml.py`: recibe
`obtener_html_busqueda` y `abrir_ficha` inyectados, así se puede probar
todo el flujo con HTML ya capturado. `ejecutar_matching_real` es el punto
de entrada que arma esas funciones con Playwright + Chrome real.

**Retrieval vs. matching (ajuste #3, aprobado por la usuaria)**: la
generación de la query es una lista ordenable de estrategias
(`generadores_query`), probadas en orden hasta que una devuelva algún
resultado. Por ahora solo hay una (`generar_query_busqueda_v1`: el propio
título de ML limpiado, SIN traducir) -- se prueba primero por ser la más
barata. Si la validación real (ver ESTADO_ACTUAL.md) muestra que no
recupera el producto conocido con suficiente frecuencia, se agrega una
segunda estrategia (ej. título traducido al inglés) a esta misma lista,
sin tocar `matcher.py` en absoluto: retrieval y matching son problemas
distintos, y "la búsqueda no encontró nada" nunca se interpreta como "el
producto no existe" (`matcher.ejecutar_matching` ya lo deja explícito en
el motivo cuando la lista de candidatos viene vacía).

Uso:
    python orquestador_matching.py "https://articulo.mercadolibre.com.ar/MLA-..."
    python orquestador_matching.py "https://articulo.mercadolibre.com.ar/MLA-..." --top-k 5 --login
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "database"))

from playwright.sync_api import Error as PlaywrightError  # noqa: E402

from embeddings import EmbedderImagenClip, EmbedderTextoClip  # noqa: E402
from matcher import (  # noqa: E402
    CandidatoAlibabaListado,
    PesosMatching,
    ProductoMLParaMatching,
    TOP_K_DEFAULT,
    UmbralesMatching,
    ejecutar_matching,
    match_result_a_dict,
)
from navegador_ml import (  # noqa: E402
    DELAY_MAX_SEG_DEFAULT,
    DELAY_MIN_SEG_DEFAULT,
    abrir_pagina_ml,
    confirmar_login_manual,
    contenido_seguro,
    es_primera_vez,
    esperar_entre_fichas,
    navegador_persistente,
    pausar_por_bloqueo_y_continuar,
)
from capturador_exploratorio import _guardar_html, _registrar_captura  # noqa: E402
from parser_busqueda_alibaba import parsear_listado_busqueda  # noqa: E402
from parser_ficha_ml import parsear_ficha_ml  # noqa: E402
from scraper import contiene_marcadores_bloqueo as bloqueado_alibaba  # noqa: E402
import db  # noqa: E402

URL_BUSQUEDA_ALIBABA = "https://www.alibaba.com/trade/search?SearchText={query}"
URL_ALIBABA_HOME = "https://www.alibaba.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "orquestador_matching.log")],
)
logger = logging.getLogger("orquestador_matching")

_STOPWORDS_ES = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "con", "para", "por",
    "y", "o", "en", "del", "al", "a", "que", "sin", "más", "mas",
}


def generar_query_busqueda_v1(nombre_ml: str, max_palabras: int = 6) -> str:
    """
    Única estrategia de retrieval por ahora (ajuste #3): el propio título
    de ML, limpiado de stopwords y números sueltos, SIN traducir. Se
    prueba primero por ser la más barata -- si la validación real muestra
    recall insuficiente, se agrega una segunda estrategia a
    `ESTRATEGIAS_QUERY_DEFAULT` en vez de tocar esta función.
    """
    palabras = re.findall(r"[a-záéíóúñ0-9]+", (nombre_ml or "").lower())
    significativas = [p for p in palabras if p not in _STOPWORDS_ES and not p.isdigit()]
    return " ".join(significativas[:max_palabras]) or (nombre_ml or "")


ESTRATEGIAS_QUERY_DEFAULT: list[Callable[[str], str]] = [generar_query_busqueda_v1]


def _url_busqueda_alibaba(query: str) -> str:
    import urllib.parse

    return URL_BUSQUEDA_ALIBABA.format(query=urllib.parse.quote(query))


def _listado_a_candidatos(resultados: list[dict]) -> list[CandidatoAlibabaListado]:
    return [
        CandidatoAlibabaListado(
            id_alibaba=r["id_alibaba"],
            url_alibaba=r["url_alibaba"],
            nombre=r.get("nombre"),
            imagen_url=r.get("imagen_url"),
            posicion=r["posicion"],
        )
        for r in resultados
    ]


def procesar_candidato_matching(
    candidato_id: int,
    producto_ml: ProductoMLParaMatching,
    conexion,
    obtener_html_busqueda: Callable[[str], str],
    abrir_ficha: Callable[[str], str],
    embedder_texto,
    embedder_imagen,
    generadores_query: list[Callable[[str], str]] | None = None,
    top_k: int = TOP_K_DEFAULT,
    pesos: PesosMatching | None = None,
    umbrales: UmbralesMatching | None = None,
    tolerancias_atributos: dict[str, float] | None = None,
) -> dict:
    """
    Prueba cada estrategia de `generadores_query` en orden hasta obtener
    algún resultado de Alibaba, corre `matcher.ejecutar_matching` sobre
    esos candidatos, persiste el resultado completo (auditable) en
    `matching_alibaba`, y actualiza el estado del candidato en
    `candidatos_ml` (`con_comparable` si hubo match, `descartado_sin_comparable`
    si no -- estados que ya existían en el esquema para exactamente esto).
    """
    generadores_query = generadores_query or ESTRATEGIAS_QUERY_DEFAULT
    pesos = pesos or PesosMatching()
    umbrales = umbrales or UmbralesMatching()

    query_usada = ""
    candidatos_listado: list[CandidatoAlibabaListado] = []
    for generador in generadores_query:
        query = generador(producto_ml.nombre)
        query_usada = query
        html_busqueda = obtener_html_busqueda(query)
        resultados = parsear_listado_busqueda(html_busqueda)
        logger.info("Query '%s' devolvió %d resultados en Alibaba.", query, len(resultados))
        if resultados:
            candidatos_listado = _listado_a_candidatos(resultados)
            break

    resultado = ejecutar_matching(
        producto_ml, query_usada, candidatos_listado, abrir_ficha, embedder_texto, embedder_imagen,
        top_k=top_k, pesos=pesos, umbrales=umbrales, tolerancias_atributos=tolerancias_atributos,
    )

    data = match_result_a_dict(resultado, pesos=pesos, umbrales=umbrales)
    db.insertar_resultado_matching(conexion, candidato_id, data)

    if resultado.candidato_elegido is not None:
        db.actualizar_estado_candidato(
            conexion, candidato_id, "con_comparable",
            f"Match Mode: {resultado.categoria} -- {resultado.candidato_elegido.url_alibaba}",
        )
    else:
        db.actualizar_estado_candidato(conexion, candidato_id, "descartado_sin_comparable", resultado.motivo)

    logger.info("Candidato %s (%s): %s -- %s", producto_ml.id_ml, producto_ml.nombre[:40], resultado.categoria, resultado.motivo)
    return data


def _goto_seguro(pagina, url: str, intentos: int = 3, espera_ms: int = 1000) -> None:
    """
    `page.goto()` puede fallar con un error transitorio de Playwright si
    la página anterior todavía tiene una navegación propia en vuelo --
    hallazgo real: el listado de búsqueda de Alibaba dispara sola una
    redirección de canonicalización (agrega `has4Tab=true&tab=all` a la
    URL) poco después de cargar, y si ya arrancamos a navegar hacia la
    ficha de un candidato en ese momento, Playwright corta la navegación
    nueva ("Navigation to '...' is interrupted by another navigation to
    '...'"). Reintenta en vez de romper la corrida -- mismo criterio que
    `navegador_ml.contenido_seguro` para errores transitorios.
    """
    ultimo_error = None
    for _ in range(intentos):
        try:
            pagina.goto(url, wait_until="domcontentloaded")
            return
        except PlaywrightError as exc:
            ultimo_error = exc
            logger.info("goto('%s') interrumpido por una navegación transitoria, reintentando...", url)
            pagina.wait_for_timeout(espera_ms)
    raise ultimo_error


def _abrir_pagina_alibaba(pagina, url: str, etiqueta: str, tipo: str) -> str:
    """
    Equivalente a `navegador_ml.abrir_pagina_ml` pero para Alibaba (mismo
    patrón real ya validado en `capturador_busqueda_alibaba.py`): navega,
    y si `scraper.contiene_marcadores_bloqueo` detecta el bloqueo de
    Alibaba, pausa (nunca resuelve/evade) hasta que se resuelva a mano.
    Se define acá en vez de en `navegador_ml.py` para no tocar ese módulo
    ya validado por fuera de lo estrictamente necesario.

    **Registro de diagnóstico** (pedido explícito durante la validación
    real: dejar evidencia de cada intento, bloqueado o no, para poder
    comparar corridas): cada navegación queda guardada -- HTML +
    entrada en `capturas_exploratorias/manifiesto.jsonl` (reusa
    `_guardar_html`/`_registrar_captura` de `capturador_exploratorio.py`,
    el mismo mecanismo que ya usan las demás herramientas del proyecto,
    así todo el historial de capturas queda en un solo lugar). Si hubo
    bloqueo, se registra el intento bloqueado Y el resultado ya resuelto
    por separado -- permite ver, mirando el manifiesto, en qué momentos
    exactos apareció el CAPTCHA y si tardó uno o varios reintentos en
    resolverse.
    """
    _goto_seguro(pagina, url)
    html = contenido_seguro(pagina)
    bloqueado_inicial = bloqueado_alibaba(html)

    archivo = _guardar_html(tipo, html)
    _registrar_captura(tipo, url, archivo, bloqueado_inicial)

    if bloqueado_inicial:
        html = pausar_por_bloqueo_y_continuar(pagina, url, etiqueta, sigue_bloqueado=bloqueado_alibaba, sitio="Alibaba")
        archivo_resuelto = _guardar_html(f"{tipo}_resuelto", html)
        _registrar_captura(f"{tipo}_resuelto", url, archivo_resuelto, bloqueado_alibaba(html))

    return html


def ejecutar_matching_real(
    url_ml: str,
    top_k: int = TOP_K_DEFAULT,
    pesos: PesosMatching | None = None,
    umbrales: UmbralesMatching | None = None,
    tolerancias_atributos: dict[str, float] | None = None,
    generadores_query: list[Callable[[str], str]] | None = None,
    forzar_login: bool = False,
    delay_min: float = DELAY_MIN_SEG_DEFAULT,
    delay_max: float = DELAY_MAX_SEG_DEFAULT,
) -> dict:
    """
    Punto de entrada real: `url_ml` tiene que ser la URL de un candidato
    YA detectado por la Fase 1 (existe en `candidatos_ml`, ver
    `orquestador_demanda_ml.py`) -- Match Mode verifica demanda->comparable,
    no descubre productos nuevos. Reabre la ficha de ML (Chrome real) para
    tener nombre/descripción/imagen frescos (esos tres campos no viven en
    `candidatos_ml`), y arma `obtener_html_busqueda`/`abrir_ficha` con
    Playwright real, reusando el mismo perfil persistente y la misma
    pausa humana ante bloqueo que el resto del proyecto.
    """
    conexion = db.conectar()
    candidato = db.obtener_candidato_por_url(conexion, url_ml)
    if candidato is None:
        raise ValueError(
            f"No hay un candidato en la base para {url_ml!r} -- Match Mode opera sobre candidatos ya "
            "detectados en la Fase 1 (ver orquestador_demanda_ml.py), no descubre productos nuevos."
        )
    if candidato["estado"] != "demanda_confirmada":
        logger.warning(
            "Candidato %s tiene estado '%s' (no 'demanda_confirmada') -- se sigue igual, pero revisá si es el candidato correcto.",
            candidato["id_ml"], candidato["estado"],
        )

    primera_vez = es_primera_vez()

    with navegador_persistente() as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        if primera_vez or forzar_login:
            pagina.goto(URL_ALIBABA_HOME, wait_until="domcontentloaded")
            confirmar_login_manual()

        html_ficha_ml = abrir_pagina_ml(pagina, url_ml, f"ficha ML {candidato['id_ml']}")
        datos_ml = parsear_ficha_ml(html_ficha_ml, url=url_ml)
        producto_ml = ProductoMLParaMatching(
            id_ml=candidato["id_ml"] or "",
            nombre=datos_ml.get("nombre") or candidato["nombre"] or "",
            descripcion=datos_ml.get("descripcion"),
            imagen_url=datos_ml.get("imagen_url"),
        )
        logger.info("Producto ML para matching: %s (imagen: %s)", producto_ml.nombre, producto_ml.imagen_url)

        def obtener_html_busqueda(query: str) -> str:
            return _abrir_pagina_alibaba(
                pagina, _url_busqueda_alibaba(query), f"búsqueda Alibaba '{query}'", tipo="matching_alibaba_busqueda"
            )

        def abrir_ficha(url: str) -> str:
            espera = esperar_entre_fichas(delay_min, delay_max)
            logger.info("Esperando %.1fs antes de abrir la ficha de Alibaba %s.", espera, url)
            return _abrir_pagina_alibaba(pagina, url, f"ficha Alibaba {url}", tipo="matching_alibaba_ficha")

        resultado = procesar_candidato_matching(
            candidato["id"], producto_ml, conexion, obtener_html_busqueda, abrir_ficha,
            EmbedderTextoClip(), EmbedderImagenClip(),
            generadores_query=generadores_query, top_k=top_k, pesos=pesos, umbrales=umbrales,
            tolerancias_atributos=tolerancias_atributos,
        )

    logger.info("Matching de %s terminado: %s", url_ml, resultado["categoria"])
    return resultado


def main() -> None:
    argparser = argparse.ArgumentParser(description="Match Mode: busca y verifica un comparable de Alibaba para un candidato de ML.")
    argparser.add_argument("url_ml", help="URL del candidato de ML ya detectado en la Fase 1 (candidatos_ml.url_ml).")
    argparser.add_argument("--top-k", type=int, default=TOP_K_DEFAULT, help="Cantidad de candidatos de Alibaba a verificar (abrir su ficha).")
    argparser.add_argument("--login", action="store_true", help="Forzar el paso de login manual de nuevo.")
    argparser.add_argument("--delay-min", type=float, default=DELAY_MIN_SEG_DEFAULT, help="Espera mínima en segundos antes de abrir cada ficha de Alibaba.")
    argparser.add_argument("--delay-max", type=float, default=DELAY_MAX_SEG_DEFAULT, help="Espera máxima en segundos antes de abrir cada ficha de Alibaba.")
    args = argparser.parse_args()

    resultado = ejecutar_matching_real(
        args.url_ml, top_k=args.top_k, forzar_login=args.login, delay_min=args.delay_min, delay_max=args.delay_max,
    )
    print(f"Categoría: {resultado['categoria']}")
    print(f"Motivo: {resultado['motivo']}")
    if resultado.get("url_alibaba_elegido"):
        print(f"Candidato elegido: {resultado['url_alibaba_elegido']}")


if __name__ == "__main__":
    main()
