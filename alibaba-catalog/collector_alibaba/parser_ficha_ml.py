"""
Parser de la ficha individual de producto de Mercado Libre.

Confirmado con HTML real (ver `tests/fixtures/ml_ficha_real.html`,
capturado por `capturador_exploratorio.py` — item MLA2023730583).

Dos fuentes distintas en la misma página:

1. Bloques `<script type="application/ld+json">` con marcado schema.org
   `Product` — estándar, estable, pensado para SEO. De acá sale nombre,
   precio, moneda, disponibilidad, y `aggregateRating` (rating promedio y
   cantidad de opiniones/reviews). Es la fuente principal: no depende de
   la estructura interna de ML, es un estándar público.
2. El contexto interno de renderizado (`__NORDIC_RENDERING_CTX__`, el
   framework frontend de Mercado Libre) trae `sold_quantity` (unidades
   vendidas, la señal de demanda más importante según las reglas del
   proyecto) y `quantity` (stock visible actual, para el historial de
   rotación). Estos dos campos NO están en el JSON-LD estándar, así que
   hace falta esta segunda fuente, más frágil por ser interna.
"""

from __future__ import annotations

import json
import re


def extraer_producto_ld_json(html: str) -> dict | None:
    """Busca el primer bloque JSON-LD con @type == "Product"."""
    for bloque in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(bloque)
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "Product":
            return data
    return None


_RE_QUANTITY_SOLD = re.compile(r'"quantity":(\d+),"sold_quantity":(\d+)')


def extraer_stock_y_ventas(html: str) -> tuple[int | None, int | None]:
    """
    Devuelve (stock_visible, unidades_vendidas) a partir del contexto
    interno de renderizado. No hay garantía de que este patrón puntual
    sobreviva a un cambio de versión del frontend de ML (es más frágil que
    el JSON-LD) -- si deja de matchear, devuelve (None, None) en vez de
    romper el resto del parseo.
    """
    match = _RE_QUANTITY_SOLD.search(html)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def parsear_ficha_ml(html: str, url: str | None = None) -> dict:
    """
    Devuelve un dict con la forma de `candidatos_ml` (ver database/db.py)
    más `stock_visible` (no es columna de `candidatos_ml`, se usa para
    armar la primera fila de `historial_ml` al momento de crear el
    candidato).
    """
    resultado = {
        "url_ml": url,
        "nombre": None,
        "evidencia_demanda": None,
        "unidades_vendidas": None,
        "precio_ml": None,
        "moneda_ml": None,
        "stock_visible": None,
    }

    producto = extraer_producto_ld_json(html)
    if producto is not None:
        resultado["nombre"] = producto.get("name")
        oferta = producto.get("offers") or {}
        resultado["precio_ml"] = oferta.get("price")
        resultado["moneda_ml"] = oferta.get("priceCurrency")

        rating = producto.get("aggregateRating") or {}
        if rating:
            resultado["evidencia_demanda"] = (
                f"{rating.get('reviewCount', 0)} opiniones, rating {rating.get('ratingValue')}"
            )

    stock, vendidas = extraer_stock_y_ventas(html)
    resultado["stock_visible"] = stock
    if vendidas is not None:
        resultado["unidades_vendidas"] = vendidas
        # La cantidad vendida es la señal de demanda más fuerte (regla del
        # proyecto): si está disponible, reemplaza a la evidencia basada
        # solo en opiniones/rating.
        resultado["evidencia_demanda"] = f"+{vendidas} vendidos"

    return resultado
