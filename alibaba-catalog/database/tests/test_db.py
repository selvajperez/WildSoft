import sqlite3

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


def test_conectar_agrega_columnas_nuevas_a_una_base_existente_sin_perder_datos(tmp_path):
    """
    Simula la base real de 224 productos, creada antes de agregar
    compra_directa/envio_calculable: conectar() debe agregar las columnas
    faltantes con ALTER TABLE (CREATE TABLE IF NOT EXISTS no las agrega
    retroactivamente) sin tocar los datos ya guardados.
    """
    ruta = tmp_path / "catalogo_viejo.db"
    conexion_vieja = sqlite3.connect(ruta)
    conexion_vieja.execute("""
        CREATE TABLE productos_alibaba (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id_alibaba INTEGER,
            nombre TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            precio_min REAL,
            precio_max REAL,
            moneda TEXT,
            moq TEXT,
            cantidad_vendida INTEGER,
            imagen_principal TEXT,
            categoria_id INTEGER,
            categoria TEXT,
            peso_gramos REAL,
            fecha_scrapeo TEXT NOT NULL
        )
    """)
    conexion_vieja.execute(
        "INSERT INTO productos_alibaba (nombre, url, fecha_scrapeo) VALUES (?, ?, ?)",
        ("Producto ya guardado", "https://ejemplo.test/viejo", "2026-01-01T00:00:00+00:00"),
    )
    conexion_vieja.commit()
    conexion_vieja.close()

    conexion = db.conectar(ruta)

    columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(productos_alibaba)")}
    assert {"compra_directa", "envio_calculable"} <= columnas

    assert db.contar_productos(conexion) == 1
    fila = conexion.execute(
        "SELECT nombre, compra_directa, envio_calculable FROM productos_alibaba WHERE url = ?",
        ("https://ejemplo.test/viejo",),
    ).fetchone()
    assert fila == ("Producto ya guardado", None, None)
