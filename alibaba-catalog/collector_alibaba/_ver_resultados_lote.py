"""
Helper de un solo uso, de solo lectura: muestra todo lo que ya quedó
guardado en `matching_alibaba` -- útil después de una corrida de
`orquestador_matching_lote.py` que se cortó a mitad de camino (ej. por
CAPTCHA). No abre Chrome, no navega a ningún lado, no modifica nada.

Uso (desde alibaba-catalog/collector_alibaba):
    python _ver_resultados_lote.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "database"))

import db


def main():
    conexion = db.conectar()
    conexion.row_factory = sqlite3.Row
    filas = conexion.execute(
        """
        SELECT m.fecha_matching, m.categoria, m.url_alibaba_elegido, m.score_final,
               c.id_ml, c.nombre
        FROM matching_alibaba m
        JOIN candidatos_ml c ON c.id = m.candidato_id
        ORDER BY m.fecha_matching DESC
        """
    ).fetchall()
    conexion.close()

    if not filas:
        print("Todavía no hay ningún resultado guardado en matching_alibaba.")
        return

    print("=" * 70)
    print(f"{len(filas)} resultado(s) guardado(s) en matching_alibaba (más reciente primero):")
    print("=" * 70)
    for fila in filas:
        print()
        print(f"  {fila['fecha_matching']}")
        print(f"  {fila['id_ml']} -- {fila['nombre'][:60]}")
        print(f"  -> {fila['categoria']}", end="")
        if fila["url_alibaba_elegido"]:
            print(f" ({fila['score_final']:.2f}): {fila['url_alibaba_elegido']}")
        else:
            print()


if __name__ == "__main__":
    main()
