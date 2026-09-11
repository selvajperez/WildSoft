import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "database"))
import db  # noqa: E402

from orquestador_demanda_ml import _determinar_resultado_ficha, procesar_busqueda_ml  # noqa: E402

BUSQUEDA_REAL = (Path(__file__).parent / "fixtures" / "ml_busqueda_real.html").read_text(encoding="utf-8")
FICHA_REAL = (Path(__file__).parent / "fixtures" / "ml_ficha_real.html").read_text(encoding="utf-8")


def _conexion_memoria():
    return db.conectar(":memory:")


# --- _determinar_resultado_ficha (lógica pura) ------------------------------

def test_determinar_resultado_ficha_confirma_demanda_sobre_el_umbral():
    estado, motivo = _determinar_resultado_ficha({"precio_ml": 1000, "unidades_vendidas": 1000}, umbral_unidades_vendidas=50)
    assert estado == "demanda_confirmada"
    assert "1000" in motivo and "50" in motivo


def test_determinar_resultado_ficha_descarta_bajo_el_umbral():
    estado, motivo = _determinar_resultado_ficha({"precio_ml": 1000, "unidades_vendidas": 10}, umbral_unidades_vendidas=50)
    assert estado == "descartado_demanda_no_confirmada"
    assert "10" in motivo and "50" in motivo


def test_determinar_resultado_ficha_indeterminado_si_no_expone_ventas():
    estado, motivo = _determinar_resultado_ficha({"precio_ml": 1000, "unidades_vendidas": None}, umbral_unidades_vendidas=50)
    assert estado == "indeterminado_ficha"


def test_determinar_resultado_ficha_indeterminado_si_no_se_extrajo_nada():
    estado, motivo = _determinar_resultado_ficha({"precio_ml": None, "unidades_vendidas": None}, umbral_unidades_vendidas=50)
    assert estado == "indeterminado_ficha"
    assert "no se pudo extraer" in motivo.lower()


# --- procesar_busqueda_ml con datos reales inyectados -----------------------
#
# La búsqueda real (4 casos reales: 1 prioridad A, 1 prioridad B, 2 sin
# señal) y la única ficha real que se capturó hasta ahora (item
# MLA2023730583, 1000 unidades vendidas confirmadas) se inyectan como
# funciones -- sin esto no se podría probar el flujo completo sin un
# navegador real. Es HTML 100% real en ambos casos; lo que es una
# simplificación es reusar la MISMA ficha real para cualquier candidato
# que se abra (no tenemos fichas reales de los candidatos concretos de
# esta búsqueda todavía) -- documentado acá a propósito, no escondido.

def _abrir_busqueda_real(_url: str) -> str:
    return BUSQUEDA_REAL


def _abrir_ficha_real(_url: str, _etiqueta: str) -> str:
    return FICHA_REAL


def test_procesar_busqueda_ml_con_datos_reales_confirma_demanda():
    conexion = _conexion_memoria()

    resumen = procesar_busqueda_ml(
        "cepillo de limpieza", conexion, _abrir_busqueda_real, _abrir_ficha_real,
        max_fichas_por_busqueda=15, candidatos_objetivo=5, umbral_unidades_vendidas=50,
    )

    assert resumen["extraidos"] == 4
    assert resumen["prioridad_a"] == 1
    assert resumen["prioridad_b"] == 1
    assert resumen["sin_senal"] == 2
    # Solo se abren fichas de A y B -- los 2 "sin_senal" nunca se tocan.
    assert resumen["fichas_abiertas"] == 2
    assert resumen["demanda_confirmada"] == 2  # la ficha real muestra 1000 vendidas, sobre el umbral de 50
    assert resumen["descartado_demanda_no_confirmada"] == 0
    assert resumen["indeterminado_ficha"] == 0
    assert resumen["detenido_por"] == "sin_mas_candidatos_en_cola"

    total_candidatos = conexion.execute("SELECT COUNT(*) FROM candidatos_ml").fetchone()[0]
    assert total_candidatos == 4
    confirmados = conexion.execute(
        "SELECT COUNT(*) FROM candidatos_ml WHERE estado = 'demanda_confirmada'"
    ).fetchone()[0]
    assert confirmados == 2


def test_procesar_busqueda_ml_con_umbral_alto_descarta_por_demanda_no_confirmada():
    conexion = _conexion_memoria()

    resumen = procesar_busqueda_ml(
        "cepillo de limpieza", conexion, _abrir_busqueda_real, _abrir_ficha_real,
        umbral_unidades_vendidas=5000,  # la ficha real tiene 1000 -- queda por debajo
    )

    assert resumen["demanda_confirmada"] == 0
    assert resumen["descartado_demanda_no_confirmada"] == 2


def test_procesar_busqueda_ml_respeta_max_fichas_configurado():
    conexion = _conexion_memoria()

    resumen = procesar_busqueda_ml(
        "cepillo de limpieza", conexion, _abrir_busqueda_real, _abrir_ficha_real,
        max_fichas_por_busqueda=1, candidatos_objetivo=5,
    )

    assert resumen["fichas_abiertas"] == 1
    assert resumen["detenido_por"] == "max_fichas_alcanzado"


def test_procesar_busqueda_ml_se_detiene_al_alcanzar_el_objetivo():
    conexion = _conexion_memoria()

    resumen = procesar_busqueda_ml(
        "cepillo de limpieza", conexion, _abrir_busqueda_real, _abrir_ficha_real,
        max_fichas_por_busqueda=15, candidatos_objetivo=1,
    )

    assert resumen["fichas_abiertas"] == 1
    assert resumen["demanda_confirmada"] == 1
    assert resumen["detenido_por"] == "candidatos_objetivo_alcanzado"


def test_procesar_busqueda_ml_prioridad_a_se_abre_antes_que_b():
    conexion = _conexion_memoria()

    resumen = procesar_busqueda_ml(
        "cepillo de limpieza", conexion, _abrir_busqueda_real, _abrir_ficha_real,
        max_fichas_por_busqueda=1, candidatos_objetivo=5,
    )

    # con max_fichas=1 solo se abre UNA ficha -- tiene que ser la de prioridad A
    assert resumen["detalle"][0]["id_ml"] == "MLA1399281097"  # el del badge "MÁS VENDIDO" en el fixture


def test_procesar_busqueda_ml_guarda_observacion_real_en_historial():
    conexion = _conexion_memoria()

    procesar_busqueda_ml(
        "cepillo de limpieza", conexion, _abrir_busqueda_real, _abrir_ficha_real,
        max_fichas_por_busqueda=1, candidatos_objetivo=5,
    )

    fila = conexion.execute(
        "SELECT precio, stock_visible, unidades_vendidas_visible, cantidad_opiniones, rating "
        "FROM historial_ml LIMIT 1"
    ).fetchone()
    assert fila == (68780.0, 5, 1000, 273, 4.2)


def test_procesar_busqueda_ml_registra_motivo_explicito_por_candidato():
    conexion = _conexion_memoria()

    resumen = procesar_busqueda_ml(
        "cepillo de limpieza", conexion, _abrir_busqueda_real, _abrir_ficha_real,
        max_fichas_por_busqueda=15, candidatos_objetivo=5,
    )

    for entrada in resumen["detalle"]:
        assert entrada["motivo"]  # nunca vacío/None -- siempre hay una explicación guardable
