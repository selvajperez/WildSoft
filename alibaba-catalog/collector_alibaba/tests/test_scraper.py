from dataclasses import dataclass
from pathlib import Path

from scraper import _es_bloqueo

FIXTURES = Path(__file__).parent / "fixtures"
PAGINA_BLOQUEADA = (FIXTURES / "pagina_bloqueada_captcha.html").read_text(encoding="utf-8")
PAGINA_LISTADO_OK = (FIXTURES / "productlist_page19.html").read_text(encoding="utf-8")


@dataclass
class RespuestaFalsa:
    status_code: int
    text: str


def test_detecta_pagina_de_bloqueo_captcha_real():
    """
    HTML real capturado de dcsjry888.m.en.alibaba.com/productlist-1.html: el
    sitio devuelve el slider CAPTCHA "punish" con HTTP 200 en vez de un 403.
    La página de bloqueo incluye la URL original (/productlist-1.html) como
    metadata de su propio verify-callback, así que el heurístico viejo
    ("captcha" en el cuerpo y "productlist" ausente) le daba falso negativo.
    """
    assert _es_bloqueo(RespuestaFalsa(status_code=200, text=PAGINA_BLOQUEADA)) is True


def test_no_marca_como_bloqueo_un_listado_real():
    assert _es_bloqueo(RespuestaFalsa(status_code=200, text=PAGINA_LISTADO_OK)) is False


def test_marca_como_bloqueo_status_codes_tipicos():
    for status_code in (403, 429, 503):
        assert _es_bloqueo(RespuestaFalsa(status_code=status_code, text="")) is True


def test_no_marca_como_bloqueo_status_200_sin_marcadores():
    assert _es_bloqueo(RespuestaFalsa(status_code=200, text="<html><body>ok</body></html>")) is False
