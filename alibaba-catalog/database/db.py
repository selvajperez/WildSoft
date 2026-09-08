"""
Persistencia en SQLite del catálogo scrapeado.

Un único archivo (`catalogo_alibaba.db` por defecto) con dos tablas:
`productos_alibaba` (el upsert deduplica por `url`, estable entre corridas
del collector) y `progreso_paginas` (qué páginas de listado ya se
recorrieron con éxito, para poder retomar sin repetirlas si el collector
se corta a mitad de camino).
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH_DEFAULT = Path(__file__).parent / "catalogo_alibaba.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS productos_alibaba (
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
    compra_directa INTEGER,
    envio_calculable INTEGER,
    fecha_scrapeo TEXT NOT NULL
);
"""

COLUMNAS_PRODUCTO = [
    "producto_id_alibaba", "nombre", "url", "precio_min", "precio_max", "moneda",
    "moq", "cantidad_vendida", "imagen_principal", "categoria_id", "categoria",
    "peso_gramos", "compra_directa", "envio_calculable",
]

# Columnas agregadas después de la creación inicial de la tabla: en una base
# ya existente (CREATE TABLE IF NOT EXISTS no las agrega retroactivamente),
# hace falta un ALTER TABLE explícito para no perder los datos ya guardados.
_MIGRACIONES_PRODUCTOS = {
    "compra_directa": "ALTER TABLE productos_alibaba ADD COLUMN compra_directa INTEGER",
    "envio_calculable": "ALTER TABLE productos_alibaba ADD COLUMN envio_calculable INTEGER",
}


def _migrar_columnas_faltantes(conexion: sqlite3.Connection) -> None:
    columnas_existentes = {fila[1] for fila in conexion.execute("PRAGMA table_info(productos_alibaba)")}
    for columna, sentencia in _MIGRACIONES_PRODUCTOS.items():
        if columna not in columnas_existentes:
            conexion.execute(sentencia)
    conexion.commit()

ESQUEMA_PROGRESO = """
CREATE TABLE IF NOT EXISTS progreso_paginas (
    pagina INTEGER PRIMARY KEY,
    fecha_completada TEXT NOT NULL
);
"""


def conectar(db_path: Path | str = DB_PATH_DEFAULT) -> sqlite3.Connection:
    conexion = sqlite3.connect(db_path)
    conexion.execute(ESQUEMA)
    conexion.execute(ESQUEMA_PROGRESO)
    _migrar_columnas_faltantes(conexion)
    return conexion


def upsert_producto(conexion: sqlite3.Connection, producto: dict) -> None:
    """Inserta o actualiza un producto, deduplicando por `url`."""
    valores = {clave: producto.get(clave) for clave in COLUMNAS_PRODUCTO}
    valores["fecha_scrapeo"] = datetime.now(timezone.utc).isoformat()

    columnas = ", ".join(valores.keys())
    placeholders = ", ".join(f":{clave}" for clave in valores)
    actualizaciones = ", ".join(f"{clave}=excluded.{clave}" for clave in valores if clave != "url")

    conexion.execute(
        f"""
        INSERT INTO productos_alibaba ({columnas})
        VALUES ({placeholders})
        ON CONFLICT(url) DO UPDATE SET {actualizaciones}
        """,
        valores,
    )


def upsert_productos(conexion: sqlite3.Connection, productos: list[dict]) -> None:
    for producto in productos:
        upsert_producto(conexion, producto)
    conexion.commit()


def contar_productos(conexion: sqlite3.Connection) -> int:
    return conexion.execute("SELECT COUNT(*) FROM productos_alibaba").fetchone()[0]


def exportar_csv(conexion: sqlite3.Connection, destino: Path | str) -> None:
    cursor = conexion.execute("SELECT * FROM productos_alibaba ORDER BY id")
    columnas = [descripcion[0] for descripcion in cursor.description]

    with open(destino, "w", newline="", encoding="utf-8") as archivo:
        writer = csv.writer(archivo)
        writer.writerow(columnas)
        writer.writerows(cursor.fetchall())


def marcar_pagina_completada(conexion: sqlite3.Connection, pagina: int) -> None:
    """Registra que una página de listado ya se recorrió con éxito."""
    conexion.execute(
        "INSERT OR REPLACE INTO progreso_paginas (pagina, fecha_completada) VALUES (?, ?)",
        (pagina, datetime.now(timezone.utc).isoformat()),
    )
    conexion.commit()


def obtener_paginas_completadas(conexion: sqlite3.Connection) -> set[int]:
    filas = conexion.execute("SELECT pagina FROM progreso_paginas").fetchall()
    return {fila[0] for fila in filas}


def reiniciar_progreso(conexion: sqlite3.Connection) -> None:
    """Olvida qué páginas se completaron. No borra productos ya guardados."""
    conexion.execute("DELETE FROM progreso_paginas")
    conexion.commit()
