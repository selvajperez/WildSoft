# Estado actual del motor de sourcing MUTE (ML ↔ Alibaba)

> Última actualización: sesión del 2026-09-11 (implementación de Match
> Mode). Este documento es el punto de entrada para retomar el proyecto —
> no hace falta leer todo el historial de `README.md` para saber dónde
> estamos parados.

## 🚦 Próximo punto de entrada (leer esto primero)

**Match Mode está funcionando de punta a punta con navegación real** (Caso
1 de la validación real, ver abajo) — el pipeline completo (ficha ML →
búsqueda Alibaba → ranking → verificación de top_k → decisión) corrió sin
errores sobre datos en vivo. Sigue la batería de validación (faltan más
casos) **antes de calibrar nada o avanzar al filtro económico.**

**Nota operativa importante, encontrada durante la validación**: el perfil
de Chrome (`.perfil_chrome_collector`) puede acumular "mala reputación"
ante el CAPTCHA de Alibaba después de varios intentos fallidos seguidos —
no es un problema del código. Si aparece el slider CAPTCHA de forma
persistente incluso resolviéndolo a mano, la solución que funcionó fue
crear un perfil nuevo (renombrar el viejo, dejarlo como respaldo/muestra
para comparar) y calentarlo de cero con un Chrome manual antes de volver
a correr el script. Ver sección 4 para el detalle.

Correr un caso (ya no hace falta pasar la URL a mano — hay un helper que
elige automáticamente el próximo candidato con `demanda_confirmada` y
mayor `unidades_vendidas`; como cada corrida cambia el `estado` del
candidato procesado, la corrida siguiente elige uno distinto solo):

```powershell
cd alibaba-catalog\collector_alibaba
python _validar_caso1.py --login   # solo si hace falta loguearse de nuevo
python _validar_caso1.py           # corridas siguientes
```

Casos a cubrir (pedido explícito de la usuaria, con al menos un caso por
punto) — **estado actual: 4 corridos (Casos 1 a 4), punto 1 casi
completo, punto 2 todavía sin validar de verdad**:

1. **Varios matches claros** (2-3 candidatos de ML de distinto rubro) —
   🔶 casi completo: Caso 1 dio `SIN_MATCH_CONFIABLE` por muy poco margen,
   Caso 2 dio `MATCH_PROBABLE` (cepillos para auto), Caso 3 dio
   `MATCH_ALTO` (cepillos eléctricos multiuso) — dos matches reales
   confirmados de rubros parecidos (ambos "cepillo"), todavía no de
   rubros muy distintos entre sí.
2. **Un caso sin match real** — 🔶 Caso 4 corrido, pero **no valida
   todavía el punto**: el candidato salió por fallback (no por un
   heurístico de "esto no debería tener equivalente"), y Alibaba devolvió
   numerosos productos de la misma familia — el `SIN_MATCH_CONFIABLE` que
   dio fue razonable dada la evidencia, pero no es una prueba real de que
   el sistema sepa reconocer un caso genuinamente sin equivalente. Caso 5
   en curso, con un heurístico de selección más específico (ver abajo).
3. **Un "gemelo tramposo"** — sin probar todavía (lógica ya validada con
   datos sintéticos en `tests/test_matcher.py`, falta un caso real).
4. Si se consigue, **un caso con fotos distintas del mismo producto real**
   — sin probar todavía.

Para cada caso, documentar acá mismo (ver "Validación real — resultados
por caso" abajo) o en el propio `matching_alibaba` (ya queda todo
guardado ahí, auditable).

**No avanzar con el filtro económico (×2.5 / USD 10) ni con ninguna otra
funcionalidad nueva hasta terminar esta validación real.** Tampoco
calibrar pesos/umbrales/patrones todavía — instrucción explícita de la
usuaria: juntar más observaciones independientes primero.

### Validación real — resultados por caso

#### Caso 1 (2026-09-11) — corrida real completa, sin CAPTCHA, sin crashes

- **Candidato ML**: `MLA6343795` — "Cepillo Limpiador Eléctrico 9
  accesorios Multifuncion Piso Color Blanco" (elegido automáticamente,
  mayor `unidades_vendidas` entre `demanda_confirmada`).
- **Query usada** (estrategia v1, español sin traducir): "cepillo
  limpiador eléctrico accesorios multifuncion piso" → **48 resultados**
  en Alibaba (la estrategia v1 alcanzó, no hizo falta una segunda en
  inglés para este caso).
