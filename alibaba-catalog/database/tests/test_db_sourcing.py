import time

import pytest

import db


def _conexion_memoria():
    return db.conectar(":memory:")


def test_upsert_candidato_ml_inserta_y_devuelve_id():
    conexion = _conexion_memoria()

    candidato_id = db.upsert_candidato_ml(conexion, {
        "url_ml": "https://articulo.mercadolibre.com.ar/MLA-1",
        "nombre": "Candado bicicleta",
        "evidencia_demanda": "+500 vendidos",
        "unidades_vendidas": 500,
        "precio_ml": 15000.0,
        "moneda_ml": "ARS",
    })

    assert isinstance(candidato_id, int)
    candidato = db.obtener_candidato_por_url(conexion, "https://articulo.mercadolibre.com.ar/MLA-1")
    assert candidato["nombre"] == "Candado bicicleta"
    assert candidato["estado"] == "nuevo"
    assert candidato["id"] == candidato_id


def test_upsert_candidato_ml_actualiza_por_url_sin_duplicar():
    conexion = _conexion_memoria()

    id_1 = db.upsert_candidato_ml(conexion, {
        "url_ml": "https://articulo.mercadolibre.com.ar/MLA-1", "nombre": "Candado", "precio_ml": 15000.0,
    })
    id_2 = db.upsert_candidato_ml(conexion, {
        "url_ml": "https://articulo.mercadolibre.com.ar/MLA-1", "nombre": "Candado", "precio_ml": 16000.0,
    })

    assert id_1 == id_2
    total = conexion.execute("SELECT COUNT(*) FROM candidatos_ml").fetchone()[0]
    assert total == 1
    assert db.obtener_candidato_por_url(conexion, "https://articulo.mercadolibre.com.ar/MLA-1")["precio_ml"] == 16000.0


def test_upsert_candidato_ml_preserva_fecha_detectado_en_updates():
    conexion = _conexion_memoria()

    db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "A"})
    fecha_original = db.obtener_candidato_por_url(conexion, "https://ejemplo.test/1")["fecha_detectado"]

    time.sleep(0.01)
    db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "A actualizado"})
    candidato = db.obtener_candidato_por_url(conexion, "https://ejemplo.test/1")

    assert candidato["fecha_detectado"] == fecha_original
    assert candidato["nombre"] == "A actualizado"
    assert candidato["fecha_actualizado"] != fecha_original


def test_obtener_candidato_por_url_devuelve_none_si_no_existe():
    conexion = _conexion_memoria()
    assert db.obtener_candidato_por_url(conexion, "https://no-existe.test") is None


def test_actualizar_estado_candidato_valido():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "A"})

    db.actualizar_estado_candidato(conexion, candidato_id, "descartado_filtro_economico", motivo_descarte="diferencia < USD 10")

    candidato = db.obtener_candidato_por_url(conexion, "https://ejemplo.test/1")
    assert candidato["estado"] == "descartado_filtro_economico"
    assert candidato["motivo_descarte"] == "diferencia < USD 10"


def test_actualizar_estado_candidato_rechaza_estado_desconocido():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "A"})

    with pytest.raises(ValueError):
        db.actualizar_estado_candidato(conexion, candidato_id, "estado_inventado")


def test_insertar_comparable_alibaba_asociado_al_candidato():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "A"})

    comparable_id = db.insertar_comparable_alibaba(conexion, candidato_id, {
        "url_alibaba": "https://www.alibaba.com/product-detail/x.html",
        "proveedor": "Proveedor X",
        "moq": "50 pieces",
        "precio_alibaba_50u": 1.8,
        "moneda": "USD",
        "precio_no_verificado": False,
    })

    fila = conexion.execute(
        "SELECT candidato_id, proveedor, precio_alibaba_50u, precio_no_verificado FROM alibaba_comparables WHERE id = ?",
        (comparable_id,),
    ).fetchone()
    assert fila == (candidato_id, "Proveedor X", 1.8, 0)


