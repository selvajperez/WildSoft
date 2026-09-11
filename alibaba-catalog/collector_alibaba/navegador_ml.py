"""
Utilidades compartidas de navegador real (Playwright + Chrome + perfil
persistente) para Mercado Libre.

Extraído de `capturador_exploratorio.py` cuando apareció un segundo
consumidor real (`orquestador_demanda_ml.py`) para no duplicar lógica ya
probada con HTML real: detección del desafío Proof-of-Work de Akamai Bot
Manager, reintento de `page.content()` ante la carrera de timing que eso
provoca, y la pausa (sin resolver ni evadir) ante un bloqueo real.

Bloqueos reales confirmados con HTML real hasta ahora:
  - Desafío PoW de Akamai (`es_desafio_pow_ml`): se resuelve solo con el
    JS de la propia página -- se espera, no se pausa.
  - "Tráfico sospechoso" (`es_bloqueo_trafico_sospechoso_ml`): pide
    loguearse o registrarse (ruta `/gz/account-verification`,
    "negative_traffic"). Confirmado en una corrida real de
    `medicion_confiabilidad_ml.py` después de ~20 fichas seguidas en
    pocos minutos -- afectó TODAS las fichas posteriores hasta
    resolverse a mano. A diferencia del PoW, esto sí necesita una
    persona: se pausa.

`pausar_por_bloqueo_y_continuar` nunca cierra Chrome ni resuelve/evade
el bloqueo -- pausa indefinidamente (sin timeout corto), y al presionar
Enter recarga la MISMA URL y verifica que el bloqueo realmente haya
desaparecido antes de seguir; si sigue bloqueado, vuelve a pausar en vez
de avanzar. Como el reload es sobre la página que ya se estaba
procesando, quien llama (`abrir_pagina_ml`) siempre retoma exactamente
esa misma ficha/URL al resolverse -- no hace falta guardar un índice
aparte: el estado "qué ficha se estaba procesando" ya vive en la propia
llamada bloqueada de Python, y ningún dato se escribe en la base hasta
que esa llamada devuelve contenido real, así que una pausa nunca pierde
ni duplica observaciones.

`esperar_entre_fichas` agrega una pausa configurable con jitter aleatorio
entre fichas, para reducir la frecuencia con la que aparece el bloqueo
de tráfico sospechoso en primer lugar (más vale evitarlo que resolverlo).
"""

from __future__ import annotations

import logging
import random
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

# Mismo perfil que collector_browser.py: un solo login manual sirve para
# Alibaba y Mercado Libre (es solo un directorio de datos de Chrome, no hay
# conflicto entre sesiones de distintos dominios).
PERFIL_DEDICADO = Path(__file__).parent.parent / ".perfil_chrome_collector"

# Hallazgo real: el bloqueo de tráfico sospechoso apareció después de
# ~20 fichas abiertas en ~1 segundo cada una. Este rango es un punto de
# partida razonable, no un valor confirmado como "seguro" -- siempre
# configurable desde afuera (--delay-min/--delay-max).
DELAY_MIN_SEG_DEFAULT = 3.0
DELAY_MAX_SEG_DEFAULT = 8.0

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

# Bloqueo real de ML por "tráfico sospechoso" -- pide loguearse o
# registrarse para seguir navegando (ruta interna /gz/account-verification,
# "negative_traffic"). Confirmado con HTML real (ver
# tests/fixtures/ml_bloqueo_trafico_sospechoso_real.html): apareció a
# mitad de una corrida real de medicion_confiabilidad_ml.py después de
# ~20 fichas abiertas en pocos minutos, y afectó TODAS las fichas
# posteriores (directas y de tracking por igual) hasta resolverse a mano.
# A diferencia del desafío PoW, esto sí necesita una persona: no hay
# forma de resolverlo solo con JS, hay que loguearse o registrarse.
_MARCADORES_TRAFICO_SOSPECHOSO_ML = (
    "suspicious-traffic-frontend",
    "gz-account-verification-index",
    "account-verification-main",
)


def es_desafio_pow_ml(html: str) -> bool:
    cuerpo = html.lower()
    return any(marcador in cuerpo for marcador in _MARCADORES_DESAFIO_POW_ML)


def es_bloqueo_trafico_sospechoso_ml(html: str) -> bool:
    cuerpo = html.lower()
    return any(marcador in cuerpo for marcador in _MARCADORES_TRAFICO_SOSPECHOSO_ML)


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


def esperar_marcador_en_pagina(pagina, marcador: str, intentos: int = 8, espera_ms: int = 1000) -> str:
    """
    Espera en pasos cortos hasta que `marcador` aparezca en el HTML, o
    hasta agotar `intentos`. Hallazgo real: en el listado de búsqueda de
    ML (framework "search-nordic", React), `domcontentloaded` puede
    disparar antes de que el listado real se inyecte en el DOM -- una
    corrida real capturó una página de 1.1MB con título normal pero CERO
    apariciones de "ui-search-layout" (el marcador de cada resultado),
    solo la pantalla de carga ("search.loading-screen"). Si se agotan los
    intentos, devuelve el último HTML igual (puede ser un 0 resultados
    genuino, no siempre es la carrera de timing).
    """
    html = contenido_seguro(pagina)
    for _ in range(intentos):
        if marcador in html:
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


