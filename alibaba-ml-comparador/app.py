"""
Comparador Alibaba -> Mercado Libre Argentina.

App Streamlit para decidir qué productos conviene importar y revender,
a partir de un CSV/Excel cargado manualmente (sin scraping). La lógica
de cálculo está en calculos.py; este archivo solo arma la interfaz.
"""

import pandas as pd
import streamlit as st

from calculos import (
    COLUMNAS_REQUERIDAS,
    PESOS_SCORE_DEFAULT,
    procesar,
    validar_columnas,
)

st.set_page_config(page_title="Comparador Alibaba -> ML", layout="wide")

COLUMNAS_A_MOSTRAR = [
    "producto",
    "score",
    "margen_bruto_ars",
    "margen_pct",
    "roi_pct",
    "ganancia_por_100g_ars",
    "costo_producto_ars",
    "costo_envio_unitario_ars",
    "costo_total_unitario_ars",
    "precio_ml_ars",
    "peso_gramos",
    "unidades_max_por_envio",
    "ventas_ml",
    "moq",
]

FORMATOS = {
    "score": "{:.1f}",
    "margen_bruto_ars": "$ {:,.0f}",
    "margen_pct": "{:.1f}%",
    "roi_pct": "{:.1f}%",
    "ganancia_por_100g_ars": "$ {:,.0f}",
    "costo_producto_ars": "$ {:,.0f}",
    "costo_envio_unitario_ars": "$ {:,.0f}",
    "costo_total_unitario_ars": "$ {:,.0f}",
    "precio_ml_ars": "$ {:,.0f}",
    "peso_gramos": "{:,.0f} g",
}

st.title("🦊 Comparador Alibaba → Mercado Libre")
st.caption(
    "Cargá un CSV o Excel con tus productos y obtené costos, márgenes, ROI "
    "y un ranking para decidir qué importar. Primera versión: datos manuales, sin scraping."
)

with st.sidebar:
    st.header("1. Cargar datos")
    archivo = st.file_uploader("CSV o Excel (.csv, .xlsx)", type=["csv", "xlsx", "xls"])

    with open("data/ejemplo.csv", "rb") as f:
        st.download_button(
            "⬇️ Descargar plantilla de ejemplo",
            data=f,
            file_name="plantilla_comparador.csv",
            mime="text/csv",
        )

    st.header("2. Ajustar el score (opcional)")
    st.caption("Los pesos deben sumar 1.0. Se re-normalizan automáticamente si no.")
    pesos_usuario = {}
    for nombre, valor_default in PESOS_SCORE_DEFAULT.items():
        pesos_usuario[nombre] = st.slider(nombre, 0.0, 1.0, valor_default, 0.05)

    suma_pesos = sum(pesos_usuario.values()) or 1.0
    pesos_normalizados = {k: v / suma_pesos for k, v in pesos_usuario.items()}

if archivo is None:
    st.info("Subí un archivo desde la barra lateral para ver los resultados.")
    st.subheader("Columnas esperadas")
    st.code(", ".join(COLUMNAS_REQUERIDAS))
    st.stop()

try:
    if archivo.name.endswith(".csv"):
        df_crudo = pd.read_csv(archivo)
    else:
        df_crudo = pd.read_excel(archivo)
except Exception as error:
    st.error(f"No se pudo leer el archivo: {error}")
    st.stop()

df_crudo.columns = df_crudo.columns.str.strip().str.lower()

columnas_faltantes = validar_columnas(df_crudo)
if columnas_faltantes:
    st.error(
        "Faltan columnas obligatorias en el archivo: "
        + ", ".join(columnas_faltantes)
    )
    st.stop()

resultados, invalidas = procesar(df_crudo, pesos=pesos_normalizados)

if not invalidas.empty:
    st.warning(
        f"Se excluyeron {len(invalidas)} fila(s) por tener peso, límite de envío, "
        "precio de venta o tipo de cambio en cero o negativo."
    )
    with st.expander("Ver filas excluidas"):
        st.dataframe(invalidas, use_container_width=True)

if resultados.empty:
    st.error("No quedaron filas válidas para calcular.")
    st.stop()

st.subheader("Ranking de productos")

col_orden, col_direccion = st.columns([2, 1])
with col_orden:
    orden_por = st.selectbox(
        "Ordenar por",
        options=["score", "margen_bruto_ars", "margen_pct", "roi_pct", "ganancia_por_100g_ars"],
        format_func=lambda x: {
            "score": "Score",
            "margen_bruto_ars": "Margen bruto ($)",
            "margen_pct": "Margen (%)",
            "roi_pct": "ROI (%)",
            "ganancia_por_100g_ars": "Ganancia cada 100g",
        }[x],
    )
with col_direccion:
    descendente = st.radio("Dirección", ["Mayor a menor", "Menor a mayor"]) == "Mayor a menor"

tabla = resultados.sort_values(orden_por, ascending=not descendente)[COLUMNAS_A_MOSTRAR]

st.dataframe(
    tabla.style.format(FORMATOS),
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "⬇️ Descargar resultados (CSV)",
    data=tabla.to_csv(index=False).encode("utf-8"),
    file_name="ranking_productos.csv",
    mime="text/csv",
)

st.divider()
st.subheader("Detalle por producto")
producto_elegido = st.selectbox("Producto", resultados["producto"])
fila = resultados[resultados["producto"] == producto_elegido].iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Score", f"{fila['score']:.1f}")
c2.metric("Margen bruto", f"$ {fila['margen_bruto_ars']:,.0f}")
c3.metric("Margen %", f"{fila['margen_pct']:.1f}%")
c4.metric("ROI", f"{fila['roi_pct']:.1f}%")

c5, c6, c7, c8 = st.columns(4)
c5.metric("Ganancia c/100g", f"$ {fila['ganancia_por_100g_ars']:,.0f}")
c6.metric("Costo total unitario", f"$ {fila['costo_total_unitario_ars']:,.0f}")
c7.metric("Unidades máx. por envío", f"{fila['unidades_max_por_envio']:.0f}")
c8.metric("Ventas en ML", f"{fila['ventas_ml']:.0f}")
