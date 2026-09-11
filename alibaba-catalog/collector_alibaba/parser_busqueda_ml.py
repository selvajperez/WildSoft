"""
Parser del listado de resultados de búsqueda de Mercado Libre.

Objetivo (regla del proyecto): extraer la mayor señal de demanda posible
SIN abrir ninguna ficha individual, para prefiltrar antes de gastar
tiempo/riesgo abriendo fichas una por una.

Confirmado con HTML real (ver tests/fixtures/ml_busqueda_real.html,
búsqueda "cepillo de limpieza", 60 resultados reales). Cada resultado es
un `<li class="ui-search-layout__item">` con una tarjeta "poly-card"
(framework propio de ML). Por tarjeta, cuando están presentes:

  - Título + item_id + posición: en el `href` de
    `a.poly-component__title` (ej. "...&item_id%3AMLA123...&position=4...").
    Cuando el `href` es un link de tracking de clicks (no la URL final
    del producto), se construye una URL navegable a partir del
    `searchVariation` que el propio href ya trae en su fragmento
    (`https://www.mercadolibre.com.ar/p/<searchVariation>?pdp_filters=item_id:<item_id>`,
    o `/up/` si el ID tiene 4 letras de prefijo) -- confirmado con
    navegación real controlada, ver `experimento_url_producto_reconstruida.py`
    y el comentario junto a `_extraer_item_id_y_url` más abajo.
  - Precio: `span.andes-money-amount` dentro de `.poly-price__current`,
    vía su `aria-label` ("111420 pesos argentinos") -- más confiable que
    parsear el texto visible con separadores de miles.
  - Rating promedio (SIN cantidad de opiniones): `.poly-component__review-compacted`.
  - Badge "MÁS VENDIDO": booleano, no es un conteo.
  - Texto libre "+N vendidos" / "+N mil vendidos": buscado por si
    aparece, pero **en la búsqueda real de referencia no apareció en
    ningún resultado del grid principal** (sí apareció, en otra captura,
    en un carrusel de recomendados dentro de una ficha individual — un
    contexto distinto). No asumir que siempre está.

Regla del proyecto: nunca tratar "+500" como exactamente 500.
`unidades_vendidas` es una aproximación (ver `_normalizar_conteo_vendidos`);
`evidencia_demanda` conserva siempre el texto crudo tal cual se vio.

IMPORTANTE (ajuste de semántica): el listado es solo un prefiltro y un
orden de prioridad, NUNCA una validación definitiva de demanda.
`clasificar_prioridad()` separa los resultados en:
  - Prioridad 'A' (señal fuerte): badge "MÁS VENDIDO" o conteo explícito
    de vendidos.
  - Prioridad 'B' (señal débil): rating visible u otra señal parcial --
    ya NO cuenta como demanda confirmada por sí sola.
  - Sin señal (None): se descarta sin abrir la ficha.
La demanda recién se confirma al abrir la ficha individual (ver
`orquestador_demanda_ml.py`), contra un umbral configurable.
"""

from __future__ import annotations

import re
import urllib.parse

from bs4 import BeautifulSoup

MAS_VENDIDO_TEXTO = "MÁS VENDIDO"

# Clase del <li> de cada resultado -- también usado como marcador para
# esperar a que el listado termine de renderizar (ver
# `navegador_ml.abrir_pagina_ml(..., esperar_marcador=MARCADOR_ITEM_LISTADO)`):
# el framework "search-nordic" (React) puede tardar en inyectar el
# listado real después de `domcontentloaded` -- confirmado con HTML real
# (una búsqueda devolvió 1.1MB con título normal pero 0 apariciones de
# este marcador, solo la pantalla de carga).
MARCADOR_ITEM_LISTADO = "ui-search-layout__item"

