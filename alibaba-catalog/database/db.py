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
- `matching_alibaba`: resultado de Match Mode (Fase 2, ver `matcher.py`)
  para un candidato de ML -- categoría (MATCH_ALTO/MATCH_PROBABLE/
  SIN_MATCH_CONFIABLE), el candidato de Alibaba elegido si lo hay, y la
  evidencia completa (todos los candidatos evaluados, no solo el
  ganador) en columnas JSON, para poder auditar por qué se aceptó o
  rechazó cada uno. Deliberadamente separada de `alibaba_comparables`
  (que guarda el precio ya verificado para la etapa económica, todavía
  sin empezar) -- son preguntas distintas: "¿es el mismo producto?" vs
  "¿a qué precio?". Append-only, igual que `historial_ml`: correr el
  matching de nuevo agrega una fila, no pisa la anterior.
"""

from __future__ import annotations

import csv
import json
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

# Columnas agregadas después de la creación inicial de una tabla: en una
# base ya existente (CREATE TABLE IF NOT EXISTS no las agrega
# retroactivamente), hace falta un ALTER TABLE explícito para no perder
# los datos ya guardados.
_MIGRACIONES_PRODUCTOS = {
    "compra_directa": "ALTER TABLE productos_alibaba ADD COLUMN compra_directa INTEGER",
    "envio_calculable": "ALTER TABLE productos_alibaba ADD COLUMN envio_calculable INTEGER",
}

_MIGRACIONES_CANDIDATOS_ML = {
    "prioridad_listado": "ALTER TABLE candidatos_ml ADD COLUMN prioridad_listado TEXT",
}

_MIGRACIONES_HISTORIAL_ML = {
    "rating": "ALTER TABLE historial_ml ADD COLUMN rating REAL",
}


def _migrar_columnas(conexion: sqlite3.Connection, tabla: str, migraciones: dict[str, str]) -> None:
    columnas_existentes = {fila[1] for fila in conexion.execute(f"PRAGMA table_info({tabla})")}
    for columna, sentencia in migraciones.items():
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
    "nuevo",                              # detectado en ML con prioridad A o B en el listado, ficha todavía sin abrir
    "descartado_demanda_insuficiente",    # sin ninguna señal de demanda visible en el listado de ML (prefiltro barato, nunca se abrió su ficha)
    "demanda_confirmada",                 # se abrió la ficha individual de ML y la demanda supera el umbral configurado
    "descartado_demanda_no_confirmada",   # se abrió la ficha individual de ML pero no alcanzó el umbral configurado
    "indeterminado_ficha",                # se abrió la ficha individual de ML pero no se pudo extraer nada confiable
    "con_comparable",                     # tiene un comparable de Alibaba asociado, precio sin verificar
    "precio_verificado",                  # se abrió la ficha individual de Alibaba y se obtuvo un precio confiable
    "descartado_filtro_economico",        # diferencia_inicial < USD 10
    "descartado_no_verificado",           # precio de Alibaba no se pudo determinar de forma confiable
    "descartado_sin_comparable",          # no se encontró un producto comparable en Alibaba
    "segunda_etapa",                      # sobrevivió el filtro económico, en análisis de logística/margen
    "finalista",                          # en la shortlist final
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
    prioridad_listado TEXT,
    estado TEXT NOT NULL DEFAULT 'nuevo',
    motivo_descarte TEXT,
    fecha_detectado TEXT NOT NULL,
    fecha_actualizado TEXT NOT NULL
);
"""

