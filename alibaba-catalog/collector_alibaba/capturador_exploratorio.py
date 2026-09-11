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

Captura tres objetivos de referencia (parametrizables, con default para
poder correrlo sin pasarle nada):
    1. Una búsqueda en Mercado Libre.
    2. La ficha del primer resultado de esa búsqueda (best-effort: la
       extracción del link todavía no está confirmada contra HTML real
       de ML, así que si no encuentra nada, lo loguea y sigue).
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

from playwright.sync_api import sync_playwright  # noqa: E402

from scraper import contiene_marcadores_bloqueo as bloqueado_alibaba  # noqa: E402

# Mismo perfil que collector_browser.py: un solo login manual sirve para
# Alibaba y Mercado Libre (es solo un directorio de datos de Chrome, no hay
# conflicto entre sesiones de distintos dominios).
PERFIL_DEDICADO = Path(__file__).parent.parent / ".perfil_chrome_collector"

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


# --- Detección de bloqueo -----------------------------------------------
#
# Para Alibaba reutilizamos el detector ya probado con HTML real
# (scraper.contiene_marcadores_bloqueo).
#
# Para Mercado Libre confirmamos con una captura real (ver
# tests/fixtures/ml_desafio_pow.html) que lo primero que aparece NO es un
# CAPTCHA que requiera a una persona: es un desafío "Proof of Work" de
# Akamai Bot Manager que el propio JavaScript de la página resuelve solo
# (cualquier navegador real que ejecute JS, como el nuestro, lo pasa en
# unos segundos) y después navega sola al contenido real. Por eso NO se
# pausa para pedir intervención humana ante esto: se espera a que se
# resuelva. Si después de esperar seguimos en esta misma página, recién
# ahí puede hacer falta un CAPTCHA real -- pero eso todavía no lo vimos
# con HTML real, así que `bloqueado_ml_heuristico` sigue siendo un
# heurístico genérico y explícitamente provisorio para ese caso.
_MARCADORES_DESAFIO_POW_ML = (
    "micro-landing-container",
    "verifychallenge",
    "snoopy-generation-web",
)

_MARCADORES_BLOQUEO_ML_PROVISORIOS = (
    "captcha",
    "verificación de seguridad",
    "verifica que no sos un robot",
    "unusual traffic",
    "recaptcha",
)


def es_desafio_pow_ml(html: str) -> bool:
    cuerpo = html.lower()
    return any(marcador in cuerpo for marcador in _MARCADORES_DESAFIO_POW_ML)


def bloqueado_ml_heuristico(html: str) -> bool:
    cuerpo = html.lower()
    return any(marcador in cuerpo for marcador in _MARCADORES_BLOQUEO_ML_PROVISORIOS)


def _esperar_resolucion_desafio_pow(pagina, intentos: int = 8, espera_ms: int = 2000) -> str:
    """
    El desafío PoW se resuelve solo con JS real en unos segundos. Espera
    en pasos cortos en vez de un único timeout largo, para no perder
    tiempo si se resuelve rápido.
    """
    html = pagina.content()
    for _ in range(intentos):
        if not es_desafio_pow_ml(html):
            break
        pagina.wait_for_timeout(espera_ms)
        html = pagina.content()
    return html


def _extraer_primer_link_producto_ml(html: str) -> str | None:
    """
    Best-effort: los ids de publicación de ML tienen el patrón MLA-<dígitos>
    en la URL. No está confirmado contra HTML real todavía -- si no
    encuentra nada, quien llama debe loguearlo y seguir, no fallar.
    """
    match = re.search(r'href="(https://[^"]*mercadolibre\.com\.ar/[^"]*MLA-?\d+[^"]*)"', html)
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


# --- Login / pausa por bloqueo (mismo patrón que collector_browser.py) ----

def _confirmar_login_manual() -> None:
    print("\n" + "=" * 70)
    print("Se abrió Chrome con el perfil dedicado del proyecto.")
    print("Iniciá sesión manualmente en Mercado Libre y/o Alibaba en esa")
    print("ventana, si hace falta. La sesión queda guardada para las")
    print("próximas corridas (de esta herramienta y de collector_browser.py).")
    print("=" * 70)
    input("Cuando termines, volvé a esta terminal y presioná ENTER para continuar...")


