from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

import navegador_ml as nav

DESAFIO_POW_ML = (Path(__file__).parent / "fixtures" / "ml_desafio_pow.html").read_text(encoding="utf-8")
BLOQUEO_TRAFICO_SOSPECHOSO_ML = (
    Path(__file__).parent / "fixtures" / "ml_bloqueo_trafico_sospechoso_real.html"
).read_text(encoding="utf-8")


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


def test_es_bloqueo_trafico_sospechoso_ml_detecta_html_real():
    """
    Hallazgo real (corrida de medicion_confiabilidad_ml.py del
    2026-09-11): a mitad de una corrida larga, ML empezó a devolver esta
    pantalla de "tráfico sospechoso" (pide loguearse o registrarse) para
    TODAS las fichas siguientes, directas y de tracking por igual. A
    diferencia del desafío PoW, esto sí necesita una persona.
    """
    assert nav.es_bloqueo_trafico_sospechoso_ml(BLOQUEO_TRAFICO_SOSPECHOSO_ML) is True


def test_es_bloqueo_trafico_sospechoso_ml_no_marca_html_normal():
    assert nav.es_bloqueo_trafico_sospechoso_ml("<html><body>Resultados de la búsqueda</body></html>") is False
    assert nav.es_bloqueo_trafico_sospechoso_ml(DESAFIO_POW_ML) is False  # no confundir con el desafío PoW


class _PaginaFalsa:
    """Stub de una Page de Playwright: devuelve HTMLs distintos en cada `content()`."""

    def __init__(self, secuencia_html):
        self._secuencia = list(secuencia_html)
        self.esperas = 0

    def content(self):
        return self._secuencia[min(self.esperas, len(self._secuencia) - 1)]

    def wait_for_timeout(self, _ms):
        self.esperas += 1


def test_esperar_marcador_en_pagina_reintenta_hasta_que_aparece():
    """
    Hallazgo real: una búsqueda capturó una página de 1.1MB con título
    normal pero 0 apariciones de "ui-search-layout" (el listado real
    renderiza con React después de domcontentloaded). Esta espera evita
    devolver el HTML antes de que el listado esté.
    """
    pagina = _PaginaFalsa(["<html><body>cargando...</body></html>", "<html><body><li class=\"ui-search-layout__item\">real</li></body></html>"])

    html_final = nav.esperar_marcador_en_pagina(pagina, "ui-search-layout", intentos=5, espera_ms=1)

    assert "ui-search-layout" in html_final
    assert pagina.esperas == 1


def test_esperar_marcador_en_pagina_no_hace_nada_si_ya_esta():
    pagina = _PaginaFalsa(["<html><body><li class=\"ui-search-layout__item\">real</li></body></html>"])

    html_final = nav.esperar_marcador_en_pagina(pagina, "ui-search-layout", intentos=5, espera_ms=1)

    assert pagina.esperas == 0
    assert "ui-search-layout" in html_final


def test_esperar_marcador_en_pagina_se_rinde_tras_agotar_intentos():
    pagina = _PaginaFalsa(["<html><body>cargando...</body></html>"])

    html_final = nav.esperar_marcador_en_pagina(pagina, "ui-search-layout", intentos=3, espera_ms=1)

    assert "ui-search-layout" not in html_final
    assert pagina.esperas == 3


def test_abrir_pagina_ml_espera_el_marcador_de_listado_si_se_pide():
    class _PaginaConGoto(_PaginaFalsa):
        def goto(self, _url, wait_until=None):
            pass

    pagina = _PaginaConGoto([
        "<html><body>cargando...</body></html>",
        "<html><body><li class=\"ui-search-layout__item\">real</li></body></html>",
    ])
    html = nav.abrir_pagina_ml(pagina, "https://listado.mercadolibre.com.ar/x", "búsqueda", esperar_marcador="ui-search-layout")

    assert "ui-search-layout" in html


def test_abrir_pagina_ml_sin_esperar_marcador_no_espera_de_mas():
    class _PaginaConGoto(_PaginaFalsa):
        def goto(self, _url, wait_until=None):
            pass

    pagina = _PaginaConGoto(["<html><body>ficha normal</body></html>"])
    html = nav.abrir_pagina_ml(pagina, "https://www.mercadolibre.com.ar/p/MLA1", "ficha")

    assert html == "<html><body>ficha normal</body></html>"
    assert pagina.esperas == 0


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


class _PaginaConGotoQueFallaYLuegoResponde:
    """
    Stub de `Page` para `goto_seguro`: falla con `PlaywrightError` un par
    de veces (simula la navegación interrumpida real vista en Alibaba,
    ver Match Mode) antes de "aterrizar" bien.
    """

    def __init__(self, fallos_antes_de_exito: int):
        self.fallos_restantes = fallos_antes_de_exito
        self.intentos = 0
        self.esperas = 0

    def goto(self, _url, wait_until=None):
        self.intentos += 1
        if self.fallos_restantes > 0:
            self.fallos_restantes -= 1
            raise PlaywrightError("Navigation to '...' is interrupted by another navigation to '...'")

    def wait_for_timeout(self, _ms):
        self.esperas += 1


