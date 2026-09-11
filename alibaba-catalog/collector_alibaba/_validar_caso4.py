"""
Helper de un solo uso para el Caso 4 de la validación real de Match Mode:
probar específicamente la capacidad de decir "no hay match" cuando
corresponde -- no un caso armado a mano, sino elegido automáticamente
por un heurístico explicable, igual de "no me pidas buscar/copiar una
URL" que `_validar_caso1.py`.

No toca matcher.py/atributos_matching.py/embeddings.py/parser_ficha_ml.py
ni ningún peso/umbral -- corre exactamente el mismo Match Mode, solo
cambia CUÁL candidato se elige.

Heurístico de selección (`_PALABRAS_BAJA_PROBABILIDAD`): entre los
candidatos con `estado = demanda_confirmada`, prioriza los que mencionan
en el título indicios de ser repuestos/piezas ligadas a una marca o
modelo específico (autopartes de marca, "original", "homologado",
normas locales tipo IRAM, personalización) -- productos donde Alibaba,
que vende manufactura genérica sin licencia de marca, tiene baja
probabilidad de ofrecer algo realmente equivalente. Es un heurístico de
texto, no una certeza -- por eso el resultado se compara después contra
la evidencia real (`candidatos_evaluados`), no se da por sentado.

Si ningún candidato dispara ninguna palabra del heurístico, cae de
vuelta al mismo criterio que `_validar_caso1.py` (mayor
`unidades_vendidas`) y lo deja explícito en el log -- nunca elige a
ciegas ni le pide a la usuaria que elija a mano.

Uso (desde alibaba-catalog/collector_alibaba, con el perfil de Chrome ya
logueado):
    python _validar_caso4.py
    python _validar_caso4.py --login
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "database"))

import db
from orquestador_matching import ejecutar_matching_real

# Indicios de "repuesto/pieza ligada a una marca o modelo específico" o
# "producto sujeto a homologación/personalización local" -- ninguno de los
# dos encaja bien con lo que Alibaba ofrece (manufactura genérica, sin
# licencia de marca, para exportación masiva).
_PALABRAS_BAJA_PROBABILIDAD = [
    "ford", "chevrolet", "fiat", "renault", "volkswagen", "vw", "peugeot",
    "toyota", "honda", "citroen", "citroën", "nissan", "jeep", "fiat",
    "gol", "corsa", "clio", "megane", "palio", "onix", "cronos",
    "original", "homologado", "homologada", "iram", "genuino", "genuina",
    "personalizado", "personalizada", "a medida", "grabado", "grabada",
    "repuesto original", "oem",
]


def _score_baja_probabilidad(nombre: str) -> tuple[int, list[str]]:
    nombre_low = (nombre or "").lower()
    matches = [
        palabra for palabra in _PALABRAS_BAJA_PROBABILIDAD
        if re.search(rf"\b{re.escape(palabra)}\b", nombre_low)
    ]
    return len(matches), matches


def elegir_candidato(conexion):
    conexion.row_factory = sqlite3.Row
    filas = conexion.execute("SELECT * FROM candidatos_ml WHERE estado = 'demanda_confirmada'").fetchall()
    conexion.row_factory = None
    candidatos = [dict(fila) for fila in filas]
    if not candidatos:
        return None, "sin_candidatos", []

    for candidato in candidatos:
        score, matches = _score_baja_probabilidad(candidato["nombre"])
        candidato["_score_baja_probabilidad"] = score
        candidato["_matches"] = matches

    candidatos.sort(key=lambda c: (-c["_score_baja_probabilidad"], -(c["unidades_vendidas"] or 0)))
    mejor = candidatos[0]

    if mejor["_score_baja_probabilidad"] > 0:
        return mejor, "heuristico_baja_probabilidad", mejor["_matches"]

    # Ningún candidato disparó el heurístico -- fallback explícito al
    # mismo criterio de _validar_caso1.py, nunca una elección a ciegas.
    candidatos.sort(key=lambda c: -(c["unidades_vendidas"] or 0))
    return candidatos[0], "fallback_mayor_unidades_vendidas", []


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--login", action="store_true")
    args = argparser.parse_args()

    conexion = db.conectar()
    candidato, criterio, matches = elegir_candidato(conexion)
    conexion.close()

    if candidato is None:
        print("No hay ningún candidato con estado 'demanda_confirmada' en la base todavía.")
        return

    print("=" * 70)
    print("Candidato elegido automáticamente para el Caso 4 (probar decir NO):")
    print(f"  criterio: {criterio}")
    if matches:
        print(f"  palabras que dispararon el heurístico: {matches}")
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