def _pausar_por_bloqueo_y_continuar(pagina, url: str, etiqueta: str) -> str:
    """
    A diferencia de collector_browser.py, acá NO se corta la corrida: se
    pausa, se espera que la usuaria resuelva el CAPTCHA a mano en la
    ventana visible, y al presionar ENTER se recarga la página y se sigue
    con la captura (y con el resto de los objetivos) automáticamente.
    """
    logger.warning("Posible bloqueo/CAPTCHA detectado en '%s' (%s).", etiqueta, url)
    print("\n" + "!" * 70)
    print(f"Posible CAPTCHA / bloqueo detectado en: {etiqueta}")
    print(f"URL: {url}")
    print("No se resuelve ni se evade automáticamente. Resolvelo vos en la")
    print("ventana de Chrome (si hace falta) y volvé acá.")
    print("Cuando esté resuelto, presioná ENTER: la captura va a continuar sola.")
    print("!" * 70 + "\n")
    input()
    pagina.reload(wait_until="domcontentloaded")
    return pagina.content()


# --- Capturas individuales -------------------------------------------------

def _capturar_busqueda_ml(pagina, busqueda: str) -> str:
    url = f"{URL_BASE_ML}/{urllib.parse.quote(busqueda.replace(' ', '-'))}"
    logger.info("Abriendo búsqueda de Mercado Libre: %s", url)
    pagina.goto(url, wait_until="domcontentloaded")
    html = pagina.content()

    if es_desafio_pow_ml(html):
        logger.info("Desafío PoW de Mercado Libre detectado; esperando resolución automática...")
        html = _esperar_resolucion_desafio_pow(pagina)

    if bloqueado_ml_heuristico(html):
        html = _pausar_por_bloqueo_y_continuar(pagina, url, "búsqueda Mercado Libre")

    archivo = _guardar_html("ml_busqueda", html)
    _registrar_captura("ml_busqueda", url, archivo, bloqueado_ml_heuristico(html))
    logger.info("Búsqueda ML guardada en %s", archivo)
    return html


def _capturar_ficha_ml(pagina, html_busqueda: str) -> None:
    link = _extraer_primer_link_producto_ml(html_busqueda)
    if not link:
        logger.warning(
            "No se pudo extraer un link de producto del HTML de búsqueda de ML "
            "(patrón todavía no confirmado contra HTML real). Se omite la ficha ML."
        )
        _registrar_captura("ml_ficha", "(no encontrado)", None, False)
        return

    logger.info("Abriendo ficha de Mercado Libre: %s", link)
    pagina.goto(link, wait_until="domcontentloaded")
    html = pagina.content()

    if es_desafio_pow_ml(html):
        logger.info("Desafío PoW de Mercado Libre detectado; esperando resolución automática...")
        html = _esperar_resolucion_desafio_pow(pagina)

    if bloqueado_ml_heuristico(html):
        html = _pausar_por_bloqueo_y_continuar(pagina, link, "ficha Mercado Libre")

    archivo = _guardar_html("ml_ficha", html)
    _registrar_captura("ml_ficha", link, archivo, bloqueado_ml_heuristico(html))
    logger.info("Ficha ML guardada en %s", archivo)


def _capturar_ficha_alibaba(pagina, url: str) -> None:
    logger.info("Abriendo ficha de Alibaba: %s", url)
    pagina.goto(url, wait_until="domcontentloaded")
    html = pagina.content()

    if bloqueado_alibaba(html):
        html = _pausar_por_bloqueo_y_continuar(pagina, url, "ficha Alibaba")

    archivo = _guardar_html("alibaba_ficha", html)
    _registrar_captura("alibaba_ficha", url, archivo, bloqueado_alibaba(html))
    logger.info("Ficha Alibaba guardada en %s", archivo)


def capturar_muestras(
    busqueda_ml: str = BUSQUEDA_ML_DEFAULT,
    url_alibaba: str = URL_ALIBABA_REFERENCIA,
    forzar_login: bool = False,
) -> None:
    es_primera_vez = not PERFIL_DEDICADO.exists()

    with sync_playwright() as p:
        contexto = p.chromium.launch_persistent_context(
            user_data_dir=str(PERFIL_DEDICADO),
            channel="chrome",
            headless=False,
        )
        try:
            pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

            if es_primera_vez or forzar_login:
                pagina.goto(URL_BASE_ML, wait_until="domcontentloaded")
                _confirmar_login_manual()

            html_busqueda = _capturar_busqueda_ml(pagina, busqueda_ml)
            _capturar_ficha_ml(pagina, html_busqueda)
            _capturar_ficha_alibaba(pagina, url_alibaba)
        finally:
            contexto.close()

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
