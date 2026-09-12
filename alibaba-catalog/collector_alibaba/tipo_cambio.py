"""
Resuelve el tipo de cambio USD/ARS a partir del dólar MEP (referencia
elegida explícitamente por la usuaria), en vivo, en cada corrida.

**Nunca hay una tasa fija en el código.** `obtener_dolar_mep()` consulta
una fuente pública cada vez que se llama -- no hay ningún valor numérico
hardcodeado acá, y el resultado puede (y debe) variar de una corrida a
otra.

**Nunca se cae en silencio a otra cotización.** Si la fuente de MEP no
está disponible, responde con un error, o la respuesta no tiene un valor
interpretable, se devuelve un `TipoCambioResuelto` con `disponible=False`
y el motivo explícito -- nunca se intenta oficial/blue/tarjeta como
"mejor que nada". Quien llama decide qué hacer (en `filtro_economico.py`,
esto significa que el candidato queda `indeterminado`).

**Toda consulta exitosa guarda su evidencia**: el valor usado, la fuente
(URL de la API), la fecha de referencia que la propia fuente reporta para
ese valor, y el momento en que MUTE la consultó (`obtenido_en`) -- pueden
no coincidir si la fuente actualiza su dato con demora.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import requests

URL_DOLAR_MEP = "https://dolarapi.com/v1/dolares/bolsa"
TIMEOUT_SEG_DEFAULT = 10.0


@dataclass
class TipoCambioResuelto:
    """
    `disponible=False` siempre que no haya certeza real del valor -- en
    ese caso `valor` es `None` y `detalle` explica por qué, nunca se
    inventa ni se aproxima con otra cotización.
    """

    valor: float | None
    fuente: str | None
    fecha_referencia: str | None  # fecha que la fuente reporta para ese valor (puede venir en cualquier formato que la fuente use)
    obtenido_en: str | None  # timestamp ISO de cuándo MUTE hizo esta consulta
    disponible: bool
    detalle: str


def obtener_dolar_mep(timeout: float = TIMEOUT_SEG_DEFAULT) -> TipoCambioResuelto:
    """
    Consulta el dólar MEP ("bolsa") en dolarapi.com y devuelve su cotización
    de venta. No reintenta con otra fuente ni otra cotización ante ningún
    tipo de falla -- ver docstring del módulo.
    """
    obtenido_en = datetime.now(timezone.utc).isoformat()

    try:
        respuesta = requests.get(URL_DOLAR_MEP, timeout=timeout)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except Exception as exc:
        return TipoCambioResuelto(
            valor=None, fuente=URL_DOLAR_MEP, fecha_referencia=None, obtenido_en=obtenido_en,
            disponible=False, detalle=f"No se pudo consultar el dólar MEP ({URL_DOLAR_MEP}): {exc}",
        )

    valor = datos.get("venta") if isinstance(datos, dict) else None
    fecha_referencia = datos.get("fechaActualizacion") if isinstance(datos, dict) else None

    if not isinstance(valor, (int, float)) or isinstance(valor, bool) or valor <= 0:
        return TipoCambioResuelto(
            valor=None, fuente=URL_DOLAR_MEP, fecha_referencia=fecha_referencia, obtenido_en=obtenido_en,
            disponible=False,
            detalle=f"La respuesta del dólar MEP no tiene un valor de venta válido: {datos!r}",
        )

    return TipoCambioResuelto(
        valor=float(valor), fuente=URL_DOLAR_MEP, fecha_referencia=fecha_referencia, obtenido_en=obtenido_en,
        disponible=True, detalle=f"Dólar MEP (venta) obtenido de {URL_DOLAR_MEP}.",
    )
