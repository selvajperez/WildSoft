import json

import db
from orquestador_filtro_economico import (
    ejecutar_filtro_economico_real,
    procesar_candidato_viabilidad,
    procesar_lote_viabilidad,
)
from tipo_cambio import TipoCambioResuelto

_MEP_DISPONIBLE = TipoCambioResuelto(
    valor=1000.0, fuente="https://dolarapi.com/v1/dolares/bolsa",
    fecha_referencia="2026-09-12T10:00:00.000Z", obtenido_en="2026-09-12T10:05:00+00:00",
    disponible=True, detalle="ok",
)
_MEP_NO_DISPONIBLE = TipoCambioResuelto(
    valor=None, fuente=None, fecha_referencia=None, obtenido_en="2026-09-12T10:05:00+00:00",
    disponible=False, detalle="No se pudo consultar el dólar MEP: timeout.",
)


def _conexion_memoria():
    return db.conectar(":memory:")


def _html_ficha_alibaba(precio: float, moq: int = 10) -> str:
    data = {
        "globalData": {
            "product": {
                "subject": "Producto de prueba",
                "productBasicProperties": [], "productKeyIndustryProperties": [], "mediaItems": [],
                "moq": moq,
                "customPrice": {"unitEven": "pieces"},
                "price": {"productRangePrices": {"dollarPriceRangeLow": precio, "dollarPriceRangeHigh": precio}},
            }
        }
    }
    return f"<html><script>window.detailData = {json.dumps(data)};</script></html>"


def _candidato_pendiente(conexion, precio_ml, moneda_ml, categoria_match, url_alibaba="https://alibaba.test/x.html"):
    candidato_id = db.upsert_candidato_ml(conexion, {
        "url_ml": f"https://ml.test/{candidato_id_counter[0]}", "nombre": "Cepillo de prueba",
        "precio_ml": precio_ml, "moneda_ml": moneda_ml,
    })
    candidato_id_counter[0] += 1
    db.actualizar_estado_candidato(conexion, candidato_id, "con_comparable")
    db.insertar_resultado_matching(conexion, candidato_id, {
        "id_ml": f"MLA{candidato_id}", "categoria": categoria_match, "motivo": "x",
        "candidato_elegido": {"url_alibaba": url_alibaba, "score_final": 0.9} if url_alibaba else None,
        "candidatos_evaluados": [], "candidatos_rankeados": [],
    })
    return db.obtener_candidatos_pendientes_de_viabilidad(conexion)[-1]


candidato_id_counter = [1]


def test_procesar_candidato_viabilidad_match_alto_viable():
    conexion = _conexion_memoria()
    candidato = _candidato_pendiente(conexion, precio_ml=18.0, moneda_ml="USD", categoria_match="MATCH_ALTO")

    def abrir_ficha(url):
        return _html_ficha_alibaba(precio=4.20, moq=20)

    resultado = procesar_candidato_viabilidad(candidato, conexion, abrir_ficha, _MEP_NO_DISPONIBLE)

    assert resultado["resultado"] == "viable"
    assert resultado["ratio"] > 2.5

    fila = db.obtener_candidato_por_url(conexion, candidato["url_ml"])
    assert fila["estado"] == "precio_verificado"


def test_procesar_candidato_viabilidad_match_probable_pasa_reglas_es_viable_dudoso_y_no_se_descarta():
    conexion = _conexion_memoria()
    candidato = _candidato_pendiente(conexion, precio_ml=18.0, moneda_ml="USD", categoria_match="MATCH_PROBABLE")

    def abrir_ficha(url):
        return _html_ficha_alibaba(precio=4.20, moq=20)

    resultado = procesar_candidato_viabilidad(candidato, conexion, abrir_ficha, _MEP_NO_DISPONIBLE)

    assert resultado["resultado"] == "viable_dudoso"
    fila = db.obtener_candidato_por_url(conexion, candidato["url_ml"])
    assert fila["estado"] == "precio_verificado"  # no se descarta


def test_procesar_candidato_viabilidad_no_alcanza_reglas_es_no_viable():
    conexion = _conexion_memoria()
    candidato = _candidato_pendiente(conexion, precio_ml=5.0, moneda_ml="USD", categoria_match="MATCH_ALTO")

    def abrir_ficha(url):
        return _html_ficha_alibaba(precio=4.20, moq=20)

    resultado = procesar_candidato_viabilidad(candidato, conexion, abrir_ficha, _MEP_NO_DISPONIBLE)

    assert resultado["resultado"] == "no_viable"
    fila = db.obtener_candidato_por_url(conexion, candidato["url_ml"])
    assert fila["estado"] == "descartado_filtro_economico"