# Hay TRES formas de href en la misma búsqueda real, según el tipo de
# resultado:
#   - Orgánico "catálogo" (".../p/MLA21816514#..."): link directo y
#     limpio. Se usa tal cual (recortando el fragmento de tracking
#     después del #).
#   - Orgánico "publicación individual" (".../up/MLAU3256312831#..."):
#     mismo caso, pero con el segmento "/up/" (no "/p/") y un prefijo de
#     4 letras ("MLAU", no "MLA") -- son publicaciones sin página de
#     catálogo unificada. Una primera versión de este regex solo
#     contemplaba "/p/" + 3 letras y perdía TODOS estos resultados
#     silenciosamente -- confirmado corriendo contra el HTML real.
#   - Con wrapper de tracking de clicks (resultados con
#     is_advertising=true en el propio href): no hay URL directa en el
#     href, solo un item_id en el query string
#     ("...pdp_filters=item_id%3AMLA123..."). Este href también trae, en
#     su propio fragmento, "searchVariation=<ID>" -- el mismo tipo de ID
#     de catálogo/publicación que usan las dos formas orgánicas de
#     arriba. Confirmado con navegación real controlada (ver
#     `experimento_url_producto_reconstruida.py`, 5/5 casos reales): la
#     URL construida como `/p/<searchVariation>?pdp_filters=item_id:<item_id>`
#     (sin slug) resuelve igual que el permalink completo cuando el ID
#     tiene 3 letras de prefijo, y `/up/<searchVariation>?...` cuando
#     tiene 4 -- mismo criterio de arriba. Una primera versión (antes de
#     ese experimento) reconstruía `articulo.mercadolibre.com.ar/<item_id>`
#     sin guion, que dio 404 en el 100% de una medición real (31/31) --
#     nunca funcionó, no era "intermitente". Si el href no trae un
#     searchVariation con ese formato (ej. un ID puramente numérico, caso
#     todavía no confirmado), el resultado se descarta en vez de adivinar
#     un formato sin evidencia.
# Entre las dos formas orgánicas, la primera versión de este parser (que
# solo buscaba el patrón de tracking) perdía el 80% de los resultados
# reales; sumando "/up/" todavía faltaba un tercio de los restantes.
_RE_ITEM_ID_DIRECTO = re.compile(r"/u?p/([A-Za-z]+\d+)")
_RE_ITEM_ID_TRACKING = re.compile(r"item_id:([A-Za-z]+\d+)")
_RE_SEARCH_VARIATION = re.compile(r"searchVariation=([A-Za-z0-9]+)")
_RE_ID_CON_PREFIJO_VALIDO = re.compile(r"^[A-Za-z]{3,4}\d+$")
_RE_POSICION = re.compile(r"[?&]position=(\d+)")
_RE_PRECIO_ARIA = re.compile(r"([\d]+)\s*pesos argentinos", re.I)
_RE_VENDIDOS = re.compile(r"\+\s*([\d.,]+)\s*(mil)?\s*vendidos", re.I)


def _normalizar_conteo_vendidos(texto_crudo: str) -> int | None:
    """
    '+500' -> 500; '+1.000' -> 1000; '+5 mil' -> 5000. Es una
    aproximación -- el propio texto de ML ya es aproximado ("+500" no
    promete exactamente 500), nunca se trata como un conteo exacto real.
    """
    match = _RE_VENDIDOS.search(texto_crudo)
    if not match:
        return None
    numero_str, mil = match.groups()
    numero = float(numero_str.replace(".", "").replace(",", "."))
    if mil:
        numero *= 1000
    return int(numero)


def segmento_ruta_producto_id(product_id: str) -> str:
    """
    "p" para IDs con prefijo de 3 letras (ej. "MLA"+dígitos, página de
    catálogo); "up" para IDs con prefijo de 4 letras (ej. "MLAU"+dígitos,
    publicación individual sin catálogo compartido). Mismo criterio ya
    usado para distinguir "/p/" de "/up/" en los links directos de arriba,
    confirmado también para URLs reconstruidas con navegación real
    controlada (ver `experimento_url_producto_reconstruida.py`).
    """
    match = re.match(r"[A-Za-z]+", product_id)
    prefijo = match.group(0) if match else ""
    return "up" if len(prefijo) == 4 else "p"


def _url_desde_search_variation(item_id: str, search_variation: str) -> str | None:
    """
    None si `search_variation` no tiene el formato de ID ya confirmado
    (letras+dígitos) -- ej. el caso, visto en HTML real pero todavía sin
    probar, de un ID puramente numérico. No se adivina un formato sin
    evidencia: quien llama descarta el resultado en ese caso.
    """
    if not _RE_ID_CON_PREFIJO_VALIDO.match(search_variation):
        return None
    segmento = segmento_ruta_producto_id(search_variation)
    return f"https://www.mercadolibre.com.ar/{segmento}/{search_variation}?pdp_filters=item_id:{item_id}"


def _extraer_item_id_y_url(href_crudo: str) -> tuple[str, str, str] | None:
    """
    Devuelve (item_id, url_ml, origen_url) probando primero el link
    directo, después el de tracking. `origen_url` es "directo" (href real
    del propio listado, usado tal cual) o "tracking" (URL construida a
    partir del `searchVariation` que trae el propio href de tracking --
    ver el comentario sobre las tres formas de href, arriba). Si el link
    de tracking no trae un `searchVariation` utilizable, el resultado se
    descarta (`None`) en vez de reconstruir una URL sin evidencia de que
    funcione.
    """
    href = urllib.parse.unquote(href_crudo)

    match_directo = _RE_ITEM_ID_DIRECTO.search(href)
    if match_directo:
        item_id = match_directo.group(1).upper()
        return item_id, href.split("#")[0], "directo"

    match_tracking = _RE_ITEM_ID_TRACKING.search(href)
    if match_tracking:
        item_id = match_tracking.group(1).upper()
        match_search_variation = _RE_SEARCH_VARIATION.search(href)
        if match_search_variation is None:
            return None
        url = _url_desde_search_variation(item_id, match_search_variation.group(1).upper())
        if url is None:
            return None
        return item_id, url, "tracking"

    return None


