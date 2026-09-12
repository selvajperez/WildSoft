from pathlib import Path

from parser_ficha_alibaba import extraer_detail_data, parsear_ficha_alibaba

FICHA_REAL = (Path(__file__).parent / "fixtures" / "alibaba_ficha_real.html").read_text(encoding="utf-8")


def test_extraer_detail_data_de_ficha_real():
    data = extraer_detail_data(FICHA_REAL)
    assert data is not None
    assert data["globalData"]["product"]["productId"] == 1601487795601


def test_extraer_detail_data_devuelve_none_si_no_hay_bloque():
    assert extraer_detail_data("<html><body>otra cosa</body></html>") is None


def test_parsear_ficha_alibaba_precio_unico_verificado():
    """
    Producto real (Alibaba ID 1601487795601) sin escalones de precio: el
    mismo valor está en dollarPriceRangeLow y dollarPriceRangeHigh.
    """
    resultado = parsear_ficha_alibaba(FICHA_REAL, url="https://www.alibaba.com/product-detail/x_1601487795601.html")

    assert resultado["precio_alibaba_50u"] == 1.5
    assert resultado["moneda"] == "USD"
    assert resultado["precio_no_verificado"] is False
    assert resultado["moq"] == "10 pieces"
    assert resultado["moq_valor"] == 10
    assert resultado["precio_ladder_crudo"] is None
    assert resultado["url_alibaba"] == "https://www.alibaba.com/product-detail/x_1601487795601.html"


def test_parsear_ficha_alibaba_sin_detail_data_marca_no_verificado():
    resultado = parsear_ficha_alibaba("<html><body>página inesperada</body></html>")

    assert resultado["precio_alibaba_50u"] is None
    assert resultado["precio_no_verificado"] is True
    assert resultado["nombre_ficha"] is None
    assert resultado["atributos"] == {}
    assert resultado["imagenes"] == []


def test_parsear_ficha_alibaba_extrae_nombre_atributos_e_imagenes_reales():
    """
    Producto real 1601487795601 (ver docstring del módulo): trae subject,
    specs estructuradas por el proveedor y 6 fotos reales (más un video,
    que se descarta -- no es una imagen).
    """
    resultado = parsear_ficha_alibaba(FICHA_REAL, url="https://www.alibaba.com/product-detail/x_1601487795601.html")

    assert resultado["nombre_ficha"] == (
        "Washable BPA Free Clean Dish Washing Scrubber Sponge Silicone Sponge Brush Sponge Kitchen Dish Scrubber"
    )
    assert resultado["atributos"]["material"] == "Silicone"
    assert resultado["atributos"]["type"] == "Cleaning Brush"
    assert resultado["atributos"]["weight"] == "39(g)"
    assert len(resultado["imagenes"]) == 6
    assert all(url.startswith("https://sc04.alicdn.com/") for url in resultado["imagenes"])


def test_parsear_ficha_alibaba_con_rango_de_precio_no_adivina():
    """
    Si dollarPriceRangeLow != High (producto con escalones de precio por
    cantidad), no hay que adivinar cuál tramo corresponde a ~50 unidades:
    debe quedar marcado como no verificado.
    """
    html = """
    <script>
    window.detailData = {"globalData": {"product": {
        "productId": 999,
        "moq": 5,
        "customPrice": {"unitEven": "pieces"},
        "price": {"productRangePrices": {"dollarPriceRangeLow": 0.58, "dollarPriceRangeHigh": 0.60}}
    }}};
    </script>
    """
    resultado = parsear_ficha_alibaba(html)

    assert resultado["precio_alibaba_50u"] is None
    assert resultado["precio_no_verificado"] is True


def test_parsear_ficha_alibaba_guarda_escalones_crudos_sin_interpretarlos():
    """
    Si viene productLadderPrices, se guarda tal cual (evidencia para
    reconstruir el cálculo después) -- no se intenta adivinar qué campo
    indica la cantidad de cada escalón, sin evidencia real de su forma.
    """
    html = """
    <script>
    window.detailData = {"globalData": {"product": {
        "productId": 999,
        "moq": 2,
        "customPrice": {"unitEven": "pieces"},
        "price": {
            "productRangePrices": {"dollarPriceRangeLow": 0.80, "dollarPriceRangeHigh": 4.50},
            "productLadderPrices": [{"algunCampoDesconocido": 2, "dollarPrice": 4.50}, {"algunCampoDesconocido": 1000, "dollarPrice": 0.80}]
        }
    }}};
    </script>
    """
    resultado = parsear_ficha_alibaba(html)

    assert resultado["precio_alibaba_50u"] is None
    assert resultado["precio_no_verificado"] is True
    assert resultado["precio_ladder_crudo"] == [
        {"algunCampoDesconocido": 2, "dollarPrice": 4.50}, {"algunCampoDesconocido": 1000, "dollarPrice": 0.80}
    ]
