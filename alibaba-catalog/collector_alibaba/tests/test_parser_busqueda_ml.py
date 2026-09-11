from pathlib import Path

from parser_busqueda_ml import (
    _normalizar_conteo_vendidos,
    clasificar_prioridad,
    parsear_listado_busqueda,
    resultado_a_candidato,
)

FIXTURE = (Path(__file__).parent / "fixtures" / "ml_busqueda_real.html").read_text(encoding="utf-8")


def test_parsear_listado_busqueda_extrae_los_4_casos_reales():
    resultados = parsear_listado_busqueda(FIXTURE)
    assert len(resultados) == 4


def test_caso_real_con_badge_mas_vendido_es_prioridad_a():
    resultados = parsear_listado_busqueda(FIXTURE)
    item = next(r for r in resultados if r["id_ml"] == "MLA1399281097")

    assert item["mas_vendido"] is True
    assert item["evidencia_demanda"] == "MÁS VENDIDO"
    assert item["unidades_vendidas"] is None  # el badge no es un conteo
    assert item["url_ml"] == "https://articulo.mercadolibre.com.ar/MLA1399281097"
    assert item["precio_ml"] == 3999.0
    assert item["posicion"] == 1
    assert clasificar_prioridad(item) == "A"


def test_caso_real_con_link_de_tracking_sin_ninguna_senal():
    resultados = parsear_listado_busqueda(FIXTURE)
    item = next(r for r in resultados if r["id_ml"] == "MLA2789721006")

    assert item["evidencia_demanda"] is None
    assert clasificar_prioridad(item) is None
    # aun sin señal de demanda, la URL se reconstruye igual desde el item_id
    assert item["url_ml"] == "https://articulo.mercadolibre.com.ar/MLA2789721006"


def test_caso_real_con_rating_visible_es_prioridad_b_no_demanda_confirmada():
    """
    Ajuste de semántica: el rating visible (sin cantidad de opiniones) ya
    NO cuenta como demanda confirmada -- es prioridad B (señal débil),
    solo determina el orden en que se abren las fichas, no si el
    candidato es válido.
    """
    resultados = parsear_listado_busqueda(FIXTURE)
    item = next(r for r in resultados if r["id_ml"] == "MLA2040677716")

    assert item["rating_visible"] == 4.7
    assert item["mas_vendido"] is False
    assert item["evidencia_demanda"] == "rating 4.7 (sin cantidad de opiniones visible)"
    assert clasificar_prioridad(item) == "B"


def test_caso_real_con_link_directo_de_catalogo_sin_senal():
    resultados = parsear_listado_busqueda(FIXTURE)
    item = next(r for r in resultados if r["id_ml"] == "MLA21816514")

    # link directo (/p/), no reconstruido -- se usa tal cual, recortando el "#..."
    assert item["url_ml"] == (
        "https://www.mercadolibre.com.ar/limpiavidrio-mango-aluminio-extensible-70cm-doble-cabeza/p/MLA21816514"
    )
    assert clasificar_prioridad(item) is None


def test_normalizar_conteo_vendidos_no_asume_el_numero_exacto():
    assert _normalizar_conteo_vendidos("+500 vendidos") == 500
    assert _normalizar_conteo_vendidos("+1.000 vendidos") == 1000
    assert _normalizar_conteo_vendidos("+5 mil vendidos") == 5000
    assert _normalizar_conteo_vendidos("sin ninguna mención") is None


def test_caso_sintetico_con_conteo_de_vendidos_todavia_sin_confirmar_en_grid_real():
    """
    En la búsqueda real de referencia ("cepillo de limpieza", 60
    resultados) NINGÚN resultado del grid principal mostró "+N vendidos"
    -- ese patrón solo se vio en un carrusel de recomendados dentro de
    una ficha individual, un contexto distinto. Este caso es sintético a
    propósito (no HTML real) para dejar la rama cubierta por si otra
    búsqueda sí lo muestra en el grid.
    """
    html = """
    <li class="ui-search-layout__item">
      <a class="poly-component__title" href="https://www.mercadolibre.com.ar/x/p/MLA999?position=1">Producto con ventas</a>
      <span>+500 vendidos</span>
    </li>
    """
    resultados = parsear_listado_busqueda(html)
    assert len(resultados) == 1
    assert resultados[0]["unidades_vendidas"] == 500
    assert resultados[0]["evidencia_demanda"] == "+500 vendidos"


def test_parsear_listado_busqueda_ignora_li_sin_titulo():
    html = '<li class="ui-search-layout__item"><div>banner sin producto</div></li>'
    assert parsear_listado_busqueda(html) == []


def test_parsear_listado_busqueda_ignora_li_sin_item_id_reconocible():
    html = '<li class="ui-search-layout__item"><a class="poly-component__title" href="https://ejemplo.test/sin-id">Título</a></li>'
    assert parsear_listado_busqueda(html) == []


def test_resultado_a_candidato_prioridad_a_queda_nuevo():
    resultados = parsear_listado_busqueda(FIXTURE)
    con_badge = next(r for r in resultados if r["id_ml"] == "MLA1399281097")

    candidato = resultado_a_candidato(con_badge)

    assert candidato["estado"] == "nuevo"
    assert candidato["prioridad_listado"] == "A"
    assert candidato["motivo_descarte"] is None
    assert candidato["url_ml"] == con_badge["url_ml"]


def test_resultado_a_candidato_prioridad_b_tambien_queda_nuevo_pero_marcada_como_debil():
    resultados = parsear_listado_busqueda(FIXTURE)
    con_rating = next(r for r in resultados if r["id_ml"] == "MLA2040677716")

    candidato = resultado_a_candidato(con_rating)

    assert candidato["estado"] == "nuevo"
    assert candidato["prioridad_listado"] == "B"


def test_resultado_a_candidato_sin_senal_queda_descartado_sin_abrir_ficha():
    resultados = parsear_listado_busqueda(FIXTURE)
    sin_senal = next(r for r in resultados if r["id_ml"] == "MLA2789721006")

    candidato = resultado_a_candidato(sin_senal)

    assert candidato["estado"] == "descartado_demanda_insuficiente"
    assert candidato["motivo_descarte"] is not None


def test_guardar_resultados_del_listado_en_candidatos_ml(tmp_path):
    """
    Prueba de integración liviana: los 4 resultados reales del fixture se
    guardan en candidatos_ml con el estado correcto según el prefiltro de
    demanda, sin tocar nada de collector_alibaba/db.py más que las
    funciones ya existentes.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "database"))
    import db

    conexion = db.conectar(":memory:")
    resultados = parsear_listado_busqueda(FIXTURE)

    for item in resultados:
        db.upsert_candidato_ml(conexion, resultado_a_candidato(item))

    total = conexion.execute("SELECT COUNT(*) FROM candidatos_ml").fetchone()[0]
    assert total == 4

    nuevos = conexion.execute(
        "SELECT COUNT(*) FROM candidatos_ml WHERE estado = 'nuevo'"
    ).fetchone()[0]
    descartados = conexion.execute(
        "SELECT COUNT(*) FROM candidatos_ml WHERE estado = 'descartado_demanda_insuficiente'"
    ).fetchone()[0]
    assert nuevos == 2  # badge "MÁS VENDIDO" + rating visible
    assert descartados == 2  # los dos sin ninguna señal