def test_registrar_observacion_historial_no_sobreescribe_anteriores():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "A"})

    db.registrar_observacion_historial(conexion, candidato_id, {"precio": 15000.0, "stock_visible": 4})
    db.registrar_observacion_historial(conexion, candidato_id, {"precio": 15000.0, "stock_visible": 3})

    historial = db.obtener_historial(conexion, candidato_id)
    assert len(historial) == 2
    assert [h["stock_visible"] for h in historial] == [4, 3]


def test_obtener_historial_vacio_si_no_hay_observaciones():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "A"})
    assert db.obtener_historial(conexion, candidato_id) == []


def _resultado_matching_match_alto():
    return {
        "id_ml": "MLA1",
        "query_usada": "cepillo de limpieza",
        "categoria": "MATCH_ALTO",
        "motivo": "Candidato elegido: https://alibaba.test/x.html",
        "candidato_elegido": {"url_alibaba": "https://alibaba.test/x.html", "nombre_alibaba": "Cleaning brush", "score_final": 0.9},
        "candidatos_evaluados": [{"url_alibaba": "https://alibaba.test/x.html", "categoria": "MATCH_ALTO"}],
        "candidatos_rankeados": [{"candidato": {"id_alibaba": "x"}, "score_ranking": 0.85}],
    }


def test_insertar_resultado_matching_match_alto_guarda_candidato_elegido():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "Cepillo"})

    matching_id = db.insertar_resultado_matching(conexion, candidato_id, _resultado_matching_match_alto())

    assert isinstance(matching_id, int)
    resultado = db.obtener_ultimo_matching(conexion, candidato_id)
    assert resultado["categoria"] == "MATCH_ALTO"
    assert resultado["url_alibaba_elegido"] == "https://alibaba.test/x.html"
    assert resultado["score_final"] == 0.9
    assert resultado["candidatos_evaluados"][0]["url_alibaba"] == "https://alibaba.test/x.html"
    assert resultado["candidatos_rankeados"][0]["score_ranking"] == 0.85


def test_insertar_resultado_matching_sin_match_no_tiene_candidato_elegido():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "Cepillo"})

    db.insertar_resultado_matching(conexion, candidato_id, {
        "id_ml": "MLA1",
        "query_usada": "cepillo de limpieza",
        "categoria": "SIN_MATCH_CONFIABLE",
        "motivo": "Se agotaron los candidatos del top_k.",
        "candidato_elegido": None,
        "candidatos_evaluados": [],
        "candidatos_rankeados": [],
    })

    resultado = db.obtener_ultimo_matching(conexion, candidato_id)
    assert resultado["categoria"] == "SIN_MATCH_CONFIABLE"
    assert resultado["url_alibaba_elegido"] is None
    assert resultado["score_final"] is None


def test_insertar_resultado_matching_rechaza_categoria_desconocida():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "Cepillo"})

    resultado = _resultado_matching_match_alto()
    resultado["categoria"] = "CATEGORIA_INVENTADA"
    with pytest.raises(ValueError):
        db.insertar_resultado_matching(conexion, candidato_id, resultado)


def test_matching_alibaba_es_append_only_no_pisa_corridas_anteriores():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "Cepillo"})

    db.insertar_resultado_matching(conexion, candidato_id, _resultado_matching_match_alto())
    time.sleep(0.01)
    resultado_2 = _resultado_matching_match_alto()
    resultado_2["categoria"] = "MATCH_PROBABLE"
    db.insertar_resultado_matching(conexion, candidato_id, resultado_2)

    historial = db.obtener_historial_matching(conexion, candidato_id)
    assert len(historial) == 2
    assert [h["categoria"] for h in historial] == ["MATCH_ALTO", "MATCH_PROBABLE"]
    assert db.obtener_ultimo_matching(conexion, candidato_id)["categoria"] == "MATCH_PROBABLE"


def test_obtener_ultimo_matching_devuelve_none_si_nunca_se_corrio():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "Cepillo"})
    assert db.obtener_ultimo_matching(conexion, candidato_id) is None