def test_goto_seguro_reintenta_ante_navegacion_interrumpida():
    pagina = _PaginaConGotoQueFallaYLuegoResponde(fallos_antes_de_exito=2)

    nav.goto_seguro(pagina, "https://x/ficha.html", intentos=3, espera_ms=1)

    assert pagina.intentos == 3
    assert pagina.esperas == 2


def test_goto_seguro_relanza_el_error_si_se_agotan_los_intentos():
    pagina = _PaginaConGotoQueFallaYLuegoResponde(fallos_antes_de_exito=10)

    try:
        nav.goto_seguro(pagina, "https://x/ficha.html", intentos=3, espera_ms=1)
        assert False, "debería haber relanzado PlaywrightError"
    except PlaywrightError:
        pass

    assert pagina.intentos == 3


def test_abrir_pagina_ml_usa_goto_seguro():
    class _PaginaConGoto(_PaginaFalsa):
        def __init__(self, secuencia_html):
            super().__init__(secuencia_html)
            self.intentos_goto = 0

        def goto(self, _url, wait_until=None):
            self.intentos_goto += 1
            if self.intentos_goto == 1:
                raise PlaywrightError("Navigation to '...' is interrupted by another navigation to '...'")

    pagina = _PaginaConGoto(["<html><body>resultados reales</body></html>"])
    html = nav.abrir_pagina_ml(pagina, "https://listado.mercadolibre.com.ar/x", "búsqueda de prueba")

    assert html == "<html><body>resultados reales</body></html>"
    assert pagina.intentos_goto == 2


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


def test_abrir_pagina_ml_pausa_ante_el_bloqueo_de_trafico_sospechoso(monkeypatch):
    """
    Antes de agregar `es_bloqueo_trafico_sospechoso_ml`, esta pantalla no
    la detectaba ni el heurístico genérico ni el desafío PoW -- la
    corrida seguía en silencio devolviendo esta página como si fuera una
    ficha normal (de ahí el otro_error masivo real). Ahora tiene que
    pausar y, al "resolverse" (ENTER + reload), devolver el contenido real.
    """
    class _PaginaBloqueadaQueSeResuelve:
        def __init__(self):
            self._resuelta = False

        def goto(self, _url, wait_until=None):
            pass

        def reload(self, wait_until=None):
            self._resuelta = True

        def content(self):
            return "<html><body>ficha real</body></html>" if self._resuelta else BLOQUEO_TRAFICO_SOSPECHOSO_ML

    monkeypatch.setattr("builtins.input", lambda: "")

    pagina = _PaginaBloqueadaQueSeResuelve()
    html = nav.abrir_pagina_ml(pagina, "https://www.mercadolibre.com.ar/p/MLA123", "ficha de prueba")

    assert html == "<html><body>ficha real</body></html>"


def test_pausar_por_bloqueo_y_continuar_vuelve_a_esperar_si_sigue_bloqueado(monkeypatch):
    """
    Manejo humano del bloqueo: si después de un Enter el bloqueo sigue
    presente, no puede avanzar igual ni darlo por resuelto -- tiene que
    volver a pausar (sin timeout corto) hasta que realmente desaparezca.
    """
    class _PaginaBloqueadaDosVeces:
        def __init__(self):
            self.reloads = 0

        def reload(self, wait_until=None):
            self.reloads += 1

        def content(self):
            if self.reloads < 2:
                return BLOQUEO_TRAFICO_SOSPECHOSO_ML
            return "<html><body>ficha real</body></html>"

    llamadas_a_input = []
    monkeypatch.setattr("builtins.input", lambda: llamadas_a_input.append(1))

    pagina = _PaginaBloqueadaDosVeces()
    html = nav.pausar_por_bloqueo_y_continuar(pagina, "https://www.mercadolibre.com.ar/p/MLA123", "ficha de prueba")

    assert html == "<html><body>ficha real</body></html>"
    assert pagina.reloads == 2  # se recargó (y verificó) dos veces antes de darlo por resuelto
    assert len(llamadas_a_input) == 2  # pausó dos veces -- nunca avanzó con el bloqueo todavía activo


def test_esperar_entre_fichas_respeta_el_rango(monkeypatch):
    monkeypatch.setattr(nav.time, "sleep", lambda _s: None)

    for _ in range(30):
        espera = nav.esperar_entre_fichas(2.0, 5.0)
        assert 2.0 <= espera <= 5.0


def test_esperar_entre_fichas_usa_los_defaults_del_hallazgo_real(monkeypatch):
    dormidos = []
    monkeypatch.setattr(nav.time, "sleep", dormidos.append)

    espera = nav.esperar_entre_fichas()

    assert dormidos == [espera]
    assert nav.DELAY_MIN_SEG_DEFAULT <= espera <= nav.DELAY_MAX_SEG_DEFAULT