- **Top 3 verificados** (fichas abiertas en orden, todos productos reales
  de "cepillo eléctrico recargable multifunción para baño/cocina/piso" —
  muy parecidos entre sí y al candidato de ML):
  1. Score final 0.591
  2. Score final 0.595
  3. Score final 0.593
- **Decisión: `SIN_MATCH_CONFIABLE`.** Ningún veto por atributo esencial
  (ninguno de los 3 fue un "gemelo tramposo" — la categoría `cepillo`
  coincidió en los tres), pero los tres quedaron justo por debajo del
  umbral de `MATCH_PROBABLE` (≥0.60 hace falta, sacaron ~0.59-0.595).
  Motivo completo en `matching_alibaba`: "Se agotaron los 3 candidatos
  verificables del top_k sin encontrar un match confiable (0 vetados por
  atributo esencial incompatible, el resto por debajo del umbral de
  match)."

**Dos hallazgos registrados, sin tocar código todavía** (pesos, umbral
0.60, patrones de atributos y parser de imagen quedan igual hasta juntar
más casos):

1. **La ficha de ML de este candidato devolvió `imagen_url = None`**
   (`parser_ficha_ml.py` no encontró `image` en su JSON-LD esta vez —
   puede pasar según el producto). Sin imagen de ML, la señal visual
   (35% del peso) aportó `0.0` en los tres candidatos verificados, aunque
   sean visualmente muy parecidos al ojo. Con `atributos_score=1.0` (el
   único atributo comparable, `categoria`, coincidió) y `texto_score`
   entre 0.87-0.88, el cálculo real fue `0.88×0.45 + 0×0.35 + 1.0×0.20 ≈
   0.596` — muy cerca del umbral. Es razonable sospechar que si la imagen
   hubiera estado disponible, al menos uno de los tres podría haber
   cruzado a `MATCH_PROBABLE`. Sin evidencia todavía de cuán seguido pasa
   esto (¿todas las fichas de ML tienen imagen, o es una excepción?) —
   necesita más casos antes de decidir un fallback (ej. tomar la
   miniatura del listado si la ficha no trae imagen).
2. **"9 accesorios" (del título de ML) no fue reconocido como cantidad de
   piezas** por `atributos_matching._RE_CANTIDAD_PIEZAS` — el patrón solo
   reconoce "pcs/piezas/unidades/units", no "accesorios". No apareció en
   ninguna `comparaciones_atributos` de este caso. Candidato a ampliar el
   patrón más adelante, con más evidencia real de qué palabras usa la
   gente para esto.

#### Caso 2 (2026-09-11) — primer `MATCH_PROBABLE` real, sin señal visual

- **Candidato ML**: `MLA28873639` — "Cepillo De Mano Calabro Suave Para
  Lavar Autos Ruedas Y Carrocería" (elegido automáticamente igual que el
  Caso 1 — el candidato del Caso 1 ya había cambiado de estado, así que
  `_validar_caso1.py` pasó solo al siguiente).
