import pandas as pd

from calculos import calcular_metricas, calcular_score, procesar, separar_filas_validas


def _fila_ejemplo(**overrides):
    fila = {
        "producto": "Producto test",
        "precio_alibaba_usd": 3.50,
        "moq": 50,
        "peso_gramos": 60,
        "precio_ml_ars": 15000,
        "ventas_ml": 340,
        "costo_envio_usd": 120,
        "limite_envio_gramos": 21000,
        "tipo_cambio": 1450,
    }
    fila.update(overrides)
    return fila


def test_calcular_metricas_valores_esperados():
    df = pd.DataFrame([_fila_ejemplo()])
    resultado = calcular_metricas(df).iloc[0]

    assert resultado["costo_producto_ars"] == 3.50 * 1450
    assert round(resultado["costo_envio_unitario_ars"], 2) == round(120 * 60 / 21000 * 1450, 2)
    assert resultado["unidades_max_por_envio"] == 21000 // 60

    costo_total = resultado["costo_producto_ars"] + resultado["costo_envio_unitario_ars"]
    assert round(resultado["margen_bruto_ars"], 2) == round(15000 - costo_total, 2)


def test_separar_filas_validas_excluye_peso_cero():
    df = pd.DataFrame([_fila_ejemplo(), _fila_ejemplo(producto="Peso cero", peso_gramos=0)])
    validas, invalidas = separar_filas_validas(df)

    assert len(validas) == 1
    assert len(invalidas) == 1
    assert invalidas.iloc[0]["producto"] == "Peso cero"


def test_score_entre_0_y_100():
    df = pd.DataFrame([_fila_ejemplo(), _fila_ejemplo(producto="Otro", peso_gramos=200, precio_ml_ars=9000)])
    con_metricas = calcular_metricas(df)
    con_score = calcular_score(con_metricas)

    assert (con_score["score"] >= 0).all()
    assert (con_score["score"] <= 100).all()


def test_procesar_extremo_a_extremo():
    df = pd.DataFrame([_fila_ejemplo(), _fila_ejemplo(producto="Invalido", limite_envio_gramos=0)])
    validas, invalidas = procesar(df)

    assert "score" in validas.columns
    assert len(invalidas) == 1
