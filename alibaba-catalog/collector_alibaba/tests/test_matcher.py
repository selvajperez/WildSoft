import json

import numpy as np
import pytest

from embeddings import EmbedderImagenPorClaves, EmbedderTextoBolsaDePalabras
from matcher import (
    CandidatoAlibabaListado,
    PesosMatching,
    ProductoMLParaMatching,
    UmbralesMatching,
    _combinar_score,
    ejecutar_matching,
    rankear_candidatos,
)


def _html_ficha_alibaba(subject: str, atributos: dict, imagenes: list[str]) -> str:
    """Arma un `window.detailData` mínimo con la misma forma real que lee parser_ficha_alibaba.py."""
    media_items = [{"type": "image", "imageUrl": {"big": url}} for url in imagenes]
    data = {
        "globalData": {
            "product": {
                "subject": subject,
                "productBasicProperties": [{"attrName": k, "attrValue": v} for k, v in atributos.items()],
                "productKeyIndustryProperties": [],
                "mediaItems": media_items,
                "moq": 10,
                "customPrice": {"unitEven": "pieces"},
                "price": {"productRangePrices": {"dollarPriceRangeLow": 1.0, "dollarPriceRangeHigh": 1.0}},
            }
        }
    }
    return f"<html><script>window.detailData = {json.dumps(data)};</script></html>"


@pytest.fixture
def embedder_texto():
    return EmbedderTextoBolsaDePalabras()


def _candidato(id_alibaba, url, nombre, imagen_url, posicion):
    return CandidatoAlibabaListado(id_alibaba=id_alibaba, url_alibaba=url, nombre=nombre, imagen_url=imagen_url, posicion=posicion)


def _vector_similar(base: np.ndarray, ruido: float = 0.0) -> np.ndarray:
    return base + ruido


IMG_ML = np.array([1.0, 0.0, 0.0])
IMG_PARECIDA = np.array([0.95, 0.05, 0.0])
IMG_DISTINTA = np.array([0.0, 0.0, 1.0])


def test_rankear_candidatos_ordena_por_similitud_de_texto_e_imagen(embedder_texto):
    producto_ml = ProductoMLParaMatching(id_ml="MLA1", nombre="cepillo de silicona para limpieza de platos", imagen_url="ml.jpg")
    candidatos = [
        _candidato("a", "https://x/a.html", "wireless bluetooth earbuds", "a.jpg", 1),
        _candidato("b", "https://x/b.html", "silicone cleaning brush kitchen dish", "b.jpg", 2),
    ]
    embedder_imagen = EmbedderImagenPorClaves({"ml.jpg": IMG_ML, "a.jpg": IMG_DISTINTA, "b.jpg": IMG_PARECIDA})

    rankeados = rankear_candidatos(producto_ml, candidatos, embedder_texto, embedder_imagen, top_k=2)

    assert [r.candidato.id_alibaba for r in rankeados] == ["b", "a"]


def test_rankear_candidatos_respeta_top_k():
    producto_ml = ProductoMLParaMatching(id_ml="MLA1", nombre="cepillo de silicona")
    candidatos = [_candidato(str(i), f"https://x/{i}.html", "cepillo de silicona", None, i) for i in range(5)]
    embedder_texto = EmbedderTextoBolsaDePalabras()
    embedder_imagen = EmbedderImagenPorClaves({})

    rankeados = rankear_candidatos(producto_ml, candidatos, embedder_texto, embedder_imagen, top_k=2)
    assert len(rankeados) == 2


def test_ejecutar_matching_sin_candidatos_no_abre_ninguna_ficha_y_no_afirma_que_no_existe(embedder_texto):
    producto_ml = ProductoMLParaMatching(id_ml="MLA1", nombre="cepillo de silicona")
    llamadas = []

    def abrir_ficha(url):
        llamadas.append(url)
        return ""

    resultado = ejecutar_matching(
        producto_ml, "cepillo de silicona", [], abrir_ficha, embedder_texto, EmbedderImagenPorClaves({})
    )

    assert resultado.categoria == "SIN_MATCH_CONFIABLE"
    assert resultado.candidato_elegido is None
    assert llamadas == []
    assert "no devolvió ningún resultado" in resultado.motivo


