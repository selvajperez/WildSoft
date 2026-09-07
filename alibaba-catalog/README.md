# Catálogo Alibaba (collector automatizado)

Proyecto independiente del resto del repo (vive solo en esta carpeta, con
su propio `requirements.txt`). Es la evolución de `alibaba-ml-comparador/`
(que carga datos a mano): acá el objetivo es automatizar la recolección
del catálogo completo de un proveedor puntual de Alibaba.

**Alcance de esta versión: solo el collector del catálogo de Alibaba.**
Mercado Libre, el comparador y la UI quedan pendientes para una sesión
posterior (ver `comparator/README.md` y `ui/README.md`), una vez que se
valide que el catálogo se extrae bien.

## Estructura

```
alibaba-catalog/
  collector_alibaba/
    scraper.py       # capa HTTP: headers, robots.txt, reintentos con backoff, delay
    parser.py        # extrae el JSON embebido en el HTML y lo normaliza
    collector.py      # orquesta: recorre la paginación real y guarda en la base
    tests/
      test_parser.py
      fixtures/productlist_page19.html   # HTML real (recortado) para testear sin red
  database/
    db.py             # esquema SQLite + upsert + export a CSV
  comparator/README.md   # pendiente (fase 2)
  ui/README.md           # pendiente (fase 2)
  requirements.txt
```

## Cómo funciona el scraping

El listado (`https://dcsjry888.m.en.alibaba.com/productlist-N.html?filter=all&sortType=modified-desc`)
no necesita un navegador headless: cada módulo de la página (lista de
productos, categorías, paginación) viaja completo como JSON dentro del
atributo `module-data` de un `<div>`, codificado como URL-encoding. Con
`requests` + `BeautifulSoup` alcanza para extraerlo — se confirmó
inspeccionando el HTML real de la página 19 del listado.

La paginación real usa el patrón `formatString` que el propio sitio
declara en ese JSON (`/productlist-{page}.html?filter=all&sortType=modified-desc`),
así que el collector no adivina la URL: la lee de la respuesta de la
página 1 junto con el total de productos y de productos por página, y
calcula cuántas páginas recorrer. Si en algún punto una página no trae
productos, corta ahí (protección extra por si el conteo declarado no
coincide con la realidad).

### Scraping "educado"

- User-Agent identificable con datos de contacto.
- Delay aleatorio de 1-2 segundos entre página y página.
- Reintentos cortos (máx. 3) con backoff exponencial (2s, 4s, 8s) ante
  errores de red o status inesperado.
- Chequeo de `robots.txt` del dominio antes de arrancar (si no se puede
  obtener, se asume permitido — no hay forma de "denegar por las dudas"
  sin bloquear scraping legítimo).
- Sin rotación de proxies, sin resolución de CAPTCHAs, sin ninguna otra
  técnica de evasión. Si el sitio bloquea (403/429/503 o CAPTCHA), el
  collector corta, loguea el bloqueo en `collector_alibaba/collector.log`
  y no reintenta indefinidamente.

## Qué se extrae por producto

| Campo | Origen | Notas |
|---|---|---|
| `nombre` | `subject` | |
| `url` | `url` | clave de deduplicación en la base |
| `precio_min` / `precio_max` | `fobPriceWithoutUnit` (con fallback a `priceFrom` en USD) | precio único → min = max |
| `moneda` | detectada del string de precio | depende de la localización que devuelva el sitio en el momento del scrapeo |
| `moq` | `moq` | texto tal cual lo muestra el sitio (ej. "10 unidades") |
| `cantidad_vendida` | `prodSold180` | ventas de los últimos 180 días, si el sitio la expone |
| `imagen_principal` | `imageUrls.original` | normalizada a URL absoluta |
| `categoria_id` / `categoria` | `groupId`, resuelto contra el módulo de categorías | puede ser `null` / "Sin agrupar" |
| `peso_gramos` | — | **siempre `NULL` en esta fase**: no está en el listado, solo en la ficha de detalle (fase 2, fuera de esta tarea) |
| `producto_id_alibaba` | `id` | id interno de Alibaba, útil como referencia adicional |

## Base de datos (`database/db.py`)

SQLite, tabla `productos_alibaba` con las columnas de la tabla de arriba
más `fecha_scrapeo` (UTC, ISO 8601). `upsert_producto`/`upsert_productos`
insertan o actualizan por `url` (no se duplican filas si se vuelve a
correr el collector). `exportar_csv` vuelca la tabla completa a un CSV.

## Instalación y uso

```bash
cd alibaba-catalog
pip install -r requirements.txt

# Correr el collector completo (recorre toda la paginación real):
python collector_alibaba/collector.py

# Exportar lo guardado a CSV:
python -c "from database import db; c = db.conectar(); db.exportar_csv(c, 'catalogo.csv')"

# Tests (no requieren red, usan el fixture HTML real guardado):
pip install pytest
pytest
```

## Qué falta

- **Fase 2 (fuera de esta tarea)**: visitar la ficha de detalle de cada
  producto para completar `peso_gramos` (y eventualmente confirmar/afinar
  `categoria` para productos sin categoría en el listado).
- **`comparator/`**: lógica de rentabilidad y score, una vez que haya
  también datos de Mercado Libre.
- **`ui/`**: app Streamlit para explorar catálogo + comparación.
