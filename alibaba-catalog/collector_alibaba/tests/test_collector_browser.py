from collector_browser import _paginas_pendientes


def test_paginas_pendientes_sin_progreso_previo():
    assert _paginas_pendientes(5, set()) == [1, 2, 3, 4, 5]


def test_paginas_pendientes_con_progreso_previo():
    assert _paginas_pendientes(5, {1, 2, 3}) == [4, 5]


def test_paginas_pendientes_todo_completado():
    assert _paginas_pendientes(5, {1, 2, 3, 4, 5}) == []


def test_paginas_pendientes_ignora_completadas_fuera_de_rango():
    assert _paginas_pendientes(3, {1, 2, 3, 4, 99}) == []
