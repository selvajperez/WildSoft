"""
Lógica de cálculo del comparador Alibaba -> Mercado Libre.

Todo lo relacionado a fórmulas de costos, márgenes y al score de
ranking vive en este único archivo, separado de la interfaz (app.py),
para que sea fácil de leer, testear y modificar sin tocar Streamlit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Columnas que debe traer el CSV/Excel de entrada.
COLUMNAS_REQUERIDAS = [
    "producto",
    "precio_alibaba_usd",
    "moq",
    "peso_gramos",
    "precio_ml_ars",
    "ventas_ml",
    "costo_envio_usd",
    "limite_envio_gramos",
    "tipo_cambio",
]

# Columnas que no pueden ser cero/negativas porque se usan como
# denominador o como base de una conversión. Si una fila las viola,
# se separa como "inválida" en vez de romper el cálculo con Inf/NaN.
COLUMNAS_POSITIVAS_OBLIGATORIAS = [
    "peso_gramos",
    "limite_envio_gramos",
    "precio_ml_ars",
    "tipo_cambio",
]

# Pesos por defecto del score (deben sumar 1.0). Se pueden pasar otros
# pesos a calcular_score() sin tocar esta función, por ejemplo desde
# sliders en la interfaz.
PESOS_SCORE_DEFAULT = {
    "margen_pct": 0.30,      # rentabilidad relativa al precio de venta
    "roi_pct": 0.25,         # retorno relativo a lo invertido
    "peso_gramos": 0.15,     # cuanto menos pese, mejor (se invierte)
    "precio_ml_ars": 0.10,   # precio de venta más accesible = más atractivo (se invierte)
    "ventas_ml": 0.20,       # evidencia de que el producto ya se vende
}


def validar_columnas(df: pd.DataFrame) -> list[str]:
    """Devuelve la lista de columnas requeridas que faltan en el df."""
    return [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]


def separar_filas_validas(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Separa el dataframe en (filas_validas, filas_invalidas).

    Una fila es inválida si tiene valores en cero o negativos en
    columnas que se usan para dividir o convertir moneda (peso,
    límite de envío, precio de venta, tipo de cambio), porque eso
    generaría divisiones por cero o resultados sin sentido.
    """
    mascara_valida = pd.Series(True, index=df.index)
    for columna in COLUMNAS_POSITIVAS_OBLIGATORIAS:
        mascara_valida &= df[columna] > 0

    return df[mascara_valida].copy(), df[~mascara_valida].copy()


def calcular_metricas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega al dataframe las columnas de costos y rentabilidad por producto.

    Supuestos de negocio (fáciles de ajustar acá si cambian):
    - `costo_envio_usd` es el costo total de un envío que admite hasta
      `limite_envio_gramos`. El costo de envío de una unidad se
      prorratea según cuánto pesa esa unidad dentro de ese límite:
          costo_envio_unitario = costo_envio_usd * (peso_unidad / limite_envio)
    - Todo se expresa en ARS usando `tipo_cambio` (ARS por USD).
    - "Antes de impuestos" significa que no se restan impuestos de
      importación, IVA ni comisiones de Mercado Libre: eso se puede
      sumar más adelante como otra columna de costo si hace falta.
    """
    df = df.copy()

    df["costo_producto_ars"] = df["precio_alibaba_usd"] * df["tipo_cambio"]

    envio_unitario_usd = df["costo_envio_usd"] * df["peso_gramos"] / df["limite_envio_gramos"]
    df["costo_envio_unitario_ars"] = envio_unitario_usd * df["tipo_cambio"]

    df["costo_total_unitario_ars"] = df["costo_producto_ars"] + df["costo_envio_unitario_ars"]

    df["margen_bruto_ars"] = df["precio_ml_ars"] - df["costo_total_unitario_ars"]
    df["margen_pct"] = df["margen_bruto_ars"] / df["precio_ml_ars"] * 100
    df["roi_pct"] = df["margen_bruto_ars"] / df["costo_total_unitario_ars"] * 100
    df["ganancia_por_100g_ars"] = df["margen_bruto_ars"] / df["peso_gramos"] * 100
    df["unidades_max_por_envio"] = np.floor(df["limite_envio_gramos"] / df["peso_gramos"]).astype(int)

    return df


def _normalizar(serie: pd.Series, invertir: bool = False) -> pd.Series:
    """
    Normaliza una serie a un rango [0, 1] (min-max).

    Si todos los valores son iguales (max == min) devuelve 0.5 para
    todas las filas, en vez de dividir por cero.
    Si `invertir` es True, el valor más bajo pasa a valer 1 (útil para
    "menos peso es mejor" o "precio más accesible es mejor").
    """
    minimo, maximo = serie.min(), serie.max()
    if maximo == minimo:
        return pd.Series(0.5, index=serie.index)

    normalizada = (serie - minimo) / (maximo - minimo)
    return 1 - normalizada if invertir else normalizada


def calcular_score(df: pd.DataFrame, pesos: dict[str, float] | None = None) -> pd.DataFrame:
    """
    Agrega la columna `score` (0 a 100), combinando de forma ponderada:
    margen %, ROI %, peso (invertido), precio de venta (invertido) y
    ventas en ML (con log para no dejar que un outlier domine todo).

    `pesos` permite pasar una combinación distinta a la default sin
    tocar código, por ejemplo desde controles en la interfaz.
    """
    pesos = pesos or PESOS_SCORE_DEFAULT
    df = df.copy()

    componentes = {
        "margen_pct": _normalizar(df["margen_pct"]),
        "roi_pct": _normalizar(df["roi_pct"]),
        "peso_gramos": _normalizar(df["peso_gramos"], invertir=True),
        "precio_ml_ars": _normalizar(df["precio_ml_ars"], invertir=True),
        "ventas_ml": _normalizar(np.log1p(df["ventas_ml"].clip(lower=0))),
    }

    score = sum(componentes[nombre] * peso for nombre, peso in pesos.items())
    df["score"] = (score * 100).round(2)

    return df


def procesar(df: pd.DataFrame, pesos: dict[str, float] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Punto de entrada único para la app: valida, calcula métricas y
    score. Devuelve (resultados_validos, filas_invalidas).
    """
    validas, invalidas = separar_filas_validas(df)
    validas = calcular_metricas(validas)
    validas = calcular_score(validas, pesos=pesos)
    return validas, invalidas
