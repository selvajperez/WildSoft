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
    navegador_ml.py             # sesión Playwright/Chrome real compartida (login, PoW de Akamai, pausa por bloqueo) usada por capturador_exploratorio.py y orquestador_demanda_ml.py
    capturador_exploratorio.py  # Fase 1 del sourcing: captura automática de muestras ML + Alibaba
    parser_ficha_alibaba.py     # Fase 2 (arranque): parsea la ficha individual de Alibaba (precio real, MOQ)
    parser_ficha_ml.py          # Fase 1 (arranque): parsea la ficha individual de Mercado Libre (demanda, precio)
    parser_busqueda_ml.py       # Fase 1: parsea el listado de búsqueda de ML (prioridad A/B/sin señal, nunca demanda confirmada)
    orquestador_demanda_ml.py   # Fase 1: busca, prioriza y abre fichas individuales hasta confirmar demanda real (configurable)
    medicion_confiabilidad_ml.py  # Diagnóstico: mide % de éxito/404 al abrir fichas, separado por origen de URL -- no toca candidatos_ml
    tests/
      test_parser.py
      test_scraper.py
      test_collector_browser.py
      test_diagnostico_precio.py
      test_navegador_ml.py
      test_capturador_exploratorio.py
      test_parser_ficha_alibaba.py
      test_parser_ficha_ml.py
      test_parser_busqueda_ml.py
      test_orquestador_demanda_ml.py
      test_medicion_confiabilidad_ml.py
      fixtures/
        productlist_page19.html          # HTML real (recortado) de un listado válido
        productlist_page_mixto.html      # los mismos 2 + 2 productos reales "a Cotizar" (RFQ)
        pagina_bloqueada_captcha.html    # HTML real (recortado) de la página de bloqueo CAPTCHA
        ml_desafio_pow.html              # HTML real: desafío Proof-of-Work de Mercado Libre (no es un CAPTCHA humano)
        alibaba_ficha_real.html          # HTML real (recortado) de una ficha de producto de Alibaba
        ml_ficha_real.html               # HTML real (recortado) de una ficha de producto de Mercado Libre
        ml_busqueda_real.html            # HTML real (recortado): 4 tarjetas representativas de una búsqueda de 60 resultados
        ml_ficha_no_encontrada_real.html # HTML real (recortado): 404 real de ML para una URL de ficha reconstruida inválida
        ml_bloqueo_trafico_sospechoso_real.html # HTML real (recortado): bloqueo de "tráfico sospechoso" que pide loguearse
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
  `prioridad_listado` (`"A"`/`"B"`/`NULL`) guarda con qué prioridad salió
  del listado (ver `parser_busqueda_ml.clasificar_prioridad` más abajo) —
  es solo el orden en que se abren las fichas, no una confirmación de
  demanda. `estado` recorre el pipeline (`ESTADOS_CANDIDATO` en `db.py`):
  `nuevo` → `demanda_confirmada` → `con_comparable` → `precio_verificado`
  → `segunda_etapa` → `finalista`, o alguno de los `descartado_*`
  (incluye `descartado_demanda_insuficiente`, del prefiltro de listado, y
  `descartado_demanda_no_confirmada`, de la ficha individual) o
  `indeterminado_ficha` (la ficha no se pudo leer con confianza), cada uno
  con su `motivo_descarte` explícito. `fecha_detectado` se preserva entre
  actualizaciones (no se pisa).
- **`alibaba_comparables`**: el producto de Alibaba elegido como
  comparable de un candidato (`candidato_id`), con el precio **verificado
  en la ficha individual** (`precio_alibaba_50u`) — nunca el de la
  búsqueda. `precio_no_verificado`/`requiere_contacto_proveedor` son los
  flags de la regla "si no se puede determinar el precio con confianza,
  excluir de esta corrida".
- **`historial_ml`**: observaciones de un candidato en el tiempo (precio,
  stock visible, ventas visibles, cantidad de opiniones, `rating`,
  ranking). **Append-only**: `registrar_observacion_historial` siempre
  inserta una fila nueva, nunca actualiza una existente — es la base para
  medir rotación real comparando observaciones sucesivas, no un snapshot
  que se pisa.

