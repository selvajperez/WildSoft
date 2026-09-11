from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

import navegador_ml as nav

DESAFIO_POW_ML = (Path(__file__).parent / "fixtures" / "ml_desafio_pow.html").read_text(encoding="utf-8")


def test_bloqueado_ml_heuristico_detecta_marcadores_provisorios():
    assert nav.bloqueado_ml_heuristico("<html>Por favor completá el CAPTCHA</html>") is True
    assert nav.bloqueado_ml_heuristico("<html>Verificación de seguridad requerida</html>") is True


def test_bloqueado_ml_heuristico_no_marca_html_normal():
    assert nav.bloqueado_ml_heuristico("<html><body>Resultados de la búsqueda</body></html>") is False


def test_es_desafio_pow_ml_detecta_html_real():
    """
    HTML real capturado al buscar "cepillo de limpieza" en Mercado Libre:
    no es el resultado de búsqueda, es el desafío Proof-of-Work de Akamai
    Bot Manager que la propia página resuelve sola con JavaScript.
    """
    assert nav.es_desafio_pow_ml(DESAFIO_POW_ML) is True


def test_es_desafio_pow_ml_no_marca_html_normal():
    assert nav.es_desafio_pow_ml("<html><body>Resultados de la búsqueda</body></html>") is False


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

    html_final = nav.esperar_resolucion_desafio_pow(pagina, intentos=5, espera_ms=1)

    assert html_final == "<html><body>resultados reales</body></html>"
    assert pagina.esperas == 2


def test_esperar_resolucion_desafio_pow_no_hace_nada_si_no_hace_falta():
    pagina = _PaginaFalsa(["<html><body>resultados reales</body></html>"])

    html_final = nav.esperar_resolucion_desafio_pow(pagina, intentos=5, espera_ms=1)

    assert html_final == "<html><body>resultados reales</body></html>"
    assert pagina.esperas == 0


def test_esperar_resolucion_desafio_pow_se_rinde_tras_agotar_intentos():
    pagina = _PaginaFalsa([DESAFIO_POW_ML])

    html_final = nav.esperar_resolucion_desafio_pow(pagina, intentos=3, espera_ms=1)

    assert nav.es_desafio_pow_ml(html_final) is True
    assert pagina.esperas == 3


class _PaginaQueFallaYLuegoResponde:
    """
    Stub que reproduce el error real de Playwright: `content()` falla
    mientras la página está navegando, y funciona apenas se estabiliza.
    """

    def __init__(self, fallos_antes_de_responder: int, html_final: str):
        self._fallos_restantes = fallos_antes_de_responder
        self._html_final = html_final
        self.esperas = 0

    def content(self):
        if self._fallos_restantes > 0:
            self._fallos_restantes -= 1
            raise PlaywrightError("Page.content: Unable to retrieve content because the page is navigating")
        return self._html_final

    def wait_for_timeout(self, _ms):
        self.esperas += 1


def test_contenido_seguro_reintenta_ante_error_de_navegacion_transitorio():
    pagina = _PaginaQueFallaYLuegoResponde(fallos_antes_de_responder=2, html_final="<html>listo</html>")

    assert nav.contenido_seguro(pagina, intentos=5, espera_ms=1) == "<html>listo</html>"
    assert pagina.esperas == 2


def test_contenido_seguro_relanza_el_error_si_nunca_se_estabiliza():
    pagina = _PaginaQueFallaYLuegoResponde(fallos_antes_de_responder=10, html_final="<html>listo</html>")

    try:
        nav.contenido_seguro(pagina, intentos=3, espera_ms=1)
        assert False, "debería haber relanzado PlaywrightError"
    except PlaywrightError:
        pass


def test_abrir_pagina_ml_espera_el_desafio_pow_y_devuelve_contenido_real():
    class _PaginaConGoto(_PaginaFalsa):
        def goto(self, _url, wait_until=None):
            pass

    pagina = _PaginaConGoto([DESAFIO_POW_ML, "<html><body>resultados reales</body></html>"])
    html = nav.abrir_pagina_ml(pagina, "https://listado.mercadolibre.com.ar/x", "búsqueda de prueba")

    assert html == "<html><body>resultados reales</body></html>"


def test_abrir_pagina_ml_sin_desafio_devuelve_directo():
    class _PaginaConGoto(_PaginaFalsa):
        def goto(self, _url, wait_until=None):
            pass

    pagina = _PaginaConGoto(["<html><body>resultados reales</body></html>"])
    html = nav.abrir_pagina_ml(pagina, "https://listado.mercadolibre.com.ar/x", "búsqueda de prueba")

    assert html == "<html><body>resultados reales</body></html>"
