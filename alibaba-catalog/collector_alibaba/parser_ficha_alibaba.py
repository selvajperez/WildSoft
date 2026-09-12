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

**Match Mode (Fase 2)**: el mismo bloque `globalData.product` trae, además
de precio/MOQ, todo lo que hace falta para verificar un candidato contra
un producto de ML (confirmado con HTML real, producto 1601487795601):

  - `subject`: el título real de la ficha -- más específico/confiable que
    el título del listado (`nombre` en `parser_busqueda_alibaba.py`), que
    puede venir recortado o ser el de una variante distinta.
  - `productBasicProperties` / `productKeyIndustryProperties`: listas de
    `{attrName, attrNameId, attrValue, attrValueId}` -- especificaciones
    estructuradas del proveedor (material, tipo, peso, medidas, etc.).
    `productKeyIndustryProperties` en la práctica es un subconjunto de
    `productBasicProperties` (mismos pares en el fixture real) -- se
    mezclan en un único dict `atributos` (clave = `attrName` en
    minúscula) sin duplicar, así el módulo de matching no tiene que saber
    de la distinción entre las dos listas.
  - `mediaItems`: lista de fotos (y a veces un video, con
    `type != "image"` -- se descarta) en varias resoluciones
    (`imageUrl.big/normal/small/thumb`). Se guarda la resolución `big` de
    cada foto en `imagenes` -- son fotos reales del proveedor, mejor
    insumo para similitud visual que la única miniatura del listado.

**Filtro económico (Fase 3)**: `product.price.productLadderPrices` es el
campo real (confirmado por su propio nombre en las `globalDataKeys` de
varios módulos de la página, ej. `"product.price.productLadderPrices"`)
que Alibaba usa para precios escalonados por cantidad -- pero el producto
del fixture real (1601487795601) no tiene escalones (viene `None`/ausente
ahí), así que todavía no hay evidencia real de la forma exacta de cada
entrada (qué campo indica la cantidad de cada escalón). Por eso
`precio_ladder_crudo` guarda la lista tal cual viene, sin interpretarla
-- ver `filtro_economico.py`, que la deja como "no verificado" en vez de
adivinar a qué escalón corresponde el precio buscado.
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


def _extraer_atributos(producto: dict) -> dict[str, str]:
    """
    Mezcla `productBasicProperties` + `productKeyIndustryProperties` en un
    único dict `{attrName en minúscula: attrValue}`. `productBasicProperties`
    se aplica después para que gane si hay overlap (es la lista más
    completa en el fixture real -- `productKeyIndustryProperties` es un
    subconjunto ahí, pero no hay garantía de que sea así en todos los
    productos).
    """
    atributos: dict[str, str] = {}
    for lista in (producto.get("productKeyIndustryProperties"), producto.get("productBasicProperties")):
        for item in lista or []:
            nombre = item.get("attrName")
            valor = item.get("attrValue")
            if nombre and valor is not None:
                atributos[nombre.strip().lower()] = valor
    return atributos


def _extraer_imagenes(producto: dict) -> list[str]:
    """Fotos reales del producto (resolución `big`) -- descarta el video, si lo hay."""
    imagenes = []
    for item in producto.get("mediaItems") or []:
        if item.get("type") != "image":
            continue
        url_big = (item.get("imageUrl") or {}).get("big")
        if url_big:
            imagenes.append(url_big)
    return imagenes


def parsear_ficha_alibaba(html: str, url: str | None = None) -> dict:
    """
    Devuelve un dict con la forma de `alibaba_comparables` (ver
    database/db.py) más `nombre_ficha`, `atributos` e `imagenes` -- estos
    tres últimos no son columnas de `alibaba_comparables`, los usa
    `matcher.py` (Match Mode) para verificar un candidato, no el flujo de
    verificación de precio. Si no se puede extraer o interpretar el
    precio con confianza, `precio_no_verificado=True` y
    `precio_alibaba_50u=None` — nunca se adivina un precio.
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
        "nombre_ficha": None,
        "atributos": {},
        "imagenes": [],
        "moq_valor": None,
        "precio_ladder_crudo": None,
    }

    data = extraer_detail_data(html)
    if data is None:
        return resultado

    producto = data.get("globalData", {}).get("product", {})
    custom_price = producto.get("customPrice") or {}
    precio = producto.get("price") or {}
    rango_precio = precio.get("productRangePrices") or {}

    resultado["nombre_ficha"] = producto.get("subject")
    resultado["atributos"] = _extraer_atributos(producto)
    resultado["imagenes"] = _extraer_imagenes(producto)

    moq = producto.get("moq") or producto.get("customsMoq")
    resultado["moq"] = f"{moq} {custom_price.get('unitEven', 'pieces')}" if moq else None
    resultado["moq_valor"] = moq

    precio_bajo = rango_precio.get("dollarPriceRangeLow")
    precio_alto = rango_precio.get("dollarPriceRangeHigh")

    if precio_bajo is not None and precio_alto is not None and precio_bajo == precio_alto:
        # Precio único (sin escalones por cantidad): vale para cualquier
        # cantidad, incluida el MOQ.
        resultado["precio_alibaba_50u"] = precio_bajo
        resultado["moneda"] = "USD"
        resultado["precio_no_verificado"] = False
    # Si precio_bajo != precio_alto, el producto tiene escalones de precio
    # por cantidad y todavía no confirmamos contra HTML real cuál campo
    # indica el escalón exacto -- se deja precio_no_verificado=True a
    # propósito en vez de adivinar cuál tramo corresponde. Se guarda el
    # escalonado crudo (si vino) para no perder la evidencia.
    escalones = precio.get("productLadderPrices")
    if escalones:
        resultado["precio_ladder_crudo"] = escalones

    return resultado