`candidatos_ml`/`historial_ml` ya se llenan con datos reales — ver
`orquestador_demanda_ml.py` más abajo. `alibaba_comparables` sigue siendo
solo esquema + funciones de acceso (fase 2, todavía no empezada), ya
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

## Parser del listado de búsqueda de Mercado Libre (`parser_busqueda_ml.py`)

Objetivo (regla del proyecto): extraer señal de demanda de cada resultado
**sin abrir ninguna ficha individual**, para prefiltrar antes de gastar
tiempo/riesgo abriendo fichas una por una. Confirmado con HTML real
(`tests/fixtures/ml_busqueda_real.html`, búsqueda "cepillo de limpieza",
60 resultados reales).

### Estructura real de cada resultado

Cada resultado es un `<li class="ui-search-layout__item">` con una
tarjeta "poly-card" (framework propio de ML). Por tarjeta:

- **Título + item_id + posición**: en el `href` de `a.poly-component__title`.
- **Precio**: `aria-label` del `span.andes-money-amount` dentro de
  `.poly-price__current` (ej. `"111420 pesos argentinos"`) — más
  confiable que parsear el texto visible con separadores de miles.
- **Rating promedio** (sin cantidad de opiniones): `.poly-component__review-compacted`.
- **Badge "MÁS VENDIDO"**: booleano, no es un conteo.
- **Texto libre "+N vendidos"**: buscado, pero ver más abajo.

### Hallazgo real importante: la URL del resultado tiene TRES formas distintas

Se descubrieron corriendo el parser contra el HTML real, no adivinando de
antemano — dos iteraciones de bugs reales, cada una perdiendo resultados
silenciosamente:

1. **Orgánico "catálogo"**: `.../nombre-del-producto/p/MLA21816514#...` —
   link directo y limpio, se usa tal cual (recortando el `#...` de tracking).
2. **Orgánico "publicación individual"**: `.../nombre/up/MLAU3256312831#...`
   — mismo caso, pero segmento `/up/` (no `/p/`) y prefijo de **4 letras**
   ("MLAU", no "MLA"). La primera versión del regex solo contemplaba
   `/p/` + 3 letras y perdía **estos 17 resultados silenciosamente**.
3. **Con wrapper de tracking de clicks**: no hay URL directa en el
   `href`, solo un `item_id` en el query string
   (`pdp_filters=item_id%3AMLA123...`). Ahí se reconstruye la URL
   canónica (`https://articulo.mercadolibre.com.ar/<item_id>`).

Una primera versión del parser (que solo buscaba el patrón de tracking,
caso 3) extraía **12 de 60** resultados reales — perdía el 80% sin dar
ningún error. Con los tres casos cubiertos: **60 de 60**.

### Hallazgo real importante: el grid principal NO muestra "+N vendidos"

De los 60 resultados reales de la búsqueda de referencia, **ninguno**
mostró el texto "+N vendidos" en el grid principal. Ese patrón sí
apareció, en otra captura, dentro de un carrusel de "también te puede
interesar" en una ficha individual — un contexto distinto. El parser
sigue buscando ese patrón por si otra búsqueda sí lo muestra (cubierto con
un caso sintético en los tests, marcado explícitamente como no confirmado
con HTML real todavía), pero **no se puede asumir que el listado siempre
trae el conteo de ventas** — de los 60 resultados, la señal disponible fue
badge "MÁS VENDIDO" (2) o rating promedio sin conteo de opiniones (18); 40
no mostraron ninguna señal.

Regla del proyecto respetada: `_normalizar_conteo_vendidos()` nunca trata
"+500" como exactamente 500 (es una conversión aproximada), y
`evidencia_demanda` siempre conserva el texto/badge tal cual se vio, para
poder auditar después.

### Prefiltro de prioridad (NO es confirmación de demanda) y guardado en `candidatos_ml`

Ajuste de semántica importante: **el listado nunca confirma demanda por sí
solo**, solo establece una prioridad de revisión. `clasificar_prioridad(item)`
devuelve:

- `"A"` (señal fuerte): badge "MÁS VENDIDO" o conteo explícito de "+N
  vendidos".
- `"B"` (señal débil): rating promedio visible, sin cantidad de opiniones
  — antes se trataba como demanda confirmada; ya no.
- `None`: ninguna señal visible. Se descarta sin abrir la ficha
  (`estado="descartado_demanda_insuficiente"`).

