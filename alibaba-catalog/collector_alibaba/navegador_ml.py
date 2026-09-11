"""
Utilidades compartidas de navegador real (Playwright + Chrome + perfil
persistente) para Mercado Libre.

Extraído de `capturador_exploratorio.py` cuando apareció un segundo
consumidor real (`orquestador_demanda_ml.py`) para no duplicar lógica ya
probada con HTML real: detección del desafío Proof-of-Work de Akamai Bot
Manager, reintento de `page.content()` ante la carrera de timing que eso
provoca, y la pausa (sin resolver ni evadir) ante un bloqueo real.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

# Mismo perfil que collector_browser.py: un solo login manual sirve para
# Alibaba y Mercado Libre (es solo un directorio de datos de Chrome, no hay
# conflicto entre sesiones de distintos dominios).
PERFIL_DEDICADO = Path(__file__).parent.parent / ".perfil_chrome_collector"

logger = logging.getLogger("navegador_ml")

# Ver capturador_exploratorio.py (git history) para el razonamiento
# completo: confirmado con HTML real (tests/fixtures/ml_desafio_pow.html)
# que lo primero que aparece en Mercado Libre NO es un CAPTCHA que
# requiera a una persona, es un desafío PoW que el propio JS resuelve
# solo. `bloqueado_ml_heuristico` sigue siendo un heurístico genérico y
# explícitamente provisorio para un bloqueo real distinto de ese, que
# todavía no vimos con HTML real.
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


def contenido_seguro(pagina, intentos: int = 5, espera_ms: int = 500) -> str:
    """
    `page.content()` de Playwright puede tirar un error transitorio si se
    llama justo mientras la página está navegando (pasa seguido acá: el
    desafío PoW de ML redirige sola apenas se resuelve). Reintenta en vez
    de romper la corrida.
    """
    ultimo_error = None
    for _ in range(intentos):
        try:
            return pagina.content()
        except PlaywrightError as exc:
            ultimo_error = exc
            pagina.wait_for_timeout(espera_ms)
    raise ultimo_error


def esperar_resolucion_desafio_pow(pagina, intentos: int = 8, espera_ms: int = 2000) -> str:
    """El desafío PoW se resuelve solo con JS real en unos segundos. Espera en pasos cortos."""
    html = contenido_seguro(pagina)
    for _ in range(intentos):
        if not es_desafio_pow_ml(html):
            break
        pagina.wait_for_timeout(espera_ms)
        html = contenido_seguro(pagina)
    return html


def confirmar_login_manual() -> None:
    print("\n" + "=" * 70)
    print("Se abrió Chrome con el perfil dedicado del proyecto.")
    print("Iniciá sesión manualmente en Mercado Libre y/o Alibaba en esa")
    print("ventana, si hace falta. La sesión queda guardada para las")
    print("próximas corridas.")
    print("=" * 70)
    input("Cuando termines, volvé a esta terminal y presioná ENTER para continuar...")


def pausar_por_bloqueo_y_continuar(pagina, url: str, etiqueta: str) -> str:
    """
    No corta la corrida: pausa, espera que la usuaria resuelva el bloqueo
    a mano en la ventana visible, y al presionar ENTER recarga y sigue
    automáticamente.
    """
    logger.warning("Posible bloqueo/CAPTCHA detectado en '%s' (%s).", etiqueta, url)
    print("\n" + "!" * 70)
    print(f"Posible CAPTCHA / bloqueo detectado en: {etiqueta}")
    print(f"URL: {url}")
    print("No se resuelve ni se evade automáticamente. Resolvelo vos en la")
    print("ventana de Chrome (si hace falta) y volvé acá.")
    print("Cuando esté resuelto, presioná ENTER: la corrida va a continuar sola.")
    print("!" * 70 + "\n")
    input()
    pagina.reload(wait_until="domcontentloaded")
    return contenido_seguro(pagina)


def abrir_pagina_ml(pagina, url: str, etiqueta: str) -> str:
    """
    Navega a una URL de Mercado Libre manejando el desafío PoW (espera
    automática) y un bloqueo real (pausa + continúa). Devuelve el HTML
    final. Punto de entrada único para no repetir esta secuencia en cada
    lugar que visita una página de ML.
    """
    pagina.goto(url, wait_until="domcontentloaded")
    html = contenido_seguro(pagina)

    if es_desafio_pow_ml(html):
        logger.info("Desafío PoW de Mercado Libre detectado en '%s'; esperando resolución automática...", etiqueta)
        html = esperar_resolucion_desafio_pow(pagina)

    if bloqueado_ml_heuristico(html):
        html = pausar_por_bloqueo_y_continuar(pagina, url, etiqueta)

    return html


def es_primera_vez() -> bool:
    return not PERFIL_DEDICADO.exists()


@contextmanager
def navegador_persistente(headless: bool = False):
    with sync_playwright() as p:
        contexto = p.chromium.launch_persistent_context(
            user_data_dir=str(PERFIL_DEDICADO),
            channel="chrome",
            headless=headless,
        )
        try:
            yield contexto
        finally:
            contexto.close()
