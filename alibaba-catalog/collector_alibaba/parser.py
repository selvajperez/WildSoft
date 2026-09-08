"""
Parser para las páginas de listado del minisite de Alibaba (m.en.alibaba.com).

El HTML no requiere un navegador: cada módulo de la página (categorías,
lista de productos, paginación) viaja completo como JSON en el atributo
`module-data` de su <div>, codificado con percent-encoding (URL encoding).
Alcanza con requests + BeautifulSoup para extraerlo.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass

from bs4 import BeautifulSoup

MODULE_PRODUCT_LIST = "icbu-pc-productListPc"
MODULE_PRODUCT_GROUPS = "icbu-pc-productGroups"


@dataclass
class Paginacion:
    pagina_actual: int
    productos_por_pagina: int
    total_productos: int
    formato_url: str  # ej: "/productlist-{0}.html?filter=all&sortType=modified-desc"

    @property
    def total_paginas(self) -> int:
        if self.productos_por_pagina <= 0:
            return self.pagina_actual
        return max(1, -(-self.total_productos // self.productos_por_pagina))  # ceil


def _extraer_module_data(soup: BeautifulSoup, module_name: str) -> dict | None:
    """Busca el <div module-name="..."> y decodifica su atributo module-data a dict."""
    div = soup.find(attrs={"module-name": module_name})
    if div is None:
        return None
    crudo = div.get("module-data")
    if not crudo:
        return None
    decodificado = urllib.parse.unquote(crudo)
    return json.loads(decodificado)


def parsear_categorias(html: str) -> dict[int, str]:
    """Devuelve {id_categoria: nombre}, aplanando el árbol de categorías (con hijos)."""
    soup = BeautifulSoup(html, "html.parser")
    data = _extraer_module_data(soup, MODULE_PRODUCT_GROUPS)
    if data is None:
        return {}

    grupos = data.get("mds", {}).get("moduleData", {}).get("data", {}).get("groups", [])
    categorias: dict[int, str] = {}

    def _recorrer(nodos):
        for nodo in nodos:
            categorias[nodo["id"]] = nodo["name"]
            _recorrer(nodo.get("children") or [])

    _recorrer(grupos)
    return categorias


_PRECIO_RE = re.compile(r"([A-Za-z]+)\s*([\d.,]+)(?:\s*-\s*([\d.,]+))?")


def _parsear_numero_latam(texto: str) -> float:
    """'2.374,02' -> 2374.02 (formato es-AR: punto de miles, coma decimal)."""
    return float(texto.replace(".", "").replace(",", "."))


def parsear_precio(fob_price_without_unit: str | None, price_from_usd: str | None) -> tuple[float | None, float | None, str | None]:
    """
    Devuelve (precio_min, precio_max, moneda) a partir del string localizado que
    trae el listado (ej. "ARS 2.374,02" o "ARS 237,41- 791,34").

    Si no se puede parsear el string localizado, se cae de vuelta al precio
    mínimo en USD (`priceFrom`), que Alibaba siempre entrega sin formatear.
    """
    if fob_price_without_unit:
        match = _PRECIO_RE.search(fob_price_without_unit)
        if match:
            moneda, minimo_str, maximo_str = match.groups()
            minimo = _parsear_numero_latam(minimo_str)
            maximo = _parsear_numero_latam(maximo_str) if maximo_str else minimo
            return minimo, maximo, moneda

    if price_from_usd:
        try:
            minimo = float(price_from_usd)
            return minimo, minimo, "USD"
        except ValueError:
            pass

    return None, None, None


def _normalizar_url(url: str | None) -> str | None:
    """Antepone el esquema a URLs relativas al protocolo (ej. '//foo' -> 'https://foo').

    Alibaba entrega `url` (el link a la ficha) sin esquema en productos "a
    Cotizar" (RFQ, sin compra directa) y con esquema completo en productos
    de compra directa; `imageUrls.original` es siempre relativo al protocolo.
    Mismo tratamiento para ambos casos.
    """
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    return url


def parsear_pagina_listado(html: str, categorias: dict[int, str] | None = None) -> tuple[list[dict], Paginacion | None]:
    """
    Extrae los productos y la info de paginación de una página de listado.

    Devuelve (productos, paginacion). `productos` es una lista de dicts ya
    normalizados, listos para insertar en la base (ver database/db.py).
    """
    soup = BeautifulSoup(html, "html.parser")
    data = _extraer_module_data(soup, MODULE_PRODUCT_LIST)
    if data is None:
        return [], None

    contenido = data.get("mds", {}).get("moduleData", {}).get("data", {})
    productos_crudos = contenido.get("productList", [])
    categorias = categorias or {}

    productos = []
    for item in productos_crudos:
        precio_min, precio_max, moneda = parsear_precio(item.get("fobPriceWithoutUnit"), item.get("priceFrom"))
        group_id = item.get("groupId")
        productos.append({
            "producto_id_alibaba": item.get("id"),
            "nombre": item.get("subject"),
            "url": _normalizar_url(item.get("url")),
            "precio_min": precio_min,
            "precio_max": precio_max,
            "moneda": moneda,
            "moq": item.get("moq"),
            "cantidad_vendida": item.get("prodSold180"),
            "imagen_principal": _normalizar_url((item.get("imageUrls") or {}).get("original")),
            "categoria_id": group_id,
            "categoria": categorias.get(group_id),
            "peso_gramos": None,  # solo disponible en la ficha de detalle (fase 2)
            # Productos "a Cotizar" (RFQ, sin compra directa) apagan juntos
            # tradeProduct, rtsProduct y aliFreight, y omiten localFreightStr
            # directamente del JSON — confirmado con HTML real (ver tests).
            "compra_directa": bool(item.get("tradeProduct")) and bool(item.get("rtsProduct")),
            "envio_calculable": bool(item.get("aliFreight")),
        })

    pnv = contenido.get("pageNavView")
    paginacion = None
    if pnv:
        paginacion = Paginacion(
            pagina_actual=pnv.get("currentPage", 0),
            productos_por_pagina=pnv.get("pageLines", 0),
            total_productos=pnv.get("totalLines", 0),
            formato_url=pnv.get("formatString", ""),
        )

    return productos, paginacion