`resultado_a_candidato(item)` traduce un resultado a los campos de
`candidatos_ml`, guardando la prioridad en `prioridad_listado` ("A"/"B"
quedan en `estado="nuevo"`, pendientes de que se abra su ficha;
`None` ya entra descartado, con su `motivo_descarte`, para que el
pipeline nunca gaste una visita a esa ficha individual). `parser_busqueda_ml.py`
no toca la base directamente (función pura); guardar es un `for` simple
con `db.upsert_candidato_ml` (ver `test_guardar_resultados_del_listado_en_candidatos_ml`).

### Resultado de la prueba real (búsqueda "cepillo de limpieza")

| | |
|---|---|
| Resultados extraídos | 60 / 60 |
| Prioridad A (badge/conteo) | 2 |
| Prioridad B (rating visible) | 18 |
| Sin señal (→ `descartado_demanda_insuficiente`, sin abrir su ficha) | 40 |
| Conteo explícito de vendidos en el grid | 0 (no confirmado en este grid, ver hallazgo arriba) |
| URLs duplicadas | 0 |
| Precios sin detectar / nombres vacíos | 0 |
| Falsos positivos encontrados | Ninguno una vez corregidas las 2 formas de URL faltantes (ver hallazgos arriba) |

**No se avanzó con matching contra Alibaba ni con el pipeline completo**
(regla explícita de esta etapa) hasta confirmar que este parser de
listado extrae de forma confiable — con el 60/60 y cero duplicados/campos
vacíos, se considera validado para seguir con la apertura de fichas
individuales (`orquestador_demanda_ml.py`, siguiente sección).

## Confirmación de demanda abriendo fichas individuales (`orquestador_demanda_ml.py`)

El listado (sección anterior) es solo prefiltro y orden de prioridad —
**la demanda recién se confirma al abrir la ficha individual**, contra un
umbral configurable. `orquestador_demanda_ml.py` es el punto de entrada de
esta etapa: busca en Mercado Libre, guarda todos los resultados en
`candidatos_ml` con su `prioridad_listado`, y abre fichas **primero las de
Prioridad A, después las de Prioridad B** (las "sin señal" nunca se
abren), hasta lo que ocurra primero de:

- alcanzar `--objetivo` candidatos con demanda confirmada, o
- agotar `--max-fichas` fichas abiertas en esta búsqueda.

Por cada ficha abierta:

1. Se extrae con `parser_ficha_ml.parsear_ficha_ml`: precio actual, +N
   vendidos, cantidad de opiniones, rating, stock visible.
2. Se guarda **siempre** una fila nueva en `historial_ml`
   (`registrar_observacion_historial`, append-only — nunca pisa una
   observación anterior).
3. `_determinar_resultado_ficha` decide el estado final contra
   `--umbral-vendidas` (unidades vendidas confirmadas en la ficha, no en
   el listado):
   - `demanda_confirmada`: vendidas ≥ umbral.
   - `descartado_demanda_no_confirmada`: vendidas < umbral.
   - `indeterminado_ficha`: la ficha no expone ventas (o no se pudo leer
     nada confiable) — no se puede confirmar ni descartar con la
     configuración actual.
4. `db.actualizar_estado_candidato` guarda ese estado **con un motivo
   explícito siempre presente** (nunca hay un descarte silencioso — ver
   `test_procesar_busqueda_ml_registra_motivo_explicito_por_candidato`).

La lógica de decisión (`_determinar_resultado_ficha`) y la orquestación
completa (`procesar_busqueda_ml`) están separadas de la parte que
efectivamente abre páginas: reciben `obtener_html_busqueda`/`abrir_ficha`
como funciones inyectadas, así se puede probar todo el flujo con HTML ya
capturado sin necesitar un navegador real. `ejecutar_busqueda_real` es el
único punto que arma esas funciones con Playwright/Chrome real
(reutilizando `navegador_ml.py`, la misma sesión persistente y el mismo
manejo del desafío PoW de Akamai que ya usaba `capturador_exploratorio.py`).

```bash
python collector_alibaba/orquestador_demanda_ml.py "cepillo de limpieza"
python collector_alibaba/orquestador_demanda_ml.py "candado bicicleta" --max-fichas 10 --objetivo 3 --umbral-vendidas 100
python collector_alibaba/orquestador_demanda_ml.py "cepillo de limpieza" --login   # forzar login manual de nuevo
```

