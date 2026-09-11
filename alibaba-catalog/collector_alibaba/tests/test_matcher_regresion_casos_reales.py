"""
Regresión con los 5 casos reales de la validación real de Match Mode
(ver ESTADO_ACTUAL.md) -- pedido explícito de la usuaria al implementar
la Fase A: "las mejoras no deben arreglar un caso rompiendo los que ya
funcionaban razonablemente".

Cada test usa los textos REALES de ML/Alibaba de cada caso y los
`texto_score`/`imagen_score` REALES ya medidos con el embedder CLIP real
(no se pueden reproducir exactos con los embedders fake -- serían
number no representativos), inyectados directo en `_combinar_score`/
`_categorizar` (funciones reales, sin mockear la lógica de decisión) para
poder decir con certeza qué categoría produce el código actual sobre
evidencia real ya conocida.

Resumen de los cambios de categoría encontrados por este archivo (todos
esperados y documentados en ESTADO_ACTUAL.md, no accidentes):

  - Caso 1: SIN_MATCH_CONFIABLE -> MATCH_PROBABLE (el fix de A4 corrige
    la penalización injusta por falta de imagen; A5 evita que llegue a
    MATCH_ALTO con evidencia tan delgada).
  - Caso 2: MATCH_PROBABLE -> MATCH_PROBABLE (mismo candidato, mismo
    resultado -- el score interno cambia pero la decisión no).
  - Caso 3: MATCH_ALTO -> MATCH_ALTO (tenía imagen real disponible, sin
    cambios).
  - Caso 4: SIN_MATCH_CONFIABLE -> MATCH_PROBABLE (el candidato #1 ahora
    se vetea por cantidad_piezas, distinto al Caso 1 que no llega a
    vetearse; el matcher prueba el #2 y ese sí alcanza el umbral).
  - Caso 5: MATCH_PROBABLE (falso positivo real) -> SIN_MATCH_CONFIABLE
    (el fix que motivó toda la Fase A).
"""

from atributos_matching import (
    comparar_atributos,
    extraer_atributos_alibaba,
    extraer_atributos_texto_libre,
    incompatibilidad_esencial,
    score_atributos,
)
from matcher import PesosMatching, UmbralesMatching, _categorizar, _combinar_score

PESOS = PesosMatching()
UMBRALES = UmbralesMatching()


def _evaluar_candidato(nombre_ml: str, nombre_alibaba: str, texto_score: float, imagen_score: float, imagen_disponible: bool):
    """Reproduce exactamente lo que hace `verificar_candidatos` para un candidato, con números ya medidos."""
    atributos_ml = extraer_atributos_texto_libre(nombre_ml)
    atributos_alibaba = extraer_atributos_alibaba({}, texto_extra=nombre_alibaba)
    comparaciones = comparar_atributos(atributos_ml, atributos_alibaba)
    veto = incompatibilidad_esencial(comparaciones)
    if veto is not None:
        return "SIN_MATCH_CONFIABLE", veto.tipo, None

    atributos_score, cobertura = score_atributos(comparaciones)
    score_final = _combinar_score(texto_score, imagen_score, imagen_disponible, atributos_score, cobertura, PESOS)
    categoria = _categorizar(score_final, imagen_disponible, cobertura, UMBRALES)
    return categoria, None, score_final


NOMBRE_ML_CASO_1 = "Cepillo Limpiador Eléctrico 9 accesorios Multifuncion Piso Color Blanco"
CANDIDATOS_CASO_1 = [
    ("5 in 1 Electric Rechargeable Handheld PP Nylon Eco-Friendly Multi-Functional Cleaning Brush for Bathroom & Kitchen Floors", 0.869426),
    ("Hot Sale Custom Multifunctional 4 in 1 Wireless Electric Magic Brush Spin Scrubber Scrub Cleaning Brush Power Scrubber", 0.878382),
    ("5 in 1 Rechargeable Handheld PP Nylon Eco-Friendly Multi-Functional Electric Cleaning Brush for Bathroom & Kitchen Floors", 0.872671),
]


def test_caso_1_real_ahora_alcanza_match_probable_no_altisimo_por_evidencia_delgada():
    """
    Antes del fix: los 3 candidatos quedaban en SIN_MATCH_CONFIABLE
    (~0.59, por muy poco) porque la ausencia de imagen de ML restaba 35%
    de peso a valor 0.0. Con A4 corregido, el primer candidato (mejor
    rankeado) alcanza MATCH_PROBABLE -- pero el gate de A5 le impide
    llegar a MATCH_ALTO, porque solo hay dos señales reales disponibles
    (texto + un único atributo débil, "categoria") y ninguna imagen.
    """
    nombre_candidato, texto_score = CANDIDATOS_CASO_1[0]
    categoria, veto_tipo, score = _evaluar_candidato(NOMBRE_ML_CASO_1, nombre_candidato, texto_score, 0.0, False)
    assert veto_tipo is None
    # El score ponderado puede superar numéricamente el umbral de MATCH_ALTO
    # (0.80) -- el punto del gate de A5 es justamente que, sin imagen
    # disponible, la CATEGORÍA queda topeada en MATCH_PROBABLE aunque el
    # número solo sea alto.
    assert categoria == "MATCH_PROBABLE"
    assert score is not None and score >= UMBRALES.match_probable


def test_caso_1_real_ningun_candidato_queda_vetado():
    """Los 3 candidatos son variantes genuinas del mismo tipo de cepillo -- ninguno debe vetarse."""
    for nombre_candidato, texto_score in CANDIDATOS_CASO_1:
        categoria, veto_tipo, _ = _evaluar_candidato(NOMBRE_ML_CASO_1, nombre_candidato, texto_score, 0.0, False)
        assert veto_tipo is None, f"'{nombre_candidato}' no debería vetarse"


