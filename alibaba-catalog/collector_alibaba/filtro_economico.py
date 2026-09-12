"""
Filtro económico (Fase 3): cierra el flujo completo de MUTE -- demanda
real en Mercado Libre -> match adecuado en Alibaba (Match Mode) -> ¿la
diferencia de precio alcanza para justificar importarlo?

Solo llegan acá candidatos que Match Mode ya aceptó (`MATCH_ALTO` o
`MATCH_PROBABLE`, ver `matcher.py`) -- este módulo no vuelve a evaluar si
es el mismo producto, solo si conviene económicamente.

**Reglas de negocio** (dadas por la usuaria, sin cambios, confirmadas con
su propio ejemplo -- "ratio 4.29x y diferencia USD 13.80 -> supera las
DOS reglas", o sea que ambas condiciones son necesarias, no alternativas):

  - relación mínima ×2.5 (precio_ml_usd / precio_alibaba_usd >= 2.5)
  - diferencia mínima USD 10 (precio_ml_usd - precio_alibaba_usd >= 10)

**Confianza del match** (pedido explícito): un `MATCH_PROBABLE` que pasa
las reglas económicas NO se descarta -- avanza como `viable_dudoso`
(menor confianza que un `MATCH_ALTO`, que avanza como `viable`), para que
se revise a mano antes de comprometer plata, no para tirarlo a la basura.

**Nunca se asume un valor en silencio** (pedido explícito): si el precio
de Alibaba no se pudo verificar con confianza (ver `resolver_precio_alibaba`
-- ej. escalones de precio por cantidad sin evidencia real de su forma
exacta) o si falta el tipo de cambio para convertir ARS a USD, el
resultado es `indeterminado`, nunca "no viable" ni "viable" adivinado.

**Conversión de moneda**: el precio de Mercado Libre normalmente está en
ARS, el de Alibaba en USD -- hace falta convertir para poder comparar.
El tipo de cambio (`tipo_cambio_usd_ars`) es un parámetro explícito, NO
un valor hardcodeado acá. Referencia elegida por la usuaria: dólar MEP,
consultado en vivo en cada corrida por `tipo_cambio.obtener_dolar_mep`
(ver ese módulo) -- este archivo no sabe de dónde salió el número, solo
lo recibe junto con su procedencia (`tipo_cambio_fuente`,
`tipo_cambio_fecha_referencia`) para poder guardarla como evidencia.

**Trazabilidad completa** (pedido explícito -- "no quiero que quede
solamente el resultado 'viable', quiero conservar la evidencia útil"):
`ResultadoViabilidad` guarda todos los valores intermedios (precio de
Alibaba resuelto y su cantidad asociada, precio de ML original y
convertido, tipo de cambio usado, ratio, diferencia) para poder
reconstruir de dónde salió cualquier cálculo después -- ver
`database/db.py` (columnas nuevas de `alibaba_comparables`).
"""

from __future__ import annotations

from dataclasses import dataclass

RATIO_MINIMO_DEFAULT = 2.5
DIFERENCIA_MINIMA_USD_DEFAULT = 10.0

RESULTADOS_VIABILIDAD = ("viable", "viable_dudoso", "no_viable", "indeterminado")

# candidato_elegido["categoria"] que matcher.py puede haber puesto en el
# resultado -- solo estas dos categorías deberían llegar acá (Match Mode
# ya filtró SIN_MATCH_CONFIABLE), pero se valida igual, nunca se asume.
CATEGORIAS_MATCH_ACEPTADAS = ("MATCH_ALTO", "MATCH_PROBABLE")


@dataclass
class PrecioAlibabaResuelto:
    """
    Resultado de intentar determinar un precio unitario confiable de
    Alibaba para una cantidad conocida. `no_verificado=True` siempre que
    no haya certeza real -- nunca se inventa un precio "razonable".
    """

    precio_usd: float | None
    cantidad_asociada: int | None
    fuente: str  # "precio_unico" | "escalon_ladder_sin_confirmar" | "no_disponible"
    no_verificado: bool
    detalle: str
    datos_crudos: object | None = None  # evidencia cruda cuando no se pudo interpretar (ver detalle)