def parsear_resultado(li) -> dict | None:
    """
    Parsea un único `<li class="ui-search-layout__item">`. Devuelve None
    si falta lo mínimo indispensable (título + item_id) -- pasa con
    contenido que no es un resultado de producto real (banners, etc.).
    """
    enlace = li.select_one("a.poly-component__title")
    if enlace is None or not enlace.get("href"):
        return None

    extraido = _extraer_item_id_y_url(enlace["href"])
    if extraido is None:
        return None
    item_id, url_ml, origen_url = extraido

    match_pos = _RE_POSICION.search(urllib.parse.unquote(enlace["href"]))
    posicion = int(match_pos.group(1)) if match_pos else None

    texto_tarjeta = li.get_text(" ", strip=True)

    precio = None
    precio_el = li.select_one(".poly-price__current .andes-money-amount")
    if precio_el and precio_el.get("aria-label"):
        match_precio = _RE_PRECIO_ARIA.search(precio_el["aria-label"])
        if match_precio:
            precio = float(match_precio.group(1))

    rating_visible = None
    rating_el = li.select_one(".poly-component__review-compacted .polylabel-label")
    if rating_el:
        try:
            rating_visible = float(rating_el.get_text(strip=True))
        except ValueError:
            rating_visible = None

    mas_vendido = MAS_VENDIDO_TEXTO in texto_tarjeta
    match_vendidos = _RE_VENDIDOS.search(texto_tarjeta)

    if match_vendidos:
        evidencia_demanda = match_vendidos.group(0)
    elif mas_vendido:
        evidencia_demanda = MAS_VENDIDO_TEXTO
    elif rating_visible is not None:
        evidencia_demanda = f"rating {rating_visible} (sin cantidad de opiniones visible)"
    else:
        evidencia_demanda = None

    return {
        "id_ml": item_id,
        "url_ml": url_ml,
        "origen_url": origen_url,
        "nombre": enlace.get_text(strip=True),
        "precio_ml": precio,
        "moneda_ml": "ARS" if precio is not None else None,
        "posicion": posicion,
        "rating_visible": rating_visible,
        "mas_vendido": mas_vendido,
        "evidencia_demanda": evidencia_demanda,
        "unidades_vendidas": _normalizar_conteo_vendidos(texto_tarjeta),
    }


def parsear_listado_busqueda(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    resultados = []
    for li in soup.select(f"li.{MARCADOR_ITEM_LISTADO}"):
        item = parsear_resultado(li)
        if item is not None:
            resultados.append(item)
    return resultados


def clasificar_prioridad(item: dict) -> str | None:
    """
    Clasifica un resultado del listado en una prioridad de revisión, NO en
    una demanda confirmada -- el listado es solo un prefiltro/orden para
    decidir qué fichas abrir primero. La demanda real se confirma recién
    al abrir la ficha individual (regla del proyecto).

    - 'A' (señal fuerte): badge "MÁS VENDIDO" o conteo explícito de
      vendidos. Son señales que el propio ML expone como indicador de
      volumen real.
    - 'B' (señal débil): rating promedio visible, sin cantidad de
      opiniones. Un producto puede tener rating alto con muy pocas
      compras -- no es evidencia de volumen, solo de que hay *alguna*
      actividad.
    - None: ninguna señal visible. Se descarta sin abrir la ficha.
    """
    if item["unidades_vendidas"] is not None or item["mas_vendido"]:
        return "A"
    if item["rating_visible"] is not None:
        return "B"
    return None


def resultado_a_candidato(item: dict) -> dict:
    """
    Traduce el dict de `parsear_resultado` a los campos de `candidatos_ml`
    (ver database/db.py), aplicando la clasificación de prioridad: sin
    ninguna señal visible en el listado, el candidato ya entra descartado
    -- así el pipeline nunca gasta una visita a su ficha individual (regla
    del proyecto: "evitar abrir fichas de productos con demanda
    insuficiente"). Con prioridad A o B, queda "nuevo" a la espera de que
    el orquestador de la siguiente etapa decida abrir su ficha (ver
    `orquestador_demanda_ml.py`). No hace ningún acceso a la base -- eso
    es responsabilidad de quien llama (`db.upsert_candidato_ml`).
    """
    prioridad = clasificar_prioridad(item)
    candidato = {
        "id_ml": item["id_ml"],
        "url_ml": item["url_ml"],
        "nombre": item["nombre"],
        "evidencia_demanda": item["evidencia_demanda"],
        "unidades_vendidas": item["unidades_vendidas"],
        "precio_ml": item["precio_ml"],
        "moneda_ml": item["moneda_ml"],
        "prioridad_listado": prioridad,
    }
    if prioridad is not None:
        candidato["estado"] = "nuevo"
        candidato["motivo_descarte"] = None
    else:
        candidato["estado"] = "descartado_demanda_insuficiente"
        candidato["motivo_descarte"] = (
            "Sin señal de demanda visible en el listado "
            "(ni conteo de vendidos, ni badge de más vendido, ni rating)."
        )
    return candidato
