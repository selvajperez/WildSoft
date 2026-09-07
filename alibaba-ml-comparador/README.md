# Comparador Alibaba → Mercado Libre Argentina

App simple en Streamlit para decidir qué productos conviene importar desde
Alibaba y revender en Mercado Libre Argentina. Primera versión: los datos
se cargan a mano desde un CSV/Excel (sin scraping).

Este proyecto es independiente del sitio Astro del resto del repo (vive
solo en esta carpeta, con su propio `requirements.txt`).

## Instalación

```bash
cd alibaba-ml-comparador
pip install -r requirements.txt
```

## Ejecutar

```bash
streamlit run app.py
```

## Formato de entrada (CSV o Excel)

Columnas requeridas (ver `data/ejemplo.csv` como plantilla, descargable
también desde la barra lateral de la app):

| Columna | Significado |
|---|---|
| `producto` | Nombre del producto |
| `precio_alibaba_usd` | Precio unitario en Alibaba, en USD |
| `moq` | Cantidad mínima de compra (informativo) |
| `peso_gramos` | Peso de una unidad, en gramos |
| `precio_ml_ars` | Precio de venta en Mercado Libre, en ARS |
| `ventas_ml` | Ventas/unidades vendidas observadas en ML (evidencia de demanda) |
| `costo_envio_usd` | Costo total de un envío que admite hasta `limite_envio_gramos` |
| `limite_envio_gramos` | Peso máximo que cubre ese `costo_envio_usd` |
| `tipo_cambio` | Tipo de cambio ARS por USD a usar en los cálculos |

## Qué calcula (`calculos.py`)

Por producto:

- **Costo del producto en ARS**: `precio_alibaba_usd * tipo_cambio`
- **Costo de envío prorrateado**: el envío se contrata por lote (hasta
  `limite_envio_gramos` cuesta `costo_envio_usd`), así que a cada unidad
  se le carga la parte proporcional a su peso:
  `costo_envio_usd * (peso_gramos / limite_envio_gramos) * tipo_cambio`
- **Costo total unitario (antes de impuestos)**: producto + envío. No
  incluye impuestos de importación, IVA ni comisión de ML — se puede
  sumar como otra columna de costo el día que haga falta.
- **Margen bruto ($)**: precio de venta − costo total unitario
- **Margen (%)**: margen bruto / precio de venta
- **ROI (%)**: margen bruto / costo total unitario
- **Ganancia cada 100 g transportados**: margen bruto / peso × 100
- **Unidades máximas por envío**: `limite_envio_gramos // peso_gramos`

Filas con peso, límite de envío, precio de venta o tipo de cambio en
cero o negativo se excluyen del cálculo (se muestran aparte en la app)
para no dividir por cero.

## Score de ranking

Combina, normalizados entre 0 y 1 y luego pasados a una escala de 0 a
100:

- Margen % (más alto, mejor)
- ROI % (más alto, mejor)
- Peso (más bajo, mejor — se invierte)
- Precio de venta en ML (más accesible, mejor — se invierte)
- Ventas en ML, con logaritmo para que un producto con ventas
  extremadamente altas no aplaste al resto (más alto, mejor)

Los pesos de cada componente están en `PESOS_SCORE_DEFAULT` dentro de
`calculos.py`, y también se pueden ajustar desde sliders en la barra
lateral de la app (se re-normalizan solos si no suman 1.0).

## Estructura

```
alibaba-ml-comparador/
  app.py              # interfaz Streamlit
  calculos.py         # toda la lógica de cálculo y del score
  data/ejemplo.csv     # plantilla / datos de ejemplo
  tests/test_calculos.py
  requirements.txt
```

## Cómo modificarlo

- Cambiar una fórmula de costo/margen: editar `calcular_metricas` en
  `calculos.py`.
- Cambiar qué pesa más en el ranking: editar `PESOS_SCORE_DEFAULT` o
  mover sliders en la app.
- Agregar una columna nueva a la tabla: calcularla en `calculos.py` y
  sumarla a `COLUMNAS_A_MOSTRAR` / `FORMATOS` en `app.py`.
- Correr los tests: `pytest` desde esta carpeta.
