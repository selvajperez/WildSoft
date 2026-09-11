from pathlib import Path

from parser_busqueda_alibaba import parsear_listado_busqueda, parsear_resultado

FIXTURE = (Path(__file__).parent / "fixtures" / "alibaba_busqueda_real.html").read_text(encoding="utf-8")


def test_parsear_listado_busqueda_extrae_los_7_casos_reales():
    resultados = parsear_listado_busqueda(FIXTURE)
    assert len(resultados) == 7


def test_caso_real_con_precio_en_rango_y_publicidad():
    resultados = parsear_listado_busqueda(FIXTURE)
    item = next(r for r in resultados if r["id_alibaba"] == "1601233565568")

    assert item["url_alibaba"] == (
        "https://www.alibaba.com/product-detail/New-Arrival-Bt5-3-Hifi-Stereo_1601233565568.html"
        "?priceId=c3d405a37cd3452f86ccbf9372c8983f"
    )
    assert item["nombre"].startswith("New Arrival Bt5.3 Hifi Stereo")
    assert item["precio_texto"] == "$2.10-2.40"
    assert item["moq_texto"] == "Min. order: 10,000 pieces"
    assert item["proveedor"] == "Shenzhen Jinma Communication Co., Ltd."
    assert item["proveedor_verificado"] is True
    assert item["es_publicidad"] is True
    assert item["posicion"] == 1


def test_caso_real_con_precio_unico_y_proveedor_verificado_sin_publicidad():
    resultados = parsear_listado_busqueda(FIXTURE)
    item = next(r for r in resultados if r["id_alibaba"] == "1601446585031")

    assert item["precio_texto"] == "$2.10"  # precio único, no rango
    assert item["moq_texto"] == "Min. order: 100 pieces"
    assert item["proveedor"] == "Shenzhen Linx Technology Co., Ltd."
    assert item["proveedor_verificado"] is True
    assert item["es_publicidad"] is False


def test_caso_real_sin_publicidad_ni_verificacion():
    resultados = parsear_listado_busqueda(FIXTURE)
    item = next(r for r in resultados if r["id_alibaba"] == "1601174244321")

    assert item["precio_texto"] == "$22.99"
    assert item["proveedor"] == "Shenzhen Oneking Technologies Co., Ltd."
    assert item["proveedor_verificado"] is False
    assert item["es_publicidad"] is False


def test_moq_con_unidades_distintas_a_pieces_no_se_normaliza():
    """
    Regla del proyecto: el MOQ (y el precio) del listado se guardan tal
    cual se ven, nunca parseados a un número -- las unidades varían
    ("pieces", "set", "units") y no hay que asumir nada sobre ellas acá.
    """
    resultados = parsear_listado_busqueda(FIXTURE)
    item_set = next(r for r in resultados if r["id_alibaba"] == "1601711496420")
    item_units = next(r for r in resultados if r["id_alibaba"] == "1601445074685")

    assert item_set["moq_texto"] == "Min. order: 1 set"
    assert item_units["moq_texto"] == "Min. order: 50 units"


def test_caso_real_extrae_imagen_de_la_miniatura_no_de_otros_iconos():
    resultados = parsear_listado_busqueda(FIXTURE)
    item = next(r for r in resultados if r["id_alibaba"] == "1601233565568")
    assert item["imagen_url"] == "https://s.alicdn.com/@sc04/kf/Hc675c8ec732741e4b10b0db024e710daY.jpg_300x300.jpg"


def test_todos_los_casos_reales_tienen_imagen():
    resultados = parsear_listado_busqueda(FIXTURE)
    assert all(r["imagen_url"] is not None for r in resultados)


def test_posiciones_reflejan_el_orden_real_del_listado():
    resultados = parsear_listado_busqueda(FIXTURE)
    assert [r["posicion"] for r in resultados] == list(range(1, 8))


def test_parsear_resultado_sin_link_devuelve_none():
    from bs4 import BeautifulSoup

    html = '<div class="fy26-product-card-wrapper" data-ctrdot="123"><span>sin link</span></div>'
    tarjeta = BeautifulSoup(html, "html.parser").select_one("div.fy26-product-card-wrapper")
    assert parsear_resultado(tarjeta) is None


def test_parsear_resultado_sin_id_devuelve_none():
    from bs4 import BeautifulSoup

    html = '<div class="fy26-product-card-wrapper"><a class="searchx-product-link-wrapper" href="//www.alibaba.com/product-detail/x_1.html">x</a></div>'
    tarjeta = BeautifulSoup(html, "html.parser").select_one("div.fy26-product-card-wrapper")
    assert parsear_resultado(tarjeta) is None


def test_parsear_listado_busqueda_ignora_html_sin_tarjetas():
    assert parsear_listado_busqueda("<html><body>sin resultados</body></html>") == []