def test_ejecutar_matching_caso_claro_elige_el_primer_candidato_y_no_abre_los_demas(embedder_texto):
    producto_ml = ProductoMLParaMatching(
        id_ml="MLA1", nombre="Cepillo de silicona para limpieza de platos 39g", imagen_url="ml.jpg"
    )
    candidatos = [
        _candidato("real", "https://x/real.html", "Silicone cleaning brush for dish", "real.jpg", 1),
        _candidato("otro", "https://x/otro.html", "wireless earbuds bluetooth", "otro.jpg", 2),
    ]
    embedder_imagen = EmbedderImagenPorClaves({"ml.jpg": IMG_ML, "real.jpg": IMG_PARECIDA, "otro.jpg": IMG_DISTINTA})

    fichas = {
        "https://x/real.html": _html_ficha_alibaba(
            "Silicone Cleaning Brush for Dish Kitchen", {"type": "Cleaning Brush", "material": "Silicone", "weight": "39(g)"}, ["real_big.jpg"]
        ),
        "https://x/otro.html": _html_ficha_alibaba("Wireless Earbuds", {"type": "Earbuds"}, ["otro_big.jpg"]),
    }
    embedder_imagen.vectores["real_big.jpg"] = IMG_PARECIDA
    embedder_imagen.vectores["otro_big.jpg"] = IMG_DISTINTA
    llamadas = []

    def abrir_ficha(url):
        llamadas.append(url)
        return fichas[url]

    resultado = ejecutar_matching(producto_ml, "cepillo de silicona", candidatos, abrir_ficha, embedder_texto, embedder_imagen)

    assert resultado.categoria in ("MATCH_ALTO", "MATCH_PROBABLE")
    assert resultado.candidato_elegido.url_alibaba == "https://x/real.html"
    assert llamadas == ["https://x/real.html"]  # nunca abrió la ficha del segundo candidato


def test_ejecutar_matching_gemelo_tramposo_vetea_el_primero_y_elige_el_segundo(embedder_texto):
    """
    Caso pedido explícitamente por la usuaria: un candidato visualmente
    muy parecido (imagen y texto altos) pero con un atributo esencial
    incompatible (categoría: cepillo vs esponja) no puede ganar -- el
    matcher tiene que probar el siguiente candidato del top_k.
    """
    producto_ml = ProductoMLParaMatching(
        id_ml="MLA1", nombre="Cepillo de silicona para limpieza de platos 39g", imagen_url="ml.jpg"
    )
    # Mismo título de listado y misma imagen para los dos -- así el
    # ranking barato (etapa 1, sin atributos) los deja empatados y el
    # orden de apertura queda determinado por el orden original (ver
    # `sorted(..., reverse=True)`, estable): "tramposo" se abre primero,
    # justo el escenario que debe manejar la verificación de ficha.
    candidatos = [
        _candidato("tramposo", "https://x/tramposo.html", "Silicone cleaning tool for dish", "tramposo.jpg", 1),
        _candidato("real", "https://x/real.html", "Silicone cleaning tool for dish", "real.jpg", 2),
    ]
    embedder_imagen = EmbedderImagenPorClaves(
        {"ml.jpg": IMG_ML, "tramposo.jpg": IMG_PARECIDA, "real.jpg": IMG_PARECIDA}
    )

    fichas = {
        "https://x/tramposo.html": _html_ficha_alibaba(
            "Silicone Dish Washing Scrubber Sponge", {"type": "Cleaning Sponge", "material": "Silicone", "weight": "39(g)"}, ["tramposo_big.jpg"]
        ),
        "https://x/real.html": _html_ficha_alibaba(
            "Silicone Cleaning Brush for Dish Kitchen", {"type": "Cleaning Brush", "material": "Silicone", "weight": "39(g)"}, ["real_big.jpg"]
        ),
    }
    embedder_imagen.vectores["tramposo_big.jpg"] = IMG_PARECIDA
    embedder_imagen.vectores["real_big.jpg"] = IMG_PARECIDA
    llamadas = []

    def abrir_ficha(url):
        llamadas.append(url)
        return fichas[url]

    resultado = ejecutar_matching(producto_ml, "cepillo de silicona", candidatos, abrir_ficha, embedder_texto, embedder_imagen)

    assert llamadas == ["https://x/tramposo.html", "https://x/real.html"]
    primero_evaluado = resultado.candidatos_evaluados[0]
    assert primero_evaluado.veto is not None
    assert primero_evaluado.veto.tipo == "categoria"
    assert resultado.candidato_elegido is not None
    assert resultado.candidato_elegido.url_alibaba == "https://x/real.html"


def test_ejecutar_matching_sin_match_agota_todo_el_top_k(embedder_texto):
    producto_ml = ProductoMLParaMatching(id_ml="MLA1", nombre="Cepillo de silicona para limpieza de platos", imagen_url="ml.jpg")
    candidatos = [
        _candidato("a", "https://x/a.html", "wireless bluetooth speaker", "a.jpg", 1),
        _candidato("b", "https://x/b.html", "leather wallet for men", "b.jpg", 2),
    ]
    embedder_imagen = EmbedderImagenPorClaves({"ml.jpg": IMG_ML, "a.jpg": IMG_DISTINTA, "b.jpg": IMG_DISTINTA})

    fichas = {
        "https://x/a.html": _html_ficha_alibaba("Wireless Bluetooth Speaker", {"type": "Speaker"}, []),
        "https://x/b.html": _html_ficha_alibaba("Leather Wallet", {"type": "Wallet", "material": "Leather"}, []),
    }

    def abrir_ficha(url):
        return fichas[url]

    resultado = ejecutar_matching(
        producto_ml, "cepillo de silicona", candidatos, abrir_ficha, embedder_texto, embedder_imagen,
        umbrales=UmbralesMatching(match_alto=0.95, match_probable=0.85),
    )

    assert resultado.categoria == "SIN_MATCH_CONFIABLE"
    assert resultado.candidato_elegido is None
    assert len(resultado.candidatos_evaluados) == 2


