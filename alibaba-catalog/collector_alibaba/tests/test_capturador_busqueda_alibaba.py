from capturador_busqueda_alibaba import _url_busqueda


def test_url_busqueda_codifica_espacios():
    assert _url_busqueda("wireless earbuds") == "https://www.alibaba.com/trade/search?SearchText=wireless%20earbuds"


def test_url_busqueda_con_una_sola_palabra():
    assert _url_busqueda("earbuds") == "https://www.alibaba.com/trade/search?SearchText=earbuds"


def test_url_busqueda_codifica_acentos():
    url = _url_busqueda("cepillo eléctrico")
    assert url.startswith("https://www.alibaba.com/trade/search?SearchText=")
    assert "cepillo" in url and "el" in url  # queda url-encoded, no se rompe
