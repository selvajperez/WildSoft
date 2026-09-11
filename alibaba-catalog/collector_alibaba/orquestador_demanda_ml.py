"""
Orquesta la Fase 1 completa del motor de sourcing: busca en Mercado Libre,
prioriza los resultados (ver `parser_busqueda_ml.clasificar_prioridad`), y
abre fichas individuales -- primero Prioridad A, después Prioridad B --
hasta confirmar una cantidad configurable de candidatos con demanda real,
o hasta agotar un máximo configurable de fichas por búsqueda (lo que pase
primero).

El listado nunca decide por sí solo: es prefiltro y orden de prioridad.
La demanda se confirma recién al abrir la ficha individual, contra un
umbral configurable (`umbral_unidades_vendidas`). Cada ficha abierta deja
una observación en `historial_ml` (append-only) y actualiza el `estado`
del candidato con un motivo explícito -- promovido, descartado, o
indeterminado, nunca en silencio.

Reutiliza `navegador_ml.py` (mismo Chrome real + perfil persistente que
`collector_browser.py`/`capturador_exploratorio.py`) y
`parser_busqueda_ml.py`/`parser_ficha_ml.py` sin modificarlos.

La lógica de decisión (`_determinar_resultado_ficha`, el orden de
prioridad, cuándo detenerse) está separada de la parte que efectivamente
abre páginas: `procesar_busqueda_ml` recibe `obtener_html_busqueda` y
`abrir_ficha` como funciones, así se puede probar todo el flujo con datos
reales ya capturados sin necesitar un navegador. `ejecutar_busqueda_real`
es el punto de entrada que arma esas funciones con Playwright de verdad.

Cuando una ficha queda `indeterminado_ficha` (ni precio ni ventas
extraídos), `ejecutar_busqueda_real` guarda automáticamente su HTML crudo
en `diagnostico_fichas_ml/<id_ml>.html` -- sin esto no hay forma de saber
por qué falló el parseo sin pedirle a la usuaria que navegue manualmente
a buscarlo, algo que el proyecto evita a propósito. `procesar_busqueda_ml`
recibe esto también inyectado (`guardar_diagnostico`, opcional) para no
tocar disco en los tests.

`ejecutar_busqueda_real` también espera una pausa configurable con
jitter aleatorio (`--delay-min`/`--delay-max`, ver `navegador_ml.esperar_entre_fichas`)
antes de abrir cada ficha, para reducir la frecuencia del bloqueo de
tráfico sospechoso en primer lugar (hallazgo real: apareció después de
~20 fichas seguidas en ~1 segundo cada una).

Uso:
    python orquestador_demanda_ml.py "cepillo de limpieza"
    python orquestador_demanda_ml.py "candado bicicleta" --max-fichas 10 --objetivo 3 --umbral-vendidas 100
    python orquestador_demanda_ml.py "cepillo de limpieza" --delay-min 4 --delay-max 10
"""

from __future__ import annotations

import argparse
import logging
import sys
import urllib.parse
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "database"))

from navegador_ml import (  # noqa: E402
    DELAY_MAX_SEG_DEFAULT,
    DELAY_MIN_SEG_DEFAULT,
    abrir_pagina_ml,
    confirmar_login_manual,
    es_primera_vez,
    esperar_entre_fichas,
    navegador_persistente,
)
from parser_busqueda_ml import parsear_listado_busqueda, resultado_a_candidato  # noqa: E402
from parser_ficha_ml import parsear_ficha_ml  # noqa: E402
import db  # noqa: E402

URL_BASE_ML = "https://listado.mercadolibre.com.ar"

MAX_FICHAS_POR_BUSQUEDA_DEFAULT = 15
CANDIDATOS_OBJETIVO_DEFAULT = 5
UMBRAL_UNIDADES_VENDIDAS_DEFAULT = 50

DIR_DIAGNOSTICO_FICHAS = Path(__file__).parent.parent / "diagnostico_fichas_ml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "orquestador_demanda_ml.log")],
)
logger = logging.getLogger("orquestador_demanda_ml")


def _guardar_html_diagnostico(id_ml: str, html: str) -> Path:
    """
    Guarda el HTML crudo de una ficha que quedó `indeterminado_ficha` --
    ni precio ni ventas extraídos -- para poder diagnosticar por qué
    falló el parseo sin pedirle a nadie que la vuelva a buscar a mano.
    """
    DIR_DIAGNOSTICO_FICHAS.mkdir(parents=True, exist_ok=True)
    archivo = DIR_DIAGNOSTICO_FICHAS / f"{id_ml}.html"
    archivo.write_text(html, encoding="utf-8")
    logger.warning("Ficha %s indeterminada -- HTML guardado en %s para diagnóstico.", id_ml, archivo)
    return archivo