### Validación con datos reales (antes de avanzar a matching Alibaba)

Se probó `procesar_busqueda_ml` con las 4 tarjetas reales del fixture
(`ml_busqueda_real.html`: 1 Prioridad A, 1 Prioridad B, 2 sin señal) y con
la única ficha real capturada hasta ahora (`ml_ficha_real.html`, item
MLA2023730583: 1000 vendidas, stock 5, rating 4.2, 273 opiniones) —
inyectada como stand-in de cualquier ficha que se abra, porque todavía no
hay fichas reales capturadas de los candidatos concretos de esa búsqueda
(limitación documentada explícitamente en `test_orquestador_demanda_ml.py`,
no escondida). Con esa entrada:

- Prioridad A se abre siempre antes que B (confirmado forzando
  `max_fichas_por_busqueda=1`: la única ficha abierta es la del badge
  "MÁS VENDIDO").
- `--objetivo` y `--max-fichas` cortan la corrida en el punto correcto
  (`detenido_por` queda en `"candidatos_objetivo_alcanzado"` o
  `"max_fichas_alcanzado"` según cuál se agote primero).
- Con `--umbral-vendidas` alto (5000, por encima de las 1000 reales de la
  ficha) los candidatos quedan `descartado_demanda_no_confirmada` en vez
  de `demanda_confirmada` — el umbral configurable funciona.
- La fila de `historial_ml` guardada coincide exactamente con los datos
  reales de la ficha: `(68780.0, 5, 1000, 273, 4.2)`.
- Corriendo contra el listado real completo (60 resultados, no solo las 4
  del fixture) con la configuración default
  (`max_fichas_por_busqueda=15, candidatos_objetivo=5, umbral_unidades_vendidas=50`):
  de 2 Prioridad A + 18 Prioridad B disponibles, se abrieron solo 5 fichas
  (las 2 de A + las primeras 3 de B) y se detuvo por
  `"candidatos_objetivo_alcanzado"` — nunca abrió las 15 restantes de
  Prioridad B, confirmando que el corte configurable evita navegación
  innecesaria tal como pide la regla del proyecto.

### Corrida real con Chrome (`ejecutar_busqueda_real`) — primera evidencia con fichas distintas

Confirmado: `python orquestador_demanda_ml.py "cepillo de limpieza" --max-fichas 15 --objetivo 5 --umbral-vendidas 50`
corrió con Chrome real y abrió **14 fichas realmente distintas** (cada una
con su propio `id_ml` y nombre), no la misma reusada como en la prueba
automatizada. Resultado: `extraidos=60, prioridad_a=1, prioridad_b=17,
sin_senal=42, fichas_abiertas=14, demanda_confirmada=5,
indeterminado_ficha=9, detenido_por="candidatos_objetivo_alcanzado"`. El
orden de apertura (A antes que B) y el corte al llegar a 5 confirmados
funcionan igual que en la prueba con datos inyectados.

**Hallazgo real, diagnosticado con HTML real capturado automáticamente**:
9 de las 14 fichas abiertas (64%) quedaron `indeterminado_ficha` — ni
precio ni unidades vendidas extraídas. Con el HTML crudo que
`ejecutar_busqueda_real` guarda automáticamente en
`diagnostico_fichas_ml/<id_ml>.html` para toda ficha indeterminada
(`_guardar_html_diagnostico`, inyectado como `guardar_diagnostico` en
`procesar_busqueda_ml` para no tocar disco en los tests), se confirmó la
causa real de al menos 5 de esos 9 casos: son un **404 real de Mercado
Libre** (`<main class="ui-pdp-not-found">`, título "Parece que esta
página no existe" — ver `tests/fixtures/ml_ficha_no_encontrada_real.html`,
HTML real trimeado), no una ficha sin datos. El propio
`<noscript><meta http-equiv="refresh" content="...go=https%3A%2F%2Farticulo.mercadolibre.com.ar%2FMLA...">`
de la página de error confirma que la URL pedida fue justo la
reconstruida por `parser_busqueda_ml._url_canonica` a partir del
`item_id` de un link de tracking del listado (caso 3, ver esa sección) —
esa reconstrucción funciona para algunos items (ej. `MLA1399281097`,
confirmado con 1000 vendidas en esta misma corrida) pero no para todos.