# prioridad_listado: 'A' (señal fuerte: badge "más vendido" o conteo
# explícito de vendidos), 'B' (señal débil: rating u otra señal parcial),
# o None (sin ninguna señal). Es solo un prefiltro/orden de prioridad para
# decidir qué fichas abrir primero -- NO es una validación de demanda
# (ver parser_busqueda_ml.clasificar_prioridad).
COLUMNAS_CANDIDATO_ML = [
    "id_ml", "url_ml", "nombre", "evidencia_demanda", "unidades_vendidas",
    "precio_ml", "moneda_ml", "prioridad_listado", "estado", "motivo_descarte",
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
    rating REAL,
    posicion_ranking INTEGER
);
"""

COLUMNAS_OBSERVACION_HISTORIAL = [
    "precio", "stock_visible", "unidades_vendidas_visible", "cantidad_opiniones", "rating", "posicion_ranking",
]

# Categorías posibles del resultado de Match Mode -- ver matcher.py. La
# incertidumbre es un resultado válido y explícito (SIN_MATCH_CONFIABLE),
# nunca "el candidato más parecido aunque sea malo".
CATEGORIAS_MATCHING = ("MATCH_ALTO", "MATCH_PROBABLE", "SIN_MATCH_CONFIABLE")

ESQUEMA_MATCHING_ALIBABA = """
CREATE TABLE IF NOT EXISTS matching_alibaba (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidato_id INTEGER NOT NULL REFERENCES candidatos_ml(id),
    query_usada TEXT,
    categoria TEXT NOT NULL,
    url_alibaba_elegido TEXT,
    nombre_alibaba_elegido TEXT,
    score_final REAL,
    motivo TEXT,
    candidatos_evaluados_json TEXT NOT NULL,
    candidatos_rankeados_json TEXT NOT NULL,
    pesos_json TEXT,
    umbrales_json TEXT,
    fecha_matching TEXT NOT NULL
);
"""


def conectar(db_path: Path | str = DB_PATH_DEFAULT) -> sqlite3.Connection:
    conexion = sqlite3.connect(db_path)
    conexion.execute(ESQUEMA)
    conexion.execute(ESQUEMA_PROGRESO)
    conexion.execute(ESQUEMA_CANDIDATOS_ML)
    conexion.execute(ESQUEMA_ALIBABA_COMPARABLES)
    conexion.execute(ESQUEMA_HISTORIAL_ML)
    conexion.execute(ESQUEMA_MATCHING_ALIBABA)
    _migrar_columnas(conexion, "productos_alibaba", _MIGRACIONES_PRODUCTOS)
    _migrar_columnas(conexion, "candidatos_ml", _MIGRACIONES_CANDIDATOS_ML)
    _migrar_columnas(conexion, "historial_ml", _MIGRACIONES_HISTORIAL_ML)
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


def insertar_resultado_matching(conexion: sqlite3.Connection, candidato_id: int, resultado: dict) -> int:
    """
    Guarda el resultado de una corrida de Match Mode (`matcher.MatchResult`,
    ya convertido a dict -- ver `orquestador_matching.py`). Append-only:
    correr el matching de nuevo sobre el mismo candidato agrega una fila
    nueva, nunca pisa la anterior (permite comparar corridas si se
    recalibran pesos/umbrales más adelante).

    `resultado` espera las claves de `matcher.MatchResult` más, opcionalmente,
    `pesos` y `umbrales` (dicts) para dejar registrado con qué configuración
    se corrió -- ninguna de las dos es todavía un valor fijo (ajuste #5).
    """
    elegido = resultado.get("candidato_elegido")
    valores = {
        "candidato_id": candidato_id,
        "query_usada": resultado.get("query_usada"),
        "categoria": resultado["categoria"],
        "url_alibaba_elegido": elegido.get("url_alibaba") if elegido else None,
        "nombre_alibaba_elegido": elegido.get("nombre_alibaba") if elegido else None,
        "score_final": elegido.get("score_final") if elegido else None,
        "motivo": resultado.get("motivo"),
        "candidatos_evaluados_json": json.dumps(resultado.get("candidatos_evaluados", []), ensure_ascii=False),
        "candidatos_rankeados_json": json.dumps(resultado.get("candidatos_rankeados", []), ensure_ascii=False),
        "pesos_json": json.dumps(resultado.get("pesos")) if resultado.get("pesos") is not None else None,
        "umbrales_json": json.dumps(resultado.get("umbrales")) if resultado.get("umbrales") is not None else None,
        "fecha_matching": datetime.now(timezone.utc).isoformat(),
    }

    if valores["categoria"] not in CATEGORIAS_MATCHING:
        raise ValueError(f"Categoría de matching desconocida: {valores['categoria']!r}. Válidas: {CATEGORIAS_MATCHING}")

    columnas = ", ".join(valores.keys())
    placeholders = ", ".join(f":{clave}" for clave in valores)

    cursor = conexion.execute(
        f"INSERT INTO matching_alibaba ({columnas}) VALUES ({placeholders})", valores
    )
    conexion.commit()
    return cursor.lastrowid


def _fila_matching_a_dict(fila: dict) -> dict:
    fila = dict(fila)
    fila["candidatos_evaluados"] = json.loads(fila.pop("candidatos_evaluados_json"))
    fila["candidatos_rankeados"] = json.loads(fila.pop("candidatos_rankeados_json"))
    fila["pesos"] = json.loads(fila["pesos_json"]) if fila.get("pesos_json") else None
    fila["umbrales"] = json.loads(fila["umbrales_json"]) if fila.get("umbrales_json") else None
    fila.pop("pesos_json", None)
    fila.pop("umbrales_json", None)
    return fila


def obtener_ultimo_matching(conexion: sqlite3.Connection, candidato_id: int) -> dict | None:
    """La corrida de matching más reciente para un candidato, o None si nunca se corrió."""
    conexion.row_factory = sqlite3.Row
    fila = conexion.execute(
        "SELECT * FROM matching_alibaba WHERE candidato_id = ? ORDER BY fecha_matching DESC LIMIT 1", (candidato_id,)
    ).fetchone()
    conexion.row_factory = None
    return _fila_matching_a_dict(fila) if fila else None


def obtener_historial_matching(conexion: sqlite3.Connection, candidato_id: int) -> list[dict]:
    """Todas las corridas de matching de un candidato, de la más vieja a la más nueva."""
    conexion.row_factory = sqlite3.Row
    filas = conexion.execute(
        "SELECT * FROM matching_alibaba WHERE candidato_id = ? ORDER BY fecha_matching ASC", (candidato_id,)
    ).fetchall()
    conexion.row_factory = None
    return [_fila_matching_a_dict(fila) for fila in filas]