def _determinar_resultado_ficha(datos_ficha: dict, umbral_unidades_vendidas: int) -> tuple[str, str]:
    """
    Decide el estado final de un candidato después de abrir su ficha
    individual, contra el umbral configurado. Siempre devuelve un motivo
    explícito para `motivo_descarte` -- nunca hay un descarte silencioso.
    """
    vendidas = datos_ficha.get("unidades_vendidas")

    if datos_ficha.get("pagina_no_encontrada"):
        return (
            "indeterminado_ficha",
            "La ficha devolvió un 404 real de Mercado Libre (\"esta página no existe\") -- "
            "probablemente la URL reconstruida a partir de un link de tracking del listado "
            "no es válida para este item (ver parser_ficha_ml.es_ficha_no_encontrada).",
        )

    if datos_ficha.get("precio_ml") is None and vendidas is None:
        return "indeterminado_ficha", "No se pudo extraer nada confiable de la ficha individual."

    if vendidas is not None and vendidas >= umbral_unidades_vendidas:
        return (
            "demanda_confirmada",
            f"{vendidas} unidades vendidas confirmadas en la ficha (umbral configurado: {umbral_unidades_vendidas}).",
        )

    if vendidas is not None:
        return (
            "descartado_demanda_no_confirmada",
            f"Solo {vendidas} unidades vendidas confirmadas en la ficha (umbral configurado: {umbral_unidades_vendidas}).",
        )

    return (
        "indeterminado_ficha",
        "La ficha no expone unidades vendidas; no se puede confirmar demanda con la configuración actual.",
    )


def _url_busqueda(busqueda: str) -> str:
    return f"{URL_BASE_ML}/{urllib.parse.quote(busqueda.replace(' ', '-'))}"


def procesar_busqueda_ml(
    busqueda: str,
    conexion,
    obtener_html_busqueda: Callable[[str], str],
    abrir_ficha: Callable[[str, str], str],
    max_fichas_por_busqueda: int = MAX_FICHAS_POR_BUSQUEDA_DEFAULT,
    candidatos_objetivo: int = CANDIDATOS_OBJETIVO_DEFAULT,
    umbral_unidades_vendidas: int = UMBRAL_UNIDADES_VENDIDAS_DEFAULT,
    guardar_diagnostico: Callable[[str, str], None] | None = None,
) -> dict:
    """
    Ejecuta la Fase 1 completa para una búsqueda: lista -> prioriza ->
    guarda todo en `candidatos_ml` -> abre fichas (Prioridad A primero,
    después B) hasta cumplir `candidatos_objetivo` o
    `max_fichas_por_busqueda`. Devuelve un resumen auditable de la corrida.

    `obtener_html_busqueda(url) -> html` y `abrir_ficha(url, etiqueta) -> html`
    son funciones inyectadas para no atar esta lógica a un navegador real
    -- permite probar el flujo completo con HTML ya capturado.
    `guardar_diagnostico(id_ml, html)`, si se pasa, se invoca para cada
    ficha que queda `indeterminado_ficha` (no toca disco por defecto, así
    los tests no tienen efectos secundarios de archivo).
    """
    resumen = {
        "busqueda": busqueda,
        "extraidos": 0,
        "prioridad_a": 0,
        "prioridad_b": 0,
        "sin_senal": 0,
        "fichas_abiertas": 0,
        "demanda_confirmada": 0,
        "descartado_demanda_no_confirmada": 0,
        "indeterminado_ficha": 0,
        "detenido_por": None,
        "detalle": [],
    }

    html_busqueda = obtener_html_busqueda(_url_busqueda(busqueda))
    resultados = parsear_listado_busqueda(html_busqueda)
    resumen["extraidos"] = len(resultados)

    cola_a: list[tuple[int, dict]] = []
    cola_b: list[tuple[int, dict]] = []
    for item in resultados:
        candidato = resultado_a_candidato(item)
        candidato_id = db.upsert_candidato_ml(conexion, candidato)
        prioridad = candidato["prioridad_listado"]
        if prioridad == "A":
            resumen["prioridad_a"] += 1
            cola_a.append((candidato_id, item))
        elif prioridad == "B":
            resumen["prioridad_b"] += 1
            cola_b.append((candidato_id, item))
        else:
            resumen["sin_senal"] += 1

    for candidato_id, item in cola_a + cola_b:
        if resumen["demanda_confirmada"] >= candidatos_objetivo:
            resumen["detenido_por"] = "candidatos_objetivo_alcanzado"
            break
        if resumen["fichas_abiertas"] >= max_fichas_por_busqueda:
            resumen["detenido_por"] = "max_fichas_alcanzado"
            break

        html_ficha = abrir_ficha(item["url_ml"], f"ficha {item['id_ml']}")
        resumen["fichas_abiertas"] += 1

        datos_ficha = parsear_ficha_ml(html_ficha, url=item["url_ml"])

        db.registrar_observacion_historial(conexion, candidato_id, {
            "precio": datos_ficha.get("precio_ml"),
            "stock_visible": datos_ficha.get("stock_visible"),
            "unidades_vendidas_visible": datos_ficha.get("unidades_vendidas"),
            "cantidad_opiniones": datos_ficha.get("cantidad_opiniones"),
            "rating": datos_ficha.get("rating"),
            "posicion_ranking": item.get("posicion"),
        })

        estado, motivo = _determinar_resultado_ficha(datos_ficha, umbral_unidades_vendidas)
        db.actualizar_estado_candidato(conexion, candidato_id, estado, motivo)

        if estado == "indeterminado_ficha" and guardar_diagnostico is not None:
            guardar_diagnostico(item["id_ml"], html_ficha)

        resumen[estado] += 1
        resumen["detalle"].append({
            "id_ml": item["id_ml"], "nombre": item["nombre"], "estado": estado, "motivo": motivo,
        })
        logger.info("Ficha %s (%s): %s -- %s", item["id_ml"], item["nombre"][:40], estado, motivo)

    if resumen["detenido_por"] is None:
        resumen["detenido_por"] = "sin_mas_candidatos_en_cola"

    return resumen


