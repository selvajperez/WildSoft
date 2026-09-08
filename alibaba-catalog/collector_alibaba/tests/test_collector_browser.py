import collector_browser
from collector_browser import _guardar_html_crudo, _paginas_pendientes


def test_paginas_pendientes_sin_progreso_previo():
    assert _paginas_pendientes(5, set()) == [1, 2, 3, 4, 5]


def test_paginas_pendientes_con_progreso_previo():
    assert _paginas_pendientes(5, {1, 2, 3}) == [4, 5]


def test_paginas_pendientes_todo_completado():
    assert _paginas_pendientes(5, {1, 2, 3, 4, 5}) == []


def test_paginas_pendientes_ignora_completadas_fuera_de_rango():
    assert _paginas_pendientes(3, {1, 2, 3, 4, 99}) == []


def test_guardar_html_crudo_escribe_un_archivo_por_pagina(tmp_path, monkeypatch):
    monkeypatch.setattr(collector_browser, "DIR_HTML_CRUDO", tmp_path / "paginas_html_crudo")

    _guardar_html_crudo(3, "<html>contenido de la página 3</html>")

    archivo = tmp_path / "paginas_html_crudo" / "productlist-3.html"
    assert archivo.read_text(encoding="utf-8") == "<html>contenido de la página 3</html>"
