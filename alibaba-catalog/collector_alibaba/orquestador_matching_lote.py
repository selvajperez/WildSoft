"""
Fase B de la validación de Match Mode (ver ESTADO_ACTUAL.md): corre el
mismo Match Mode ya validado (`orquestador_matching.py`) sobre varios
candidatos de `demanda_confirmada`, uno tras otro, en un solo proceso
continuo -- sin que la usuaria elija productos ni intervenga en la
selección (`seleccionar_candidatos_lote`, automática, con variedad de
tipo de producto cuando es posible), y sin scripts `_validar_casoN.py`
nuevos (ya no hacen falta: la selección automática reemplaza elegir un
candidato a mano por heurístico ad-hoc).

**Un solo proceso, un solo navegador**: a diferencia de correr
`orquestador_matching.py` varias veces (que abre y cierra Chrome en cada
corrida), acá se abre el navegador UNA vez y se reusa para los N
candidatos -- también evita recargar el modelo CLIP (`EmbedderTextoClip`/
`EmbedderImagenClip`) en cada candidato, se instancia una sola vez.

**Continuar ante errores, conservar progreso**: cada candidato se procesa
dentro de un `try/except` propio -- un error en uno (parseo, timeout,
lo que sea) se registra y el lote sigue con el siguiente, nunca corta
todo el proceso. El progreso ya queda conservado por el mismo mecanismo
que usa `orquestador_matching.py` candidato por candidato: recién al
final de `procesar_candidato_matching` se persiste el resultado en
`matching_alibaba` y se actualiza `candidatos_ml.estado` -- si un
candidato falla a mitad de camino, su estado sigue en
`demanda_confirmada` y una corrida posterior del lote simplemente lo
vuelve a elegir; no hace falta ningún checkpoint aparte.

**Solo se detiene para intervención humana ante un CAPTCHA/bloqueo real**
-- eso ya lo maneja `navegador_ml.pausar_por_bloqueo_y_continuar` (mismo
mecanismo de siempre, invocado transitivamente por
`orquestador_matching._procesar_candidato_en_pagina`): pausa la corrida
en curso hasta que se resuelva a mano, nunca la resuelve ni la evade
sola.

Uso:
    python orquestador_matching_lote.py
    python orquestador_matching_lote.py --cantidad 5 --login
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "database"))

from atributos_matching import extraer_atributos_texto_libre  # noqa: E402
from embeddings import EmbedderImagenClip, EmbedderTextoClip  # noqa: E402
from matcher import TOP_K_DEFAULT  # noqa: E402
from navegador_ml import (  # noqa: E402
    DELAY_MAX_SEG_DEFAULT,
    DELAY_MIN_SEG_DEFAULT,
    confirmar_login_manual,
    es_primera_vez,
    navegador_persistente,
)
from orquestador_matching import URL_ALIBABA_HOME, _procesar_candidato_en_pagina  # noqa: E402
import db  # noqa: E402

CANTIDAD_LOTE_DEFAULT = 10
MAX_POR_CATEGORIA_DEFAULT = 2  # evita que el lote sea 10 veces "el mismo tipo de producto"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "orquestador_matching_lote.log")],
)
logger = logging.getLogger("orquestador_matching_lote")


def seleccionar_candidatos_lote(
    conexion: sqlite3.Connection, cantidad: int = CANTIDAD_LOTE_DEFAULT, max_por_categoria: int = MAX_POR_CATEGORIA_DEFAULT
) -> list[dict]:
    """
    Elige hasta `cantidad` candidatos con `estado = demanda_confirmada`,
    automáticamente, priorizando variedad de tipo de producto cuando es
    posible: reusa `atributos_matching.extraer_atributos_texto_libre`
    (el mismo diccionario `CANON_CATEGORIA` ya usado en el matching, no
    uno nuevo) para agrupar por categoría reconocida y tomar como mucho
    `max_por_categoria` de cada una en una primera pasada, antes de
    completar con lo que quede (mayor `unidades_vendidas` primero) si
    no se llegó a `cantidad` -- nunca falla por falta de variedad, solo
    hace lo mejor posible con lo que haya en la base.
    """
    conexion.row_factory = sqlite3.Row
    filas = conexion.execute(
        "SELECT * FROM candidatos_ml WHERE estado = 'demanda_confirmada' ORDER BY unidades_vendidas DESC"
    ).fetchall()
    conexion.row_factory = None
    candidatos = [dict(fila) for fila in filas]

    for candidato in candidatos:
        atributos = extraer_atributos_texto_libre(candidato["nombre"])
        candidato["_categoria"] = atributos["categoria"].categoria_canon if "categoria" in atributos else None

    seleccionados: list[dict] = []
    vistos_por_categoria: dict[str | None, int] = {}
    for candidato in candidatos:
        if len(seleccionados) >= cantidad:
            break
        categoria = candidato["_categoria"]
        if vistos_por_categoria.get(categoria, 0) < max_por_categoria:
            seleccionados.append(candidato)
            vistos_por_categoria[categoria] = vistos_por_categoria.get(categoria, 0) + 1

    if len(seleccionados) < cantidad:
        ids_ya_elegidos = {c["id"] for c in seleccionados}
        for candidato in candidatos:
            if len(seleccionados) >= cantidad:
                break
            if candidato["id"] not in ids_ya_elegidos:
                seleccionados.append(candidato)

    return seleccionados[:cantidad]


def _motivo_dudoso(resultado: dict) -> str | None:
    """
    Un resultado es "dudoso" (para revisión manual, no para descartar)
    si: quedó en MATCH_PROBABLE (confianza media, no ALTO) o si algún
    candidato del top_k quedó vetado por un atributo esencial (vale la
    pena confirmar que el veto fue correcto y no un falso positivo del
    heurístico de atributos). Nunca se decide "dudoso" por el score
    numérico solo -- eso ya lo resuelve `matcher._categorizar`.
    """
    if resultado.get("categoria") == "MATCH_PROBABLE":
        return "MATCH_PROBABLE -- confianza media, conviene confirmar el candidato elegido a mano"

    vetos = {
        c["veto"]["tipo"]
        for c in resultado.get("candidatos_evaluados", [])
        if c.get("veto")
    }
    if vetos:
        return f"Al menos un candidato del top_k quedó vetado por {', '.join(sorted(vetos))} -- confirmar que el veto es correcto"

    return None


def _armar_resumen(resultados: list[dict]) -> dict:
    resumen = {
        "total": len(resultados),
        "match_alto": 0,
        "match_probable": 0,
        "sin_match_confiable": 0,
        "error": 0,
        "dudosos": [],
        "detalle": resultados,
    }

    for resultado in resultados:
        if resultado["estado_proceso"] == "error":
            resumen["error"] += 1
            resumen["dudosos"].append({
                "id_ml": resultado["id_ml"], "nombre_ml": resultado["nombre_ml"],
                "motivo": f"Error al procesar: {resultado.get('error')}",
            })
            continue

        categoria = resultado.get("categoria")
        if categoria == "MATCH_ALTO":
            resumen["match_alto"] += 1
        elif categoria == "MATCH_PROBABLE":
            resumen["match_probable"] += 1
        else:
            resumen["sin_match_confiable"] += 1

        motivo_dudoso = _motivo_dudoso(resultado)
        if motivo_dudoso:
            resumen["dudosos"].append({
                "id_ml": resultado["id_ml"], "nombre_ml": resultado["nombre_ml"],
                "categoria": categoria, "motivo": motivo_dudoso,
            })

    return resumen


def procesar_lote(candidatos: list[dict], procesar_uno: Callable[[dict], dict]) -> list[dict]:
    """
    Recorre `candidatos` en orden, llamando a `procesar_uno(candidato)`
    para cada uno. Un error en un candidato se registra y NO corta el
    lote -- se sigue con el próximo. Separado de `ejecutar_lote_real`
    (que arma `procesar_uno` con Playwright real) para poder probar esta
    lógica de "seguir ante errores" con candidatos/funciones inyectadas,
    sin navegador real -- mismo patrón que
    `orquestador_demanda_ml.procesar_busqueda_ml`/`ejecutar_busqueda_real`.
    """
    resultados: list[dict] = []
    for indice, candidato in enumerate(candidatos, start=1):
        logger.info(
            "--- Candidato %d/%d: %s (%s) ---", indice, len(candidatos), candidato["id_ml"], candidato["nombre"]
        )
        try:
            resultado = procesar_uno(candidato)
            resultado["nombre_ml"] = candidato["nombre"]
            resultado["estado_proceso"] = "ok"
        except Exception as exc:
            logger.exception(
                "Error procesando %s -- se registra y se sigue con el próximo candidato del lote.",
                candidato["id_ml"],
            )
            resultado = {
                "id_ml": candidato["id_ml"],
                "nombre_ml": candidato["nombre"],
                "estado_proceso": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "categoria": None,
                "candidato_elegido": None,
                "candidatos_evaluados": [],
            }
        resultados.append(resultado)
    return resultados


def ejecutar_lote_real(
    cantidad: int = CANTIDAD_LOTE_DEFAULT,
    top_k: int = TOP_K_DEFAULT,
    forzar_login: bool = False,
    delay_min: float = DELAY_MIN_SEG_DEFAULT,
    delay_max: float = DELAY_MAX_SEG_DEFAULT,
) -> dict:
    """Punto de entrada real: selecciona el lote, abre Chrome UNA vez, procesa cada candidato en orden."""
    conexion = db.conectar()
    candidatos = seleccionar_candidatos_lote(conexion, cantidad)

    if not candidatos:
        logger.warning("No hay ningún candidato con estado 'demanda_confirmada' para procesar en el lote.")
        return _armar_resumen([])

    logger.info(
        "Lote de %d candidato(s) seleccionado: %s",
        len(candidatos), [(c["id_ml"], c["_categoria"]) for c in candidatos],
    )

    primera_vez = es_primera_vez()
    embedder_texto = EmbedderTextoClip()
    embedder_imagen = EmbedderImagenClip()

    with navegador_persistente() as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        if primera_vez or forzar_login:
            pagina.goto(URL_ALIBABA_HOME, wait_until="domcontentloaded")
            confirmar_login_manual()

        def procesar_uno(candidato: dict) -> dict:
            return _procesar_candidato_en_pagina(
                pagina, candidato, conexion, embedder_texto, embedder_imagen,
                top_k=top_k, delay_min=delay_min, delay_max=delay_max,
            )

        resultados = procesar_lote(candidatos, procesar_uno)

    resumen = _armar_resumen(resultados)
    logger.info(
        "Lote terminado -- total=%d match_alto=%d match_probable=%d sin_match_confiable=%d error=%d dudosos=%d",
        resumen["total"], resumen["match_alto"], resumen["match_probable"],
        resumen["sin_match_confiable"], resumen["error"], len(resumen["dudosos"]),
    )
    return resumen


def main() -> None:
    argparser = argparse.ArgumentParser(
        description="Fase B de Match Mode: corre el matching sobre varios candidatos de demanda_confirmada en un solo proceso."
    )
    argparser.add_argument("--cantidad", type=int, default=CANTIDAD_LOTE_DEFAULT, help="Cantidad de candidatos a procesar en el lote.")
    argparser.add_argument("--top-k", type=int, default=TOP_K_DEFAULT, help="Cantidad de candidatos de Alibaba a verificar por producto de ML.")
    argparser.add_argument("--login", action="store_true", help="Forzar el paso de login manual de nuevo.")
    argparser.add_argument("--delay-min", type=float, default=DELAY_MIN_SEG_DEFAULT, help="Espera mínima en segundos antes de abrir cada ficha de Alibaba.")
    argparser.add_argument("--delay-max", type=float, default=DELAY_MAX_SEG_DEFAULT, help="Espera máxima en segundos antes de abrir cada ficha de Alibaba.")
    args = argparser.parse_args()

    resumen = ejecutar_lote_real(
        cantidad=args.cantidad, top_k=args.top_k, forzar_login=args.login,
        delay_min=args.delay_min, delay_max=args.delay_max,
    )

    print("=" * 70)
    print(f"LOTE TERMINADO -- {resumen['total']} candidatos procesados")
    print(f"  MATCH_ALTO: {resumen['match_alto']}")
    print(f"  MATCH_PROBABLE: {resumen['match_probable']}")
    print(f"  SIN_MATCH_CONFIABLE: {resumen['sin_match_confiable']}")
    print(f"  Errores: {resumen['error']}")
    print("=" * 70)

    for fila in resumen["detalle"]:
        if fila["estado_proceso"] == "error":
            print(f"  [ERROR] {fila['id_ml']} ({fila['nombre_ml'][:50]}): {fila['error']}")
        else:
            elegido = fila.get("candidato_elegido")
            url_elegido = elegido["url_alibaba"] if elegido else "(sin candidato)"
            print(f"  [{fila['categoria']}] {fila['id_ml']} ({fila['nombre_ml'][:50]}) -> {url_elegido}")

    if resumen["dudosos"]:
        print("\n" + "-" * 70)
        print(f"CASOS PARA REVISIÓN MANUAL ({len(resumen['dudosos'])}):")
        print("-" * 70)
        for caso in resumen["dudosos"]:
            print(f"  - {caso['id_ml']} ({caso['nombre_ml'][:50]}): {caso['motivo']}")

    print("\nRESUMEN COMPLETO EN JSON:")
    print(json.dumps(resumen, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
