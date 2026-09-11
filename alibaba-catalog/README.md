# Catálogo Alibaba + motor de sourcing Mercado Libre → Alibaba (MUTE)

Proyecto independiente del resto del repo (vive solo en esta carpeta, con
su propio `requirements.txt`). Es la evolución de `alibaba-ml-comparador/`
(que carga datos a mano). Tiene dos partes:

1. **Collector de catálogo Alibaba** (`collector_alibaba/`, `database/db.py`
   tablas `productos_alibaba`/`progreso_paginas`): recorre el catálogo
   completo de un proveedor puntual — ya funcionando, ver secciones de
   abajo.
2. **Motor de sourcing automático** (en construcción, por fases — ver
   `database/db.py` tablas `candidatos_ml`/`alibaba_comparables`/
   `historial_ml`): busca demanda en Mercado Libre, encuentra comparables
   en Alibaba, verifica precio real en la ficha individual, aplica un
   filtro económico, y arma una shortlist de finalistas. Pensado para
   correr solo, durante horas, sin intervención manual salvo resolver un
   CAPTCHA si aparece.

## Estructura

```
alibaba-catalog/
  collector_alibaba/
    scraper.py            # capa HTTP: headers, robots.txt, reintentos con backoff, delay
    parser.py             # extrae el JSON embebido en el HTML y lo normaliza
    collector.py           # orquesta por HTTP puro: recorre la paginación real y guarda en la base
    collector_browser.py   # orquesta con Chrome real (Playwright): alternativa cuando el sitio bloquea el HTTP puro
    diagnostico_precio.py  # busca un producto en el HTML crudo archivado y muestra su JSON sin normalizar
    capturador_exploratorio.py  # Fase 1 del sourcing: captura automática de muestras ML + Alibaba
    parser_ficha_alibaba.py     # Fase 2 (arranque): parsea la ficha individual de Alibaba (precio real, MOQ)
    parser_ficha_ml.py          # Fase 1 (arranque): parsea la ficha individual de Mercado Libre (demanda, precio)
    tests/
      test_parser.py
      test_scraper.py
      test_collector_browser.py
      test_diagnostico_precio.py
      test_capturador_exploratorio.py
      test_parser_ficha_alibaba.py
      test_parser_ficha_ml.py
      fixtures/
        productlist_page19.html          # HTML real (recortado) de un listado válido
        productlist_page_mixto.html      # los mismos 2 + 2 productos reales "a Cotizar" (RFQ)
        pagina_bloqueada_captcha.html    # HTML real (recortado) de la página de bloqueo CAPTCHA
        ml_desafio_pow.html              # HTML real: desafío Proof-of-Work de Mercado Libre (no es un CAPTCHA humano)
        alibaba_ficha_real.html          # HTML real (recortado) de una ficha de producto de Alibaba
        ml_ficha_real.html               # HTML real (recortado) de una ficha de producto de Mercado Libre
  paginas_html_crudo/       # HTML crudo de cada página visitada por collector_browser.py (no se commitea)
  capturas_exploratorias/   # muestras de capturador_exploratorio.py + manifiesto.jsonl (no se commitea)
  database/
    db.py             # esquema SQLite: catálogo Alibaba + motor de sourcing ML/Alibaba
    tests/
      test_db.py            # catálogo (productos_alibaba, progreso_paginas)
      test_db_sourcing.py   # motor de sourcing (candidatos_ml, alibaba_comparables, historial_ml)
  comparator/README.md   # pendiente (fases 3-4 del sourcing)
  ui/README.md           # pendiente (fase de shortlist final)
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
| `compra_directa` | `tradeProduct AND rtsProduct` | `True` = el producto tiene "Agregar al carrito"/compra directa; `False` = solo "Chatear ahora" (RFQ, requiere cotizar). Confirmado con 2 productos reales de cada tipo (ver `productlist_page_mixto.html`): en los "a Cotizar" ambos flags vienen en `false` juntos. |
| `envio_calculable` | `aliFreight` | `True` = Alibaba puede calcular el flete para este producto. En los productos "a Cotizar" viene `false`, y de hecho el campo `localFreightStr` del listado directamente no está presente en el JSON. |

**Nota sobre costo de envío**: no se agregó `costo_envio`/`cantidad_envio`. El único campo candidato (`localFreightStr`) no es confiable — en el fixture, dos productos completamente distintos mostraban el *mismo* valor exacto (`"ARS 61.740,30"`), señal de que es una estimación genérica y no un costo real por producto. Se decidió no exponerlo hasta confirmar un cálculo confiable por producto (probablemente haría falta visitar la ficha de detalle).

## Base de datos (`database/db.py`)

SQLite, dos tablas:

- `productos_alibaba`, con las columnas de la tabla de arriba más
  `fecha_scrapeo` (UTC, ISO 8601). `upsert_producto`/`upsert_productos`
  insertan o actualizan por `url` (no se duplican filas si se vuelve a
  correr el collector). `compra_directa`/`envio_calculable` se agregaron
  después de la primera versión: `conectar()` hace el `ALTER TABLE`
  automáticamente si la base ya existía sin esas columnas (no hace falta
  recrear ni perder los productos ya guardados).
- `progreso_paginas` (`pagina`, `fecha_completada`), usada solo por
  `collector_browser.py` para poder reanudar sin repetir páginas ya
  recorridas. `reiniciar_progreso` la vacía sin tocar los productos.

`exportar_csv` vuelca la tabla `productos_alibaba` completa a un CSV.

## Esquema del motor de sourcing (`candidatos_ml`, `alibaba_comparables`, `historial_ml`)

Tablas nuevas, independientes del catálogo Alibaba de arriba (mismo
archivo `.db`, sin tocar `productos_alibaba`/`progreso_paginas`):

- **`candidatos_ml`**: una fila por publicación de Mercado Libre con
  evidencia de demanda. Se deduplica por `url_ml` (`upsert_candidato_ml`).
  `estado` recorre el pipeline (`ESTADOS_CANDIDATO` en `db.py`): `nuevo` →
  `con_comparable` → `precio_verificado` → `segunda_etapa` → `finalista`,
  o alguno de los `descartado_*` con su `motivo_descarte`.
  `fecha_detectado` se preserva entre actualizaciones (no se pisa).
- **`alibaba_comparables`**: el producto de Alibaba elegido como
  comparable de un candidato (`candidato_id`), con el precio **verificado
  en la ficha individual** (`precio_alibaba_50u`) — nunca el de la
  búsqueda. `precio_no_verificado`/`requiere_contacto_proveedor` son los
  flags de la regla "si no se puede determinar el precio con confianza,
  excluir de esta corrida".
- **`historial_ml`**: observaciones de un candidato en el tiempo (precio,
  stock visible, ventas visibles, ranking). **Append-only**:
  `registrar_observacion_historial` siempre inserta una fila nueva, nunca
  actualiza una existente — es la base para medir rotación real
  comparando observaciones sucesivas, no un snapshot que se pisa.

Todavía no hay collector que llene estas tablas (eso es la fase 1 en
adelante) — por ahora es el esquema + las funciones de acceso, ya
testeadas con SQLite en memoria (`database/tests/test_db_sourcing.py`).

## Captura automática de muestras (`capturador_exploratorio.py`)

Antes de escribir el parser de Mercado Libre (o el de la ficha individual
de Alibaba) hace falta HTML real para inspeccionar su estructura — mismo
criterio que ya usamos con el catálogo Alibaba: nunca adivinar el formato.
Pero acá no tiene sentido pedirle a la usuaria que navegue y guarde
páginas a mano — el objetivo del proyecto es automatizar exactamente eso.

`capturador_exploratorio.py` usa el mismo Chrome real + perfil persistente
que `collector_browser.py` (mismo login manual, sirve para ambos sitios) y
captura sola, sin ningún dato manual:

1. Una búsqueda en Mercado Libre (`--busqueda-ml`, default "cepillo de
   limpieza" — la misma categoría del proveedor Alibaba ya catalogado).
2. La ficha del primer resultado de esa búsqueda (extracción best-effort
   del link por patrón `MLA-<dígitos>`; si no encuentra nada porque el
   patrón real de ML es distinto, lo loguea y sigue sin la ficha en vez
   de romper la corrida).
3. Una ficha de producto de Alibaba (`--url-alibaba`, default: un producto
   real de compra directa ya confirmado en esta catalogación).

```bash
python collector_alibaba/capturador_exploratorio.py
python collector_alibaba/capturador_exploratorio.py --busqueda-ml "candado bicicleta"
python collector_alibaba/capturador_exploratorio.py --login   # forzar login manual de nuevo
```

Guarda cada HTML en `capturas_exploratorias/` y un renglón por captura en
`capturas_exploratorias/manifiesto.jsonl` (URL, archivo, timestamp,
si se detectó un bloqueo).

**Actualización con evidencia real (primera corrida)**: lo primero que
devuelve Mercado Libre ante una visita nueva **no es un CAPTCHA que
necesite una persona** — es un desafío "Proof of Work" de Akamai Bot
Manager (`es_desafio_pow_ml`, confirmado con HTML real en
`tests/fixtures/ml_desafio_pow.html`). Ese desafío lo resuelve solo el
JavaScript de la propia página (cualquier navegador real que ejecute JS,
como el nuestro, lo pasa en unos segundos) y después navega sola al
contenido real — así que la herramienta **espera unos segundos en vez de
pedir intervención humana** (`_esperar_resolucion_desafio_pow`).
`bloqueado_ml_heuristico` (heurístico genérico, todavía sin confirmar con
HTML real) queda como red de seguridad para un bloqueo *distinto* de este
desafío — si algún día aparece uno, hay que repetir el mismo proceso: mirar
el HTML real capturado, agregar marcadores específicos, sacar el
heurístico genérico.

Para Alibaba se reutiliza `scraper.contiene_marcadores_bloqueo`, ya
confirmado con HTML real desde antes.

Si de verdad hace falta intervención humana (`bloqueado_ml_heuristico` o
el bloqueo de Alibaba), la herramienta pausa, pide resolverlo en la
ventana de Chrome, y **al presionar ENTER sigue sola** con el resto de las
capturas — a diferencia de `collector_browser.py`, acá no hay un catálogo
largo que proteger cortando la corrida, así que tiene sentido seguir en
vez de abortar todo.

**Otro detalle real que apareció en la primera corrida**: `page.content()`
de Playwright puede tirar un error transitorio si se llama justo mientras
la página está navegando — pasa seguido acá porque el desafío PoW redirige
sola apenas se resuelve. `_contenido_seguro()` reintenta en vez de romper
la captura entera por una carrera de timing.

## Parser de ficha individual de Alibaba (`parser_ficha_alibaba.py`)

Confirmado con HTML real (`tests/fixtures/alibaba_ficha_real.html`,
capturado por `capturador_exploratorio.py`): la ficha de producto
(`product-detail`) usa una plantilla completamente distinta a la del
listado — no hay `module-data` en atributos, hay un único bloque
`window.detailData = {...}` con todo (precio real, MOQ, sku, specs).

`extraer_detail_data(html)` saca ese bloque balanceando llaves (una regex
simple no alcanza porque hay strings con llaves adentro).
`parsear_ficha_alibaba(html, url)` arma un dict con la forma de
`alibaba_comparables`:

- `precio_alibaba_50u` / `moneda`: de
  `globalData.product.price.productRangePrices` — si
  `dollarPriceRangeLow == dollarPriceRangeHigh` es un precio único y vale
  para cualquier cantidad (confirmado: el producto de referencia,
  Alibaba ID 1601487795601, es así). Si son distintos, el producto tiene
  escalones de precio por cantidad y **todavía no sabemos qué campo indica
  el escalón exacto para ~50 unidades** — se marca `precio_no_verificado`
  en vez de adivinar.
- `moq`: de `globalData.product.moq` / `customsMoq`.

Falta conseguir (con el propio `capturador_exploratorio.py`, no a mano) un
ejemplo real de producto con escalones de precio para completar esa parte.

## Parser de ficha individual de Mercado Libre (`parser_ficha_ml.py`)

Confirmado con HTML real (`tests/fixtures/ml_ficha_real.html`, item
MLA2023730583, capturado automáticamente por `capturador_exploratorio.py`
en la segunda corrida — la primera se había quedado en el desafío PoW).
Dos fuentes en la misma página:

- **`application/ld+json` con `@type: "Product"`** (marcado schema.org
  estándar, pensado para SEO — no depende de la estructura interna de
  ML): `name`, `offers.price`, `offers.priceCurrency`,
  `aggregateRating.reviewCount`/`ratingValue`. Fuente principal, la más
  estable de las dos. `extraer_producto_ld_json()`.
- **Contexto interno de renderizado** (`__NORDIC_RENDERING_CTX__`): de
  ahí sale `sold_quantity` (unidades vendidas — la señal de demanda más
  importante según las reglas del proyecto) y `quantity` (stock visible
  actual, para `historial_ml`). No están en el JSON-LD estándar. Más
  frágil por ser interno: `extraer_stock_y_ventas()` usa una regex
  puntual y devuelve `(None, None)` si no matchea, en vez de romper el
  resto del parseo.

`parsear_ficha_ml(html, url)` combina las dos fuentes en un dict con la
forma de `candidatos_ml` (+`stock_visible`, para la primera fila del
historial). Confirmado con datos reales: `precio_ml=68780 ARS`,
`unidades_vendidas=1000`, `stock_visible=5`,
`evidencia_demanda="+1000 vendidos"`.

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
