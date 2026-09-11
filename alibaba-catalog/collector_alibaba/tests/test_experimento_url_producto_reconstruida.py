from pathlib import Path

from experimento_url_producto_reconstruida import _construir_url, _diagnosticar

FICHA_REAL = (Path(__file__).parent / "fixtures" / "ml_ficha_real.html").read_text(encoding="utf-8")
FICHA_NO_ENCONTRADA_REAL = (
    Path(__file__).parent / "fixtures" / "ml_ficha_no_encontrada_real.html"
).read_text(encoding="utf-8")


def test_construir_url_sin_slug_con_prefijo_de_3_letras_usa_p():
    assert _construir_url("MLA28873639", "MLA1399281097") == (
        "https://www.mercadolibre.com.ar/p/MLA28873639?pdp_filters=item_id:MLA1399281097"
    )


def test_construir_url_sin_slug_con_prefijo_de_4_letras_usa_up():
    """
    Segunda ronda del experimento real: 2/2 IDs de 3 letras (MLA+dígitos)
    funcionaron con /p/, pero 3/3 IDs de 4 letras (MLAU+dígitos) dieron
    404 con /p/ -- mismo criterio 3 vs. 4 letras ya confirmado para los
    links directos del listado (parser_busqueda_ml._RE_ITEM_ID_DIRECTO).
    """
    assert _construir_url("MLAU3739976006", "MLA2789721006") == (
        "https://www.mercadolibre.com.ar/up/MLAU3739976006?pdp_filters=item_id:MLA2789721006"
    )


def test_diagnosticar_con_ficha_real_que_abre_bien():
    resultado = _diagnosticar(
        product_id="MLA23532244",
        item_id="MLA2023730583",
        url_pedida="https://www.mercadolibre.com.ar/p/MLA23532244?pdp_filters=item_id:MLA2023730583",
        status=200,
        url_final="https://www.mercadolibre.com.ar/cepillo-electrico.../p/MLA23532244?pdp_filters=item_id:MLA2023730583",
        html=FICHA_REAL,
    )

    assert resultado["status_http"] == 200
    assert resultado["hubo_redirect"] is True  # la URL final trae el slug, la pedida no
    assert resultado["es_404_real_ml"] is False
    assert resultado["item_id_esperado_presente_en_html"] is True  # MLA2023730583 aparece en la ficha real
    assert resultado["precio_ml"] == 68780
    assert resultado["unidades_vendidas"] == 1000
    assert resultado["extraccion_normal"] is True


def test_diagnosticar_con_404_real():
    resultado = _diagnosticar(
        product_id="MLA00000000",
        item_id="MLA1758275889",
        url_pedida="https://www.mercadolibre.com.ar/p/MLA00000000?pdp_filters=item_id:MLA1758275889",
        status=200,
        url_final="https://www.mercadolibre.com.ar/p/MLA00000000?pdp_filters=item_id:MLA1758275889",
        html=FICHA_NO_ENCONTRADA_REAL,
    )

    assert resultado["es_404_real_ml"] is True
    assert resultado["extraccion_normal"] is False


def test_diagnosticar_detecta_item_id_no_esperado():
    resultado = _diagnosticar(
        product_id="MLA23532244",
        item_id="MLA9999999999",  # item_id que no aparece en la ficha real inyectada
        url_pedida="https://www.mercadolibre.com.ar/p/MLA23532244?pdp_filters=item_id:MLA9999999999",
        status=200,
        url_final="https://www.mercadolibre.com.ar/p/MLA23532244?pdp_filters=item_id:MLA9999999999",
        html=FICHA_REAL,
    )

    assert resultado["item_id_esperado_presente_en_html"] is False