def test_procesar_candidato_viabilidad_precio_ars_sin_tipo_de_cambio_es_indeterminado():
    conexion = _conexion_memoria()
    candidato = _candidato_pendiente(conexion, precio_ml=18000.0, moneda_ml="ARS", categoria_match="MATCH_ALTO")

    def abrir_ficha(url):
        return _html_ficha_alibaba(precio=4.20, moq=20)

    resultado = procesar_candidato_viabilidad(candidato, conexion, abrir_ficha, _MEP_NO_DISPONIBLE)

    assert resultado["resultado"] == "indeterminado"
    fila = db.obtener_candidato_por_url(conexion, candidato["url_ml"])
    assert fila["estado"] == "descartado_no_verificado"


def test_procesar_candidato_viabilidad_convierte_ars_con_dolar_mep_y_guarda_su_procedencia():
    conexion = _conexion_memoria()
    candidato = _candidato_pendiente(conexion, precio_ml=18000.0, moneda_ml="ARS", categoria_match="MATCH_ALTO")

    def abrir_ficha(url):
        return _html_ficha_alibaba(precio=4.20, moq=20)

    resultado = procesar_candidato_viabilidad(candidato, conexion, abrir_ficha, _MEP_DISPONIBLE)

    assert resultado["resultado"] == "viable"

    fila = conexion.execute(
        "SELECT tipo_cambio_usado, tipo_cambio_fuente, tipo_cambio_fecha_referencia "
        "FROM alibaba_comparables WHERE candidato_id = ?",
        (candidato["id"],),
    ).fetchone()
    assert fila[0] == 1000.0
    assert fila[1] == "https://dolarapi.com/v1/dolares/bolsa"
    assert fila[2] == "2026-09-12T10:00:00.000Z"


def test_procesar_candidato_viabilidad_guarda_evidencia_completa_en_alibaba_comparables():
    conexion = _conexion_memoria()
    candidato = _candidato_pendiente(conexion, precio_ml=18.0, moneda_ml="USD", categoria_match="MATCH_ALTO")

    def abrir_ficha(url):
        return _html_ficha_alibaba(precio=4.20, moq=20)

    procesar_candidato_viabilidad(candidato, conexion, abrir_ficha, _MEP_NO_DISPONIBLE)

    fila = conexion.execute(
        "SELECT precio_alibaba_50u, cantidad_precio_alibaba, ratio, diferencia_usd, resultado_viabilidad, "
        "precio_ml_original, moneda_ml_original FROM alibaba_comparables WHERE candidato_id = ?",
        (candidato["id"],),
    ).fetchone()
    assert fila[0] == 4.20
    assert fila[1] == 20
    assert round(fila[2], 2) == 4.29
    assert round(fila[3], 2) == 13.80
    assert fila[4] == "viable"
    assert fila[5] == 18.0
    assert fila[6] == "USD"


def test_procesar_candidato_viabilidad_sin_url_alibaba_no_intenta_abrir_ficha():
    conexion = _conexion_memoria()
    candidato = _candidato_pendiente(
        conexion, precio_ml=18.0, moneda_ml="USD", categoria_match="MATCH_ALTO", url_alibaba=None
    )

    def abrir_ficha(url):
        raise AssertionError("no debería intentar abrir ninguna ficha")

    resultado = procesar_candidato_viabilidad(candidato, conexion, abrir_ficha, _MEP_NO_DISPONIBLE)
    assert resultado["resultado"] == "indeterminado"


def test_procesar_lote_viabilidad_sigue_ante_un_error_en_un_candidato():
    conexion = _conexion_memoria()
    candidato_1 = _candidato_pendiente(conexion, precio_ml=18.0, moneda_ml="USD", categoria_match="MATCH_ALTO")
    candidato_2 = _candidato_pendiente(conexion, precio_ml=18.0, moneda_ml="USD", categoria_match="MATCH_ALTO")

    llamadas = []

    def procesar_uno(candidato):
        llamadas.append(candidato["id"])
        if candidato["id"] == candidato_1["id"]:
            raise RuntimeError("fallo simulado")
        return {"id_ml": candidato["id_ml"], "nombre": candidato["nombre"], "resultado": "viable", "motivo": "ok"}

    resultados = procesar_lote_viabilidad([candidato_1, candidato_2], conexion, procesar_uno)

    assert len(resultados) == 2
    assert resultados[0]["resultado"] == "error"
    assert resultados[1]["resultado"] == "viable"
    assert llamadas == [candidato_1["id"], candidato_2["id"]]
