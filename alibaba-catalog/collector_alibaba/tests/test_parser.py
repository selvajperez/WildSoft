from pathlib import Path

from parser import parsear_categorias, parsear_pagina_listado, parsear_precio

FIXTURE = (Path(__file__).parent / "fixtures" / "productlist_page19.html").read_text(encoding="utf-8")
FIXTURE_MIXTO = (Path(__file__).parent / "fixtures" / "productlist_page_mixto.html").read_text(encoding="utf-8")


def test_parsear_categorias_aplana_el_arbol():
    categorias = parsear_categorias(FIXTURE)

    assert categorias[954418042] == "Cepillo de limpieza"
    assert categorias[0] == "Sin agrupar"
    # "Suministros de limpieza" tiene hijos anidados; deben quedar aplanados también.
    assert categorias[951797212] == "Fregona"


def test_parsear_pagina_listado_extrae_productos_y_paginacion():
    categorias = parsear_categorias(FIXTURE)
    productos, paginacion = parsear_pagina_listado(FIXTURE, categorias)

    assert len(productos) == 2

    primero = productos[0]
    assert primero["nombre"].startswith("Lavable sin BPA")
    assert primero["url"].endswith("Washable-BPA-Free-Clean-Dish-Washing_1601487795601.html")
    assert primero["moq"] == "10 unidades"
    assert primero["categoria"] == "Cepillo de limpieza"
    assert primero["peso_gramos"] is None
    assert primero["precio_min"] == primero["precio_max"] == 2374.02
    assert primero["moneda"] == "ARS"
    assert primero["compra_directa"] is True
    assert primero["envio_calculable"] is True

    segundo = productos[1]
    assert segundo["precio_min"] == 237.41
    assert segundo["precio_max"] == 791.34
    assert segundo["categoria_id"] == 0
    assert segundo["categoria"] == "Sin agrupar"
    assert segundo["compra_directa"] is True
    assert segundo["envio_calculable"] is True

    assert paginacion.pagina_actual == 19
    assert paginacion.productos_por_pagina == 16
    assert paginacion.total_productos == 443
    assert paginacion.total_paginas == 28
    assert paginacion.formato_url == "/productlist-{0}.html?filter=all&sortType=modified-desc"


def test_parsear_pagina_listado_distingue_compra_directa_de_cotizar():
    """
    Regresión con 2 productos reales "a Cotizar" (RFQ, sin compra directa):
    Alibaba product ID 1601726374426 (Faucet Anti-Splash) y 1601425511881
    (Glass Silicone Scraper), confirmados por captura directa del HTML real
    del listado. En ambos, tradeProduct/rtsProduct/aliFreight vienen en
    `false` juntos (y `localFreightStr` directamente ausente del JSON),
    a diferencia de los 2 productos de compra directa del fixture original.
    """
    categorias = parsear_categorias(FIXTURE_MIXTO)
    productos, _ = parsear_pagina_listado(FIXTURE_MIXTO, categorias)
    por_id = {p["producto_id_alibaba"]: p for p in productos}

    assert len(productos) == 4

    # Los 2 de compra directa (ya cubiertos en el otro test, pero confirmamos acá también).
    assert por_id[1601487795601]["compra_directa"] is True
    assert por_id[1601487795601]["envio_calculable"] is True
    assert por_id[1601463572898]["compra_directa"] is True
    assert por_id[1601463572898]["envio_calculable"] is True

    # Los 2 "a Cotizar": sin compra directa, sin envío calculable.
    faucet = por_id[1601726374426]
    assert faucet["compra_directa"] is False
    assert faucet["envio_calculable"] is False
    # `url` real venía sin esquema ("//www.alibaba.com/..."); debe normalizarse.
    assert faucet["url"] == "https://www.alibaba.com/product-detail/Faucet-Anti-Splash-Device-Splash-Proof_1601726374426.html"

    scraper = por_id[1601425511881]
    assert scraper["compra_directa"] is False
    assert scraper["envio_calculable"] is False
    assert scraper["url"].startswith("https://www.alibaba.com/")


def test_parsear_precio_sin_rango():
    minimo, maximo, moneda = parsear_precio("ARS 2.374,02", "1.5")
    assert (minimo, maximo, moneda) == (2374.02, 2374.02, "ARS")


def test_parsear_precio_con_rango():
    minimo, maximo, moneda = parsear_precio("ARS 237,41- 791,34", "0.15")
    assert (minimo, maximo, moneda) == (237.41, 791.34, "ARS")


def test_parsear_precio_cae_a_usd_si_no_hay_texto_localizado():
    minimo, maximo, moneda = parsear_precio(None, "8.0")
    assert (minimo, maximo, moneda) == (8.0, 8.0, "USD")


def test_parsear_pagina_listado_sin_modulo_devuelve_vacio():
    productos, paginacion = parsear_pagina_listado("<html><body>nada</body></html>")
    assert productos == []
    assert paginacion is None