def test_pesos_y_umbrales_son_configurables_no_fijos(embedder_texto):
    """Ajuste #5: con un umbral absurdamente bajo, cualquier candidato debería calificar."""
    producto_ml = ProductoMLParaMatching(id_ml="MLA1", nombre="cepillo de silicona", imagen_url="ml.jpg")
    candidatos = [_candidato("a", "https://x/a.html", "algo completamente distinto", "a.jpg", 1)]
    embedder_imagen = EmbedderImagenPorClaves({"ml.jpg": IMG_ML, "a.jpg": IMG_DISTINTA})

    def abrir_ficha(url):
        return _html_ficha_alibaba("Algo completamente distinto", {}, [])

    resultado = ejecutar_matching(
        producto_ml, "cepillo de silicona", candidatos, abrir_ficha, embedder_texto, embedder_imagen,
        umbrales=UmbralesMatching(match_alto=0.99, match_probable=-1.0),
    )
    assert resultado.categoria in ("MATCH_ALTO", "MATCH_PROBABLE")


# --- A4: re-normalización cuando falta la imagen de un lado (hallazgo real,
# Casos 1/2/4 de la validación: la ficha de ML no siempre expone foto) ------


def test_combinar_score_sin_imagen_disponible_no_cuenta_como_muy_distinta():
    pesos = PesosMatching(texto=0.45, imagen=0.35, atributos=0.20)
    con_imagen = _combinar_score(0.9, 0.0, True, 1.0, 1.0, pesos)
    sin_imagen = _combinar_score(0.9, 0.0, False, 1.0, 1.0, pesos)
    # Si la imagen realmente valiera 0.0 (muy distinta) el score con imagen
    # sería MENOR -- acá tiene que ser MAYOR, porque excluir la señal
    # ausente del promedio no es lo mismo que contarla como "muy distinta".
    assert sin_imagen > con_imagen


def test_combinar_score_solo_texto_si_no_hay_imagen_ni_atributos():
    pesos = PesosMatching(texto=0.45, imagen=0.35, atributos=0.20)
    assert _combinar_score(0.8, 0.0, False, 0.5, 0.0, pesos) == pytest.approx(0.8)


def test_combinar_score_sin_ninguna_senal_disponible_es_cero():
    pesos = PesosMatching(texto=0.0, imagen=0.0, atributos=0.0)
    assert _combinar_score(0.8, 0.9, True, 1.0, 1.0, pesos) == 0.0


def test_ejecutar_matching_sin_imagen_de_ml_puntua_mas_alto_que_si_contara_como_muy_distinta(embedder_texto):
    """
    Reproduce el patrón real de los Casos 1/2/4 (ver ESTADO_ACTUAL.md):
    sin imagen de ML, antes el 35% de peso de imagen se perdía a valor
    0.0 en vez de excluirse. Compara el score real contra el que hubiera
    dado la fórmula vieja (imagen a 0.0 pero con su peso completo) para
    el mismo caso -- tiene que ser estrictamente mayor.
    """
    producto_ml = ProductoMLParaMatching(id_ml="MLA1", nombre="Cepillo de silicona para limpieza de platos")
    candidatos = [_candidato("a", "https://x/a.html", "Silicone cleaning brush for dish", "a.jpg", 1)]
    embedder_imagen = EmbedderImagenPorClaves({})  # sin "ml.jpg" ni "a.jpg": no hay ninguna imagen real

    def abrir_ficha(url):
        return _html_ficha_alibaba("Silicone Cleaning Brush for Dish", {"type": "Cleaning Brush", "material": "Silicone"}, [])

    pesos = PesosMatching()
    resultado = ejecutar_matching(
        producto_ml, "cepillo de silicona", candidatos, abrir_ficha, embedder_texto, embedder_imagen, pesos=pesos,
        umbrales=UmbralesMatching(match_alto=0.99, match_probable=0.99),  # no importa la categoría acá, solo el score
    )

    elegido = resultado.candidatos_evaluados[0]
    assert elegido.imagen_score == 0.0  # no hay con qué comparar, se muestra en 0 pero no participó del promedio

    score_formula_vieja = (
        elegido.texto_score * pesos.texto + 0.0 * pesos.imagen + elegido.atributos_score * pesos.atributos
    ) / (pesos.texto + pesos.imagen + pesos.atributos)
    assert elegido.score_final > score_formula_vieja
