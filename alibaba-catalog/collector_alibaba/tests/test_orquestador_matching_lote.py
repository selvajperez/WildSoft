import db
from orquestador_matching_lote import (
    _armar_resumen,
    _motivo_dudoso,
    procesar_lote,
    seleccionar_candidatos_lote,
)


def _conexion_memoria():
    return db.conectar(":memory:")


def _agregar_candidato(conexion, url_ml, nombre, unidades_vendidas, estado="demanda_confirmada"):
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": url_ml, "nombre": nombre, "unidades_vendidas": unidades_vendidas})
    if estado != "nuevo":
        db.actualizar_estado_candidato(conexion, candidato_id, estado)
    return candidato_id


def test_seleccionar_candidatos_lote_prioriza_variedad_de_categoria():
    conexion = _conexion_memoria()
    _agregar_candidato(conexion, "https://x/1", "Cepillo de limpieza eléctrico A", 500)
    _agregar_candidato(conexion, "https://x/2", "Cepillo de limpieza eléctrico B", 400)
    _agregar_candidato(conexion, "https://x/3", "Cepillo de limpieza eléctrico C", 300)
    _agregar_candidato(conexion, "https://x/4", "Esponja de cocina", 200)
    _agregar_candidato(conexion, "https://x/5", "Camiseta de fútbol", 100)

    seleccionados = seleccionar_candidatos_lote(conexion, cantidad=4, max_por_categoria=2)

    categorias = [c["_categoria"] for c in seleccionados]
    assert categorias.count("cepillo") <= 2  # nunca más de max_por_categoria de la misma categoría
    assert "esponja" in categorias
    assert "camiseta" in categorias


def test_seleccionar_candidatos_lote_completa_con_lo_que_quede_si_falta_variedad():
    conexion = _conexion_memoria()
    for i in range(5):
        _agregar_candidato(conexion, f"https://x/{i}", f"Cepillo de limpieza modelo {i}", 500 - i)

    seleccionados = seleccionar_candidatos_lote(conexion, cantidad=4, max_por_categoria=2)

    assert len(seleccionados) == 4  # completa aunque todos sean la misma categoría


def test_seleccionar_candidatos_lote_ignora_los_que_no_estan_demanda_confirmada():
    conexion = _conexion_memoria()
    _agregar_candidato(conexion, "https://x/1", "Cepillo A", 500, estado="demanda_confirmada")
    _agregar_candidato(conexion, "https://x/2", "Cepillo B", 900, estado="descartado_demanda_no_confirmada")

    seleccionados = seleccionar_candidatos_lote(conexion, cantidad=10)

    assert len(seleccionados) == 1
    assert seleccionados[0]["url_ml"] == "https://x/1"


def test_seleccionar_candidatos_lote_vacio_si_no_hay_candidatos():
    conexion = _conexion_memoria()
    assert seleccionar_candidatos_lote(conexion, cantidad=10) == []


def test_procesar_lote_sigue_ante_un_error_y_no_corta_el_resto():
    candidatos = [
        {"id_ml": "A", "nombre": "Candidato A"},
        {"id_ml": "B", "nombre": "Candidato B"},
        {"id_ml": "C", "nombre": "Candidato C"},
    ]

    def procesar_uno(candidato):
        if candidato["id_ml"] == "B":
            raise RuntimeError("fallo simulado en B")
        return {"id_ml": candidato["id_ml"], "categoria": "MATCH_ALTO", "candidato_elegido": None, "candidatos_evaluados": []}

    resultados = procesar_lote(candidatos, procesar_uno)

    assert len(resultados) == 3
    assert [r["estado_proceso"] for r in resultados] == ["ok", "error", "ok"]
    assert "fallo simulado en B" in resultados[1]["error"]


def test_motivo_dudoso_match_probable_es_dudoso():
    resultado = {"categoria": "MATCH_PROBABLE", "candidatos_evaluados": []}
    assert _motivo_dudoso(resultado) is not None


def test_motivo_dudoso_con_veto_es_dudoso():
    resultado = {
        "categoria": "SIN_MATCH_CONFIABLE",
        "candidatos_evaluados": [{"veto": {"tipo": "identidad"}}],
    }
    motivo = _motivo_dudoso(resultado)
    assert motivo is not None
    assert "identidad" in motivo


def test_motivo_dudoso_match_alto_sin_veto_no_es_dudoso():
    resultado = {
        "categoria": "MATCH_ALTO",
        "candidatos_evaluados": [{"veto": None}],
    }
    assert _motivo_dudoso(resultado) is None


def test_motivo_dudoso_sin_match_confiable_sin_veto_no_es_dudoso():
    """Un SIN_MATCH_CONFIABLE limpio (agotó el top_k sin ningún veto) no necesita revisión especial."""
    resultado = {"categoria": "SIN_MATCH_CONFIABLE", "candidatos_evaluados": [{"veto": None}, {"veto": None}]}
    assert _motivo_dudoso(resultado) is None


def test_armar_resumen_cuenta_categorias_y_errores():
    resultados = [
        {"id_ml": "A", "nombre_ml": "A", "estado_proceso": "ok", "categoria": "MATCH_ALTO", "candidatos_evaluados": []},
        {"id_ml": "B", "nombre_ml": "B", "estado_proceso": "ok", "categoria": "MATCH_PROBABLE", "candidatos_evaluados": []},
        {"id_ml": "C", "nombre_ml": "C", "estado_proceso": "ok", "categoria": "SIN_MATCH_CONFIABLE", "candidatos_evaluados": []},
        {"id_ml": "D", "nombre_ml": "D", "estado_proceso": "error", "error": "boom"},
    ]

    resumen = _armar_resumen(resultados)

    assert resumen["total"] == 4
    assert resumen["match_alto"] == 1
    assert resumen["match_probable"] == 1
    assert resumen["sin_match_confiable"] == 1
    assert resumen["error"] == 1
    assert len(resumen["dudosos"]) == 2  # el MATCH_PROBABLE + el error
