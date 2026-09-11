"""
Helper de un solo uso para la validación real de Match Mode -- NO es parte
del pipeline, no se importa desde ningún otro módulo. Elige automáticamente
un candidato de `candidatos_ml` con `estado = demanda_confirmada` (el de
mayor `unidades_vendidas`, para un primer caso claro y genérico) y corre
el flujo completo existente (`orquestador_matching.ejecutar_matching_real`)
sin modificar nada del pipeline.

Uso (desde alibaba-catalog/collector_alibaba, con el perfil de Chrome ya
logueado):
    python _validar_caso1.py
    python _validar_caso1.py --login   # si hace falta loguearse de nuevo
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "database"))

import db
from orquestador_matching import ejecutar_matching_real


def elegir_candidato(conexion):
    conexion.row_factory = sqlite3.Row
    fila = conexion.execute(
        "SELECT * FROM candidatos_ml WHERE estado = 'demanda_confirmada' "
        "ORDER BY unidades_vendidas DESC LIMIT 1"
    ).fetchone()
    conexion.row_factory = None
    return dict(fila) if fila else None


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--login", action="store_true")
    args = argparser.parse_args()

    conexion = db.conectar()
    candidato = elegir_candidato(conexion)
    conexion.close()

    if candidato is None:
        print("No hay ningún candidato con estado 'demanda_confirmada' en la base todavía.")
        print("Hace falta correr antes orquestador_demanda_ml.py para tener al menos uno.")
        return

    print("=" * 70)
    print(f"Candidato elegido automáticamente (mayor unidades_vendidas entre demanda_confirmada):")
    print(f"  id_ml: {candidato['id_ml']}")
    print(f"  nombre: {candidato['nombre']}")
    print(f"  unidades_vendidas: {candidato['unidades_vendidas']}")
    print(f"  url_ml: {candidato['url_ml']}")
    print("=" * 70)

    resultado = ejecutar_matching_real(candidato["url_ml"], forzar_login=args.login)

    print("\n" + "#" * 70)
    print("RESULTADO COMPLETO (mismo JSON que queda guardado en matching_alibaba):")
    print("#" * 70)
    print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
