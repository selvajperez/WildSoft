from pathlib import Path

from parser import parsear_categorias, parsear_pagina_listado, parsear_precio

FIXTURE = (Path(__file__).parent / "fixtures" / "productlist_page19.html").read_text(encoding="utf-8")


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

    segundo = productos[1]
    assert segundo["precio_min"] == 237.41
    assert segundo["precio_max"] == 791.34
    assert segundo["categoria_id"] == 0
    assert segundo["categoria"] == "Sin agrupar"

    assert paginacion.pagina_actual == 19
    assert paginacion.productos_por_pagina == 16
    assert paginacion.total_productos == 443
    assert paginacion.total_paginas == 28
    assert paginacion.formato_url == "/productlist-{0}.html?filter=all&sortType=modified-desc"


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
