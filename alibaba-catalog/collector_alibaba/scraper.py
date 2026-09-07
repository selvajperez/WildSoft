"""
Capa de red del collector: pedidos HTTP "educados" a la tienda de Alibaba.

Nada de rotación de proxies ni resolución de CAPTCHAs: si el sitio bloquea,
se registra el bloqueo y se corta (ver `PaginaBloqueadaError`).
"""

from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

logger = logging.getLogger("collector_alibaba")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
    "WildSoftCatalogBot/1.0 (+contacto: selvajperez@gmail.com)"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

DELAY_ENTRE_REQUESTS_SEG = (1.0, 2.0)  # rango para el sleep entre páginas
MAX_REINTENTOS = 3
BACKOFF_BASE_SEG = 2


class PaginaBloqueadaError(RuntimeError):
    """El sitio devolvió algo que indica bloqueo (403, CAPTCHA, contenido vacío persistente)."""


def robots_permite(url: str, user_agent: str = USER_AGENT) -> bool:
    """
    Chequea robots.txt del dominio antes de scrapear. Si robots.txt no se
    puede obtener (falla de red, 404, etc.), se asume permitido: no hay
    forma de "denegar por las dudas" sin bloquear el scraping legítimo.
    """
    partes = urlparse(url)
    robots_url = f"{partes.scheme}://{partes.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        respuesta = requests.get(robots_url, headers=HEADERS, timeout=10)
        if respuesta.status_code >= 400:
            logger.info("robots.txt no disponible en %s (status %s); se continúa.", robots_url, respuesta.status_code)
            return True
        rp.parse(respuesta.text.splitlines())
    except requests.RequestException as exc:
        logger.info("No se pudo obtener robots.txt (%s); se continúa.", exc)
        return True

    return rp.can_fetch(user_agent, url)


def _es_bloqueo(respuesta: requests.Response) -> bool:
    if respuesta.status_code in (403, 429, 503):
        return True
    cuerpo = respuesta.text.lower()
    return "captcha" in cuerpo and "productlist" not in cuerpo


def obtener_pagina(url: str, sesion: requests.Session | None = None) -> str:
    """
    Descarga una página con reintentos cortos y backoff exponencial.
    Lanza PaginaBloqueadaError si el sitio deja de responder de forma legítima.
    """
    sesion = sesion or requests.Session()
    ultimo_error: Exception | None = None

    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            respuesta = sesion.get(url, headers=HEADERS, timeout=20)
        except requests.RequestException as exc:
            ultimo_error = exc
            logger.warning("Intento %d/%d falló para %s: %s", intento, MAX_REINTENTOS, url, exc)
        else:
            if _es_bloqueo(respuesta):
                raise PaginaBloqueadaError(
                    f"El sitio devolvió una respuesta de bloqueo en {url} (status {respuesta.status_code})"
                )
            if respuesta.status_code == 200:
                return respuesta.text
            ultimo_error = RuntimeError(f"status inesperado {respuesta.status_code} en {url}")
            logger.warning("Intento %d/%d: %s", intento, MAX_REINTENTOS, ultimo_error)

        if intento < MAX_REINTENTOS:
            espera = BACKOFF_BASE_SEG ** intento
            time.sleep(espera)

    raise RuntimeError(f"No se pudo descargar {url} tras {MAX_REINTENTOS} intentos") from ultimo_error


def esperar_entre_requests() -> None:
    import random

    time.sleep(random.uniform(*DELAY_ENTRE_REQUESTS_SEG))
