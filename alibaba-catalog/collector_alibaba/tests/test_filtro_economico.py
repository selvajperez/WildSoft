import pytest

from filtro_economico import (
    PrecioAlibabaResuelto,
    evaluar_viabilidad,
    resolver_precio_alibaba,
)


def _ficha_precio_unico(precio=1.5, moq=10):
    return {
        "precio_alibaba_50u": precio, "precio_no_verificado": False, "moq_valor": moq,
        "precio_ladder_crudo": None,
    }


def _ficha_sin_precio():
    return {"precio_alibaba_50u": None, "precio_no_verificado": True, "moq_valor": None, "precio_ladder_crudo": None}


def _ficha_con_ladder():
    return {
        "precio_alibaba_50u": None, "precio_no_verificado": True, "moq_valor": 2,
        "precio_ladder_crudo": [{"algo": 2, "dollarPrice": 4.5}, {"algo": 1000, "dollarPrice": 0.8}],
    }


# --- resolver_precio_alibaba -------------------------------------------


def test_resolver_precio_alibaba_precio_unico():
    resuelto = resolver_precio_alibaba(_ficha_precio_unico(precio=4.20, moq=20))
    assert resuelto.precio_usd == 4.20
    assert resuelto.cantidad_asociada == 20
    assert resuelto.fuente == "precio_unico"
    assert resuelto.no_verificado is False


def test_resolver_precio_alibaba_con_ladder_no_verificado_pero_guarda_evidencia():
    resuelto = resolver_precio_alibaba(_ficha_con_ladder())
    assert resuelto.precio_usd is None
    assert resuelto.no_verificado is True
    assert resuelto.fuente == "escalon_ladder_sin_confirmar"
    assert resuelto.datos_crudos == [{"algo": 2, "dollarPrice": 4.5}, {"algo": 1000, "dollarPrice": 0.8}]


def test_resolver_precio_alibaba_sin_nada_no_verificado():
    resuelto = resolver_precio_alibaba(_ficha_sin_precio())
    assert resuelto.precio_usd is None
    assert resuelto.no_verificado is True
    assert resuelto.fuente == "no_disponible"


# --- evaluar_viabilidad: caso de la usuaria -----------------------------


def test_evaluar_viabilidad_ejemplo_real_de_la_usuaria():
    """Alibaba USD 4.20 (20u) vs ML USD 18 -> ratio 4.29x, diferencia USD 13.80, supera las dos reglas."""
    precio_alibaba = PrecioAlibabaResuelto(4.20, 20, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=18.0, moneda_ml="USD", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba)

    assert r.resultado == "viable"
    assert r.ratio == pytest.approx(4.2857, rel=1e-3)
    assert r.diferencia_usd == pytest.approx(13.80, rel=1e-3)
    assert r.cantidad_alibaba == 20


# --- las dos reglas son obligatorias (AND, no OR) -----------------------


def test_evaluar_viabilidad_ratio_alto_pero_diferencia_chica_no_es_viable():
    # ratio 3x pero diferencia de solo 2 USD -- no alcanza la regla de USD 10
    precio_alibaba = PrecioAlibabaResuelto(1.0, 50, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=3.0, moneda_ml="USD", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba)
    assert r.resultado == "no_viable"


def test_evaluar_viabilidad_diferencia_grande_pero_ratio_bajo_no_es_viable():
    # diferencia de 20 USD pero ratio de solo 1.2x -- no alcanza x2.5
    precio_alibaba = PrecioAlibabaResuelto(100.0, 50, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=120.0, moneda_ml="USD", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba)
    assert r.resultado == "no_viable"


# --- MATCH_PROBABLE que pasa las reglas queda "viable_dudoso", no se descarta ---


def test_evaluar_viabilidad_match_probable_que_pasa_reglas_es_viable_dudoso():
    precio_alibaba = PrecioAlibabaResuelto(4.20, 20, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=18.0, moneda_ml="USD", categoria_match="MATCH_PROBABLE", precio_alibaba=precio_alibaba)
    assert r.resultado == "viable_dudoso"


def test_evaluar_viabilidad_match_probable_que_no_pasa_reglas_es_no_viable():
    precio_alibaba = PrecioAlibabaResuelto(10.0, 50, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=11.0, moneda_ml="USD", categoria_match="MATCH_PROBABLE", precio_alibaba=precio_alibaba)
    assert r.resultado == "no_viable"


# --- nunca se asume un valor: casos "indeterminado" ---------------------


