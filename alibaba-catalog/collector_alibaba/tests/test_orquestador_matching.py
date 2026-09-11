import json

import db
from embeddings import EmbedderImagenPorClaves, EmbedderTextoBolsaDePalabras
from matcher import ProductoMLParaMatching
from orquestador_matching import (
    _listado_a_candidatos,
    generar_query_busqueda_v1,
    procesar_candidato_matching,
)


def _conexion_memoria():
    return db.conectar(":memory:")


def _html_ficha_alibaba(subject: str, atributos: dict) -> str:
    data = {
        "globalData": {
            "product": {
                "subject": subject,
                "productBasicProperties": [{"attrName": k, "attrValue": v} for k, v in atributos.items()],
                "productKeyIndustryProperties": [],
                "mediaItems": [],
                "moq": 10,
                "customPrice": {"unitEven": "pieces"},
                "price": {"productRangePrices": {"dollarPriceRangeLow": 1.0, "dollarPriceRangeHigh": 1.0}},
            }
        }
    }
    return f"<html><script>window.detailData = {json.dumps(data)};</script></html>"


def _html_busqueda_alibaba(items: list[tuple[str, str]]) -> str:
    """items: lista de (id_alibaba, nombre) -- arma el HTML mínimo real que lee parser_busqueda_alibaba.py."""
    tarjetas = "".join(
        f'<div class="fy26-product-card-wrapper" data-ctrdot="{id_}">'
        f'<a class="searchx-product-link-wrapper" href="//www.alibaba.com/product-detail/x_{id_}.html">x</a>'
        f'<span class="searchx-product-e-title">{nombre}</span>'
        f"</div>"
        for id_, nombre in items
    )
    return f"<html><body>{tarjetas}</body></html>"


def test_generar_query_busqueda_v1_limpia_stopwords_numeros_y_recorta():
    query = generar_query_busqueda_v1("Cepillo de Limpieza Electrico Recargable para el Hogar 220v 3")
    assert "de" not in query.split()
    assert "para" not in query.split()
    assert "3" not in query.split()
    assert len(query.split()) <= 6


def test_generar_query_busqueda_v1_sin_texto_no_falla():
    assert generar_query_busqueda_v1("") == ""


def test_listado_a_candidatos_preserva_orden_y_campos():
    resultados = [
        {"id_alibaba": "1", "url_alibaba": "https://x/1.html", "nombre": "a", "imagen_url": "1.jpg", "posicion": 1},
        {"id_alibaba": "2", "url_alibaba": "https://x/2.html", "nombre": "b", "imagen_url": None, "posicion": 2},
    ]
    candidatos = _listado_a_candidatos(resultados)
    assert [c.id_alibaba for c in candidatos] == ["1", "2"]
    assert candidatos[1].imagen_url is None


def test_procesar_candidato_matching_persiste_resultado_y_actualiza_estado():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "Cepillo de silicona"})
    producto_ml = ProductoMLParaMatching(id_ml="MLA1", nombre="Cepillo de silicona para limpieza de platos")

    def obtener_html_busqueda(query):
        return _html_busqueda_alibaba([("a", "Silicone cleaning brush for dish")])

    def abrir_ficha(url):
        return _html_ficha_alibaba("Silicone Cleaning Brush", {"type": "Cleaning Brush", "material": "Silicone"})

    resultado = procesar_candidato_matching(
        candidato_id, producto_ml, conexion, obtener_html_busqueda, abrir_ficha,
        EmbedderTextoBolsaDePalabras(), EmbedderImagenPorClaves({}),
    )

    assert resultado["categoria"] in ("MATCH_ALTO", "MATCH_PROBABLE", "SIN_MATCH_CONFIABLE")
    guardado = db.obtener_ultimo_matching(conexion, candidato_id)
    assert guardado is not None
    assert guardado["categoria"] == resultado["categoria"]

    candidato = db.obtener_candidato_por_url(conexion, "https://ejemplo.test/1")
    assert candidato["estado"] in ("con_comparable", "descartado_sin_comparable")


def test_procesar_candidato_matching_prueba_segunda_estrategia_si_la_primera_no_devuelve_nada():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "Cepillo de silicona"})
    producto_ml = ProductoMLParaMatching(id_ml="MLA1", nombre="Cepillo de silicona")

    queries_probadas = []

    def obtener_html_busqueda(query):
        queries_probadas.append(query)
        if query == "primera falla":
            return _html_busqueda_alibaba([])
        return _html_busqueda_alibaba([("a", "Silicone brush")])

    def abrir_ficha(url):
        return _html_ficha_alibaba("Silicone Brush", {"type": "Cleaning Brush"})

    procesar_candidato_matching(
        candidato_id, producto_ml, conexion, obtener_html_busqueda, abrir_ficha,
        EmbedderTextoBolsaDePalabras(), EmbedderImagenPorClaves({}),
        generadores_query=[lambda n: "primera falla", lambda n: "segunda estrategia"],
    )

    assert queries_probadas == ["primera falla", "segunda estrategia"]


def test_procesar_candidato_matching_sin_resultados_en_ninguna_estrategia_queda_sin_match():
    conexion = _conexion_memoria()
    candidato_id = db.upsert_candidato_ml(conexion, {"url_ml": "https://ejemplo.test/1", "nombre": "Cepillo de silicona"})
    producto_ml = ProductoMLParaMatching(id_ml="MLA1", nombre="Cepillo de silicona")

    def obtener_html_busqueda(query):
        return _html_busqueda_alibaba([])

    def abrir_ficha(url):
        raise AssertionError("no debería abrir ninguna ficha si no hay candidatos")

    resultado = procesar_candidato_matching(
        candidato_id, producto_ml, conexion, obtener_html_busqueda, abrir_ficha,
        EmbedderTextoBolsaDePalabras(), EmbedderImagenPorClaves({}),
    )

    assert resultado["categoria"] == "SIN_MATCH_CONFIABLE"
    candidato = db.obtener_candidato_por_url(conexion, "https://ejemplo.test/1")
    assert candidato["estado"] == "descartado_sin_comparable"