def pausar_por_bloqueo_y_continuar(
    pagina,
    url: str,
    etiqueta: str,
    sigue_bloqueado: Callable[[str], bool] | None = None,
    sitio: str = "Mercado Libre",
) -> str:
    """
    No corta la corrida ni cierra Chrome, y no resuelve ni evade el
    bloqueo. Pausa indefinidamente (sin timeout corto) a que la usuaria
    lo resuelva a mano en la ventana visible. Al presionar Enter recarga
    la MISMA URL y verifica que el bloqueo realmente haya desaparecido
    antes de devolver el control -- si sigue bloqueado, vuelve a pausar
    en vez de avanzar o darlo por resuelto. Como retoma la misma URL,
    quien llama continúa exactamente con esa ficha, nunca la pierde ni
    la procesa dos veces.

    `sigue_bloqueado(html) -> bool`, si se pasa, reemplaza el chequeo
    default (específico de ML: `es_bloqueo_trafico_sospechoso_ml`/
    `bloqueado_ml_heuristico`) -- necesario para reusar esta misma pausa
    con otro sitio (ej. Alibaba, con `scraper.contiene_marcadores_bloqueo`),
    que muestra una página de bloqueo completamente distinta: sin esto,
    la verificación pensaría "ya se resolvió" apenas los marcadores de ML
    no aparezcan, sin importar si el otro sitio sigue bloqueado de
    verdad. `sitio` solo cambia el nombre en el mensaje impreso.
    """
    if sigue_bloqueado is None:
        def sigue_bloqueado(html: str) -> bool:
            return es_bloqueo_trafico_sospechoso_ml(html) or bloqueado_ml_heuristico(html)

    while True:
        logger.warning("Bloqueo/CAPTCHA detectado en '%s' (%s). Pausando para intervención humana.", etiqueta, url)
        print("\n" + "!" * 70)
        print(f"{sitio} requiere intervención humana. Resolvé el login/CAPTCHA")
        print("en la ventana de Chrome y luego presioná Enter para continuar.")
        print(f"Página en curso: {etiqueta}")
        print(f"URL: {url}")
        print("!" * 70 + "\n")
        input()

        pagina.reload(wait_until="domcontentloaded")
        html = contenido_seguro(pagina)

        if not sigue_bloqueado(html):
            logger.info("Bloqueo resuelto en '%s'. Continuando.", etiqueta)
            return html

        logger.warning("Sigue bloqueado en '%s' -- se vuelve a pausar en vez de avanzar.", etiqueta)
        print("Todavía parece bloqueado. Volvé a intentar resolverlo y presioná Enter de nuevo.\n")


def esperar_entre_fichas(delay_min: float = DELAY_MIN_SEG_DEFAULT, delay_max: float = DELAY_MAX_SEG_DEFAULT) -> float:
    """
    Pausa una cantidad aleatoria de segundos en [delay_min, delay_max]
    antes de abrir la próxima ficha, para reducir la frecuencia del
    bloqueo de tráfico sospechoso (mejor evitarlo que resolverlo).
    Devuelve la espera real usada, para poder loguearla.
    """
    espera = random.uniform(delay_min, delay_max)
    time.sleep(espera)
    return espera


def abrir_pagina_ml(pagina, url: str, etiqueta: str, esperar_marcador: str | None = None) -> str:
    """
    Navega a una URL de Mercado Libre manejando el desafío PoW (espera
    automática) y un bloqueo real (pausa + continúa). Devuelve el HTML
    final. Punto de entrada único para no repetir esta secuencia en cada
    lugar que visita una página de ML.

    `esperar_marcador`, si se pasa (ej. "ui-search-layout" para un
    listado de búsqueda), espera hasta que ese texto aparezca en el HTML
    antes de devolverlo -- ver `esperar_marcador_en_pagina` para el
    hallazgo real que motivó esto (contenido capturado antes de que
    termine de renderizar).
    """
    pagina.goto(url, wait_until="domcontentloaded")
    html = contenido_seguro(pagina)

    if es_desafio_pow_ml(html):
        logger.info("Desafío PoW de Mercado Libre detectado en '%s'; esperando resolución automática...", etiqueta)
        html = esperar_resolucion_desafio_pow(pagina)

    if es_bloqueo_trafico_sospechoso_ml(html) or bloqueado_ml_heuristico(html):
        html = pausar_por_bloqueo_y_continuar(pagina, url, etiqueta)

    if esperar_marcador is not None and esperar_marcador not in html:
        logger.info("Esperando a que '%s' aparezca en '%s'...", esperar_marcador, etiqueta)
        html = esperar_marcador_en_pagina(pagina, esperar_marcador)

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