def test_evaluar_viabilidad_categoria_no_aceptada_es_indeterminado():
    precio_alibaba = PrecioAlibabaResuelto(4.20, 20, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=18.0, moneda_ml="USD", categoria_match="SIN_MATCH_CONFIABLE", precio_alibaba=precio_alibaba)
    assert r.resultado == "indeterminado"


def test_evaluar_viabilidad_precio_ml_faltante_es_indeterminado():
    precio_alibaba = PrecioAlibabaResuelto(4.20, 20, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=None, moneda_ml="USD", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba)
    assert r.resultado == "indeterminado"


def test_evaluar_viabilidad_precio_alibaba_no_verificado_es_indeterminado_no_no_viable():
    precio_alibaba = resolver_precio_alibaba(_ficha_con_ladder())
    r = evaluar_viabilidad(precio_ml=18.0, moneda_ml="USD", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba)
    assert r.resultado == "indeterminado"
    assert r.precio_ladder_crudo == [{"algo": 2, "dollarPrice": 4.5}, {"algo": 1000, "dollarPrice": 0.8}]


def test_evaluar_viabilidad_ars_sin_tipo_de_cambio_es_indeterminado_no_asume_nada():
    precio_alibaba = PrecioAlibabaResuelto(4.20, 20, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=18000.0, moneda_ml="ARS", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba)
    assert r.resultado == "indeterminado"
    assert "tipo de cambio" in r.motivo.lower()


def test_evaluar_viabilidad_moneda_desconocida_es_indeterminado():
    precio_alibaba = PrecioAlibabaResuelto(4.20, 20, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=18.0, moneda_ml="EUR", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba)
    assert r.resultado == "indeterminado"


# --- conversión de moneda con tipo de cambio explícito -------------------


def test_evaluar_viabilidad_convierte_ars_con_tipo_de_cambio_explicito():
    # ML: 18000 ARS, tipo de cambio 1000 ARS/USD -> 18 USD -- mismo resultado que el ejemplo en USD directo.
    precio_alibaba = PrecioAlibabaResuelto(4.20, 20, "precio_unico", False, "x")
    r = evaluar_viabilidad(
        precio_ml=18000.0, moneda_ml="ARS", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba,
        tipo_cambio_usd_ars=1000.0,
    )
    assert r.resultado == "viable"
    assert r.precio_ml_usd == pytest.approx(18.0)
    assert r.tipo_cambio_usado == 1000.0


def test_evaluar_viabilidad_guarda_fuente_y_fecha_del_tipo_de_cambio():
    """La procedencia del tipo de cambio (ej. dólar MEP) se conserva junto con el cálculo."""
    precio_alibaba = PrecioAlibabaResuelto(4.20, 20, "precio_unico", False, "x")
    r = evaluar_viabilidad(
        precio_ml=18000.0, moneda_ml="ARS", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba,
        tipo_cambio_usd_ars=1000.0,
        tipo_cambio_fuente="https://dolarapi.com/v1/dolares/bolsa",
        tipo_cambio_fecha_referencia="2026-09-12T10:00:00.000Z",
    )
    assert r.resultado == "viable"
    assert r.tipo_cambio_fuente == "https://dolarapi.com/v1/dolares/bolsa"
    assert r.tipo_cambio_fecha_referencia == "2026-09-12T10:00:00.000Z"


def test_evaluar_viabilidad_sin_fuente_de_tipo_de_cambio_queda_none():
    precio_alibaba = PrecioAlibabaResuelto(4.20, 20, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=18.0, moneda_ml="USD", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba)
    assert r.tipo_cambio_fuente is None
    assert r.tipo_cambio_fecha_referencia is None


def test_evaluar_viabilidad_moneda_none_se_asume_ya_en_usd():
    precio_alibaba = PrecioAlibabaResuelto(4.20, 20, "precio_unico", False, "x")
    r = evaluar_viabilidad(precio_ml=18.0, moneda_ml=None, categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba)
    assert r.resultado == "viable"


# --- umbrales configurables, no fijos ------------------------------------


def test_evaluar_viabilidad_umbrales_configurables():
    precio_alibaba = PrecioAlibabaResuelto(10.0, 50, "precio_unico", False, "x")
    r_default = evaluar_viabilidad(precio_ml=15.0, moneda_ml="USD", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba)
    assert r_default.resultado == "no_viable"  # ratio 1.5x, diferencia 5 USD -- no alcanza ninguna regla default

    r_laxo = evaluar_viabilidad(
        precio_ml=15.0, moneda_ml="USD", categoria_match="MATCH_ALTO", precio_alibaba=precio_alibaba,
        ratio_minimo=1.2, diferencia_minima_usd=3.0,
    )
    assert r_laxo.resultado == "viable"
