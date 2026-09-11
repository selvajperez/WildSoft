from atributos_matching import (
    AtributoExtraido,
    comparar_atributos,
    extraer_atributos_alibaba,
    extraer_atributos_texto_libre,
    incompatibilidad_esencial,
    score_atributos,
)


def test_extraer_capacidad_normaliza_litros_a_ml():
    atributos = extraer_atributos_texto_libre("Botella de 1.5 L")
    assert atributos["capacidad"].valor_numerico == 1500.0


def test_extraer_peso_normaliza_kg_a_gramos():
    atributos = extraer_atributos_texto_libre("Pesa 2.5 kg en total")
    assert atributos["peso"].valor_numerico == 2500.0


def test_extraer_peso_con_parentesis_real_de_alibaba():
    """Formato real visto en la ficha de Alibaba: attrValue == '39(g)'."""
    atributos = extraer_atributos_texto_libre("39(g)")
    assert atributos["peso"].valor_numerico == 39.0


def test_extraer_cantidad_piezas_pack_of():
    atributos = extraer_atributos_texto_libre("Set de herramientas, pack of 10")
    assert atributos["cantidad_piezas"].valor_numerico == 10.0


def test_extraer_dimensiones_normaliza_mm_a_cm():
    atributos = extraer_atributos_texto_libre("Medidas: 100x50x30mm")
    assert atributos["dimensiones"].valor_dimensiones == (10.0, 5.0, 3.0)


def test_extraer_categoria_frase_completa_prioriza_sobre_palabra_suelta():
    atributos = extraer_atributos_texto_libre("Cleaning Brush portátil")
    assert atributos["categoria"].categoria_canon == "cepillo"


def test_extraer_categoria_esponja():
    atributos = extraer_atributos_texto_libre("Silicone dish washing sponge scrubber")
    assert atributos["categoria"].categoria_canon == "esponja"


def test_extraer_material_silicona_en_espanol_e_ingles():
    assert extraer_atributos_texto_libre("cepillo de silicona")["material"].categoria_canon == "silicona"
    assert extraer_atributos_texto_libre("silicone brush")["material"].categoria_canon == "silicona"


def test_texto_sin_ningun_patron_no_extrae_nada():
    assert extraer_atributos_texto_libre("un producto cualquiera sin datos") == {}


def test_texto_vacio_o_none_no_extrae_nada():
    assert extraer_atributos_texto_libre("") == {}
    assert extraer_atributos_texto_libre(None) == {}


def test_extraer_atributos_alibaba_prioriza_specs_estructuradas_sobre_texto():
    estructurados = {"type": "Cleaning Brush", "material": "Silicone", "weight": "39(g)"}
    atributos = extraer_atributos_alibaba(estructurados, texto_extra="algo totalmente distinto sin specs")
    assert atributos["categoria"].categoria_canon == "cepillo"
    assert atributos["material"].categoria_canon == "silicona"
    assert atributos["peso"].valor_numerico == 39.0


def test_extraer_atributos_alibaba_completa_con_texto_libre_lo_que_falta_en_specs():
    estructurados = {"material": "Silicone"}
    atributos = extraer_atributos_alibaba(estructurados, texto_extra="Cleaning Brush 39(g)")
    assert atributos["material"].categoria_canon == "silicona"  # de specs, no se pisa
    assert atributos["categoria"].categoria_canon == "cepillo"  # completado desde texto_extra
    assert atributos["peso"].valor_numerico == 39.0


def test_extraer_atributos_alibaba_marca_generica_se_descarta():
    estructurados = {"brand name": "none"}
    assert "marca" not in extraer_atributos_alibaba(estructurados)


def test_comparar_atributos_sin_evidencia_de_un_lado_no_es_incompatible():
    a = {"categoria": AtributoExtraido("categoria", "brush", categoria_canon="cepillo")}
    b: dict = {}
    comparaciones = comparar_atributos(a, b)
    assert comparaciones[0].compatible is None
    assert incompatibilidad_esencial(comparaciones) is None


def test_comparar_atributos_categoria_incompatible_es_veto_esencial():
    a = extraer_atributos_texto_libre("Cepillo de silicona para limpieza, 39g")
    b = extraer_atributos_texto_libre("Silicone dish washing sponge scrubber, 39g")
    comparaciones = comparar_atributos(a, b)
    veto = incompatibilidad_esencial(comparaciones)
    assert veto is not None
    assert veto.tipo == "categoria"


def test_comparar_atributos_mismo_producto_no_tiene_veto():
    a = extraer_atributos_texto_libre("Cepillo de limpieza de silicona, 39g, negro")
    b = extraer_atributos_texto_libre("Silicone cleaning brush, 39(g), black")
    comparaciones = comparar_atributos(a, b)
    assert incompatibilidad_esencial(comparaciones) is None
    score, cobertura = score_atributos(comparaciones)
    assert score == 1.0
    assert cobertura > 0


def test_comparar_atributos_capacidad_dentro_de_tolerancia_es_compatible():
    a = {"capacidad": AtributoExtraido("capacidad", "500ml", valor_numerico=500.0)}
    b = {"capacidad": AtributoExtraido("capacidad", "540ml", valor_numerico=540.0)}
    comparaciones = comparar_atributos(a, b)
    assert comparaciones[0].compatible is True


def test_comparar_atributos_capacidad_fuera_de_tolerancia_es_incompatible():
    a = {"capacidad": AtributoExtraido("capacidad", "500ml", valor_numerico=500.0)}
    b = {"capacidad": AtributoExtraido("capacidad", "5000ml", valor_numerico=5000.0)}
    comparaciones = comparar_atributos(a, b)
    assert comparaciones[0].compatible is False
    assert incompatibilidad_esencial(comparaciones) is not None


def test_comparar_atributos_tolerancia_configurable_no_es_fija():
    a = {"capacidad": AtributoExtraido("capacidad", "500ml", valor_numerico=500.0)}
    b = {"capacidad": AtributoExtraido("capacidad", "600ml", valor_numerico=600.0)}
    estricta = comparar_atributos(a, b, tolerancias={"capacidad": 0.05})
    laxa = comparar_atributos(a, b, tolerancias={"capacidad": 0.5})
    assert estricta[0].compatible is False
    assert laxa[0].compatible is True


def test_comparar_atributos_color_distinto_nunca_es_veto_aunque_sea_incompatible():
    a = {"color": AtributoExtraido("color", "red", categoria_canon="rojo")}
    b = {"color": AtributoExtraido("color", "blue", categoria_canon="azul")}
    comparaciones = comparar_atributos(a, b)
    assert comparaciones[0].compatible is False
    assert comparaciones[0].esencial is False
    assert incompatibilidad_esencial(comparaciones) is None


def test_score_atributos_sin_comparaciones_evaluables_es_neutral():
    a = {"categoria": AtributoExtraido("categoria", "brush", categoria_canon="cepillo")}
    comparaciones = comparar_atributos(a, {})
    score, cobertura = score_atributos(comparaciones)
    assert score == 0.5
    assert cobertura == 0.0