- **Query usada**: "cepillo mano calabro suave lavar autos" (estrategia
  v1, español sin traducir). **Hallazgo útil**: la propia Alibaba
  reinterpretó/tradujo la query sola ("Showing results for 'soft pump
  hand brush wash cars'. Search instead for '<la query literal>'.") y
  mostró resultados igual — buena señal de que la v1 puede alcanzar sin
  agregar una traducción propia, al menos en casos como este.
- **Decisión: `MATCH_PROBABLE`.** Aceptó el **primer candidato del
  ranking** (no hizo falta abrir el #2 ni el #3) — candidato de Alibaba:
  "High Quality Soft Bristle Handle Car Cleaning Brush Reusable Car Wash
  Accessories Brush Car Wheel Cleaning Brush"
  (`https://www.alibaba.com/product-detail/High-Quality-Soft-Bristle-Handle-Car_1601141738501.html`).
  Score final **0.606** (texto 0.90, imagen 0.00, atributos 1.00 con 33%
  de cobertura — `categoria` "cepillo" coincidió; `color`/`marca` sin
  datos de ningún lado). Sin veto por atributo esencial. Ambos productos
  son, a simple vista, cepillos de mano de cerda suave para lavar
  auto/ruedas — pinta de match real y razonable.
- **Importante: cruzó el umbral (0.60) igual, a pesar de tener imagen=0.0
  otra vez** — el texto solo (0.90, más fuerte que en el Caso 1) alcanzó.
  Confirma que el diseño de 3 señales funciona razonablemente incluso
  cuando una señal completa está ausente, aunque también confirma que la
  ausencia de imagen no es un caso aislado.

**Van 2 de 2 casos reales con `imagen_url=None` del lado de ML** —
suficientemente sistemático como para sospechar que no es "a veces ML no
tiene foto" sino algo más estructural (ver el diagnóstico agregado para
el Caso 3, abajo). Tampoco se extrajo ningún atributo de texto más allá
de `categoria` en ninguno de los dos casos (ni material, ni nada de
`descripcion`) — compatible con la misma sospecha: si el bloque JSON-LD
completo no se está encontrando, se explicarían los dos síntomas a la vez
(imagen Y descripción ausentes), no son necesariamente dos problemas
separados.

**Antes del Caso 3**: se agregó el mismo registro de diagnóstico
automático que ya tenía Alibaba también para la ficha de ML
(`orquestador_matching.py`, etiqueta `matching_ml_ficha` en
`capturas_exploratorias/manifiesto.jsonl` — guarda el HTML real sin
intervención manual).

#### Caso 3 (2026-09-11) — primer `MATCH_ALTO` real, con señal visual funcionando de punta a punta

- **Candidato ML**: `MLA7478325` — "Cepillo Eléctrico Limpieza
  Inalámbrico 8 En 1 Recargable Cabezales Intercambiables Mango
  Extensible Giratorio Baño Cocina Azulejos Juntas Piso Ducha Inodoro
  Bacha Multifunción Profunda USB" (elegido automáticamente).
- **Esta vez la ficha de ML SÍ trajo imagen**:
  `https://http2.mlstatic.com/D_NQ_NP_951927-MLA1140056000051_072026-O.webp`
  — con el mismo `parser_ficha_ml.py` sin ningún cambio. Esto responde la
  pregunta abierta del Caso 2: si el mismo código encuentra la imagen acá
  sin tocar nada, lo más probable es que **no sea un bug del parser**,
  sino que algunas fichas de ML genuinamente no exponen `image` en su
  JSON-LD (dependiendo del producto/plantilla). No hizo falta ni siquiera
  revisar el HTML crudo guardado (aunque quedó disponible) para esta
  conclusión — si vuelve a salir `imagen_url=None` en un caso futuro, eso
  sí lo vamos a poder confirmar con certeza porque ahora se guarda el
  HTML real de cada ficha de ML.
- **Decisión: `MATCH_ALTO`.** Aceptó el primer candidato del ranking —
  candidato de Alibaba: "Hot Sale Custom Multifunctional 4 In 1 Wireless
  Electric Magic Brush Spin Scrubber Scrub Cleaning Brush Power Scrubber"
  (`https://www.alibaba.com/product-detail/Hot-Sale-Custom-Multifunctional-4-In_1600791676220.html`).
  Score final **0.875** — texto 0.86, **imagen 0.82** (primera vez que la
  señal visual aporta un valor real, no 0.0), atributos 1.00 (cobertura
  33%, solo `categoria` comparable). Sin veto por atributo esencial.
- **Por qué importa**: es la primera confirmación real, de punta a punta,
  de que el pipeline de imagen funciona en la práctica -- descarga de la
  foto real de ML vía `requests`, descarga de la foto real de Alibaba,
  embedding CLIP de las dos, y similitud de coseno con un valor alto
  (0.82) para dos fotos de productos genuinamente parecidos. Hasta este
  caso, la señal de imagen solo se había probado con datos sintéticos en
  los tests.

#### Caso 4 (2026-09-11) — `SIN_MATCH_CONFIABLE` razonable, pero NO valida el caso negativo buscado

- **Candidato ML**: `MLA4781026` — "Set 4 Cepillos Limpieza Oh My Shop
  Surcos Hendiduras Cerdas Duraderas". Se intentó elegir automáticamente
  (`_validar_caso4.py`) un candidato con baja probabilidad de tener
  equivalente en Alibaba, priorizando indicios de marca/homologación
  local en el título — pero **ningún candidato de la base disparó el
  heurístico**, así que cayó al mismo criterio de siempre (mayor
  `unidades_vendidas`). "Oh My Shop" (marca de venta por TV) no estaba en
  la lista de palabras del heurístico.
- **Decisión: `SIN_MATCH_CONFIABLE`**, sin veto. Los 3 candidatos
  verificados fueron sets de cepillos de limpieza genéricos ("Cleaning
  Brush Set of 3", "Household Cleaning Brush Set Multifunctional",
  "Deep Cleaning Brush Set") con scores 0.564-0.595, todos por debajo del
  umbral de `MATCH_PROBABLE`.
- **Veredicto sobre si la decisión fue razonable**: sí, dado lo que el
  sistema pudo comparar (sin imagen de ML otra vez, sin material
  comparable en ningún candidato) — pero **este caso NO prueba que el
  sistema reconozca correctamente un producto sin equivalente real**.
  Alibaba devolvió numerosos productos de la misma familia genérica
  ("set de cepillos de limpieza"), así que el resultado negativo pudo
  deberse tanto a que genuinamente no hay un equivalente exacto como a
  falta de evidencia suficiente (mismo patrón que el Caso 1) — no hay
  forma de distinguir las dos causas con este caso en particular. El
  Caso 5 apunta a un heurístico de selección más estructural para
  cerrar esta brecha.

**Dos hallazgos de calibración registrados, sin corregir todavía**:

1. **Reconocimiento incompleto de marcas locales**: el heurístico de
   `_validar_caso4.py` no tenía "Oh My Shop" (ni, seguramente, muchas
   otras marcas de venta por TV/nicho) en su lista. Es un heurístico de
   *selección de casos de prueba*, no del matcher -- pero confirma que
   cualquier lista de palabras clave hardcodeada tiene huecos reales.
2. **Cantidad de piezas no normalizada entre expresiones equivalentes**:
   `atributos_matching._RE_PACK_OF`/`_RE_CANTIDAD_PIEZAS` no reconocen
   "Set 4" (español, sin "de") ni "Set of 3" (inglés) como cantidad de
   piezas -- solo "pack of N"/"set de N"/"juego de N"/"N pcs/piezas/
   unidades/units". En este caso, ML decía "Set 4" y el candidato top de
   Alibaba "Set of 3" -- una posible diferencia real de cantidad de
   piezas que el sistema nunca llegó a comparar porque ninguna de las dos
   expresiones matcheó el patrón.

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

## 2. Qué está terminado en Alibaba + Match Mode (Fase 2)

- **`capturador_busqueda_alibaba.py`**: captura automática (Chrome real)
  de un listado de búsqueda de Alibaba por palabra clave. **Probado con
  éxito real** (búsqueda "wireless earbuds", HTML de 1.9MB con 48
  resultados reales).
- **`parser_busqueda_alibaba.py`**: extrae de cada resultado el
  `id_alibaba`, `url_alibaba`, `nombre`, `precio_texto`/`moq_texto`
  (**crudos, nunca parseados a un número**), `proveedor`,
  `proveedor_verificado`, `es_publicidad`, y ahora también `imagen_url`
  (miniatura del listado, `img.searchx-product-e-slider__img`) — usada
  por el ranking barato de Match Mode. Probado con los 7 resultados
  reales de `alibaba_busqueda_real.html`.
- **`parser_ficha_alibaba.py`**: además del precio real (sin cambios en
  esa parte), ahora también extrae `nombre_ficha` (`subject`, más
  confiable que el título del listado), `atributos` (dict fusionado de
  `productBasicProperties` + `productKeyIndustryProperties`, specs reales
  del proveedor) e `imagenes` (fotos reales en resolución `big` desde
  `mediaItems`, descartando el video si lo hay). Probado con el fixture
  real `alibaba_ficha_real.html` (producto 1601487795601: cepillo/esponja
  de silicona, 6 fotos reales, atributos `type=Cleaning Brush`,
  `material=Silicone`, `weight=39(g)`, etc.)
- **`parser_ficha_ml.py`**: ahora también extrae `imagen_url` (JSON-LD
  `image`, confirmado real), `descripcion` y `marca` — insumo de texto
  extra para el matcher cuando el nombre del listado es corto/ambiguo.
- **Match Mode implementado** — ver sección 3 para el diseño completo.
  Probado con datos sintéticos (incluido el caso "gemelo tramposo") y
  verificado manualmente contra los dos fixtures reales existentes
  (ficha de ML + ficha de Alibaba) — **todavía sin la validación con
  navegación en vivo pedida por la usuaria** (ver 🚦 arriba).

## 3. Diseño de Match Mode (aprobado por la usuaria, con 5 ajustes)

**Objetivo**: dado un candidato de ML con demanda confirmada, decidir si
existe un producto en Alibaba que sea el mismo producto (o
sustancialmente equivalente — no "más similar entre resultados malos").
Si no hay evidencia suficiente, el resultado explícito es
`SIN_MATCH_CONFIABLE`, nunca un candidato débil disfrazado de match.

**Dos etapas** (para no pagar el costo de abrir todas las fichas):

1. **Ranking barato** (`matcher.rankear_candidatos`): usa solo lo ya
   disponible en el listado de búsqueda de Alibaba (título + miniatura)
   contra el nombre/imagen de ML. Se queda con el `top_k` (default 3,
   `--top-k` configurable).
2. **Verificación de ficha** (`matcher.verificar_candidatos`): abre la
   ficha de cada uno de esos `top_k`, **en orden**. Si el #1 revela una
   incompatibilidad esencial (ver abajo), se prueba el #2, después el #3
   — recién se devuelve `SIN_MATCH_CONFIABLE` después de agotar todo el
   `top_k` (ajuste #1 de la usuaria: nunca abrir solo el ganador del
   ranking barato).

**Tres señales**, cada una detrás de una interfaz intercambiable
(`embeddings.py`, ajuste #4):

- **Texto**: coseno entre embeddings de nombre+descripción de ML y
  nombre de Alibaba (título de listado en el ranking, `subject` real en
  la verificación). El embedder real (`EmbedderTextoClip`,
  `sentence-transformers`, modelo `clip-ViT-B-32-multilingual-v1`) es
  multilingüe — compara español (ML) contra inglés (Alibaba) sin traducir.
- **Imagen**: coseno entre embedding de la imagen de ML y la(s) de
  Alibaba — en la verificación se compara contra TODAS las fotos de la
  ficha y se toma la mejor. Embedder real: `EmbedderImagenClip`
  (`clip-ViT-B-32`, mismo espacio vectorial que el de texto). Descarga
  con `requests` (URLs estáticas de CDN, no hace falta navegador),
  `None` ante cualquier falla — "imagen no disponible" es un resultado
  esperado, nunca una excepción.
- **Atributos** (`atributos_matching.py`, ajuste #2): nada de un umbral
  universal (ej. ">3x"). Cada TIPO de atributo (categoría, material,
  capacidad, peso, potencia, voltaje, cantidad de piezas, dimensiones,
  color, marca) tiene su propio comparador y tolerancia configurable, y
  se clasifica en **esencial** (categoría/material/capacidad/potencia/
  voltaje/cantidad_piezas/dimensiones) o **secundario** (color, marca —
  la propia usuaria los dio como diferencia menor admisible). **Solo un
  atributo esencial con valor confiable en AMBOS lados e incompatible
  puede vetar un candidato**; si falta un lado o el valor no se
  interpreta con confianza, la comparación queda "no comparable" (nunca
  cuenta como incompatibilidad) y solo baja la cobertura/confianza del
  score. Fuente de atributos: specs estructuradas de Alibaba
  (`productBasicProperties`, prioritarias) + regex sobre texto libre
  (título/descripción de ML, o lo que falte en Alibaba).

**Combinación**: score ponderado (`PesosMatching`, default texto 0.45 /
imagen 0.35 / atributos 0.20 — re-normalizado sobre texto+imagen si no
hubo ningún atributo comparable de ningún lado). Categoría final según
`UmbralesMatching` (default MATCH_ALTO≥0.80, MATCH_PROBABLE≥0.60) —
**salvo que haya un veto esencial, que fuerza `SIN_MATCH_CONFIABLE` sin
importar el score** (requisito explícito: "una similitud visual alta con
una especificación esencial incompatible debe poder impedir un match").
Pesos y umbrales son valores iniciales, no calibrados (ajuste #5) — se
pasan como parámetro, no están hardcodeados.

**Retrieval separado de matching** (ajuste #3): la generación de la query
de búsqueda vive en `orquestador_matching.py`
(`ESTRATEGIAS_QUERY_DEFAULT`, hoy solo `generar_query_busqueda_v1`: título
de ML limpiado de stopwords, sin traducir), NO en `matcher.py`. Si una
query no devuelve resultados, `procesar_candidato_matching` prueba la
siguiente estrategia de la lista antes de rendirse. `matcher.ejecutar_matching`
nunca interpreta "la búsqueda no encontró nada" como "el producto no
existe" — lo deja explícito en el motivo (`candidatos_listado` vacío →
`SIN_MATCH_CONFIABLE` con un mensaje que dice literalmente eso).

**Auditoría completa**: `MatchResult` (`matcher.py`) guarda TODOS los
candidatos evaluados (no solo el ganador), con su propio score,
comparaciones de atributos, veto si lo hubo, y motivo — persistido en la
tabla nueva `matching_alibaba` (`database/db.py`, append-only, separada a
propósito de `alibaba_comparables`: "¿es el mismo producto?" es una
pregunta distinta de "¿a qué precio?", que sigue siendo la etapa
siguiente sin empezar).

Precio, MOQ, `proveedor_verificado` y `es_publicidad` del listado de
Alibaba **nunca entran en el cálculo de similitud** — son señales de
calidad comercial para el filtro económico, no de si el producto es el
mismo (regla explícita de la usuaria).

## 4. Cómo funcionan las sesiones/perfiles y CAPTCHA

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
- **Hallazgo nuevo (validación real de Match Mode, 2026-09-11): la
  reputación del perfil se puede "ensuciar"**. Después de varios intentos
  fallidos seguidos contra el CAPTCHA de Alibaba (incluso resolviéndolo a
  mano en un Chrome manual, siguiendo el truco de arriba), el mismo
  perfil siguió recibiendo el slider una y otra vez. Experimento
  controlado (perfil viejo sin tocar como control, perfil nuevo desde
  cero): con un perfil `.perfil_chrome_collector` recién creado, tanto la
  navegación manual como la automatizada (Playwright) pasaron la
  búsqueda y la apertura de ficha de Alibaba **sin un solo CAPTCHA**
  (confirmado en `capturas_exploratorias/manifiesto.jsonl`, entradas
  `matching_alibaba_busqueda`/`matching_alibaba_ficha` con
  `bloqueado: false`). Conclusión: el CAPTCHA de Playwright en sí mismo
  sigue siendo real (ver el hallazgo de arriba), pero ADEMÁS la sesión/
  perfil puede acumular sospecha con el tiempo/intentos — dos problemas
  distintos, no uno solo. Si vuelve a aparecer el CAPTCHA de forma
  persistente: renombrar `.perfil_chrome_collector` (nunca borrarlo, sirve
  de referencia) y dejar que el próximo `navegador_persistente()` cree uno
  nuevo en su lugar, después calentarlo con el truco de Chrome manual de
  arriba.
- **Manejo del bloqueo dentro del pipeline** (`navegador_ml.pausar_por_bloqueo_y_continuar`):
  nunca cierra Chrome ni intenta resolver/evadir nada. Pausa
  indefinidamente (sin timeout corto) con el mensaje "[Sitio] requiere
  intervención humana. Resolvé el login/CAPTCHA en la ventana de Chrome
  y luego presioná Enter para continuar." Al presionar Enter, recarga la
  misma URL y **verifica** que el bloqueo realmente desapareció antes de
  seguir — si sigue bloqueado, vuelve a pausar en vez de avanzar. Es
  reusable para cualquier sitio vía el parámetro `sigue_bloqueado`
  (chequeo inyectable) — `orquestador_matching._abrir_pagina_alibaba` lo
  reusa igual que `capturador_busqueda_alibaba.py`.
- **Desafío PoW de Akamai** (Mercado Libre): distinto de todo lo
  anterior — se resuelve solo con el JS de la propia página en unos
  segundos, no necesita intervención humana (`navegador_ml.es_desafio_pow_ml`
  + `esperar_resolucion_desafio_pow`).
- **Pausa configurable entre fichas** (`navegador_ml.esperar_entre_fichas`,
  `--delay-min`/`--delay-max`, default 3-8s): reduce la frecuencia con la
  que aparece el bloqueo de "tráfico sospechoso" en primer lugar — mejor
  evitarlo que resolverlo. `orquestador_matching.py` la reusa también
  entre fichas de Alibaba durante la verificación del `top_k`.

## 5. Parsers existentes y qué extrae cada uno

| Archivo | Qué parsea | Campos principales |
|---|---|---|
| `parser.py` | Listado del catálogo completo de un proveedor Alibaba conocido (`module-data` en atributos HTML) | nombre, url, precio_min/max, moq, cantidad_vendida, imagen, categoría, `compra_directa`/`envio_calculable` |
| `parser_ficha_alibaba.py` | Ficha individual de un producto de Alibaba (`window.detailData`) | precio_alibaba_50u (solo si es precio único), moq, moneda, **`nombre_ficha`, `atributos`, `imagenes`** (nuevo, para Match Mode) |
| `parser_busqueda_alibaba.py` | Listado de búsqueda de Alibaba por palabra clave | id_alibaba, url_alibaba, nombre, precio_texto/moq_texto (crudos), proveedor, proveedor_verificado, es_publicidad, posición, **`imagen_url`** (nuevo) |
| `parser_busqueda_ml.py` | Listado de búsqueda de Mercado Libre | id_ml, url_ml, nombre, precio_ml, rating_visible, mas_vendido, unidades_vendidas (aprox.), `origen_url`, prioridad |
| `parser_ficha_ml.py` | Ficha individual de Mercado Libre (JSON-LD + `__NORDIC_RENDERING_CTX__`) | nombre, precio_ml, moneda_ml, unidades_vendidas, stock_visible, cantidad_opiniones, rating, `pagina_no_encontrada`, **`imagen_url`, `descripcion`, `marca`** (nuevo) |
| `atributos_matching.py` (nuevo) | Extracción/comparación de atributos de producto (texto libre + specs estructuradas de Alibaba) | tipos numéricos (capacidad/peso/potencia/voltaje/cantidad_piezas/dimensiones, normalizados) y categóricos (categoría/material/color/marca, canonicalizados) |
| `embeddings.py` (nuevo) | Interfaz de embeddings de texto/imagen | `EmbedderTextoClip`/`EmbedderImagenClip` (reales, carga perezosa) y `EmbedderTextoBolsaDePalabras`/`EmbedderImagenPorClaves` (fakes para tests) |
| `matcher.py` (nuevo) | Núcleo de Match Mode: ranking + verificación + `MatchResult` auditable | ver sección 3 |
| `orquestador_matching.py` (nuevo) | Orquesta Match Mode real: genera query, busca en Alibaba, corre el matcher, persiste | ver sección 3 |

## 6. Pruebas reales realizadas y sus resultados

- **Medición de confiabilidad de fichas de ML** (`medicion_confiabilidad_ml.py`),
  3 corridas reales sucesivas: terminó en **75 fichas, 100% de éxito, 0%
  de 404, 0% de otros errores.**
- **Experimento controlado de URL** (`experimento_url_producto_reconstruida.py`,
  5 pares reales): confirmó el formato `/p|up/<searchVariation>?pdp_filters=item_id:<item_id>`.
- **Captura de búsqueda de Alibaba**: 1 corrida real exitosa ("wireless
  earbuds", 48 resultados, 7 confirmados con extracción completa).
- **Match Mode**: verificado con los dos fixtures HTML reales ya
  existentes (`ml_ficha_real.html` + `alibaba_ficha_real.html`, productos
  NO relacionados entre sí — un cepillo eléctrico de piso vs. un cepillo/
  esponja de silicona para platos) — correctamente **no** dio un match
  alto (score de atributos con cobertura baja, sin veto por falta de
  material del lado de ML, tal como se espera de datos reales
  incompletos). No reemplaza la validación real pedida por la usuaria
  (navegación en vivo, ver 🚦 arriba) — es una verificación de plomería,
  no la demostración final.

## 7. Qué queda pendiente de Fase 2

En orden, cada uno bloqueado por el anterior:

1. **🚦 Validación real de Match Mode con navegación en vivo** (ver
   arriba) — el bloqueante actual.
2. Calibrar pesos/umbrales/estrategias de query con los resultados de esa
   validación.
3. Si el diccionario de categorías/materiales resulta demasiado grueso en
   la validación real (ver limitación en la sección 🚦), ampliarlo con
   los términos que aparezcan en los casos reales — no antes, para no
   ajustar a ciegas.
4. Verificación de precio en cadena: para el comparable elegido por Match
   Mode, guardar en `alibaba_comparables` (`db.insertar_comparable_alibaba`,
   ya existe) — hoy Match Mode NO llena esa tabla, solo `matching_alibaba`.
5. Filtro económico (×2.5 de markup, USD 10 de diferencia mínima) —
   todavía sin implementar.
6. Segunda etapa de análisis + shortlist final (`ESTADOS_CANDIDATO` ya
   define `segunda_etapa`/`finalista`, sin lógica que los use todavía).
7. Pendiente menor, no bloqueante: confirmar el caso de precio de Alibaba
   con escalones por cantidad.

## 8. Decisiones técnicas importantes y por qué

- **Nunca confiar en el precio/MOQ del listado, solo en la ficha
  individual** — regla del proyecto desde el arranque, aplicada
  consistentemente en ML y en Alibaba.
- **El listado de ML nunca confirma demanda por sí solo.**
- **Dedup de `candidatos_ml` por `url_ml`, no por el href crudo del
  link de tracking.**
- **No seguir el link de tracking real de ML para resolver su
  redirect** (`is_advertising=true`).
- **Nunca adivinar un formato de URL sin evidencia real.**
- **Captura automática de HTML de diagnóstico** para cualquier caso
  anómalo — nunca se le pide a la usuaria que recolecte HTML a mano.
- **Pausa humana que verifica su propia resolución** en vez de asumir
  que un Enter significa "resuelto".
- **Session-hardening manual** como solución al problema de
  automatización, en vez de evadir la detección de Playwright.
- **Matching no depende principalmente del título** (requisito explícito
  de la usuaria): texto es una de tres señales, no la única — imagen y
  atributos estructurados pesan tanto o más, y un atributo esencial
  incompatible puede vetar aunque el texto/imagen puntúen alto.
- **Incompatibilidad dura solo desde certeza, nunca desde ausencia de
  dato** (ajuste #2): si un atributo no se pudo extraer de un lado, la
  comparación es "no comparable", no "incompatible" — evita vetos falsos
  por datos faltantes, que son la norma más que la excepción en texto
  libre real.
- **top_k con reintento ordenado, no solo el ganador del ranking barato**
  (ajuste #1): el ranking barato (solo texto+imagen de listado) es
  aproximado a propósito — puede rankear primero un "gemelo tramposo"
  visualmente parecido; la verificación de ficha con atributos reales es
  la que realmente decide, probando el siguiente candidato si el primero
  queda vetado.
- **Retrieval (generar la query) y matching (decidir si es el mismo
  producto) son problemas separados** (ajuste #3): viven en módulos
  distintos, y "la búsqueda no encontró nada" nunca se traduce a "no
  existe" en el resultado.
- **Embeddings de texto/imagen detrás de una interfaz** (ajuste #4,
  `embeddings.py`): permite cambiar de modelo (o de proveedor) sin tocar
  `matcher.py`, y permite testear toda la lógica de ranking/veto/top_k
  con fakes deterministas, sin red ni modelos pesados en la suite de
  tests normal.
- **Pesos, umbrales y tolerancias son parámetros, no constantes**
  (ajuste #5): se pasan explícitamente (`PesosMatching`,
  `UmbralesMatching`, `tolerancias_atributos`) — ninguno se calibró
  todavía con datos reales, a propósito.
- **Match Mode guarda su evidencia completa (`matching_alibaba`),
  separada de `alibaba_comparables`**: "¿es el mismo producto?" y "¿a qué
  precio?" son preguntas distintas, resueltas en etapas distintas — la
  segunda todavía no empezó.
- **`sentence-transformers`/Pillow con carga perezosa**: instanciar
  `EmbedderTextoClip`/`EmbedderImagenClip` no descarga ni carga ningún
  modelo — recién pasa en el primer `.embed(...)` real. La suite de
  tests completa corre sin esas dependencias pesadas cargadas ni
  necesidad de red.

## 9. Estado de los tests

**201/201 tests pasan** (`pytest` desde la raíz de `alibaba-catalog/`,
147 previos a esta fase + 54 nuevos de Match Mode: `test_embeddings.py`,
`test_atributos_matching.py`, `test_matcher.py`,
`test_orquestador_matching.py`, más tests agregados a los parsers
existentes, a `test_db_sourcing.py` y a `test_navegador_ml.py`
(`goto_seguro`, ver sección 8). Cada test de matching usa embedders fake
(deterministas, sin red) — la validación en vivo real (sección 🚦) ya
arrancó y confirmó que el pipeline funciona con navegación real (Caso 1),
sigue con más casos.

```bash
cd alibaba-catalog
pip install -r requirements.txt   # trae numpy, sentence-transformers, Pillow (nuevo)
pytest
```