`parser_ficha_ml.es_ficha_no_encontrada()` detecta este 404 específico y
`_determinar_resultado_ficha` ahora guarda un motivo explícito y
distinguible ("La ficha devolvió un 404 real de Mercado Libre...") en vez
del genérico "no se pudo extraer nada" — no soluciona la URL rota (eso
requeriría confirmar con más evidencia real qué formato sí funciona para
esos item_id, algo que no se puede adivinar sin arriesgar otro dato
inventado), pero la hace visible, medible y distinguible de otras causas
de indeterminación (bloqueo, cambio de plantilla, etc.) en las próximas
corridas.

**Segundo hallazgo (corrida posterior, ~25 minutos después, misma
búsqueda)**: el item `MLA1399281097` había confirmado demanda
(`demanda_confirmada`, 1000 vendidas) en la primera corrida y, con la
*misma* URL reconstruida, dio el 404 real en la segunda. Esto descarta la
hipótesis de "ciertos item_id específicos están simplemente rotos": la
reconstrucción (`articulo.mercadolibre.com.ar/<item_id>`, sin guion) es
**intermitente/poco confiable en general** para resultados envueltos en
un link de tracking de clicks, no un problema fijo de una lista de IDs.

Se evaluó usar directamente el href de tracking crudo (que sí es una URL
real y navegable, un endpoint de click-tracking de ML) en vez de
reconstruir nada, pero se descartó: `candidatos_ml` deduplica por
`url_ml` (`ON CONFLICT(url_ml)`, ver `database/db.py`), y ese href trae
un parámetro cifrado (`a=...`) que aparenta cambiar en cada carga de
página — usarlo tal cual generaría una fila nueva por cada búsqueda
futura que vuelva a encontrar el mismo producto, rompiendo la
deduplicación en silencio. Mantener una URL reconstruida estable (aunque
a veces falle al abrirla) sigue siendo la opción correcta para el
identificador en base; el costo es navegación desperdiciada, no datos
corruptos (nunca fabrica una demanda confirmada falsa).

### Medición cuantitativa de la pérdida (`medicion_confiabilidad_ml.py`)

Antes de decidir si esta intermitencia amerita resolver la navegación
antes de seguir, o si la pérdida es chica y se puede documentar y avanzar,
hacía falta medirla con más de una búsqueda real — no alcanza con las 14
fichas de una sola corrida. `medicion_confiabilidad_ml.py` es una
herramienta de diagnóstico **separada del pipeline de producción**: corre
varias búsquedas reales (5 por defecto, mismo rubro), abre **todas** las
fichas Prioridad A/B de cada una (sin el corte por `candidatos_objetivo`
de `orquestador_demanda_ml.py`, porque acá el objetivo es medir, no
curar candidatos) hasta un máximo configurable por búsqueda, y clasifica
cada intento en `abierta_ok` / `404` / `otro_error`, separado por
`origen_url` (`"directo"` vs. `"tracking"` — nuevo campo agregado a
`parser_busqueda_ml.parsear_resultado`, aditivo, no rompe nada existente).
**No escribe en `candidatos_ml`/`historial_ml`** — no mezcla datos de
medición con el estado real de candidatos ni toca el progreso existente.
Guarda el detalle completo (cada intento) + el resumen agregado en
`medicion_confiabilidad_ml/reporte_<timestamp>.json` (no se commitea).

```bash
python collector_alibaba/medicion_confiabilidad_ml.py
python collector_alibaba/medicion_confiabilidad_ml.py "cepillo de limpieza" "trapo de piso" --max-fichas-por-busqueda 20
```

**Resultado de la medición real (55 fichas, 5 búsquedas)**: la pérdida
era total y sistemática, no chica — **0% de éxito (0/31) para URLs de
tracking** reconstruidas con `articulo.mercadolibre.com.ar/<item_id>`
(nunca funcionaba, no era "intermitente" como parecía con una sola
corrida), frente a **100% (24/24) para URLs directas**. Con ese resultado
correspondía resolver la navegación antes de seguir, no solo documentar
la limitación.

