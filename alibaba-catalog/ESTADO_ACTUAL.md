# Estado actual del motor de sourcing MUTE (ML ↔ Alibaba)

> Última actualización: sesión del 2026-09-11. Este documento es el punto
> de entrada para retomar el proyecto — no hace falta leer todo el
> historial de `README.md` para saber dónde estamos parados.

## 🚦 Próximo punto de entrada (leer esto primero)

**Diseñar el matching ML ↔ Alibaba antes de escribir código.**

La usuaria pidió explícitamente no resolver "qué dos productos son
comparables" solo por similitud de título — hace falta pensar el criterio
con cuidado antes de tocar `parser_busqueda_alibaba.py` o cualquier
lógica nueva. **No avanzar con el filtro económico (×2.5 / USD 10) ni con
ninguna funcionalidad nueva de Fase 2 hasta que ese diseño esté
definido.**

Preguntas abiertas para esa conversación de diseño (no respondidas
todavía, a propósito):

- ¿Similitud de texto entre `candidatos_ml.nombre` y `resultado.nombre`
  de Alibaba? ¿Con qué algoritmo — y qué umbral evita falsos positivos
  (ej. "cepillo de limpieza eléctrico" vs. "cepillo de dientes
  eléctrico")?
- ¿Se usa la categoría/rubro del candidato de ML como filtro previo,
  antes de comparar títulos?
- ¿Cuántos candidatos de Alibaba se evalúan por cada producto de ML (el
  primero que matchea razonablemente, o varios en paralelo con un
  score)?
- ¿Qué pasa si ningún resultado de Alibaba parece un comparable
  razonable — se descarta el candidato de ML, o se marca para revisión
  manual?
- ¿Se pondera de alguna forma `proveedor_verificado` o `es_publicidad`
  al elegir el comparable, o son solo metadata informativa?

---

## 1. Qué está terminado y validado en Mercado Libre (Fase 1)

**Validada de punta a punta con datos reales: 75/75 fichas abiertas
correctamente (100%), 0% de 404, 0% de otros errores**, tanto en URLs
directas (41/41) como en URLs reconstruidas desde tracking (34/34) —
corrida real completa, 5 búsquedas, sesión logueada en frío,
`--delay-min 4 --delay-max 10`.

El pipeline completo:

1. **`parser_busqueda_ml.py`** parsea el listado de búsqueda (sin abrir
   fichas) y clasifica cada resultado en Prioridad A (badge "MÁS
   VENDIDO" o conteo explícito de vendidos), Prioridad B (rating
   visible, señal débil) o sin señal (se descarta ahí mismo). **El
   listado nunca confirma demanda por sí solo** — es prefiltro y orden
   de prioridad.
2. **`orquestador_demanda_ml.py`** busca, prioriza (A antes que B), y
   abre fichas individuales hasta confirmar una cantidad configurable de
   candidatos con demanda real (`--objetivo`) o agotar un máximo de
   fichas por búsqueda (`--max-fichas`) — lo que pase primero. La
   demanda se confirma recién en la ficha individual, contra un umbral
   configurable de unidades vendidas (`--umbral-vendidas`).
3. Cada ficha abierta deja una observación en `historial_ml`
   (append-only) y actualiza `candidatos_ml.estado` con un motivo
   explícito — nunca un descarte silencioso.

## 2. Qué está terminado y validado en Alibaba (arranque de Fase 2)

- **`capturador_busqueda_alibaba.py`**: captura automática (Chrome real)
  de un listado de búsqueda de Alibaba por palabra clave. **Probado con
  éxito real** (búsqueda "wireless earbuds", HTML de 1.9MB con 48
  resultados reales).
- **`parser_busqueda_alibaba.py`**: extrae de cada resultado el
  `id_alibaba`, `url_alibaba` (normalizada a `https://`, mismo formato
  `.../product-detail/<slug>_<id>.html` que ya sabe leer
  `parser_ficha_alibaba.py`), `nombre`, `precio_texto` y `moq_texto`
  (**crudos, nunca parseados a un número** — el precio/MOQ del listado
  no es confiable, regla ya aplicada en ML), `proveedor`,
  `proveedor_verificado`, `es_publicidad`. Probado con 7 resultados
  reales (fixture `alibaba_busqueda_real.html`).
- **`parser_ficha_alibaba.py`** (de una fase anterior, sin cambios):
  abre la ficha individual de un producto de Alibaba y extrae el precio
  real desde `window.detailData` — nunca confía en el precio del
  listado. Ya sabe manejar el caso de precio único (`precio_alibaba_50u`
  confiable) vs. precio con escalones por cantidad (todavía sin
  confirmar qué campo indica el escalón para ~50 unidades →
  `precio_no_verificado=True` en ese caso, nunca se adivina).

**Lo que NO existe todavía**: ninguna lógica que conecte un candidato de
ML con un resultado de Alibaba (matching), ninguna verificación
automática de precio en cadena (buscar → elegir comparable → abrir su
ficha), y ningún filtro económico. Ver la sección de pendientes.

## 3. Cómo funcionan las sesiones/perfiles y CAPTCHA

- **Un solo perfil de Chrome** (`.perfil_chrome_collector/`, carpeta
  dentro de `alibaba-catalog/`) sirve para Mercado Libre y Alibaba — es
  un directorio de datos de Chrome manejado por Playwright
  (`navegador_ml.navegador_persistente`), no el Chrome habitual de la
  usuaria. Un solo login ahí sirve para ambos sitios.
- **Hallazgo real importante**: tanto el reCAPTCHA de Mercado Libre como
  el slider CAPTCHA de Alibaba (`punish-component`) **rechazan la
  resolución específicamente cuando la ventana está controlada por
  Playwright** — el humano completa el desafío correctamente pero el
  servidor igual lo rechaza ("no se pudo conectar con el servicio
  reCAPTCHA" / "Oops... something's wrong"). No es un problema de
  cuenta, contraseña, conexión ni extensiones — confirmado comparando
  con un Chrome normal, donde el mismo login/captcha funciona sin
  drama.
- **Solución que funciona, confirmada dos veces (ML y Alibaba)**: abrir
  el mismo directorio de perfil (`.perfil_chrome_collector`) con un
  Chrome lanzado **manualmente**, no por Playwright:
  ```powershell
  & "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="<ruta>\alibaba-catalog\.perfil_chrome_collector"
  ```
  Resolver el login/CAPTCHA ahí con normalidad, **cerrar esa ventana por
  completo**, y recién ahí correr el script — reutiliza la sesión ya
  "calentada" sin volver a toparse con el problema.
- **Manejo del bloqueo dentro del pipeline** (`navegador_ml.pausar_por_bloqueo_y_continuar`):
  nunca cierra Chrome ni intenta resolver/evadir nada. Pausa
  indefinidamente (sin timeout corto) con el mensaje "[Sitio] requiere
  intervención humana. Resolvé el login/CAPTCHA en la ventana de Chrome
  y luego presioná Enter para continuar." Al presionar Enter, recarga la
  misma URL y **verifica** que el bloqueo realmente desapareció antes de
  seguir — si sigue bloqueado, vuelve a pausar en vez de avanzar. Es
  reusable para cualquier sitio vía el parámetro `sigue_bloqueado`
  (chequeo inyectable) — con esto se corrigió un bug latente donde
  `capturador_exploratorio.py` verificaba la resolución del bloqueo de
  Alibaba con detectores específicos de ML, que nunca iban a matchear.
- **Desafío PoW de Akamai** (Mercado Libre): distinto de todo lo
  anterior — se resuelve solo con el JS de la propia página en unos
  segundos, no necesita intervención humana (`navegador_ml.es_desafio_pow_ml`
  + `esperar_resolucion_desafio_pow`).
- **Pausa configurable entre fichas** (`navegador_ml.esperar_entre_fichas`,
  `--delay-min`/`--delay-max`, default 3-8s): reduce la frecuencia con la
  que aparece el bloqueo de "tráfico sospechoso" en primer lugar — mejor
  evitarlo que resolverlo. Se disparaba después de ~20 fichas seguidas en
  ~1 segundo cada una.

## 4. Parsers existentes y qué extrae cada uno

| Archivo | Qué parsea | Campos principales |
|---|---|---|
| `parser.py` | Listado del catálogo completo de un proveedor Alibaba conocido (`module-data` en atributos HTML) | nombre, url, precio_min/max, moq, cantidad_vendida, imagen, categoría, `compra_directa`/`envio_calculable` |
| `parser_ficha_alibaba.py` | Ficha individual de un producto de Alibaba (`window.detailData`) | precio_alibaba_50u (solo si es precio único, si no `precio_no_verificado=True`), moq, moneda |
| `parser_busqueda_alibaba.py` | Listado de búsqueda de Alibaba por palabra clave (**nuevo**) | id_alibaba, url_alibaba, nombre, precio_texto (crudo), moq_texto (crudo), proveedor, proveedor_verificado, es_publicidad, posición |
| `parser_busqueda_ml.py` | Listado de búsqueda de Mercado Libre | id_ml, url_ml, nombre, precio_ml, rating_visible, mas_vendido, unidades_vendidas (aprox.), `origen_url` ("directo"/"tracking"), prioridad ("A"/"B"/None vía `clasificar_prioridad`) |
| `parser_ficha_ml.py` | Ficha individual de Mercado Libre (JSON-LD + `__NORDIC_RENDERING_CTX__`) | nombre, precio_ml, moneda_ml, unidades_vendidas, stock_visible, cantidad_opiniones, rating, `pagina_no_encontrada` (404 real de ML) |

## 5. Pruebas reales realizadas y sus resultados

- **Medición de confiabilidad de fichas de ML** (`medicion_confiabilidad_ml.py`),
  3 corridas reales sucesivas, cada una resolviendo el hallazgo de la
  anterior:
  1. 55 fichas: 43.6% de éxito total — **0% de éxito (0/31) en URLs de
     tracking** (reconstrucción rota) vs. 100% (24/24) en URLs directas.
  2. Tras el fix de `searchVariation`: 47 fichas, 0% de 404 pero 36.2%
     de "otro_error" — bloqueo de tráfico sospechoso no detectado,
     contaminando el resto de la corrida en silencio.
  3. Tras el manejo humano reforzado + espera al render del listado:
     **75 fichas, 100% de éxito, 0% de 404, 0% de otros errores.**
- **Experimento controlado de URL** (`experimento_url_producto_reconstruida.py`,
  5 pares reales): confirmó que
  `https://www.mercadolibre.com.ar/p|up/<searchVariation>?pdp_filters=item_id:<item_id>`
  (sin slug) redirige al permalink completo con status 200 — `/p/` para
  IDs con 3 letras de prefijo (catálogo), `/up/` para 4 letras
  (publicación individual). 5/5 casos reales consistentes.
- **Captura de búsqueda de Alibaba**: 1 corrida real exitosa ("wireless
  earbuds", 48 resultados, 7 confirmados con extracción completa en el
  parser).

## 6. Qué queda pendiente de Fase 2

En orden, cada uno bloqueado por el anterior:

1. **🚦 Diseñar el criterio de matching ML ↔ Alibaba** (ver sección de
   arriba) — el bloqueante actual, sin resolver a propósito.
2. Implementar el matching ya diseñado (probablemente en un nuevo
   `matcher_alibaba.py` o similar, con tests sobre casos reales).
3. Verificación de precio en cadena: para el/los comparable(s) elegidos,
   abrir la ficha real con `parser_ficha_alibaba.py` (ya existe, sin
   cambios necesarios) y guardar en `alibaba_comparables`
   (`db.insertar_comparable_alibaba`, ya existe).
4. Filtro económico (×2.5 de markup, USD 10 de diferencia mínima según
   la especificación original del proyecto) — todavía sin implementar.
5. Segunda etapa de análisis + shortlist final (`ESTADOS_CANDIDATO`
   ya define `segunda_etapa`/`finalista`, sin lógica que los use
   todavía).
6. Pendiente menor, no bloqueante: confirmar el caso de precio de
   Alibaba con escalones por cantidad (`parser_ficha_alibaba.py` ya lo
   deja `precio_no_verificado=True` en vez de adivinar — falta un
   ejemplo real de ese caso para completarlo).

## 7. Decisiones técnicas importantes y por qué

- **Nunca confiar en el precio/MOQ del listado, solo en la ficha
  individual** — regla del proyecto desde el arranque, aplicada
  consistentemente en ML y en Alibaba. El listado es prefiltro, la ficha
  es la fuente de verdad.
- **El listado de ML nunca confirma demanda por sí solo** (ajuste de
  semántica pedido explícitamente): rating visible sin cantidad de
  opiniones es señal débil (Prioridad B), no una confirmación.
- **Dedup de `candidatos_ml` por `url_ml`, no por el href crudo del
  link de tracking**: ese href trae un parámetro cifrado que cambia en
  cada carga de página — usarlo como clave rompería la deduplicación en
  silencio. Por eso se optó por reconstruir una URL estable
  (`searchVariation` + `item_id`) en vez de navegar directamente el
  link de tracking.
- **No seguir el link de tracking real de ML para resolver su
  redirect**: esos links traen `is_advertising=true` — navegarlos
  programáticamente podría registrar clics publicitarios reales. Se
  prefirió construir la URL desde datos ya presentes en el propio HTML
  del listado (`searchVariation`), sin tocar el tracker.
- **Nunca adivinar un formato de URL sin evidencia real**: cada cambio
  de estrategia de URL (tanto en ML como conceptualmente para Alibaba)
  se validó primero con un experimento controlado y navegación real
  antes de incorporarse al pipeline.
- **Captura automática de HTML de diagnóstico** (`guardar_diagnostico`,
  `guardar_diagnostico_busqueda`) para cualquier caso anómalo (ficha
  indeterminada, búsqueda con 0 resultados) — nunca se le pide a la
  usuaria que recolecte HTML a mano; el propio sistema lo guarda para
  que Claude lo inspeccione en la siguiente iteración.
- **Pausa humana que verifica su propia resolución** (recarga + chequea
  de nuevo) en vez de asumir que un Enter significa "resuelto" — evita
  perder o duplicar una ficha si la usuaria no llegó a resolver el
  bloqueo del todo.
- **Session-hardening manual como solución al problema de
  automatización**: en vez de intentar evadir la detección de Playwright
  (fuera de alcance y en contra de las reglas del proyecto de no
  evadir/resolver CAPTCHAs automáticamente), se resolvió operativamente:
  calentar la sesión con un Chrome lanzado a mano una sola vez.

## 8. Estado de los tests

**147/147 tests pasan** (`pytest` desde la raíz de `alibaba-catalog/`).
Incluye tests de catálogo (`database/tests/test_db.py`), sourcing
(`test_db_sourcing.py`), y todos los parsers/orquestadores/herramientas
de captura mencionados arriba — cada uno con al menos un caso basado en
HTML real capturado, no inventado.

```bash
cd alibaba-catalog
pytest
```