def test_caso_2_real_sigue_siendo_match_probable():
    """
    Caso 2 ya cruzaba el umbral de MATCH_PROBABLE incluso antes del fix
    (0.606) -- el score interno cambia con A4, pero la categoría final
    no debe cambiar (no hay "atributos" con cobertura suficiente para
    reclasificar como ALTO, y no correspondería: sigue faltando imagen).
    """
    nombre_ml = "Cepillo De Mano Calabro Suave Para Lavar Autos Ruedas Y Carrocería"
    nombre_alibaba = "High Quality Soft Bristle Handle Car Cleaning Brush Reusable Car Wash Accessories Brush Car Wheel Cleaning Brush"
    categoria, veto_tipo, score = _evaluar_candidato(nombre_ml, nombre_alibaba, 0.901337, 0.0, False)
    assert veto_tipo is None
    assert categoria == "MATCH_PROBABLE"
    assert score is not None and score >= UMBRALES.match_probable


def test_caso_3_real_sigue_siendo_match_alto_con_imagen_disponible():
    """
    Único de los 5 casos reales con imagen real disponible en ambos
    lados (imagen_score=0.82) -- el gate de A5 no debe afectarlo: las
    tres señales están disponibles, MATCH_ALTO se mantiene.
    """
    nombre_ml = (
        "Cepillo Eléctrico Limpieza Inalámbrico 8 En 1 Recargable Cabezales Intercambiables Mango "
        "Extensible Giratorio Baño Cocina Azulejos Juntas Piso Ducha Inodoro Bacha Multifunción Profunda USB"
    )
    nombre_alibaba = (
        "Hot Sale Custom Multifunctional 4 In 1 Wireless Electric Magic Brush Spin Scrubber "
        "Scrub Cleaning Brush Power Scrubber"
    )
    categoria, veto_tipo, score = _evaluar_candidato(nombre_ml, nombre_alibaba, 0.861342, 0.820158, True)
    assert veto_tipo is None
    assert categoria == "MATCH_ALTO"
    assert score is not None and score >= UMBRALES.match_alto


NOMBRE_ML_CASO_4 = "Set 4 Cepillos Limpieza Oh My Shop Surcos Hendiduras Cerdas Duraderas"


def test_caso_4_real_el_candidato_top_ahora_se_vetea_por_cantidad_de_piezas():
    """
    Antes del fix A3, "Set 4" (ML) vs. "Set of 3" (candidato top de
    Alibaba) nunca se comparaban -- ahora sí, y 4 piezas vs. 3 piezas es
    una incompatibilidad esencial real (tolerancia 0.0 para cantidad de
    piezas).
    """
    categoria, veto_tipo, _ = _evaluar_candidato(NOMBRE_ML_CASO_4, "Cleaning Brush Set of 3", 0.876794, 0.0, False)
    assert veto_tipo == "cantidad_piezas"
    assert categoria == "SIN_MATCH_CONFIABLE"


def test_caso_4_real_el_segundo_candidato_no_vetado_alcanza_match_probable():
    """
    Al quedar vetado el #1, el matcher (ajuste #1) prueba el #2 -- que no
    menciona una cantidad de piezas específica, así que no hay
    incompatibilidad ahí, y alcanza MATCH_PROBABLE (con el mismo tope de
    A5 por falta de imagen).
    """
    nombre_candidato = (
        "Household Clothing Cleaning Brush Set Multifunctional Home Brush Nice Quality pp Cleaning Brush"
    )
    categoria, veto_tipo, score = _evaluar_candidato(NOMBRE_ML_CASO_4, nombre_candidato, 0.809350, 0.0, False)
    assert veto_tipo is None
    # Ver nota en el Caso 1: el score numérico puede superar 0.80, el gate
    # de A5 topea la categoría en MATCH_PROBABLE por falta de imagen.
    assert categoria == "MATCH_PROBABLE"
    assert score is not None and score >= UMBRALES.match_probable


NOMBRE_ML_CASO_5 = "Camiseta Oficial Boca Juniors Ranglan 2026 + Short"


def test_caso_5_real_el_falso_positivo_ahora_se_vetea_por_identidad():
    """
    El hallazgo que motivó toda la Fase A: esta camiseta con licencia
    oficial de Boca Juniors puntuaba MATCH_PROBABLE (0.75) contra una
    fábrica de Alibaba que imprime cualquier logo a pedido. Con el
    atributo "identidad" (A1), ahora vetea.
    """
    nombre_candidato = (
        "Custom Cross-Border Football Shorts and Jerseys with Logo Printing Soccer Club Uniforms "
        "for Various Football Matches"
    )
    categoria, veto_tipo, _ = _evaluar_candidato(NOMBRE_ML_CASO_5, nombre_candidato, 0.706556, 0.811735, True)
    assert veto_tipo == "identidad"
    assert categoria == "SIN_MATCH_CONFIABLE"


def test_caso_5_real_el_segundo_candidato_tambien_se_vetea():
    """El segundo candidato del top_k real de este caso también se anuncia como personalizable -- también debe vetarse."""
    nombre_candidato = (
        "Wholesale High Quality Customized Short Sleeve Summer Player Retro Version Soccer Jersey "
        "Quick Dry Polyester Football Shirt"
    )
    categoria, veto_tipo, _ = _evaluar_candidato(NOMBRE_ML_CASO_5, nombre_candidato, 0.721054, 0.813165, True)
    assert veto_tipo == "identidad"
    assert categoria == "SIN_MATCH_CONFIABLE"
