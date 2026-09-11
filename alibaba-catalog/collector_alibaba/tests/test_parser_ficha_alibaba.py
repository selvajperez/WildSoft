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
    assert resultado["url_alibaba"] == "https://www.alibaba.com/product-detail/x_1601487795601.html"


def test_parsear_ficha_alibaba_sin_detail_data_marca_no_verificado():
    resultado = parsear_ficha_alibaba("<html><body>página inesperada</body></html>")

    assert resultado["precio_alibaba_50u"] is None
    assert resultado["precio_no_verificado"] is True


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
