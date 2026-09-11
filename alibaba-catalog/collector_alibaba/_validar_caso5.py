"""
Helper de un solo uso para el Caso 5 de la validación real de Match Mode:
un caso negativo de verdad -- el Caso 4 no alcanzó, porque el candidato
salió por fallback (ninguna marca conocida en el título) y Alibaba
devolvió productos genéricos de la misma familia, así que no había forma
de distinguir "genuinamente sin equivalente" de "poca evidencia".

Este heurístico busca algo más estricto que "tiene una marca en el
título" (eso no alcanza, cualquier producto de marca puede tener un
equivalente genérico en Alibaba). Busca una RAZÓN ESTRUCTURAL para
esperar que Alibaba no tenga un equivalente real:

  - `merchandising_licenciado`: mercadería con licencia oficial de un
    club/selección de fútbol argentino -- el producto genuino requiere
    la licencia del club, algo que una fábrica genérica de Alibaba no
    puede reproducir como "el mismo producto" (como mucho vende una
    réplica no oficial, que ya es otra identidad de producto).
  - `repuesto_marca_regional`: repuesto/pieza para un electrodoméstico
    de una marca argentina/regional (Drean, Gafa, Peabody, Longvie,
    Siam, Aurora, Volcán, Orbis, Briket) -- Alibaba no fabrica piezas
    con el ajuste/licencia exacto de estas marcas. Requiere la marca Y
    una palabra de contexto de repuesto (nunca la marca sola --
    "no basta con que el título tenga una marca").
  - `norma_local`: formato/norma específica de Argentina (enchufe tipo
    argentino, homologación Enargas para gas, norma IRAM) -- Alibaba
    fabrica mayormente para estándares internacionales/chinos.

Si NINGÚN candidato de `demanda_confirmada` dispara alguna de estas
categorías, el script lo dice explícitamente y NO corre el matching --
no fuerza el caso. En ese escenario hace falta ampliar la muestra de ML
(correr `orquestador_demanda_ml.py` con búsquedas más propensas a este
tipo de producto) antes de reintentar.

No toca matcher.py/atributos_matching.py/embeddings.py/parser_ficha_ml.py
ni ningún peso/umbral/regla -- corre exactamente el mismo Match Mode,
solo cambia CUÁL candidato se elige, y por qué (motivo impreso ANTES de
tocar Alibaba, no después).

Uso (desde alibaba-catalog/collector_alibaba, con el perfil de Chrome ya
logueado):
    python _validar_caso5.py
    python _validar_caso5.py --login
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

CATEGORIAS_NEGATIVO_ESTRUCTURAL = [
    {
        "id": "merchandising_licenciado",
        "razon": (
            "Mercadería con licencia oficial de un club/selección de fútbol argentino: "
            "el producto genuino requiere la licencia del club -- una fábrica genérica de "
            "Alibaba no puede reproducir 'el mismo producto', como mucho una réplica no "
            "oficial (otra identidad de producto, no un match)."
        ),
        "fuertes": [
            r"boca juniors?", r"river plate", r"racing club", r"independiente",
            r"san lorenzo", r"selecci[oó]n argentina", r"\bafa\b", r"estudiantes",
            r"hurac[aá]n", r"v[eé]lez", r"newell'?s", r"rosario central",
            r"talleres", r"belgrano", r"gimnasia", r"argentinos juniors",
            r"banfield", r"lan[uú]s", r"\btigre\b", r"col[oó]n", r"patronato",
            r"licencia oficial", r"producto oficial",
        ],
    },
    {
        "id": "repuesto_marca_regional",
        "razon": (
            "Repuesto/pieza para un electrodoméstico de marca argentina/regional -- "
            "Alibaba no fabrica piezas con el ajuste o la licencia exacta de estas "
            "marcas locales, a diferencia de una pieza genérica sin marca."
        ),
        "debiles": ["drean", "gafa", "peabody", "longvie", "siam", "aurora", "volc[aá]n", "orbis", "briket"],
        "contexto": ["repuesto", "pieza", "filtro", "correa", "resistencia", "v[aá]lvula", "compatible"],
    },
    {
        "id": "norma_local",
        "razon": (
            "Formato/norma específica de Argentina (enchufe tipo argentino, homologación "
            "Enargas para gas, norma IRAM) -- Alibaba fabrica mayormente para estándares "
            "internacionales/chinos, no necesariamente compatibles ni homologados acá."
        ),
        "fuertes": [r"norma iram", r"tipo argentino", r"enchufe argentino", r"homologad[oa] enargas", r"norma enargas"],
    },
]


def _evaluar_categoria(nombre_low: str, categoria: dict) -> tuple[bool, str | None]:
    for patron in categoria.get("fuertes", []):
        if re.search(rf"\b{patron}\b", nombre_low):
            return True, patron

    debiles = categoria.get("debiles", [])
    contexto = categoria.get("contexto", [])
    if debiles and contexto:
        marca = next((p for p in debiles if re.search(rf"\b{p}\b", nombre_low)), None)
        ctx = next((p for p in contexto if re.search(rf"\b{p}\b", nombre_low)), None)
        if marca and ctx:
            return True, f"'{marca}' + '{ctx}'"

    return False, None


def elegir_candidato_negativo(conexion):
    """
    Devuelve (candidato, categoria_id, razon, detalle) del primer
    candidato (por mayor unidades_vendidas) que dispare alguna categoría
    estructural, o (None, None, None, None) si ninguno lo hace -- nunca
    fuerza una elección por descarte, a diferencia de _validar_caso4.py.
    """
    conexion.row_factory = sqlite3.Row
    filas = conexion.execute("SELECT * FROM candidatos_ml WHERE estado = 'demanda_confirmada'").fetchall()
    conexion.row_factory = None
    candidatos = [dict(fila) for fila in filas]
    candidatos.sort(key=lambda c: -(c["unidades_vendidas"] or 0))

    for candidato in candidatos:
        nombre_low = (candidato["nombre"] or "").lower()
        for categoria in CATEGORIAS_NEGATIVO_ESTRUCTURAL:
            disparo, detalle = _evaluar_categoria(nombre_low, categoria)
            if disparo:
                return candidato, categoria["id"], categoria["razon"], detalle

    return None, None, None, None


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--login", action="store_true")
    args = argparser.parse_args()

    conexion = db.conectar()
    candidato, categoria_id, razon, detalle = elegir_candidato_negativo(conexion)
    conexion.close()

    if candidato is None:
        print("=" * 70)
        print("NINGÚN candidato con estado 'demanda_confirmada' disparó una razón")
        print("estructural para esperar ausencia de equivalente en Alibaba (ver las")
        print("categorías en CATEGORIAS_NEGATIVO_ESTRUCTURAL de este script).")
        print("No se fuerza el caso -- no se corrió ningún matching.")
        print()
        print("Para conseguir un candidato así hace falta ampliar la muestra de ML,")
        print("por ejemplo con orquestador_demanda_ml.py sobre búsquedas más propensas")
        print("a este tipo de producto (ej. 'camiseta boca juniors', 'repuesto drean',")
        print("'termotanque orbis'), y volver a correr este script después.")
        print("=" * 70)
        return

    print("=" * 70)
    print("Candidato elegido automáticamente para el Caso 5 (negativo real):")
    print(f"  categoría del heurístico: {categoria_id}")
    print(f"  motivo estructural: {razon}")
    print(f"  detalle del match: {detalle}")
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
