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
    scraper.py            # capa HTTP: headers, robots.txt, reintentos con backoff, delay
    parser.py             # extrae el JSON embebido en el HTML y lo normaliza
    collector.py           # orquesta por HTTP puro: recorre la paginación real y guarda en la base
    collector_browser.py   # orquesta con Chrome real (Playwright): alternativa cuando el sitio bloquea el HTTP puro
    diagnostico_precio.py  # busca un producto en el HTML crudo archivado y muestra su JSON sin normalizar
    tests/
      test_parser.py
      test_scraper.py
      test_collector_browser.py
      test_diagnostico_precio.py
      fixtures/
        productlist_page19.html          # HTML real (recortado) de un listado válido
        pagina_bloqueada_captcha.html    # HTML real (recortado) de la página de bloqueo CAPTCHA
  paginas_html_crudo/    # HTML crudo de cada página visitada por collector_browser.py (no se commitea)
  database/
    db.py             # esquema SQLite + upsert + progreso de páginas + export a CSV
    tests/test_db.py
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

## Alternativa cuando el sitio bloquea el HTTP puro: `collector_browser.py`

En la práctica, el listado terminó devolviendo el CAPTCHA "punish" de
Alibaba (HTTP 200, sin datos de producto) apenas ante requests hechos con
`requests` — sin cookies de sesión ni huella de navegador real, no importa
qué tan "educados" sean. `collector_browser.py` es la alternativa: usa
[Playwright](https://playwright.dev/python/) para manejar un **Chrome real
y visible** (no headless, no Chromium embebido) con un **perfil de datos
dedicado** (`.perfil_chrome_collector/`, separado del Chrome habitual de
la usuaria). La usuaria inicia sesión en Alibaba manualmente ahí una sola
vez; esa sesión queda guardada en el perfil para las corridas siguientes.

Puntos importantes de este enfoque:

- **No resuelve ni evade CAPTCHAs.** Si aparece uno, el collector se
  detiene ahí mismo, lo loguea, deja la ventana de Chrome abierta para que
  la usuaria decida qué hacer, y espera un ENTER en la terminal antes de
  cerrar todo. Nunca hace click ni intenta pasarlo por su cuenta.
- **Reutiliza `parser.py` y la detección de bloqueo sin cambios**: el HTML
  que devuelve `page.content()` de Playwright se parsea exactamente igual
  que el que devuelve `requests`. La detección de bloqueo también es
  compartida (`scraper.contiene_marcadores_bloqueo`), solo que ahora se
  aplica al HTML renderizado en vez de a un `requests.Response`.
- **Progreso persistido y reanudable**: cada página que se procesa con
  éxito queda marcada en la tabla `progreso_paginas` de la base. Si el
  collector se corta (por un bloqueo, por cerrar la terminal, etc.), la
  próxima corrida retoma desde ahí sin volver a pedir las páginas ya
  hechas. `--reiniciar-progreso` la resetea si en algún momento se quiere
  recorrer todo el catálogo de nuevo (no borra los productos ya guardados,
  `upsert_producto` deduplica por URL).
- **Login manual solo cuando hace falta**: la primera vez que se usa el
  perfil dedicado (o si se pasa `--login`), el collector abre la página y
  espera confirmación por ENTER antes de seguir. En corridas posteriores,
  mientras la sesión guardada siga viva, no vuelve a pedirlo.

```bash
python collector_alibaba/collector_browser.py                    # corrida normal
python collector_alibaba/collector_browser.py --login             # forzar login manual de nuevo (p. ej. sesión expirada)
python collector_alibaba/collector_browser.py --reiniciar-progreso   # olvidar progreso y recorrer todo de nuevo
python collector_alibaba/collector_browser.py --max-paginas 2      # probar con pocas páginas antes de correr las 28
python collector_alibaba/collector_browser.py --recuperar-html 1-14  # ver más abajo
```

### Recuperar el HTML crudo de páginas ya completadas (`--recuperar-html`)

`--reiniciar-progreso` vuelve a recorrer **todo** el catálogo desde cero,
lo cual no sirve si solo hace falta el HTML crudo de páginas que ya están
marcadas como completadas: si el sitio bloqueara antes de llegar a donde ya
se había llegado, se perdería un checkpoint válido (aunque los productos
sigan en SQLite).

`--recuperar-html RANGO` vuelve a visitar **solo** las páginas indicadas
(`1-14`, `3`, o `1,3,5-9`) para archivar su HTML crudo en
`paginas_html_crudo/`. A propósito **no toca `progreso_paginas`**: no
marca ni desmarca ninguna página como completada, así que no puede alterar
el checkpoint existente pase lo que pase durante la recuperación (incluido
un bloqueo a mitad de camino). Sí reutiliza el parser para refrescar
`productos_alibaba` (upsert, deduplicado por URL) como efecto secundario,
pero eso tampoco toca el progreso. Seguridad, sesión y comportamiento ante
CAPTCHA son exactamente los mismos que en una corrida normal (Chrome real
y visible, perfil dedicado, se detiene y avisa si aparece un bloqueo).

### Instalación y uso en Windows

```powershell
cd alibaba-catalog
pip install -r requirements.txt
playwright install chrome

python collector_alibaba\collector_browser.py
```

Al ejecutarlo la primera vez se abre una ventana de Chrome (con el perfil
dedicado, no el habitual): iniciá sesión en Alibaba ahí manualmente,
volvé a la terminal y presioná ENTER. De ahí en más el collector recorre
las páginas solo. Si en algún punto aparece el CAPTCHA, va a avisarlo por
consola, dejar la ventana abierta, y esperar un ENTER para cerrar.

## Archivo de HTML crudo y diagnóstico (`diagnostico_precio.py`)

`collector_browser.py` guarda el HTML de cada página que visita, tal cual,
antes de parsearlo, en `paginas_html_crudo/productlist-N.html` (no se
commitea — son datos scrapeados, no código). `parser.py` solo se queda con
los campos ya normalizados (`precio_min`, `moneda`, etc.); sin este
archivo, un campo del JSON original mal interpretado no se puede
diagnosticar ni reprocesar más tarde sin volver a navegar Alibaba.

Para ver el registro crudo (sin normalizar) de un producto puntual una vez
que hay páginas archivadas:

```bash
python collector_alibaba/diagnostico_precio.py "nombre o parte del nombre del producto"
python collector_alibaba/diagnostico_precio.py "nombre del producto" --pagina 7   # si ya se sabe la página
```

Imprime el JSON completo del producto tal cual lo entrega Alibaba (todos
los campos, no solo los que usa el parser), útil para confirmar qué
representa realmente un campo antes de tocar `parser.py`.

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

SQLite, dos tablas:

- `productos_alibaba`, con las columnas de la tabla de arriba más
  `fecha_scrapeo` (UTC, ISO 8601). `upsert_producto`/`upsert_productos`
  insertan o actualizan por `url` (no se duplican filas si se vuelve a
  correr el collector).
- `progreso_paginas` (`pagina`, `fecha_completada`), usada solo por
  `collector_browser.py` para poder reanudar sin repetir páginas ya
  recorridas. `reiniciar_progreso` la vacía sin tocar los productos.

`exportar_csv` vuelca la tabla `productos_alibaba` completa a un CSV.

## Instalación y uso

```bash
cd alibaba-catalog
pip install -r requirements.txt

# Collector por HTTP puro (recorre toda la paginación real):
# en la práctica, Alibaba lo bloquea con un CAPTCHA — ver más abajo la alternativa.
python collector_alibaba/collector.py

# Collector con Chrome real (ver sección de arriba y "Windows" para el detalle):
python collector_alibaba/collector_browser.py

# Exportar lo guardado a CSV (con cualquiera de los dos collectors):
python -c "from database import db; c = db.conectar(); db.exportar_csv(c, 'catalogo.csv')"

# Tests (no requieren red ni Chrome instalado, usan fixtures HTML reales guardados):
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
