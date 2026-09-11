"""
Persistencia en SQLite del catálogo scrapeado y del motor de sourcing
Mercado Libre -> Alibaba (MUTE).

Un único archivo (`catalogo_alibaba.db` por defecto) con las tablas:

- `productos_alibaba` / `progreso_paginas`: catálogo completo de un
  proveedor puntual de Alibaba (ver collector_alibaba/collector_browser.py).
- `candidatos_ml`: publicaciones de Mercado Libre con evidencia de demanda,
  con su estado dentro del pipeline de sourcing (nuevo, con comparable,
  descartado, finalista, etc.). Se deduplica por `url_ml`.
- `alibaba_comparables`: el producto de Alibaba elegido como comparable de
  un candidato de ML, con precio ya verificado en la ficha individual (no
  el de la búsqueda).
- `historial_ml`: observaciones de una publicación de ML a lo largo del
  tiempo (precio, stock, ventas visibles) para medir rotación. Es
  append-only: nunca se actualiza ni se borra una fila existente.
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

# Estados posibles de un candidato dentro del pipeline de sourcing. Viven acá
# (no en un ENUM de SQLite, que no existe) para no tener strings mágicos
# sueltos en el código que arma el pipeline.
ESTADOS_CANDIDATO = (
    "nuevo",                             # detectado en ML, todavía sin comparable de Alibaba
    "descartado_demanda_insuficiente",   # sin ninguna señal de demanda visible en el listado de ML (prefiltro barato, nunca se abrió su ficha)
    "con_comparable",                    # tiene un comparable de Alibaba asociado, precio sin verificar
    "precio_verificado",                 # se abrió la ficha individual y se obtuvo un precio confiable
    "descartado_filtro_economico",       # diferencia_inicial < USD 10
    "descartado_no_verificado",          # precio de Alibaba no se pudo determinar de forma confiable
    "descartado_sin_comparable",         # no se encontró un producto comparable en Alibaba
    "segunda_etapa",                     # sobrevivió el filtro económico, en análisis de logística/margen
    "finalista",                         # en la shortlist final
)

ESQUEMA_CANDIDATOS_ML = """
CREATE TABLE IF NOT EXISTS candidatos_ml (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_ml TEXT,
    url_ml TEXT NOT NULL UNIQUE,
    nombre TEXT,
    evidencia_demanda TEXT,
    unidades_vendidas INTEGER,
    precio_ml REAL,
    moneda_ml TEXT,
    estado TEXT NOT NULL DEFAULT 'nuevo',
    motivo_descarte TEXT,
    fecha_detectado TEXT NOT NULL,
    fecha_actualizado TEXT NOT NULL
);
"""

COLUMNAS_CANDIDATO_ML = [
    "id_ml", "url_ml", "nombre", "evidencia_demanda", "unidades_vendidas",
    "precio_ml", "moneda_ml", "estado", "motivo_descarte",
]

ESQUEMA_ALIBABA_COMPARABLES = """
CREATE TABLE IF NOT EXISTS alibaba_comparables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidato_id INTEGER NOT NULL REFERENCES candidatos_ml(id),
    url_alibaba TEXT NOT NULL,
    proveedor TEXT,
    variante TEXT,
    moq TEXT,
    precio_alibaba_50u REAL,
    moneda TEXT,
    precio_no_verificado INTEGER NOT NULL DEFAULT 0,
    requiere_contacto_proveedor INTEGER NOT NULL DEFAULT 0,
    dimensiones TEXT,
    peso_gramos REAL,
    fecha_verificado TEXT NOT NULL
);
"""

COLUMNAS_COMPARABLE_ALIBABA = [
    "url_alibaba", "proveedor", "variante", "moq", "precio_alibaba_50u", "moneda",
    "precio_no_verificado", "requiere_contacto_proveedor", "dimensiones", "peso_gramos",
]

ESQUEMA_HISTORIAL_ML = """
CREATE TABLE IF NOT EXISTS historial_ml (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidato_id INTEGER NOT NULL REFERENCES candidatos_ml(id),
    fecha_hora TEXT NOT NULL,
    precio REAL,
    stock_visible INTEGER,
    unidades_vendidas_visible INTEGER,
    cantidad_opiniones INTEGER,
    posicion_ranking INTEGER
);
"""

COLUMNAS_OBSERVACION_HISTORIAL = [
    "precio", "stock_visible", "unidades_vendidas_visible", "cantidad_opiniones", "posicion_ranking",
]


def conectar(db_path: Path | str = DB_PATH_DEFAULT) -> sqlite3.Connection:
    conexion = sqlite3.connect(db_path)
    conexion.execute(ESQUEMA)
    conexion.execute(ESQUEMA_PROGRESO)
    conexion.execute(ESQUEMA_CANDIDATOS_ML)
    conexion.execute(ESQUEMA_ALIBABA_COMPARABLES)
    conexion.execute(ESQUEMA_HISTORIAL_ML)
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


def upsert_candidato_ml(conexion: sqlite3.Connection, candidato: dict) -> int:
    """
    Inserta o actualiza un candidato de Mercado Libre, deduplicando por
    `url_ml`. `fecha_detectado` se preserva de la primera vez que se vio el
    candidato (no se pisa en actualizaciones posteriores). Devuelve el `id`
    interno del candidato (nuevo o existente).
    """
    ahora = datetime.now(timezone.utc).isoformat()
    valores = {clave: candidato.get(clave) for clave in COLUMNAS_CANDIDATO_ML}
    if valores.get("estado") is None:
        valores["estado"] = "nuevo"
    valores["fecha_detectado"] = ahora
    valores["fecha_actualizado"] = ahora

    columnas = ", ".join(valores.keys())
    placeholders = ", ".join(f":{clave}" for clave in valores)
    actualizaciones = ", ".join(
        f"{clave}=excluded.{clave}" for clave in valores
        if clave not in ("url_ml", "fecha_detectado")
    )

    conexion.execute(
        f"""
        INSERT INTO candidatos_ml ({columnas})
        VALUES ({placeholders})
        ON CONFLICT(url_ml) DO UPDATE SET {actualizaciones}
        """,
        valores,
    )
    conexion.commit()

    fila = conexion.execute(
        "SELECT id FROM candidatos_ml WHERE url_ml = ?", (candidato["url_ml"],)
    ).fetchone()
    return fila[0]


def obtener_candidato_por_url(conexion: sqlite3.Connection, url_ml: str) -> dict | None:
    conexion.row_factory = sqlite3.Row
    fila = conexion.execute("SELECT * FROM candidatos_ml WHERE url_ml = ?", (url_ml,)).fetchone()
    conexion.row_factory = None
    return dict(fila) if fila else None


def actualizar_estado_candidato(
    conexion: sqlite3.Connection, candidato_id: int, estado: str, motivo_descarte: str | None = None
) -> None:
    if estado not in ESTADOS_CANDIDATO:
        raise ValueError(f"Estado desconocido: {estado!r}. Válidos: {ESTADOS_CANDIDATO}")
    conexion.execute(
        "UPDATE candidatos_ml SET estado = ?, motivo_descarte = ?, fecha_actualizado = ? WHERE id = ?",
        (estado, motivo_descarte, datetime.now(timezone.utc).isoformat(), candidato_id),
    )
    conexion.commit()


def insertar_comparable_alibaba(conexion: sqlite3.Connection, candidato_id: int, comparable: dict) -> int:
    """Registra el producto de Alibaba elegido como comparable de un candidato de ML."""
    valores = {clave: comparable.get(clave) for clave in COLUMNAS_COMPARABLE_ALIBABA}
    valores["precio_no_verificado"] = bool(valores.get("precio_no_verificado"))
    valores["requiere_contacto_proveedor"] = bool(valores.get("requiere_contacto_proveedor"))
    valores["candidato_id"] = candidato_id
    valores["fecha_verificado"] = datetime.now(timezone.utc).isoformat()

    columnas = ", ".join(valores.keys())
    placeholders = ", ".join(f":{clave}" for clave in valores)

    cursor = conexion.execute(
        f"INSERT INTO alibaba_comparables ({columnas}) VALUES ({placeholders})", valores
    )
    conexion.commit()
    return cursor.lastrowid


def registrar_observacion_historial(conexion: sqlite3.Connection, candidato_id: int, observacion: dict) -> None:
    """
    Agrega una observación al historial de un candidato. Nunca actualiza ni
    borra observaciones anteriores (append-only): sirve para medir
    variaciones de stock/precio/ventas en el tiempo, no para guardar el
    último estado conocido.
    """
    valores = {clave: observacion.get(clave) for clave in COLUMNAS_OBSERVACION_HISTORIAL}
    valores["candidato_id"] = candidato_id
    valores["fecha_hora"] = datetime.now(timezone.utc).isoformat()

    columnas = ", ".join(valores.keys())
    placeholders = ", ".join(f":{clave}" for clave in valores)

    conexion.execute(f"INSERT INTO historial_ml ({columnas}) VALUES ({placeholders})", valores)
    conexion.commit()


def obtener_historial(conexion: sqlite3.Connection, candidato_id: int) -> list[dict]:
    """Historial completo de un candidato, ordenado del más viejo al más nuevo."""
    conexion.row_factory = sqlite3.Row
    filas = conexion.execute(
        "SELECT * FROM historial_ml WHERE candidato_id = ? ORDER BY fecha_hora ASC", (candidato_id,)
    ).fetchall()
    conexion.row_factory = None
    return [dict(fila) for fila in filas]
