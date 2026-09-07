"""
Persistencia en SQLite del catálogo scrapeado.

Un único archivo (`catalogo_alibaba.db` por defecto) con una tabla,
`productos_alibaba`. El upsert deduplica por `url` (la ficha de producto
en Alibaba), que es estable entre corridas del collector.
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
    fecha_scrapeo TEXT NOT NULL
);
"""

COLUMNAS_PRODUCTO = [
    "producto_id_alibaba", "nombre", "url", "precio_min", "precio_max", "moneda",
    "moq", "cantidad_vendida", "imagen_principal", "categoria_id", "categoria",
    "peso_gramos",
]


def conectar(db_path: Path | str = DB_PATH_DEFAULT) -> sqlite3.Connection:
    conexion = sqlite3.connect(db_path)
    conexion.execute(ESQUEMA)
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
