"""
Orquesta la recolección completa del catálogo: recorre la paginación real
del listado, parsea cada página y guarda los productos en SQLite.

Uso:
    python collector.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "database"))

from parser import parsear_categorias, parsear_pagina_listado  # noqa: E402
from scraper import PaginaBloqueadaError, esperar_entre_requests, obtener_pagina, robots_permite  # noqa: E402
import db  # noqa: E402

URL_BASE = "https://dcsjry888.m.en.alibaba.com"
URL_PRIMERA_PAGINA = f"{URL_BASE}/productlist-1.html?filter=all&sortType=modified-desc"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "collector.log")],
)
logger = logging.getLogger("collector_alibaba")


def _url_pagina(formato_url: str, pagina: int) -> str:
    """`formato_url` viene del propio sitio, ej: '/productlist-{0}.html?filter=all&sortType=modified-desc'."""
    return URL_BASE + formato_url.format(pagina)


def recolectar_catalogo(url_inicial: str = URL_PRIMERA_PAGINA, max_paginas: int | None = None) -> int:
    """
    Recorre todo el listado y persiste los productos. Devuelve la cantidad
    total de productos guardados (tras deduplicar por URL).
    """
    if not robots_permite(url_inicial):
        logger.error("robots.txt no permite scrapear %s. Abortando.", url_inicial)
        raise SystemExit(1)

    sesion = requests.Session()
    conexion = db.conectar()

    logger.info("Descargando página 1 para conocer categorías y paginación real...")
    try:
        html_pagina_1 = obtener_pagina(url_inicial, sesion)
    except PaginaBloqueadaError as exc:
        logger.error("Bloqueado en la primera página (%s): %s", url_inicial, exc)
        raise

    categorias = parsear_categorias(html_pagina_1)
    productos, paginacion = parsear_pagina_listado(html_pagina_1, categorias)

    if paginacion is None:
        logger.error("No se pudo leer la paginación en %s; el sitio puede haber cambiado de estructura.", url_inicial)
        raise SystemExit(1)

    total_paginas = paginacion.total_paginas
    if max_paginas is not None:
        total_paginas = min(total_paginas, max_paginas)

    logger.info(
        "Catálogo: %d productos declarados, %d por página, %d páginas a recorrer.",
        paginacion.total_productos, paginacion.productos_por_pagina, total_paginas,
    )

    db.upsert_productos(conexion, productos)
    logger.info("Página 1/%d: %d productos.", total_paginas, len(productos))

    for pagina in range(2, total_paginas + 1):
        esperar_entre_requests()
        url = _url_pagina(paginacion.formato_url, pagina)
        try:
            html = obtener_pagina(url, sesion)
        except PaginaBloqueadaError as exc:
            logger.error("Bloqueado en la página %d (%s): %s. Corte del collector.", pagina, url, exc)
            break

        productos_pagina, _ = parsear_pagina_listado(html, categorias)
        if not productos_pagina:
            logger.info("Página %d sin productos nuevos; se asume fin del catálogo.", pagina)
            break

        db.upsert_productos(conexion, productos_pagina)
        logger.info("Página %d/%d: %d productos.", pagina, total_paginas, len(productos_pagina))

    total_guardado = db.contar_productos(conexion)
    logger.info("Total de productos únicos en la base: %d", total_guardado)
    return total_guardado


if __name__ == "__main__":
    recolectar_catalogo()
