from pathlib import Path

from medicion_confiabilidad_ml import _clasificar_intento, agregar_resumen, medir_busqueda

BUSQUEDA_REAL = (Path(__file__).parent / "fixtures" / "ml_busqueda_real.html").read_text(encoding="utf-8")
FICHA_REAL = (Path(__file__).parent / "fixtures" / "ml_ficha_real.html").read_text(encoding="utf-8")
FICHA_NO_ENCONTRADA_REAL = (
    Path(__file__).parent / "fixtures" / "ml_ficha_no_encontrada_real.html"
).read_text(encoding="utf-8")


# --- _clasificar_intento (lógica pura) --------------------------------------

def test_clasificar_intento_abierta_ok_con_precio():
    assert _clasificar_intento({"precio_ml": 1000, "unidades_vendidas": None, "pagina_no_encontrada": False}) == "abierta_ok"


def test_clasificar_intento_abierta_ok_con_ventas():
    assert _clasificar_intento({"precio_ml": None, "unidades_vendidas": 50, "pagina_no_encontrada": False}) == "abierta_ok"


def test_clasificar_intento_404_tiene_prioridad_aunque_falten_los_otros_campos():
    assert _clasificar_intento({"precio_ml": None, "unidades_vendidas": None, "pagina_no_encontrada": True}) == "404"


def test_clasificar_intento_otro_error_si_no_hay_nada_y_no_es_404():
    assert _clasificar_intento({"precio_ml": None, "unidades_vendidas": None, "pagina_no_encontrada": False}) == "otro_error"


# --- medir_busqueda con datos reales inyectados -----------------------------
#
# El listado real (fixture de 4 casos: 1 prioridad A, 1 prioridad B, 2 sin
# señal) se combina con dos fichas reales distintas inyectadas según el
# id_ml -- una que abre bien y otra que es el 404 real -- para ejercitar
# ambas ramas con HTML 100% real. La separación por origen_url (directo
# vs. tracking) se prueba aparte, con datos sintéticos, en
# test_agregar_resumen_calcula_total_y_por_origen -- en este fixture de 4
# casos ambos resultados con prioridad (A y B) resultan ser "tracking".

def _abrir_busqueda_real(_url: str) -> str:
    return BUSQUEDA_REAL


def _abrir_ficha_mixta(url: str, _etiqueta: str) -> str:
    # La ficha de prioridad A (MLA1399281097) es la que "funciona" en este
    # escenario de prueba; la de prioridad B (MLA2040677716) es la que da 404.
    if "MLA2040677716" in url or "2040677716" in url:
        return FICHA_NO_ENCONTRADA_REAL
    return FICHA_REAL


def test_medir_busqueda_solo_abre_fichas_prioridad_a_y_b():
    intentos = medir_busqueda("cepillo de limpieza", _abrir_busqueda_real, _abrir_ficha_mixta, max_fichas_por_busqueda=15)
    assert len(intentos) == 2  # los 2 "sin señal" del fixture nunca se abren
    assert {i["id_ml"] for i in intentos} == {"MLA1399281097", "MLA2040677716"}


def test_medir_busqueda_clasifica_cada_intento_correctamente():
    intentos = medir_busqueda("cepillo de limpieza", _abrir_busqueda_real, _abrir_ficha_mixta, max_fichas_por_busqueda=15)

    por_id = {i["id_ml"]: i for i in intentos}
    assert por_id["MLA1399281097"]["resultado"] == "abierta_ok"
    assert por_id["MLA1399281097"]["origen_url"] == "tracking"
    assert por_id["MLA1399281097"]["prioridad_listado"] == "A"

    assert por_id["MLA2040677716"]["resultado"] == "404"
    assert por_id["MLA2040677716"]["origen_url"] == "tracking"
    assert por_id["MLA2040677716"]["prioridad_listado"] == "B"


def test_medir_busqueda_respeta_max_fichas_por_busqueda():
    intentos = medir_busqueda("cepillo de limpieza", _abrir_busqueda_real, _abrir_ficha_mixta, max_fichas_por_busqueda=1)
    assert len(intentos) == 1
    assert intentos[0]["id_ml"] == "MLA1399281097"  # prioridad A siempre antes que B


# --- agregar_resumen ---------------------------------------------------------

def test_agregar_resumen_calcula_total_y_por_origen():
    intentos = [
        {"origen_url": "tracking", "resultado": "abierta_ok"},
        {"origen_url": "tracking", "resultado": "404"},
        {"origen_url": "tracking", "resultado": "404"},
        {"origen_url": "directo", "resultado": "abierta_ok"},
        {"origen_url": "directo", "resultado": "abierta_ok"},
        {"origen_url": "directo", "resultado": "otro_error"},
    ]

    resumen = agregar_resumen(intentos)

    assert resumen["total"]["fichas_intentadas"] == 6
    assert resumen["total"]["fichas_abiertas_ok"] == 3
    assert resumen["total"]["fichas_404"] == 2
    assert resumen["total"]["otros_errores"] == 1
    assert resumen["total"]["pct_exito"] == 50.0

    assert resumen["tracking"]["fichas_intentadas"] == 3
    assert resumen["tracking"]["fichas_404"] == 2
    assert resumen["tracking"]["pct_perdida_404"] == round(200 / 3, 1)

    assert resumen["directo"]["fichas_intentadas"] == 3
    assert resumen["directo"]["fichas_404"] == 0
    assert resumen["directo"]["pct_exito"] == round(200 / 3, 1)


def test_agregar_resumen_no_rompe_con_lista_vacia():
    resumen = agregar_resumen([])
    assert resumen["total"]["fichas_intentadas"] == 0
    assert resumen["total"]["pct_exito"] == 0.0
    assert resumen["tracking"]["fichas_intentadas"] == 0
