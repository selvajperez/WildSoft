"""
Parser del listado de resultados de búsqueda de Alibaba (Fase 2: buscar
comparables en Alibaba para un candidato con demanda confirmada en ML).

Confirmado con HTML real (ver `tests/fixtures/alibaba_busqueda_real.html`,
búsqueda "wireless earbuds", capturado con `capturador_busqueda_alibaba.py`).
Cada resultado vive dentro del contenedor `data-content="abox-ProductNormalList"`
como un `<div class="fy26-product-card-wrapper ...">` con `data-ctrdot="<id>"`
(el id del producto). Adentro, con clases "searchx-*" estables (no
hasheadas, a diferencia de otro widget de la misma página que sí usa
clases hasheadas tipo "_67cIk073" -- ese es un carrusel de sugerencias
aparte, no el listado principal):

  - Título: `.searchx-product-e-title` (texto visible).
  - URL del producto: `a.searchx-product-link-wrapper[href]` -- mismo
    formato `.../product-detail/<slug>_<id>.html` que ya sabe leer
    `parser_ficha_alibaba.py`. El href es protocol-relative ("//www...")
    y se normaliza a "https://...".
  - Precio: `.searchx-product-price-price-main` -- texto crudo tal cual
    ("$2.10-2.40" o "$2.10"), NUNCA un número parseado: regla del
    proyecto ya aplicada en Mercado Libre y en `parser_ficha_alibaba.py`
    -- el precio del listado no es confiable, hay que verificarlo
    abriendo la ficha individual.
  - MOQ: `.searchx-moq` -- texto crudo ("Min. order: 10,000 pieces"),
    tampoco se parsea a un número acá (las unidades varían: "pieces",
    "set", "units").
  - Proveedor: `.searchx-product-e-company` (texto) +
    `.verified-supplier-icon__wrapper` (booleano, si el proveedor está
    verificado por Alibaba).
  - Publicidad: el bloque `data-aplus-auto-offer` de cada card trae
    `is_ad=true`/`is_ad=false` en texto plano (no percent-encoded, se
    confirmó con HTML real) -- útil para no priorizar resultados pagos
    como si fueran orgánicos.

Todavía NO incluye lógica de matching/ranking contra el nombre de un
candidato de ML, ni verificación de precio -- eso es la etapa siguiente,
sin empezar. Esto es solo la extracción del listado, igual que
`parser_busqueda_ml.py` para Mercado Libre.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

_SELECTOR_TARJETA = "div.fy26-product-card-wrapper"
_RE_ES_PUBLICIDAD = re.compile(r"is_ad=(true|false)")


def _normalizar_url(href: str) -> str:
    """Protocol-relative ("//www.alibaba.com/...") -> URL absoluta con https."""
    if href.startswith("//"):
        return f"https:{href}"
    return href


def parsear_resultado(tarjeta) -> dict | None:
    """
    Parsea una única tarjeta de resultado. Devuelve None si falta lo
    mínimo indispensable (id + link al producto) -- pasa con contenido
    que no es un resultado de producto real.
    """
    id_alibaba = tarjeta.get("data-ctrdot")
    enlace = tarjeta.select_one("a.searchx-product-link-wrapper")
    if not id_alibaba or enlace is None or not enlace.get("href"):
        return None

    nombre_el = tarjeta.select_one(".searchx-product-e-title")
    precio_el = tarjeta.select_one(".searchx-product-price-price-main")
    moq_el = tarjeta.select_one(".searchx-moq")
    proveedor_el = tarjeta.select_one(".searchx-product-e-company")
    verificado = tarjeta.select_one(".verified-supplier-icon__wrapper") is not None

    match_publicidad = _RE_ES_PUBLICIDAD.search(str(tarjeta))
    es_publicidad = match_publicidad.group(1) == "true" if match_publicidad else None

    return {
        "id_alibaba": id_alibaba,
        "url_alibaba": _normalizar_url(enlace["href"]),
        "nombre": nombre_el.get_text(strip=True) if nombre_el else None,
        "precio_texto": precio_el.get_text(strip=True) if precio_el else None,
        "moq_texto": moq_el.get_text(strip=True) if moq_el else None,
        "proveedor": proveedor_el.get_text(strip=True) if proveedor_el else None,
        "proveedor_verificado": verificado,
        "es_publicidad": es_publicidad,
    }


def parsear_listado_busqueda(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    resultados = []
    for posicion, tarjeta in enumerate(soup.select(_SELECTOR_TARJETA), start=1):
        item = parsear_resultado(tarjeta)
        if item is not None:
            item["posicion"] = posicion
            resultados.append(item)
    return resultados