@dataclass
class ResultadoViabilidad:
    resultado: str  # uno de RESULTADOS_VIABILIDAD
    motivo: str
    categoria_match: str | None
    precio_ml_original: float | None
    moneda_ml: str | None
    tipo_cambio_usado: float | None
    tipo_cambio_fuente: str | None
    tipo_cambio_fecha_referencia: str | None
    precio_ml_usd: float | None
    precio_alibaba_usd: float | None
    cantidad_alibaba: int | None
    fuente_precio_alibaba: str
    precio_ladder_crudo: object | None
    ratio: float | None
    diferencia_usd: float | None
    ratio_minimo_usado: float
    diferencia_minima_usada: float


def resolver_precio_alibaba(datos_ficha_alibaba: dict) -> PrecioAlibabaResuelto:
    """
    Toma el dict que ya devuelve `parser_ficha_alibaba.parsear_ficha_alibaba`
    (reusado tal cual, no se vuelve a parsear HTML acá) y decide si hay un
    precio unitario confiable.
    """
    if not datos_ficha_alibaba.get("precio_no_verificado") and datos_ficha_alibaba.get("precio_alibaba_50u") is not None:
        return PrecioAlibabaResuelto(
            precio_usd=datos_ficha_alibaba["precio_alibaba_50u"],
            cantidad_asociada=datos_ficha_alibaba.get("moq_valor"),
            fuente="precio_unico",
            no_verificado=False,
            detalle=f"Precio único ${datos_ficha_alibaba['precio_alibaba_50u']} (sin escalones por cantidad), MOQ {datos_ficha_alibaba.get('moq_valor')}.",
        )

    if datos_ficha_alibaba.get("precio_ladder_crudo"):
        return PrecioAlibabaResuelto(
            precio_usd=None,
            cantidad_asociada=None,
            fuente="escalon_ladder_sin_confirmar",
            no_verificado=True,
            detalle=(
                "Producto con escalones de precio por cantidad (productLadderPrices) -- "
                "todavía no hay evidencia real confirmada de qué campo indica la cantidad de "
                "cada escalón, no se adivina cuál corresponde. Evidencia cruda conservada."
            ),
            datos_crudos=datos_ficha_alibaba["precio_ladder_crudo"],
        )

    return PrecioAlibabaResuelto(
        precio_usd=None,
        cantidad_asociada=None,
        fuente="no_disponible",
        no_verificado=True,
        detalle="No se pudo determinar ningún precio confiable en la ficha de Alibaba.",
    )


def _convertir_a_usd(monto: float | None, moneda: str | None, tipo_cambio_usd_ars: float | None) -> float | None:
    """
    Nunca asume una moneda ni un tipo de cambio -- devuelve None (no
    inventa) si falta cualquiera de los datos necesarios para convertir
    con confianza.
    """
    if monto is None:
        return None
    if moneda is None or moneda == "USD":
        return monto
    if moneda == "ARS":
        if tipo_cambio_usd_ars is None or tipo_cambio_usd_ars <= 0:
            return None
        return monto / tipo_cambio_usd_ars
    return None  # moneda desconocida -- no se asume nada


