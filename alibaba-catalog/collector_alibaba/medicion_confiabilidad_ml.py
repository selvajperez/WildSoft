"""
Medición cuantitativa de confiabilidad al abrir fichas individuales de
Mercado Libre -- NO cambia la estrategia de URLs ni el pipeline de
candidatos, solo mide.

Contexto: en corridas reales de `orquestador_demanda_ml.py` se encontró
que una fracción de las fichas priorizadas (Prioridad A/B) devuelve un
404 real de Mercado Libre en vez de la ficha esperada, y que esto es
intermitente (el mismo item_id funcionó en una corrida y dio 404 en la
siguiente, 25 minutos después) -- ver el hallazgo documentado en
`parser_ficha_ml.py`. Antes de decidir si hace falta resolver esto o si
la pérdida es aceptable, hace falta medirla con más de una búsqueda real.

Este script corre varias búsquedas reales, abre TODAS las fichas
Prioridad A/B de cada una (hasta un máximo configurable por búsqueda) y
clasifica cada intento en:
  - "abierta_ok": se extrajo precio y/o unidades vendidas reales.
  - "404": es el 404 real de ML (`parser_ficha_ml.es_ficha_no_encontrada`).
  - "otro_error": ni lo uno ni lo otro -- página sin datos reconocibles
    que tampoco es el 404 conocido (otra plantilla, un bloqueo no
    detectado, etc.).

Separa el resultado por `origen_url` (ver `parser_busqueda_ml.py`):
"directo" (href real del listado, usado tal cual) vs. "tracking" (URL
reconstruida a partir de un item_id de link de tracking -- la fuente del
hallazgo de 404 intermitente).

No escribe en `candidatos_ml`/`historial_ml`: es una herramienta de
diagnóstico separada del pipeline de producción, para no mezclar datos de
medición con el estado real de candidatos ni tocar el progreso existente.
Guarda el detalle completo de cada intento + el resumen agregado en
`medicion_confiabilidad_ml/reporte_<timestamp>.json` (no se commitea).

Uso:
    python medicion_confiabilidad_ml.py
    python medicion_confiabilidad_ml.py "cepillo de limpieza" "trapo de piso" --max-fichas-por-busqueda 20
    python medicion_confiabilidad_ml.py --login
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent))

from navegador_ml import abrir_pagina_ml, confirmar_login_manual, es_primera_vez, navegador_persistente  # noqa: E402
from parser_busqueda_ml import clasificar_prioridad, parsear_listado_busqueda  # noqa: E402
from parser_ficha_ml import parsear_ficha_ml  # noqa: E402

URL_BASE_ML = "https://listado.mercadolibre.com.ar"

# Mismo rubro que el resto del proyecto (catálogo Alibaba de referencia +
# búsqueda default de capturador_exploratorio.py/orquestador_demanda_ml.py)
# -- varias búsquedas relacionadas para no medir sobre un solo listado.
BUSQUEDAS_DEFAULT = [
    "cepillo de limpieza",
    "escobillon de limpieza",
    "trapo de piso",
    "esponja de cocina",
    "guantes de limpieza",
]

MAX_FICHAS_POR_BUSQUEDA_DEFAULT = 15

DIR_REPORTES = Path(__file__).parent.parent / "medicion_confiabilidad_ml"

# Mismo directorio que usa orquestador_demanda_ml.py para las fichas
# indeterminadas -- acá también para "otro_error", mismo propósito:
# tener HTML real para diagnosticar sin pedirle a nadie que lo recolecte
# a mano.
DIR_DIAGNOSTICO_FICHAS = Path(__file__).parent.parent / "diagnostico_fichas_ml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "medicion_confiabilidad_ml.log")],
)
logger = logging.getLogger("medicion_confiabilidad_ml")


def _url_busqueda(busqueda: str) -> str:
    return f"{URL_BASE_ML}/{urllib.parse.quote(busqueda.replace(' ', '-'))}"


def _clasificar_intento(datos_ficha: dict) -> str:
    if datos_ficha.get("pagina_no_encontrada"):
        return "404"
    if datos_ficha.get("precio_ml") is not None or datos_ficha.get("unidades_vendidas") is not None:
        return "abierta_ok"
    return "otro_error"


def _guardar_html_diagnostico(id_ml: str, html: str) -> Path:
    """
    Guarda el HTML crudo de una ficha que quedó "otro_error" -- ni 404 ni
    datos extraídos -- para diagnosticar la causa (ej. un bloqueo/pedido
    de login que el heurístico actual no detecta) sin pedirle a nadie que
    lo recolecte a mano.
    """
    DIR_DIAGNOSTICO_FICHAS.mkdir(parents=True, exist_ok=True)
    archivo = DIR_DIAGNOSTICO_FICHAS / f"otro_error_{id_ml}.html"
    archivo.write_text(html, encoding="utf-8")
    logger.warning("Ficha %s con otro_error -- HTML guardado en %s para diagnóstico.", id_ml, archivo)
    return archivo


def medir_busqueda(
    busqueda: str,
    obtener_html_busqueda: Callable[[str], str],
    abrir_ficha: Callable[[str, str], str],
    max_fichas_por_busqueda: int,
    guardar_diagnostico: Callable[[str, str], None] | None = None,
) -> list[dict]:
    """
    Abre TODAS las fichas Prioridad A/B de una búsqueda (A primero, igual
    que `orquestador_demanda_ml.py`), hasta `max_fichas_por_busqueda`, sin
    ningún criterio de corte por "candidatos ya confirmados" -- acá el
    objetivo es medir, no curar candidatos. `guardar_diagnostico`, si se
    pasa, se invoca para cada ficha que quede "otro_error" (no toca disco
    por defecto, así los tests no tienen efectos secundarios de archivo).
    """
    html_busqueda = obtener_html_busqueda(_url_busqueda(busqueda))
    resultados = parsear_listado_busqueda(html_busqueda)

    cola_a = [item for item in resultados if clasificar_prioridad(item) == "A"]
    cola_b = [item for item in resultados if clasificar_prioridad(item) == "B"]

    intentos = []
    for item in (cola_a + cola_b)[:max_fichas_por_busqueda]:
        html_ficha = abrir_ficha(item["url_ml"], f"ficha {item['id_ml']}")
        datos_ficha = parsear_ficha_ml(html_ficha, url=item["url_ml"])
        resultado = _clasificar_intento(datos_ficha)

        if resultado == "otro_error" and guardar_diagnostico is not None:
            guardar_diagnostico(item["id_ml"], html_ficha)

        intentos.append({
            "busqueda": busqueda,
            "id_ml": item["id_ml"],
            "nombre": item["nombre"],
            "origen_url": item["origen_url"],
            "prioridad_listado": clasificar_prioridad(item),
            "resultado": resultado,
        })
        logger.info(
            "[%s] Ficha %s (origen=%s, prioridad=%s): %s",
            busqueda, item["id_ml"], item["origen_url"], clasificar_prioridad(item), resultado,
        )

    return intentos


def ejecutar_medicion_real(
    busquedas: list[str],
    max_fichas_por_busqueda: int = MAX_FICHAS_POR_BUSQUEDA_DEFAULT,
    forzar_login: bool = False,
) -> list[dict]:
    """Punto de entrada real: arma `obtener_html_busqueda`/`abrir_ficha` con Chrome real + Playwright."""
    primera_vez = es_primera_vez()
    todos_los_intentos: list[dict] = []

    with navegador_persistente() as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        if primera_vez or forzar_login:
            pagina.goto(URL_BASE_ML, wait_until="domcontentloaded")
            confirmar_login_manual()

        def obtener_html_busqueda(url: str) -> str:
            return abrir_pagina_ml(pagina, url, f"búsqueda de medición: {url}")

        def abrir_ficha(url: str, etiqueta: str) -> str:
            return abrir_pagina_ml(pagina, url, etiqueta)

        for busqueda in busquedas:
            logger.info("=== Midiendo búsqueda: %s ===", busqueda)
            todos_los_intentos.extend(
                medir_busqueda(
                    busqueda, obtener_html_busqueda, abrir_ficha, max_fichas_por_busqueda,
                    guardar_diagnostico=_guardar_html_diagnostico,
                )
            )

    return todos_los_intentos


def _pct(parte: int, total: int) -> float:
    return round(100 * parte / total, 1) if total else 0.0


def _resumen_de(intentos: list[dict]) -> dict:
    total = len(intentos)
    abiertas_ok = sum(1 for i in intentos if i["resultado"] == "abierta_ok")
    en_404 = sum(1 for i in intentos if i["resultado"] == "404")
    otro_error = sum(1 for i in intentos if i["resultado"] == "otro_error")
    return {
        "fichas_intentadas": total,
        "fichas_abiertas_ok": abiertas_ok,
        "fichas_404": en_404,
        "otros_errores": otro_error,
        "pct_exito": _pct(abiertas_ok, total),
        "pct_perdida_404": _pct(en_404, total),
        "pct_otro_error": _pct(otro_error, total),
    }


def agregar_resumen(intentos: list[dict]) -> dict:
    """
    Resumen agregado total + separado por `origen_url` ("directo" vs.
    "tracking"), que es la variable que el hallazgo real señaló como
    relevante para la tasa de 404.
    """
    return {
        "total": _resumen_de(intentos),
        "directo": _resumen_de([i for i in intentos if i["origen_url"] == "directo"]),
        "tracking": _resumen_de([i for i in intentos if i["origen_url"] == "tracking"]),
    }


def _guardar_reporte(intentos: list[dict], resumen: dict) -> Path:
    DIR_REPORTES.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archivo = DIR_REPORTES / f"reporte_{timestamp}.json"
    archivo.write_text(
        json.dumps({"resumen": resumen, "intentos": intentos}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return archivo


def _imprimir_resumen(resumen: dict) -> None:
    for etiqueta, clave in (("TOTAL", "total"), ("Solo URLs directas", "directo"), ("Solo URLs de tracking (reconstruidas)", "tracking")):
        r = resumen[clave]
        print(f"\n--- {etiqueta} ---")
        print(f"Fichas intentadas:      {r['fichas_intentadas']}")
        print(f"Abiertas correctamente: {r['fichas_abiertas_ok']} ({r['pct_exito']}%)")
        print(f"404 (URL reconstruida): {r['fichas_404']} ({r['pct_perdida_404']}%)")
        print(f"Otros errores:          {r['otros_errores']} ({r['pct_otro_error']}%)")


def main() -> None:
    argparser = argparse.ArgumentParser(
        description="Mide la tasa de éxito/404 al abrir fichas de ML, sin cambiar la estrategia de URLs ni tocar candidatos_ml."
    )
    argparser.add_argument("busquedas", nargs="*", default=BUSQUEDAS_DEFAULT, help="Búsquedas a correr (default: 5 términos del mismo rubro).")
    argparser.add_argument(
        "--max-fichas-por-busqueda", type=int, default=MAX_FICHAS_POR_BUSQUEDA_DEFAULT,
        help="Máximo de fichas Prioridad A/B a abrir por búsqueda.",
    )
    argparser.add_argument("--login", action="store_true", help="Forzar el paso de login manual de nuevo.")
    args = argparser.parse_args()

    intentos = ejecutar_medicion_real(
        args.busquedas, max_fichas_por_busqueda=args.max_fichas_por_busqueda, forzar_login=args.login,
    )
    resumen = agregar_resumen(intentos)
    archivo = _guardar_reporte(intentos, resumen)

    _imprimir_resumen(resumen)
    print(f"\nReporte completo (detalle por ficha + resumen) guardado en: {archivo}")


if __name__ == "__main__":
    main()