def ejecutar_busqueda_real(
    busqueda: str,
    max_fichas_por_busqueda: int = MAX_FICHAS_POR_BUSQUEDA_DEFAULT,
    candidatos_objetivo: int = CANDIDATOS_OBJETIVO_DEFAULT,
    umbral_unidades_vendidas: int = UMBRAL_UNIDADES_VENDIDAS_DEFAULT,
    forzar_login: bool = False,
    delay_min: float = DELAY_MIN_SEG_DEFAULT,
    delay_max: float = DELAY_MAX_SEG_DEFAULT,
) -> dict:
    """Punto de entrada real: arma `obtener_html_busqueda`/`abrir_ficha` con Chrome real + Playwright."""
    conexion = db.conectar()
    primera_vez = es_primera_vez()

    with navegador_persistente() as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        if primera_vez or forzar_login:
            pagina.goto(URL_BASE_ML, wait_until="domcontentloaded")
            confirmar_login_manual()

        def obtener_html_busqueda(url: str) -> str:
            return abrir_pagina_ml(pagina, url, f"búsqueda '{busqueda}'")

        def abrir_ficha(url: str, etiqueta: str) -> str:
            espera = esperar_entre_fichas(delay_min, delay_max)
            logger.info("Esperando %.1fs antes de abrir '%s' (reduce el riesgo de bloqueo).", espera, etiqueta)
            return abrir_pagina_ml(pagina, url, etiqueta)

        resumen = procesar_busqueda_ml(
            busqueda, conexion, obtener_html_busqueda, abrir_ficha,
            max_fichas_por_busqueda=max_fichas_por_busqueda,
            candidatos_objetivo=candidatos_objetivo,
            umbral_unidades_vendidas=umbral_unidades_vendidas,
            guardar_diagnostico=_guardar_html_diagnostico,
        )

    logger.info("Búsqueda '%s' terminada: %s", busqueda, resumen)
    return resumen


def main() -> None:
    argparser = argparse.ArgumentParser(description="Fase 1 del sourcing: busca demanda en Mercado Libre.")
    argparser.add_argument("busqueda", help="Término a buscar en Mercado Libre.")
    argparser.add_argument(
        "--max-fichas", type=int, default=MAX_FICHAS_POR_BUSQUEDA_DEFAULT,
        help="Máximo de fichas individuales a abrir por búsqueda (evita navegación innecesaria y reduce bloqueos).",
    )
    argparser.add_argument(
        "--objetivo", type=int, default=CANDIDATOS_OBJETIVO_DEFAULT,
        help="Cantidad de candidatos con demanda confirmada a alcanzar antes de parar.",
    )
    argparser.add_argument(
        "--umbral-vendidas", type=int, default=UMBRAL_UNIDADES_VENDIDAS_DEFAULT,
        help="Unidades vendidas mínimas (confirmadas en la ficha) para considerar la demanda válida.",
    )
    argparser.add_argument("--login", action="store_true", help="Forzar el paso de login manual de nuevo.")
    argparser.add_argument(
        "--delay-min", type=float, default=DELAY_MIN_SEG_DEFAULT,
        help="Espera mínima en segundos antes de abrir cada ficha (con jitter aleatorio hasta --delay-max).",
    )
    argparser.add_argument(
        "--delay-max", type=float, default=DELAY_MAX_SEG_DEFAULT,
        help="Espera máxima en segundos antes de abrir cada ficha.",
    )
    args = argparser.parse_args()

    resumen = ejecutar_busqueda_real(
        args.busqueda,
        max_fichas_por_busqueda=args.max_fichas,
        candidatos_objetivo=args.objetivo,
        umbral_unidades_vendidas=args.umbral_vendidas,
        forzar_login=args.login,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
    )
    print(resumen)


if __name__ == "__main__":
    main()
