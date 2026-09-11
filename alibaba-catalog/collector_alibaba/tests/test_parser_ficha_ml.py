from pathlib import Path

from parser_ficha_ml import (
    es_ficha_no_encontrada,
    extraer_producto_ld_json,
    extraer_stock_y_ventas,
    parsear_ficha_ml,
)

FICHA_REAL = (Path(__file__).parent / "fixtures" / "ml_ficha_real.html").read_text(encoding="utf-8")
FICHA_NO_ENCONTRADA_REAL = (
    Path(__file__).parent / "fixtures" / "ml_ficha_no_encontrada_real.html"
).read_text(encoding="utf-8")


def test_extraer_producto_ld_json_de_ficha_real():
    producto = extraer_producto_ld_json(FICHA_REAL)
    assert producto is not None
    assert producto["name"] == "Cepillo Eléctrico Recargable Limpieza Mopa 7 en 1 Multiuso"
    assert producto["offers"]["price"] == 68780
    assert producto["offers"]["priceCurrency"] == "ARS"
    assert producto["aggregateRating"]["reviewCount"] == 273


def test_extraer_producto_ld_json_devuelve_none_si_no_hay_product():
    assert extraer_producto_ld_json("<html><body>nada</body></html>") is None


def test_extraer_stock_y_ventas_de_ficha_real():
    stock, vendidas = extraer_stock_y_ventas(FICHA_REAL)
    assert stock == 5
    assert vendidas == 1000


def test_extraer_stock_y_ventas_devuelve_none_si_no_matchea():
    assert extraer_stock_y_ventas("<html><body>nada</body></html>") == (None, None)


def test_parsear_ficha_ml_completo():
    resultado = parsear_ficha_ml(FICHA_REAL, url="https://www.mercadolibre.com.ar/.../MLA2023730583")

    assert resultado["nombre"] == "Cepillo Eléctrico Recargable Limpieza Mopa 7 en 1 Multiuso"
    assert resultado["precio_ml"] == 68780
    assert resultado["moneda_ml"] == "ARS"
    assert resultado["unidades_vendidas"] == 1000
    assert resultado["stock_visible"] == 5
    assert resultado["evidencia_demanda"] == "+1000 vendidos"
    assert resultado["url_ml"] == "https://www.mercadolibre.com.ar/.../MLA2023730583"
    assert resultado["cantidad_opiniones"] == 273
    assert resultado["rating"] == 4.2


def test_parsear_ficha_ml_sin_ventas_usa_opiniones_como_evidencia():
    html = """
    <script type="application/ld+json">
    {"@type": "Product", "name": "Producto sin ventas visibles",
     "offers": {"price": 1000, "priceCurrency": "ARS"},
     "aggregateRating": {"reviewCount": 42, "ratingValue": 4.5}}
    </script>
    """
    resultado = parsear_ficha_ml(html)

    assert resultado["unidades_vendidas"] is None
    assert resultado["evidencia_demanda"] == "42 opiniones, rating 4.5"
    assert resultado["cantidad_opiniones"] == 42
    assert resultado["rating"] == 4.5


def test_parsear_ficha_ml_sin_datos_devuelve_todo_none():
    resultado = parsear_ficha_ml("<html><body>página inesperada</body></html>")

    assert resultado["nombre"] is None
    assert resultado["precio_ml"] is None
    assert resultado["unidades_vendidas"] is None
    assert resultado["evidencia_demanda"] is None
    assert resultado["pagina_no_encontrada"] is False


# --- 404 real de Mercado Libre (hallazgo de la corrida real del 2026-09-10) --
#
# 5 de 14 fichas abiertas en una búsqueda real resultaron ser este 404 --
# no un producto sin datos, sino que la URL reconstruida a partir del
# item_id de un link de tracking del listado no era válida para esos
# items. Confirmado con HTML real (ver docstring de parser_ficha_ml.py).

def test_es_ficha_no_encontrada_detecta_el_404_real():
    assert es_ficha_no_encontrada(FICHA_NO_ENCONTRADA_REAL) is True


def test_es_ficha_no_encontrada_es_false_para_una_ficha_real_normal():
    assert es_ficha_no_encontrada(FICHA_REAL) is False


def test_parsear_ficha_ml_marca_pagina_no_encontrada_en_el_404_real():
    resultado = parsear_ficha_ml(FICHA_NO_ENCONTRADA_REAL, url="https://articulo.mercadolibre.com.ar/MLA1758275889")

    assert resultado["pagina_no_encontrada"] is True
    # sigue sin nada útil, como cualquier página sin datos -- lo que la distingue es el flag
    assert resultado["precio_ml"] is None
    assert resultado["unidades_vendidas"] is None
