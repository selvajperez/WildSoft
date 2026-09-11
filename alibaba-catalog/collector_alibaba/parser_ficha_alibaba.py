"""
Parser de la ficha individual de producto de Alibaba (product-detail), NO
la página de listado (esa la maneja `parser.py`).

Es una plantilla completamente distinta: no usa `module-data` en atributos
HTML, sino un único bloque `window.detailData = {...}` con toda la
información del producto (precio real, MOQ, sku, specs). Confirmado con
HTML real (ver `tests/fixtures/alibaba_ficha_real.html`) del producto
Alibaba 1601487795601, ya conocido en esta catalogación.

Por qué esto importa para el motor de sourcing: el precio que muestra un
resultado de búsqueda/listado NO alcanza para calcular rentabilidad (regla
del proyecto) — hay que abrir la ficha y leer el precio real de acá.
"""

from __future__ import annotations

import json
import re

_INICIO_DETAIL_DATA = "window.detailData = "


def extraer_detail_data(html: str) -> dict | None:
    """
    Extrae el objeto JSON asignado a `window.detailData`, balanceando
    llaves (no alcanza una regex simple porque el JSON tiene llaves
    anidadas y strings con llaves escapadas). Devuelve None si la página
    no tiene ese bloque (por ejemplo, si es una página de bloqueo/CAPTCHA
    en vez de la ficha real).
    """
    inicio = html.find(_INICIO_DETAIL_DATA)
    if inicio == -1:
        return None
    inicio += len(_INICIO_DETAIL_DATA)

    i = inicio
    profundidad = 0
    en_string = False
    escape = False
    comilla = None
    while i < len(html):
        c = html[i]
        if en_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == comilla:
                en_string = False
        else:
            if c in ('"', "'"):
                en_string = True
                comilla = c
            elif c == "{":
                profundidad += 1
            elif c == "}":
                profundidad -= 1
                if profundidad == 0:
                    i += 1
                    break
        i += 1

    if profundidad != 0:
        return None

    try:
        return json.loads(html[inicio:i])
    except json.JSONDecodeError:
        return None


def parsear_ficha_alibaba(html: str, url: str | None = None) -> dict:
    """
    Devuelve un dict con la forma de `alibaba_comparables` (ver
    database/db.py). Si no se puede extraer o interpretar el precio con
    confianza, `precio_no_verificado=True` y `precio_alibaba_50u=None` —
    nunca se adivina un precio.
    """
    resultado = {
        "url_alibaba": url,
        "proveedor": None,
        "variante": None,
        "moq": None,
        "precio_alibaba_50u": None,
        "moneda": None,
        "precio_no_verificado": True,
        "requiere_contacto_proveedor": False,
        "dimensiones": None,
        "peso_gramos": None,
    }

    data = extraer_detail_data(html)
    if data is None:
        return resultado

    producto = data.get("globalData", {}).get("product", {})
    custom_price = producto.get("customPrice") or {}
    rango_precio = (producto.get("price") or {}).get("productRangePrices") or {}

    moq = producto.get("moq") or producto.get("customsMoq")
    resultado["moq"] = f"{moq} {custom_price.get('unitEven', 'pieces')}" if moq else None

    precio_bajo = rango_precio.get("dollarPriceRangeLow")
    precio_alto = rango_precio.get("dollarPriceRangeHigh")

    if precio_bajo is not None and precio_alto is not None and precio_bajo == precio_alto:
        # Precio único (sin escalones por cantidad): vale para cualquier
        # cantidad, incluida ~50 unidades.
        resultado["precio_alibaba_50u"] = precio_bajo
        resultado["moneda"] = "USD"
        resultado["precio_no_verificado"] = False
    # Si precio_bajo != precio_alto, el producto tiene escalones de precio
    # por cantidad y todavía no confirmamos contra HTML real cuál campo
    # indica el escalón exacto para ~50 unidades -- se deja
    # precio_no_verificado=True a propósito en vez de adivinar cuál tramo
    # corresponde.

    return resultado
