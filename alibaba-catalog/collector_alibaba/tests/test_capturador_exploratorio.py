import json
from pathlib import Path

import capturador_exploratorio as ce

DESAFIO_POW_ML = (Path(__file__).parent / "fixtures" / "ml_desafio_pow.html").read_text(encoding="utf-8")


def test_bloqueado_ml_heuristico_detecta_marcadores_provisorios():
    assert ce.bloqueado_ml_heuristico("<html>Por favor completá el CAPTCHA</html>") is True
    assert ce.bloqueado_ml_heuristico("<html>Verificación de seguridad requerida</html>") is True


def test_bloqueado_ml_heuristico_no_marca_html_normal():
    assert ce.bloqueado_ml_heuristico("<html><body>Resultados de la búsqueda</body></html>") is False


def test_es_desafio_pow_ml_detecta_html_real():
    """
    HTML real capturado al buscar "cepillo de limpieza" en Mercado Libre:
    no es el resultado de búsqueda, es el desafío Proof-of-Work de Akamai
    Bot Manager que la propia página resuelve sola con JavaScript.
    """
    assert ce.es_desafio_pow_ml(DESAFIO_POW_ML) is True


def test_es_desafio_pow_ml_no_marca_html_normal():
    assert ce.es_desafio_pow_ml("<html><body>Resultados de la búsqueda</body></html>") is False


class _PaginaFalsa:
    """Stub de una Page de Playwright: devuelve HTMLs distintos en cada `content()`."""

    def __init__(self, secuencia_html):
        self._secuencia = list(secuencia_html)
        self.esperas = 0

    def content(self):
        return self._secuencia[min(self.esperas, len(self._secuencia) - 1)]

    def wait_for_timeout(self, _ms):
        self.esperas += 1


def test_esperar_resolucion_desafio_pow_reintenta_hasta_que_se_resuelve():
    pagina = _PaginaFalsa([DESAFIO_POW_ML, DESAFIO_POW_ML, "<html><body>resultados reales</body></html>"])

    html_final = ce._esperar_resolucion_desafio_pow(pagina, intentos=5, espera_ms=1)

    assert html_final == "<html><body>resultados reales</body></html>"
    assert pagina.esperas == 2


def test_esperar_resolucion_desafio_pow_no_hace_nada_si_no_hace_falta():
    pagina = _PaginaFalsa(["<html><body>resultados reales</body></html>"])

    html_final = ce._esperar_resolucion_desafio_pow(pagina, intentos=5, espera_ms=1)

    assert html_final == "<html><body>resultados reales</body></html>"
    assert pagina.esperas == 0


def test_esperar_resolucion_desafio_pow_se_rinde_tras_agotar_intentos():
    pagina = _PaginaFalsa([DESAFIO_POW_ML])

    html_final = ce._esperar_resolucion_desafio_pow(pagina, intentos=3, espera_ms=1)

    assert ce.es_desafio_pow_ml(html_final) is True
    assert pagina.esperas == 3


def test_extraer_primer_link_producto_ml_encuentra_patron_mla():
    html = '<a href="https://articulo.mercadolibre.com.ar/MLA-123456789-candado-_JM">Candado</a>'
    assert ce._extraer_primer_link_producto_ml(html) == (
        "https://articulo.mercadolibre.com.ar/MLA-123456789-candado-_JM"
    )


def test_extraer_primer_link_producto_ml_devuelve_none_si_no_hay_patron():
    assert ce._extraer_primer_link_producto_ml("<html><body>nada</body></html>") is None


def test_guardar_html_escribe_archivo_con_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "DIR_CAPTURAS", tmp_path / "capturas")

    archivo = ce._guardar_html("ml_busqueda", "<html>contenido</html>")

    assert archivo.exists()
    assert archivo.name.startswith("ml_busqueda_")
    assert archivo.read_text(encoding="utf-8") == "<html>contenido</html>"


def test_registrar_captura_agrega_una_linea_jsonl(tmp_path, monkeypatch):
    dir_capturas = tmp_path / "capturas"
    monkeypatch.setattr(ce, "DIR_CAPTURAS", dir_capturas)
    monkeypatch.setattr(ce, "MANIFIESTO", dir_capturas / "manifiesto.jsonl")

    ce._registrar_captura("ml_busqueda", "https://ejemplo.test", tmp_path / "x.html", bloqueado=False)
    ce._registrar_captura("ml_ficha", "(no encontrado)", None, bloqueado=False)

    lineas = (dir_capturas / "manifiesto.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2

    primera = json.loads(lineas[0])
    assert primera["etiqueta"] == "ml_busqueda"
    assert primera["url"] == "https://ejemplo.test"
    assert primera["archivo"] == "x.html"
    assert primera["bloqueado"] is False

    segunda = json.loads(lineas[1])
    assert segunda["archivo"] is None