def evaluar_viabilidad(
    precio_ml: float | None,
    moneda_ml: str | None,
    categoria_match: str | None,
    precio_alibaba: PrecioAlibabaResuelto,
    tipo_cambio_usd_ars: float | None = None,
    tipo_cambio_fuente: str | None = None,
    tipo_cambio_fecha_referencia: str | None = None,
    ratio_minimo: float = RATIO_MINIMO_DEFAULT,
    diferencia_minima_usd: float = DIFERENCIA_MINIMA_USD_DEFAULT,
) -> ResultadoViabilidad:
    """
    Punto de entrada único del filtro económico. `precio_alibaba` viene de
    `resolver_precio_alibaba` (o construido a mano en los tests). Nunca
    tira una excepción por datos faltantes -- siempre devuelve un
    `ResultadoViabilidad` con motivo explícito, `indeterminado` cuando no
    hay evidencia suficiente para decidir viable/no_viable con confianza.

    `tipo_cambio_fuente`/`tipo_cambio_fecha_referencia` son solo para
    trazabilidad (de dónde salió `tipo_cambio_usd_ars`, ej. dólar MEP) --
    esta función no valida ni interpreta esos dos, solo los guarda en el
    resultado tal cual llegan.
    """
    base = dict(
        categoria_match=categoria_match,
        precio_ml_original=precio_ml,
        moneda_ml=moneda_ml,
        tipo_cambio_usado=tipo_cambio_usd_ars,
        tipo_cambio_fuente=tipo_cambio_fuente,
        tipo_cambio_fecha_referencia=tipo_cambio_fecha_referencia,
        precio_alibaba_usd=precio_alibaba.precio_usd,
        cantidad_alibaba=precio_alibaba.cantidad_asociada,
        fuente_precio_alibaba=precio_alibaba.fuente,
        precio_ladder_crudo=precio_alibaba.datos_crudos,
        ratio_minimo_usado=ratio_minimo,
        diferencia_minima_usada=diferencia_minima_usd,
    )

    if categoria_match not in CATEGORIAS_MATCH_ACEPTADAS:
        return ResultadoViabilidad(
            resultado="indeterminado",
            motivo=f"Categoría de match '{categoria_match}' no es MATCH_ALTO ni MATCH_PROBABLE -- no corresponde evaluar viabilidad.",
            precio_ml_usd=None, ratio=None, diferencia_usd=None, **base,
        )

    if precio_ml is None:
        return ResultadoViabilidad(
            resultado="indeterminado", motivo="Falta el precio de Mercado Libre del candidato.",
            precio_ml_usd=None, ratio=None, diferencia_usd=None, **base,
        )

    if precio_alibaba.no_verificado or precio_alibaba.precio_usd is None:
        return ResultadoViabilidad(
            resultado="indeterminado",
            motivo=f"Precio de Alibaba no verificado: {precio_alibaba.detalle}",
            precio_ml_usd=None, ratio=None, diferencia_usd=None, **base,
        )

    precio_ml_usd = _convertir_a_usd(precio_ml, moneda_ml, tipo_cambio_usd_ars)
    base["precio_ml_usd"] = precio_ml_usd

    if precio_ml_usd is None:
        motivo = (
            f"No se pudo convertir el precio de ML ({precio_ml} {moneda_ml}) a USD -- "
            + ("falta el tipo de cambio USD/ARS." if moneda_ml == "ARS" else f"moneda '{moneda_ml}' desconocida.")
        )
        return ResultadoViabilidad(resultado="indeterminado", motivo=motivo, ratio=None, diferencia_usd=None, **base)

    if precio_alibaba.precio_usd <= 0:
        return ResultadoViabilidad(
            resultado="indeterminado", motivo="Precio de Alibaba inválido (0 o negativo).",
            ratio=None, diferencia_usd=None, **base,
        )

    ratio = precio_ml_usd / precio_alibaba.precio_usd
    diferencia = precio_ml_usd - precio_alibaba.precio_usd
    base["ratio"] = ratio
    base["diferencia_usd"] = diferencia

    pasa_reglas = ratio >= ratio_minimo and diferencia >= diferencia_minima_usd

    if not pasa_reglas:
        return ResultadoViabilidad(
            resultado="no_viable",
            motivo=(
                f"Ratio {ratio:.2f}x / diferencia USD {diferencia:.2f} -- no alcanza el mínimo "
                f"requerido (×{ratio_minimo} y USD {diferencia_minima_usd})."
            ),
            **base,
        )

    if categoria_match == "MATCH_ALTO":
        return ResultadoViabilidad(
            resultado="viable",
            motivo=f"Ratio {ratio:.2f}x / diferencia USD {diferencia:.2f} -- supera las dos reglas, match de alta confianza.",
            **base,
        )

    return ResultadoViabilidad(
        resultado="viable_dudoso",
        motivo=(
            f"Ratio {ratio:.2f}x / diferencia USD {diferencia:.2f} -- supera las dos reglas, pero el match es "
            "MATCH_PROBABLE (confianza media): conviene confirmar el candidato a mano antes de avanzar."
        ),
        **base,
    )
