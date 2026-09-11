"""
Extracción y comparación de atributos de producto para Match Mode.

Ajuste #2 aprobado por la usuaria: nada de un umbral universal ">3x" para
decidir incompatibilidad. En cambio:

  - Cada TIPO de atributo (capacidad, peso, material, etc.) tiene su
    propio comparador y su propia tolerancia, configurable.
  - Los tipos se clasifican en ESENCIALES (definen si el producto es
    físicamente el mismo: categoría/tipo de producto, material, potencia,
    voltaje, capacidad, cantidad de piezas, dimensiones) o SECUNDARIOS
    (color, marca -- la propia usuaria los dio como ejemplo de diferencia
    menor admisible).
  - Una incompatibilidad DURA (veto) solo puede salir de un atributo
    ESENCIAL donde AMBOS lados tienen un valor extraído con confianza y
    esos valores resultan incompatibles. Si falta un lado, o el valor no
    se pudo interpretar con confianza, la comparación queda en
    `compatible=None` ("no comparable") -- nunca cuenta como veto, como
    mucho baja la cobertura/confianza del score (ver `matcher.py`).

Dos fuentes de atributos:
  1. Texto libre (título/descripción de ML, o subject de Alibaba si no
     hay specs estructuradas) vía regex -- `extraer_atributos_texto_libre`.
  2. Specs estructuradas de la ficha de Alibaba (`productBasicProperties`/
     `productKeyIndustryProperties`, ver `parser_ficha_alibaba.py`) --
     `extraer_atributos_alibaba`, que además completa con texto libre lo
     que las specs estructuradas no cubran (las specs, cuando existen,
     tienen prioridad por venir directo del proveedor).

Los diccionarios de canonicalización (`CANON_CATEGORIA`, `CANON_MATERIAL`,
`CANON_COLOR`) y las tolerancias (`TOLERANCIAS_DEFAULT`) son un punto de
partida razonable, no un resultado calibrado -- ajuste #5: se calibran con
la validación real, no se fijan acá como definitivos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TIPOS_NUMERICOS = {"capacidad", "peso", "potencia", "voltaje", "cantidad_piezas"}
TIPOS_CATEGORICOS = {"categoria", "material", "color", "marca", "identidad"}

# Atributos esenciales: una incompatibilidad confirmada acá puede vetar un
# candidato. Atributos secundarios: nunca vetan, la propia usuaria dio
# color/marca/empaque como ejemplo de diferencia menor admisible.
#
# "identidad" (agregado tras el Caso 5 real de la validación, ver
# ESTADO_ACTUAL.md): distingue mercadería con licencia oficial
# ("licenciado_oficial") de manufactura genérica personalizable
# ("generico_personalizable") -- sin esto, una camiseta con licencia
# oficial de club y una fábrica que imprime cualquier logo a pedido
# puntuaban MATCH_PROBABLE por texto+imagen solos, un falso positivo real
# confirmado. Esencial por el mismo motivo que categoria/material: son
# productos distintos aunque se vean casi idénticos en foto.
ESENCIALES = {
    "categoria", "material", "capacidad", "potencia", "voltaje", "cantidad_piezas", "dimensiones", "identidad",
}
SECUNDARIOS = {"color", "marca"}

TOLERANCIAS_DEFAULT = {
    "capacidad": 0.15,
    "peso": 0.20,
    "potencia": 0.15,
    "voltaje": 0.05,  # el voltaje define compatibilidad eléctrica real -- tolerancia chica a propósito
    "cantidad_piezas": 0.0,  # una cantidad de piezas distinta (ej. set de 3 vs set de 5) es otro producto
    "dimensiones": 0.20,
}


@dataclass
class AtributoExtraido:
    tipo: str
    valor_crudo: str
    valor_numerico: float | None = None
    valor_dimensiones: tuple[float, ...] | None = None
    categoria_canon: str | None = None


@dataclass
class ComparacionAtributo:
    tipo: str
    esencial: bool
    compatible: bool | None  # None = no comparable (falta un lado, o valor no interpretable con confianza)
    detalle: str


# --- Canonicalización de valores categóricos -------------------------------
# Se busca por substring de frase completa primero (más específico), así
# "cleaning brush" cae en "cepillo" antes que fallar por no tener una
# entrada exacta. Punto de partida deliberadamente chico y editable.

CANON_CATEGORIA: dict[str, str] = {
    "cleaning brush": "cepillo", "scrub brush": "cepillo", "dish brush": "cepillo",
    "brush": "cepillo", "cepillo": "cepillo",
    "scrubber sponge": "esponja", "dish sponge": "esponja", "scrubber": "esponja",
    "sponge": "esponja", "esponja": "esponja",
    "holder": "soporte", "stand": "soporte", "soporte": "soporte",
    "case": "funda", "cover": "funda", "funda": "funda",
    "charger": "cargador", "cargador": "cargador",
    "cable": "cable",
    "lock": "candado", "candado": "candado",
    "flashlight": "linterna", "torch": "linterna", "linterna": "linterna",
    "lamp": "lampara", "bulb": "lampara", "lampara": "lampara", "foco": "lampara",
    "bottle": "botella", "botella": "botella",
    "backpack": "mochila", "mochila": "mochila",
    "bag": "bolso", "bolso": "bolso",
    "speaker": "parlante", "parlante": "parlante", "altavoz": "parlante",
    "earbuds": "auriculares", "earphone": "auriculares", "headphone": "auriculares", "auriculares": "auriculares",
    "watch": "reloj", "reloj": "reloj",
    "toy": "juguete", "juguete": "juguete",
    # Agregados tras el Caso 5 real (camiseta de fútbol) -- ver ESTADO_ACTUAL.md.
    "t-shirt": "camiseta", "tshirt": "camiseta", "jersey": "camiseta", "shirt": "camiseta",
    "camiseta": "camiseta", "remera": "camiseta", "playera": "camiseta", "polera": "camiseta",
}

# Identidad/licencia/originalidad del producto -- ver el comentario en
# ESENCIALES sobre por qué se agregó. No es lo mismo que "categoria"
# (ambos productos pueden ser genuinamente camisetas) ni que "marca"
# (secundaria, admite diferencias) -- es específicamente si el producto
# es la mercadería con licencia oficial o una versión genérica
# personalizable, algo que Alibaba (manufactura sin licencia de marca)
# estructuralmente no puede ofrecer como "el mismo producto".
CANON_IDENTIDAD: dict[str, str] = {
    "licencia oficial": "licenciado_oficial", "producto oficial": "licenciado_oficial",
    "oficial licenciado": "licenciado_oficial", "con licencia": "licenciado_oficial",
    "licenciado": "licenciado_oficial", "oficial": "licenciado_oficial",
    "logo printing": "generico_personalizable", "logo de tu preferencia": "generico_personalizable",
    "cualquier logo": "generico_personalizable", "personalizable": "generico_personalizable",
    "personalizado": "generico_personalizable", "customized": "generico_personalizable",
    "custom": "generico_personalizable", "réplica": "generico_personalizable",
    "replica": "generico_personalizable", "no oficial": "generico_personalizable",
    "sin licencia": "generico_personalizable",
}

CANON_MATERIAL: dict[str, str] = {
    "silicone": "silicona", "silicona": "silicona",
    "stainless steel": "acero_inoxidable", "acero inoxidable": "acero_inoxidable",
    "plastic": "plastico", "plástico": "plastico", "plastico": "plastico",
    "metal": "metal", "aluminum": "metal", "aluminio": "metal",
    "wood": "madera", "madera": "madera", "bamboo": "madera", "bambu": "madera", "bambú": "madera",
    "ceramic": "ceramica", "cerámica": "ceramica", "ceramica": "ceramica",
    "glass": "vidrio", "vidrio": "vidrio",
    "rubber": "goma", "goma": "goma",
    "leather": "cuero", "cuero": "cuero",
    "cotton": "algodon", "algodón": "algodon", "algodon": "algodon",
    "nylon": "nylon",
}

CANON_COLOR: dict[str, str] = {
    "black": "negro", "negro": "negro",
    "white": "blanco", "blanco": "blanco",
    "red": "rojo", "rojo": "rojo",
    "blue": "azul", "azul": "azul",
    "green": "verde", "verde": "verde",
    "yellow": "amarillo", "amarillo": "amarillo",
    "pink": "rosa", "rosa": "rosa",
    "purple": "violeta", "violeta": "violeta",
    "gray": "gris", "grey": "gris", "gris": "gris",
    "orange": "naranja", "naranja": "naranja",
}


def _canonicalizar(texto: str | None, diccionario: dict[str, str]) -> str | None:
    if not texto:
        return None
    cuerpo = texto.lower()
    for frase in sorted(diccionario, key=len, reverse=True):
        if frase in cuerpo:
            return diccionario[frase]
    return None


# --- Extracción numérica de texto libre -------------------------------------

_FACTORES_CAPACIDAD_A_ML = {
    "ml": 1.0, "mL": 1.0, "cc": 1.0,
    "l": 1000.0, "L": 1000.0, "litro": 1000.0, "litros": 1000.0, "liter": 1000.0, "liters": 1000.0,
    "oz": 29.5735, "fl oz": 29.5735, "fl.oz": 29.5735,
}
_RE_CAPACIDAD = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|mL|cc|l|L|litros?|liters?|fl\.?\s?oz|oz)\b")

_FACTORES_PESO_A_GRAMOS = {
    "kg": 1000.0, "kilogramo": 1000.0, "kilogramos": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "g": 1.0, "gr": 1.0, "gramo": 1.0, "gramos": 1.0, "gram": 1.0, "grams": 1.0,
    "lb": 453.592, "lbs": 453.592, "libra": 453.592, "libras": 453.592, "pound": 453.592, "pounds": 453.592,
}
_RE_PESO = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|kilogramos?|kilograms?|gr|gramos?|grams?|lbs?|libras?|pounds?|g)\b", re.IGNORECASE
)

_RE_POTENCIA = re.compile(r"(\d+(?:[.,]\d+)?)\s*w(?:atts?)?\b", re.IGNORECASE)
_RE_VOLTAJE = re.compile(r"(\d+(?:[.,]\d+)?)\s*v(?:olts?)?\b", re.IGNORECASE)

_RE_CANTIDAD_PIEZAS = re.compile(
    r"(\d+)\s*[-\s]?(?:pcs|pieces?|piezas?|unidades?|units?|accesorios?)\b", re.IGNORECASE
)
# "pack of N" / "set de N" / "juego de N" (con preposición) y también
# "set N" / "set of N" (sin preposición, español o inglés) -- hallazgo
# real del Caso 4 ("Set 4" de ML vs. "Set of 3" del candidato de Alibaba,
# ninguna de las dos matcheaba antes). Ver ESTADO_ACTUAL.md.
_RE_PACK_OF = re.compile(
    r"pack of (\d+)|set de (\d+)|juego de (\d+)|set of (\d+)|\bset (\d+)\b", re.IGNORECASE
)

_FACTORES_DIMENSION_A_CM = {
    "cm": 1.0, "mm": 0.1,
    "in": 2.54, "inch": 2.54, "inches": 2.54, "pulgada": 2.54, "pulgadas": 2.54,
}
_RE_DIMENSIONES = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)(?:\s*[x×]\s*(\d+(?:[.,]\d+)?))?\s*"
    r"(cm|mm|inches?|pulgadas?|in)\b",
    re.IGNORECASE,
)


def _numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def _extraer_capacidad_ml(texto: str) -> tuple[float, str] | None:
    match = _RE_CAPACIDAD.search(texto)
    if not match:
        return None
    unidad = match.group(2)
    factor = _FACTORES_CAPACIDAD_A_ML.get(unidad) or _FACTORES_CAPACIDAD_A_ML.get(unidad.lower())
    if factor is None:
        return None
    return _numero(match.group(1)) * factor, match.group(0).strip()


def _extraer_peso_gramos(texto: str) -> tuple[float, str] | None:
    texto_limpio = texto.replace("(", " ").replace(")", " ")
    match = _RE_PESO.search(texto_limpio)
    if not match:
        return None
    factor = _FACTORES_PESO_A_GRAMOS.get(match.group(2).lower())
    if factor is None:
        return None
    return _numero(match.group(1)) * factor, match.group(0).strip()


def _extraer_potencia_watts(texto: str) -> tuple[float, str] | None:
    match = _RE_POTENCIA.search(texto)
    if not match:
        return None
    return _numero(match.group(1)), match.group(0).strip()


def _extraer_voltaje_volts(texto: str) -> tuple[float, str] | None:
    match = _RE_VOLTAJE.search(texto)
    if not match:
        return None
    return _numero(match.group(1)), match.group(0).strip()


def _extraer_cantidad_piezas(texto: str) -> tuple[float, str] | None:
    match = _RE_PACK_OF.search(texto)
    if match:
        grupo = next(g for g in match.groups() if g is not None)
        return float(grupo), match.group(0).strip()
    match = _RE_CANTIDAD_PIEZAS.search(texto)
    if match:
        return float(match.group(1)), match.group(0).strip()
    return None


def _extraer_dimensiones_cm(texto: str) -> tuple[tuple[float, ...], str] | None:
    match = _RE_DIMENSIONES.search(texto)
    if not match:
        return None
    unidad = match.group(4)
    factor = _FACTORES_DIMENSION_A_CM.get(unidad.lower())
    if factor is None:
        return None
    dims = tuple(_numero(g) * factor for g in match.groups()[:3] if g is not None)
    return dims, match.group(0).strip()


def extraer_atributos_texto_libre(texto: str | None) -> dict[str, AtributoExtraido]:
    """
    Extrae lo que se pueda de un texto libre (título + descripción). Nunca
    inventa un tipo que no matchea ningún patrón: los tipos ausentes
    simplemente no están en el dict devuelto (se tratan como "no
    comparable" en `comparar_atributos`, no como "incompatible").
    """
    atributos: dict[str, AtributoExtraido] = {}
    if not texto:
        return atributos

    capacidad = _extraer_capacidad_ml(texto)
    if capacidad:
        atributos["capacidad"] = AtributoExtraido("capacidad", capacidad[1], valor_numerico=capacidad[0])

    peso = _extraer_peso_gramos(texto)
    if peso:
        atributos["peso"] = AtributoExtraido("peso", peso[1], valor_numerico=peso[0])

    potencia = _extraer_potencia_watts(texto)
    if potencia:
        atributos["potencia"] = AtributoExtraido("potencia", potencia[1], valor_numerico=potencia[0])

    voltaje = _extraer_voltaje_volts(texto)
    if voltaje:
        atributos["voltaje"] = AtributoExtraido("voltaje", voltaje[1], valor_numerico=voltaje[0])

    cantidad = _extraer_cantidad_piezas(texto)
    if cantidad:
        atributos["cantidad_piezas"] = AtributoExtraido("cantidad_piezas", cantidad[1], valor_numerico=cantidad[0])

    dimensiones = _extraer_dimensiones_cm(texto)
    if dimensiones:
        atributos["dimensiones"] = AtributoExtraido("dimensiones", dimensiones[1], valor_dimensiones=dimensiones[0])

    categoria = _canonicalizar(texto, CANON_CATEGORIA)
    if categoria:
        atributos["categoria"] = AtributoExtraido("categoria", texto, categoria_canon=categoria)

    material = _canonicalizar(texto, CANON_MATERIAL)
    if material:
        atributos["material"] = AtributoExtraido("material", texto, categoria_canon=material)

    color = _canonicalizar(texto, CANON_COLOR)
    if color:
        atributos["color"] = AtributoExtraido("color", texto, categoria_canon=color)

    identidad = _canonicalizar(texto, CANON_IDENTIDAD)
    if identidad:
        atributos["identidad"] = AtributoExtraido("identidad", texto, categoria_canon=identidad)

    return atributos


# --- Extracción desde las specs estructuradas de Alibaba --------------------

# Por tipo, orden de prioridad de attrName a buscar en `atributos`
# (ver parser_ficha_alibaba._extraer_atributos, ya en minúscula). Se toma
# el primer alias presente -- "handle material" queda afuera a propósito
# (es el material de una pieza secundaria, no el material principal del
# producto).
_ALIASES_ALIBABA_POR_TIPO = {
    "categoria": ["type", "product type", "item type", "style"],
    "material": ["material", "brush material"],
    "peso": ["weight", "item weight", "net weight"],
    "capacidad": ["capacity", "volume"],
    "potencia": ["power", "wattage", "rated power"],
    "voltaje": ["voltage", "rated voltage"],
    "cantidad_piezas": ["quantity", "pieces", "pack size", "qty"],
    "color": ["color", "colour"],
    "marca": ["brand name", "brand"],
}

_MARCAS_SIN_VALOR = {"none", "no", "n/a", "generic", "genérica", "generica", ""}


def extraer_atributos_alibaba(
    atributos_estructurados: dict[str, str] | None, texto_extra: str | None = None
) -> dict[str, AtributoExtraido]:
    """
    Primero usa las specs estructuradas del proveedor (más confiables que
    un regex sobre el título) y completa con `texto_extra` (ej. subject +
    descripción) cualquier tipo que las specs no hayan cubierto.
    """
    atributos_estructurados = atributos_estructurados or {}
    resultado: dict[str, AtributoExtraido] = {}

    for tipo, alias in _ALIASES_ALIBABA_POR_TIPO.items():
        valor_crudo = None
        for nombre in alias:
            if nombre in atributos_estructurados:
                valor_crudo = str(atributos_estructurados[nombre])
                break
        if valor_crudo is None:
            continue

        if tipo == "marca":
            if valor_crudo.strip().lower() in _MARCAS_SIN_VALOR:
                continue
            resultado[tipo] = AtributoExtraido(tipo, valor_crudo, categoria_canon=valor_crudo.strip().lower())
        elif tipo in ("categoria", "material", "color"):
            canon = _canonicalizar(valor_crudo, {"categoria": CANON_CATEGORIA, "material": CANON_MATERIAL, "color": CANON_COLOR}[tipo])
            if canon:
                resultado[tipo] = AtributoExtraido(tipo, valor_crudo, categoria_canon=canon)
        else:
            # numérico: probar a extraer un número con unidad del propio
            # valor ("39(g)"); si el valor es un número pelado sin unidad
            # (ej. "10" para "quantity"), se usa tal cual sin adivinar
            # una unidad que no está.
            extraido = extraer_atributos_texto_libre(valor_crudo)
            if tipo in extraido:
                resultado[tipo] = extraido[tipo]
            else:
                try:
                    resultado[tipo] = AtributoExtraido(tipo, valor_crudo, valor_numerico=float(valor_crudo.strip()))
                except ValueError:
                    pass

    if texto_extra:
        for tipo, atributo in extraer_atributos_texto_libre(texto_extra).items():
            resultado.setdefault(tipo, atributo)

    return resultado


# --- Comparación --------------------------------------------------------


def _comparar_uno(tipo: str, va: AtributoExtraido | None, vb: AtributoExtraido | None, tolerancia: float) -> ComparacionAtributo:
    esencial = tipo in ESENCIALES

    if va is None or vb is None:
        return ComparacionAtributo(tipo, esencial, None, "atributo no disponible en uno de los dos productos")

    if tipo == "dimensiones":
        if va.valor_dimensiones is None or vb.valor_dimensiones is None:
            return ComparacionAtributo(tipo, esencial, None, "medidas no interpretables")
        da, db_ = sorted(va.valor_dimensiones), sorted(vb.valor_dimensiones)
        if len(da) != len(db_):
            return ComparacionAtributo(tipo, esencial, None, "cantidad de medidas no comparable")
        compatible = all(abs(x - y) / max(x, y, 1e-9) <= tolerancia for x, y in zip(da, db_))
        return ComparacionAtributo(tipo, esencial, compatible, f"medidas {da}cm vs {db_}cm (tolerancia {tolerancia:.0%})")

    if tipo in TIPOS_NUMERICOS:
        if va.valor_numerico is None or vb.valor_numerico is None:
            return ComparacionAtributo(tipo, esencial, None, "valor no numérico")
        diferencia = abs(va.valor_numerico - vb.valor_numerico) / max(va.valor_numerico, vb.valor_numerico, 1e-9)
        compatible = diferencia <= tolerancia
        return ComparacionAtributo(
            tipo, esencial, compatible,
            f"{va.valor_numerico:g} vs {vb.valor_numerico:g} (diferencia {diferencia:.0%}, tolerancia {tolerancia:.0%})",
        )

    # categórico (categoria, material, color, marca)
    if va.categoria_canon is None or vb.categoria_canon is None:
        return ComparacionAtributo(
            tipo, esencial, None, f"'{va.valor_crudo}' vs '{vb.valor_crudo}' no reconocidos -- no comparable con confianza"
        )
    compatible = va.categoria_canon == vb.categoria_canon
    return ComparacionAtributo(tipo, esencial, compatible, f"'{va.categoria_canon}' vs '{vb.categoria_canon}'")


def comparar_atributos(
    a: dict[str, AtributoExtraido], b: dict[str, AtributoExtraido], tolerancias: dict[str, float] | None = None
) -> list[ComparacionAtributo]:
    tolerancias_finales = {**TOLERANCIAS_DEFAULT, **(tolerancias or {})}
    tipos = sorted(set(a) | set(b))
    return [_comparar_uno(tipo, a.get(tipo), b.get(tipo), tolerancias_finales.get(tipo, 0.2)) for tipo in tipos]


def incompatibilidad_esencial(comparaciones: list[ComparacionAtributo]) -> ComparacionAtributo | None:
    """
    Primera incompatibilidad DURA encontrada (esencial + confirmada, no
    incierta), o None si no hay ninguna -- ver el docstring del módulo
    para por qué solo esto puede vetar un candidato.
    """
    for comparacion in comparaciones:
        if comparacion.esencial and comparacion.compatible is False:
            return comparacion
    return None


def score_atributos(comparaciones: list[ComparacionAtributo]) -> tuple[float, float]:
    """
    Devuelve (score, cobertura). `score` en [0, 1] sobre las comparaciones
    evaluables (compatible != None); 0.5 (neutral) si no hubo ninguna
    evaluable -- ni premia ni penaliza la falta total de evidencia.
    `cobertura` es la fracción de tipos detectados que se pudieron
    comparar de verdad, útil como señal de confianza en `matcher.py`.
    """
    evaluables = [c for c in comparaciones if c.compatible is not None]
    if not evaluables:
        return 0.5, 0.0
    compatibles = sum(1 for c in evaluables if c.compatible)
    return compatibles / len(evaluables), len(evaluables) / len(comparaciones)
