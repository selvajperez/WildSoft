"""
Captura automática de muestras reales de HTML (Mercado Libre + Alibaba)
para poder diseñar los parsers del motor de sourcing sin que la usuaria
tenga que buscar, abrir ni guardar nada a mano.

Reutiliza el mismo perfil de Chrome persistente que `collector_browser.py`
(un solo login manual, para ambos sitios si hace falta) y el mismo
principio: Chrome real y visible, nunca resuelve ni evade un CAPTCHA. La
diferencia de comportamiento es a propósito: acá, después de que la
usuaria resuelve el CAPTCHA a mano, la captura sigue sola con el siguiente
objetivo en vez de cortar toda la corrida (no hay progreso "de catálogo"
que proteger, es una recolección de muestras puntuales).

La lógica de navegador (detección del desafío PoW de ML, reintento de
`content()`, pausa ante bloqueo real) vive en `navegador_ml.py`,
compartida con `orquestador_demanda_ml.py`.

Captura tres objetivos de referencia (parametrizables, con default para
poder correrlo sin pasarle nada):
    1. Una búsqueda en Mercado Libre.
    2. La ficha del primer resultado de esa búsqueda.
    3. Una ficha de producto de Alibaba (usa una URL real ya conocida del
       catálogo scrapeado en esta sesión).

Cada captura se guarda tal cual en `capturas_exploratorias/`, con un
manifiesto (`manifiesto.jsonl`) que registra URL, archivo, timestamp y si
se detectó un bloqueo en el camino.

Uso:
    python capturador_exploratorio.py
    python capturador_exploratorio.py --busqueda-ml "candado bicicleta"
    python capturador_exploratorio.py --url-alibaba "https://www.alibaba.com/product-detail/..."
    python capturador_exploratorio.py --login
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper import contiene_marcadores_bloqueo as bloqueado_alibaba  # noqa: E402

import navegador_ml  # noqa: E402
from navegador_ml import (  # noqa: E402
    PERFIL_DEDICADO,
    abrir_pagina_ml,
    confirmar_login_manual,
    contenido_seguro,
    es_primera_vez,
    navegador_persistente,
    pausar_por_bloqueo_y_continuar,
)

DIR_CAPTURAS = Path(__file__).parent.parent / "capturas_exploratorias"
MANIFIESTO = DIR_CAPTURAS / "manifiesto.jsonl"

URL_BASE_ML = "https://listado.mercadolibre.com.ar"

# Producto real, de compra directa, ya confirmado en esta misma catalogación
# (ver collector_alibaba/tests/fixtures/productlist_page19.html). Sirve de
# referencia conocida para la ficha de Alibaba mientras no tengamos todavía
# un mecanismo propio de "elegir un producto candidato".
URL_ALIBABA_REFERENCIA = (
    "https://www.alibaba.com/product-detail/Washable-BPA-Free-Clean-Dish-Washing_1601487795601.html"
)

BUSQUEDA_ML_DEFAULT = "cepillo de limpieza"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "capturador_exploratorio.log")],
)
logger = logging.getLogger("capturador_exploratorio")


def _extraer_primer_link_producto_ml(html: str) -> str | None:
    """
    Best-effort: busca cualquiera de las 3 formas reales de link de
    producto confirmadas en parser_busqueda_ml.py (directo /p/, directo
    /up/, o con wrapper de tracking). Si no encuentra nada, quien llama
    debe loguearlo y seguir, no fallar.
    """
    match = re.search(r'href="(https://[^"]*mercadolibre\.com\.ar/[^"]*(?:/u?p/[A-Za-z]+\d+|item_id%3A[A-Za-z]+\d+)[^"]*)"', html)
    return match.group(1) if match else None


# --- Manifiesto -----------------------------------------------------------

def _registrar_captura(etiqueta: str, url: str, archivo: Path | None, bloqueado: bool) -> None:
    DIR_CAPTURAS.mkdir(parents=True, exist_ok=True)
    entrada = {
        "etiqueta": etiqueta,
        "url": url,
        "archivo": archivo.name if archivo else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bloqueado": bloqueado,
    }
    with open(MANIFIESTO, "a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    logger.info("Registrado en manifiesto: %s", entrada)


def _guardar_html(etiqueta: str, html: str) -> Path:
    DIR_CAPTURAS.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archivo = DIR_CAPTURAS / f"{etiqueta}_{timestamp}.html"
    archivo.write_text(html, encoding="utf-8")
    return archivo


# --- Capturas individuales -------------------------------------------------

def _capturar_busqueda_ml(pagina, busqueda: str) -> str:
    url = f"{URL_BASE_ML}/{urllib.parse.quote(busqueda.replace(' ', '-'))}"
    logger.info("Abriendo búsqueda de Mercado Libre: %s", url)
    html = abrir_pagina_ml(pagina, url, "búsqueda Mercado Libre")

    archivo = _guardar_html("ml_busqueda", html)
    _registrar_captura("ml_busqueda", url, archivo, navegador_ml.bloqueado_ml_heuristico(html))
    logger.info("Búsqueda ML guardada en %s", archivo)
    return html


def _capturar_ficha_ml(pagina, html_busqueda: str) -> None:
    link = _extraer_primer_link_producto_ml(html_busqueda)
    if not link:
        logger.warning("No se pudo extraer un link de producto del HTML de búsqueda de ML. Se omite la ficha ML.")
        _registrar_captura("ml_ficha", "(no encontrado)", None, False)
        return

    logger.info("Abriendo ficha de Mercado Libre: %s", link)
    html = abrir_pagina_ml(pagina, link, "ficha Mercado Libre")

    archivo = _guardar_html("ml_ficha", html)
    _registrar_captura("ml_ficha", link, archivo, navegador_ml.bloqueado_ml_heuristico(html))
    logger.info("Ficha ML guardada en %s", archivo)


def _capturar_ficha_alibaba(pagina, url: str) -> None:
    logger.info("Abriendo ficha de Alibaba: %s", url)
    pagina.goto(url, wait_until="domcontentloaded")
    html = contenido_seguro(pagina)

    if bloqueado_alibaba(html):
        html = pausar_por_bloqueo_y_continuar(pagina, url, "ficha Alibaba")

    archivo = _guardar_html("alibaba_ficha", html)
    _registrar_captura("alibaba_ficha", url, archivo, bloqueado_alibaba(html))
    logger.info("Ficha Alibaba guardada en %s", archivo)


def capturar_muestras(
    busqueda_ml: str = BUSQUEDA_ML_DEFAULT,
    url_alibaba: str = URL_ALIBABA_REFERENCIA,
    forzar_login: bool = False,
) -> None:
    primera_vez = es_primera_vez()

    with navegador_persistente() as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        if primera_vez or forzar_login:
            pagina.goto(URL_BASE_ML, wait_until="domcontentloaded")
            confirmar_login_manual()

        html_busqueda = _capturar_busqueda_ml(pagina, busqueda_ml)
        _capturar_ficha_ml(pagina, html_busqueda)
        _capturar_ficha_alibaba(pagina, url_alibaba)

    logger.info("Captura terminada. Ver %s y el manifiesto en %s", DIR_CAPTURAS, MANIFIESTO)


def main() -> None:
    argparser = argparse.ArgumentParser(
        description="Captura automática de muestras de ML y Alibaba, con Chrome real."
    )
    argparser.add_argument("--busqueda-ml", default=BUSQUEDA_ML_DEFAULT, help="Término a buscar en Mercado Libre.")
    argparser.add_argument("--url-alibaba", default=URL_ALIBABA_REFERENCIA, help="Ficha de Alibaba a capturar.")
    argparser.add_argument("--login", action="store_true", help="Forzar el paso de login manual de nuevo.")
    args = argparser.parse_args()

    capturar_muestras(busqueda_ml=args.busqueda_ml, url_alibaba=args.url_alibaba, forzar_login=args.login)


if __name__ == "__main__":
    main()
