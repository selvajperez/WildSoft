import numpy as np

from embeddings import (
    EmbedderImagenPorClaves,
    EmbedderTextoBolsaDePalabras,
    similitud_coseno,
)


def test_similitud_coseno_vectores_identicos_es_uno():
    v = np.array([1.0, 2.0, 3.0])
    assert similitud_coseno(v, v) == 1.0


def test_similitud_coseno_vectores_ortogonales_es_cero():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert similitud_coseno(a, b) == 0.0


def test_similitud_coseno_con_vector_faltante_es_cero():
    assert similitud_coseno(None, np.array([1.0, 2.0])) == 0.0
    assert similitud_coseno(np.array([1.0, 2.0]), None) == 0.0
    assert similitud_coseno(None, None) == 0.0


def test_similitud_coseno_con_vector_nulo_es_cero():
    assert similitud_coseno(np.zeros(3), np.array([1.0, 2.0, 3.0])) == 0.0


def test_embedder_texto_bolsa_de_palabras_es_deterministico():
    embedder = EmbedderTextoBolsaDePalabras()
    assert np.array_equal(embedder.embed("cepillo de limpieza"), embedder.embed("cepillo de limpieza"))


def test_embedder_texto_bolsa_de_palabras_texto_vacio_devuelve_none():
    embedder = EmbedderTextoBolsaDePalabras()
    assert embedder.embed("") is None
    assert embedder.embed(None) is None


def test_embedder_texto_bolsa_de_palabras_textos_con_palabras_compartidas_son_mas_similares():
    embedder = EmbedderTextoBolsaDePalabras()
    base = embedder.embed("silicone dish brush kitchen")
    parecido = embedder.embed("silicone dish sponge kitchen")
    distinto = embedder.embed("wireless bluetooth earbuds headphones")

    sim_parecido = similitud_coseno(base, parecido)
    sim_distinto = similitud_coseno(base, distinto)
    assert sim_parecido > sim_distinto


def test_embedder_imagen_por_claves_devuelve_vector_registrado():
    vector = np.array([1.0, 0.0])
    embedder = EmbedderImagenPorClaves({"https://x/img.jpg": vector})
    assert np.array_equal(embedder.embed("https://x/img.jpg"), vector)


def test_embedder_imagen_por_claves_url_no_registrada_devuelve_default():
    embedder = EmbedderImagenPorClaves({}, vector_por_defecto=None)
    assert embedder.embed("https://x/no-existe.jpg") is None