### Resolución: URL construida desde `searchVariation` (sin tocar el link publicitario)

Antes de aceptar la pérdida o de navegar directamente el link de
tracking (descartado por el riesgo de registrar clics publicitarios
reales, dado que esos `href` traen `is_advertising=true`), se investigó
si el propio HTML del listado ya trae, sin necesidad de hacer ningún
request al tracker, algún dato estable para llegar al producto. Sí lo
trae: el fragmento del mismo `href` de tracking incluye
`searchVariation=<ID>` — en 11 de 12 casos reales inspeccionados, con el
mismo formato `MLA`/`MLAU`+dígitos que ya usan las dos formas de link
directo (el 12° caso trae un ID puramente numérico, sin ese formato, y
por ahora se descarta en vez de adivinar si sirve para algo).

Se confirmó con navegación real controlada (`experimento_url_producto_reconstruida.py`,
script aislado que no toca el pipeline ni la base) que
`https://www.mercadolibre.com.ar/p/<searchVariation>?pdp_filters=item_id:<item_id>`
(sin slug) redirige automáticamente al permalink completo — **5/5 casos
reales consistentes**: los IDs con 3 letras de prefijo (`MLA`+dígitos,
página de catálogo) funcionan con `/p/`; los de 4 letras
(`MLAU`+dígitos, publicación individual) dan 404 con `/p/` pero
funcionan con `/up/` — mismo criterio 3 vs. 4 letras que el parser ya
usaba para distinguir `/p/` de `/up/` en los links directos, no un
formato nuevo inventado. En todos los casos: status 200, el `item_id`
esperado presente en la ficha resultante, y extracción normal de
precio/ventas.

Con el umbral de confirmación cumplido, esto ya está incorporado como la
estrategia real de `parser_busqueda_ml.py` — `_extraer_item_id_y_url`
para el caso de tracking ahora usa
`segmento_ruta_producto_id`/`_url_desde_search_variation` en vez de la
vieja reconstrucción sin guion. Si un link de tracking no trae un
`searchVariation` utilizable (sin ese parámetro, o con un ID que no
matchea el formato confirmado), el resultado se descarta en vez de
reconstruir algo sin evidencia — recorta ligeramente cuántos resultados
del listado se extraen, pero todo lo que se extrae ahora tiene una URL
que se espera funcione.

### Confirmado a escala, y un segundo bloqueo real descubierto en el camino

Se volvió a correr `medicion_confiabilidad_ml.py` con la estrategia ya
incorporada: **el 404 de tracking bajó de 100% (0/31) a 0% (0/30)** — la
corrección funciona a escala real, no solo en los 5 casos puntuales
probados.

Pero apareció un problema nuevo, no relacionado con la URL: a mitad de
esa misma corrida (después de ~20 fichas abiertas en pocos minutos),
Mercado Libre empezó a devolver una pantalla real de **"tráfico
sospechoso"** (`suspicious-traffic-frontend`, ruta interna
`/gz/account-verification`, "¡Hola! Para continuar, ingresa a tu
cuenta") — un bloqueo real que pide loguearse o registrarse, distinto
del desafío PoW (que se resuelve solo). Afectó **todas** las fichas
posteriores por igual, directas y de tracking, apareciendo como
`otro_error` en la medición. Ni `es_desafio_pow_ml` ni el heurístico
genérico (`bloqueado_ml_heuristico`) lo detectaban, así que la corrida
seguía en silencio en vez de pausar — confirmado con HTML real (ver
`tests/fixtures/ml_bloqueo_trafico_sospechoso_real.html`, capturado
automáticamente por la propia medición al guardar todo intento
`otro_error`, mismo mecanismo que ya usaba `orquestador_demanda_ml.py`
para fichas indeterminadas).

`navegador_ml.es_bloqueo_trafico_sospechoso_ml()` detecta este bloqueo
específico y `abrir_pagina_ml` ahora lo trata igual que el heurístico
genérico: pausa y espera que se resuelva a mano (loguearse o
registrarse en la ventana de Chrome), a diferencia del PoW que solo
espera. **Pendiente**: correr `medicion_confiabilidad_ml.py` una vez más
para confirmar que, con esta pausa ya andando, el bloqueo de tráfico
sospechoso no vuelve a contaminar en silencio el resto de una corrida
larga.

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
