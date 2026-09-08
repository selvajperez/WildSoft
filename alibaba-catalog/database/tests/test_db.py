import db


def _conexion_memoria():
    return db.conectar(":memory:")


def test_obtener_paginas_completadas_vacio_al_principio():
    conexion = _conexion_memoria()
    assert db.obtener_paginas_completadas(conexion) == set()


def test_marcar_y_obtener_paginas_completadas():
    conexion = _conexion_memoria()
    db.marcar_pagina_completada(conexion, 1)
    db.marcar_pagina_completada(conexion, 3)

    assert db.obtener_paginas_completadas(conexion) == {1, 3}


def test_marcar_pagina_completada_es_idempotente():
    conexion = _conexion_memoria()
    db.marcar_pagina_completada(conexion, 5)
    db.marcar_pagina_completada(conexion, 5)

    assert db.obtener_paginas_completadas(conexion) == {5}


def test_reiniciar_progreso_borra_todo():
    conexion = _conexion_memoria()
    db.marcar_pagina_completada(conexion, 1)
    db.marcar_pagina_completada(conexion, 2)

    db.reiniciar_progreso(conexion)

    assert db.obtener_paginas_completadas(conexion) == set()


def test_reiniciar_progreso_no_toca_los_productos_guardados():
    conexion = _conexion_memoria()
    db.upsert_producto(conexion, {"nombre": "Producto de prueba", "url": "https://ejemplo.test/1"})
    conexion.commit()
    db.marcar_pagina_completada(conexion, 1)

    db.reiniciar_progreso(conexion)

    assert db.contar_productos(conexion) == 1
    assert db.obtener_paginas_completadas(conexion) == set()
