"""
Fase 3: cierra el flujo completo de MUTE. Para cada candidato que Match
Mode ya aceptó (`estado = con_comparable`, ver `orquestador_matching.py`),
vuelve a abrir la ficha de Alibaba elegida, lee el precio real, y corre
`filtro_economico.evaluar_viabilidad` para decidir si conviene importarlo.

**Por qué se vuelve a abrir la ficha**: Match Mode (`matcher.py`) lee el
precio de la ficha de Alibaba solo de paso, para comparar atributos --
nunca lo usa ni lo guarda, a propósito (el precio del listado/ficha en
esa etapa es una señal de calidad comercial, no de si es el mismo
producto). El filtro económico es la primera vez que ese precio real
importa de verdad, así que se lee de nuevo acá.

**Mismo patrón que `orquestador_matching_lote.py`**: un solo navegador
para todos los candidatos pendientes, reusa `goto_seguro`/el registro de
diagnóstico/la pausa humana ante bloqueo (nada de esto se reescribe),
sigue con el próximo candidato si uno falla (nunca corta todo el lote), y
persiste cada resultado apenas termina (si se corta a mitad de camino, lo
ya procesado no se pierde).

**Tipo de cambio**: dólar MEP (referencia elegida por la usuaria),
consultado en vivo UNA vez por corrida vía `tipo_cambio.obtener_dolar_mep`
-- nunca un valor fijo en el código, y puede variar de una corrida a la
siguiente. El valor, la fuente y la fecha de referencia se guardan junto
con cada cálculo (ver `database/db.py`). Si el MEP no está disponible o
no se puede verificar, NO se cae a otra cotización -- todo candidato con
precio de ML en ARS queda `indeterminado` explícitamente en esa corrida.

Uso:
    python orquestador_filtro_economico.py
    python orquestador_filtro_economico.py --login
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "database"))

from filtro_economico import (  # noqa: E402
    DIFERENCIA_MINIMA_USD_DEFAULT,
    RATIO_MINIMO_DEFAULT,
    evaluar_viabilidad,
    resolver_precio_alibaba,
)
from navegador_ml import (  # noqa: E402
    DELAY_MAX_SEG_DEFAULT,
    DELAY_MIN_SEG_DEFAULT,
    confirmar_login_manual,
    es_primera_vez,
    esperar_entre_fichas,
    navegador_persistente,
)
from orquestador_matching import URL_ALIBABA_HOME, _abrir_pagina_alibaba  # noqa: E402
from parser_ficha_alibaba import parsear_ficha_alibaba  # noqa: E402
from tipo_cambio import TipoCambioResuelto, obtener_dolar_mep  # noqa: E402
import db  # noqa: E402

# Tipo de cambio "no disponible" explícito -- usado cuando no se pudo
# consultar el dólar MEP en esta corrida, para no dejar el parámetro en
# `None` suelto sin motivo (ver `tipo_cambio.py`).
_TIPO_CAMBIO_NO_DISPONIBLE = TipoCambioResuelto(
    valor=None, fuente=None, fecha_referencia=None, obtenido_en=None,
    disponible=False, detalle="No se consultó ningún tipo de cambio en esta corrida.",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "orquestador_filtro_economico.log")],
)
logger = logging.getLogger("orquestador_filtro_economico")

# Mapeo directo a estados que ya existían en el esquema para exactamente
# esto (ver database/db.py, ESTADOS_CANDIDATO) -- no se agregó ningún
# estado nuevo, "viable_dudoso" también cae en precio_verificado (queda
# marcado en el propio resultado/motivo que es dudoso, no en el estado).
_ESTADO_POR_RESULTADO = {
    "viable": "precio_verificado",
    "viable_dudoso": "precio_verificado",
    "no_viable": "descartado_filtro_economico",
    "indeterminado": "descartado_no_verificado",
}


def procesar_candidato_viabilidad(
    candidato: dict,
    conexion,
    abrir_ficha: Callable[[str], str],
    tipo_cambio: TipoCambioResuelto = _TIPO_CAMBIO_NO_DISPONIBLE,
    ratio_minimo: float = RATIO_MINIMO_DEFAULT,
    diferencia_minima_usd: float = DIFERENCIA_MINIMA_USD_DEFAULT,
) -> dict:
    """
    `candidato` viene de `db.obtener_candidatos_pendientes_de_viabilidad`
    (ya trae `ultimo_matching` adjunto). `abrir_ficha(url) -> html` es
    inyectado para poder probar todo el flujo con HTML ya capturado, sin
    navegador real -- mismo patrón que `orquestador_matching.py`.

    `tipo_cambio` se resuelve UNA vez por corrida completa (ver
    `ejecutar_filtro_economico_real`), no por candidato -- todos los
    candidatos de una misma corrida comparten el mismo valor/fuente/fecha
    de referencia. Si `tipo_cambio.disponible` es `False`, cualquier
    candidato en ARS queda `indeterminado` (no se asume ninguna tasa).
    """
    ultimo_matching = candidato.get("ultimo_matching") or {}
    categoria_match = ultimo_matching.get("categoria")
    url_alibaba = ultimo_matching.get("url_alibaba_elegido")

    if not url_alibaba:
        # No debería pasar (con_comparable implica que Match Mode eligió
        # un candidato), pero si pasa no se adivina nada ni se inserta una
        # fila de comparable sin URL (viola el esquema, y no hay ficha
        # real que la respalde) -- se registra la inconsistencia y se
        # marca el candidato como no verificado.
        logger.warning(
            "Candidato %s en estado con_comparable sin url_alibaba_elegido en su último matching -- inconsistencia.",
            candidato.get("id_ml"),
        )
        motivo = "El resultado de matching más reciente no tiene un candidato de Alibaba elegido -- no hay ficha que abrir."
        db.actualizar_estado_candidato(conexion, candidato["id"], "descartado_no_verificado", motivo)
        return {
            "id_ml": candidato.get("id_ml"), "nombre": candidato.get("nombre"), "url_alibaba": None,
            "resultado": "indeterminado", "motivo": motivo, "ratio": None, "diferencia_usd": None,
        }

    html = abrir_ficha(url_alibaba)
    datos_ficha = parsear_ficha_alibaba(html, url=url_alibaba)
    precio_resuelto = resolver_precio_alibaba(datos_ficha)
    resultado = evaluar_viabilidad(
        precio_ml=candidato.get("precio_ml"), moneda_ml=candidato.get("moneda_ml"),
        categoria_match=categoria_match, precio_alibaba=precio_resuelto,
        tipo_cambio_usd_ars=tipo_cambio.valor if tipo_cambio.disponible else None,
        tipo_cambio_fuente=tipo_cambio.fuente if tipo_cambio.disponible else None,
        tipo_cambio_fecha_referencia=tipo_cambio.fecha_referencia if tipo_cambio.disponible else None,
        ratio_minimo=ratio_minimo, diferencia_minima_usd=diferencia_minima_usd,
    )

    db.insertar_comparable_alibaba(conexion, candidato["id"], {
        "url_alibaba": url_alibaba,
        "moq": datos_ficha.get("moq"),
        "precio_alibaba_50u": resultado.precio_alibaba_usd,
        "moneda": "USD" if resultado.precio_alibaba_usd is not None else None,
        "precio_no_verificado": resultado.resultado == "indeterminado",
        "cantidad_precio_alibaba": resultado.cantidad_alibaba,
        "fuente_precio": resultado.fuente_precio_alibaba,
        "precio_ladder_crudo_json": resultado.precio_ladder_crudo,
        "precio_ml_original": resultado.precio_ml_original,
        "moneda_ml_original": resultado.moneda_ml,
        "tipo_cambio_usado": resultado.tipo_cambio_usado,
        "tipo_cambio_fuente": resultado.tipo_cambio_fuente,
        "tipo_cambio_fecha_referencia": resultado.tipo_cambio_fecha_referencia,
        "precio_ml_usd": resultado.precio_ml_usd,
        "ratio": resultado.ratio,
        "diferencia_usd": resultado.diferencia_usd,
        "categoria_match": resultado.categoria_match,
        "resultado_viabilidad": resultado.resultado,
        "motivo_viabilidad": resultado.motivo,
    })

    estado_nuevo = _ESTADO_POR_RESULTADO[resultado.resultado]
    db.actualizar_estado_candidato(conexion, candidato["id"], estado_nuevo, resultado.motivo)

    logger.info(
        "Candidato %s (%s): %s -- %s", candidato.get("id_ml"), (candidato.get("nombre") or "")[:40],
        resultado.resultado, resultado.motivo,
    )
    return {
        "id_ml": candidato.get("id_ml"), "nombre": candidato.get("nombre"), "url_alibaba": url_alibaba,
        "resultado": resultado.resultado, "motivo": resultado.motivo,
        "ratio": resultado.ratio, "diferencia_usd": resultado.diferencia_usd,
    }


def procesar_lote_viabilidad(candidatos: list[dict], conexion, procesar_uno: Callable[[dict], dict]) -> list[dict]:
    """
    Recorre `candidatos` en orden. Un error en uno se registra y NO corta
    el lote -- mismo criterio que `orquestador_matching_lote.procesar_lote`.
    """
    resultados = []
    for indice, candidato in enumerate(candidatos, start=1):
        logger.info("--- Candidato %d/%d: %s (%s) ---", indice, len(candidatos), candidato.get("id_ml"), candidato.get("nombre"))
        try:
            resultados.append(procesar_uno(candidato))
        except Exception as exc:
            logger.exception("Error procesando %s -- se registra y se sigue con el próximo.", candidato.get("id_ml"))
            resultados.append({
                "id_ml": candidato.get("id_ml"), "nombre": candidato.get("nombre"),
                "resultado": "error", "motivo": f"{type(exc).__name__}: {exc}",
            })
    return resultados


def ejecutar_filtro_economico_real(
    ratio_minimo: float = RATIO_MINIMO_DEFAULT,
    diferencia_minima_usd: float = DIFERENCIA_MINIMA_USD_DEFAULT,
    forzar_login: bool = False,
    delay_min: float = DELAY_MIN_SEG_DEFAULT,
    delay_max: float = DELAY_MAX_SEG_DEFAULT,
    obtener_tipo_cambio: Callable[[], TipoCambioResuelto] = obtener_dolar_mep,
) -> list[dict]:
    """
    Punto de entrada real: abre Chrome UNA vez, procesa todos los
    candidatos pendientes en orden. Consulta el dólar MEP UNA sola vez al
    principio de la corrida (no hay tasa fija en el código, ver
    `tipo_cambio.py`) -- todos los candidatos de esta corrida comparten
    ese mismo valor/fuente/fecha. `obtener_tipo_cambio` es inyectable
    para poder testear sin red real; en producción es siempre
    `tipo_cambio.obtener_dolar_mep`.
    """
    conexion = db.conectar()
    candidatos = db.obtener_candidatos_pendientes_de_viabilidad(conexion)

    if not candidatos:
        logger.warning("No hay ningún candidato con estado 'con_comparable' pendiente de evaluar.")
        return []

    tipo_cambio = obtener_tipo_cambio()
    if tipo_cambio.disponible:
        logger.info(
            "Tipo de cambio MEP: $%.2f (fuente %s, fecha de referencia %s, consultado %s).",
            tipo_cambio.valor, tipo_cambio.fuente, tipo_cambio.fecha_referencia, tipo_cambio.obtenido_en,
        )
    else:
        logger.warning(
            "No se pudo obtener el dólar MEP en esta corrida (%s) -- los candidatos con precio de ML en "
            "ARS quedarán 'indeterminado', no se asume ninguna otra cotización.", tipo_cambio.detalle,
        )

    primera_vez = es_primera_vez()

    with navegador_persistente() as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        if primera_vez or forzar_login:
            pagina.goto(URL_ALIBABA_HOME, wait_until="domcontentloaded")
            confirmar_login_manual()

        def abrir_ficha(url: str) -> str:
            espera = esperar_entre_fichas(delay_min, delay_max)
            logger.info("Esperando %.1fs antes de abrir la ficha de Alibaba %s.", espera, url)
            return _abrir_pagina_alibaba(pagina, url, f"ficha Alibaba (viabilidad) {url}", tipo="filtro_economico_ficha")

        def procesar_uno(candidato: dict) -> dict:
            return procesar_candidato_viabilidad(
                candidato, conexion, abrir_ficha, tipo_cambio,
                ratio_minimo=ratio_minimo, diferencia_minima_usd=diferencia_minima_usd,
            )

        resultados = procesar_lote_viabilidad(candidatos, conexion, procesar_uno)

    return resultados


def main() -> None:
    argparser = argparse.ArgumentParser(
        description="Filtro económico (Fase 3): evalúa viabilidad de importar cada candidato con match adecuado."
    )
    argparser.add_argument("--ratio-minimo", type=float, default=RATIO_MINIMO_DEFAULT, help="Relación mínima ML/Alibaba (regla de negocio).")
    argparser.add_argument("--diferencia-minima", type=float, default=DIFERENCIA_MINIMA_USD_DEFAULT, help="Diferencia mínima en USD (regla de negocio).")
    argparser.add_argument("--login", action="store_true", help="Forzar el paso de login manual de nuevo.")
    argparser.add_argument("--delay-min", type=float, default=DELAY_MIN_SEG_DEFAULT)
    argparser.add_argument("--delay-max", type=float, default=DELAY_MAX_SEG_DEFAULT)
    args = argparser.parse_args()

    resultados = ejecutar_filtro_economico_real(
        ratio_minimo=args.ratio_minimo, diferencia_minima_usd=args.diferencia_minima,
        forzar_login=args.login, delay_min=args.delay_min, delay_max=args.delay_max,
    )

    print("=" * 70)
    print(f"FILTRO ECONÓMICO TERMINADO -- {len(resultados)} candidato(s) procesado(s)")
    for conteo_resultado in ("viable", "viable_dudoso", "no_viable", "indeterminado", "error"):
        cantidad = sum(1 for r in resultados if r["resultado"] == conteo_resultado)
        if cantidad:
            print(f"  {conteo_resultado}: {cantidad}")
    print("=" * 70)
    for r in resultados:
        print(f"  [{r['resultado']}] {r['id_ml']} ({(r.get('nombre') or '')[:50]}): {r['motivo']}")

    print("\nRESUMEN COMPLETO EN JSON:")
    print(json.dumps(resultados, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
