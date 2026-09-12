# Estado actual del motor de sourcing MUTE (ML ↔ Alibaba)

> Última actualización: sesión del 2026-09-11 (implementación de Match
> Mode). Este documento es el punto de entrada para retomar el proyecto —
> no hace falta leer todo el historial de `README.md` para saber dónde
> estamos parados.

## 👥 Cómo se organiza el trabajo (Nube / Local / Selva)

Adoptado el 2026-09-11, después de una validación real que le exigió
demasiado a Selva como intermediaria manual entre dos sesiones de Claude.
De acá en adelante:

- **Nube** (Claude Code en claude.ai/web, sin acceso a la compu de
  Selva): diseño, código, tests, documentación. **Nunca le pide a Selva
  que corra algo real solo para relayarle el resultado de vuelta** — si
  hace falta navegación real o leer la base real, eso es trabajo de Local.
- **Local** (Claude Code corriendo en la compu de Selva, mismo
  repositorio): toda ejecución real -- abrir Chrome, navegar a ML/
  Alibaba, correr los orquestadores, leer/escribir `catalogo_alibaba.db`.
  Trabaja de forma autónoma entre pausas; solo interrumpe a Selva para el
  click de un CAPTCHA/login o una decisión de negocio real.
- **Selva**: resuelve CAPTCHA/login cuando hace falta (eso nunca lo va a
  hacer una IA, es una regla del proyecto) y toma las decisiones de
  negocio (qué producto importar, qué riesgo aceptar, cuándo pasar de
  fase). **No transporta resultados, logs, comandos ni archivos entre
  sesiones** -- ese trabajo lo hacen GitHub + este archivo.

### Nube tiene dos variantes de entorno (2026-09-12): "Default" y "WildSoft"

Al investigar por qué Nube no podía consultar el dólar MEP en vivo (ver
sección 10), encontramos que la limitación de red **no es de Claude Code
en general, sino de la configuración del *cloud environment*** en el que
corre cada sesión de Nube (`claude.ai/code`, ícono de nube arriba del
cuadro de mensaje → engranaje del environment → "Acceso a la red"). Hay
cuatro niveles posibles (None/Trusted/Full/Custom); el entorno por
defecto ("Default") viene en **Trusted** (solo domina un puñado de hosts
de infraestructura -- GitHub, PyPI, npm, etc. -- nada de internet
general). Esto es configurable por la usuaria, por entorno, no algo fijo
de la plataforma.

La usuaria creó/ajustó un segundo entorno, **"WildSoft"**, con:

- **Acceso a la red: Full** (cualquier dominio, incluido `dolarapi.com`).
- **Script de configuración**:
  ```bash
  #!/bin/bash
  pip install --break-system-packages -r alibaba-catalog/requirements.txt || true
  python3 -m playwright install --with-deps chromium || true
  ```
  (instala las dependencias de Python y la build de Chromium que
  corresponde a la versión de `playwright` del proyecto -- se comprobó
  que el Chromium que ya viene preinstalado en la imagen base de estas
  sesiones tiene un desajuste de revisión con el paquete `playwright` de
  `requirements.txt`, así que hace falta este paso para que coincidan).

**Una sesión de Nube que arranca eligiendo el entorno "WildSoft" (no
"Default") puede entonces**: consultar APIs externas como el dólar MEP,
y lanzar Chromium headless sin el error de revisión. **Lo que NO cambia,
en ningún entorno de Nube**: no hay pantalla ni forma de que Nube resuelva
un CAPTCHA o un login interactivo -- eso sigue siendo exclusivamente de
Local/Selva, sin importar el nivel de red. Esto **todavía no se verificó
con una corrida real** (pendiente: abrir una sesión de Nube en WildSoft y
confirmar que `tipo_cambio.obtener_dolar_mep()` funciona de verdad y que
Chromium lanza sin errores -- ver checklist que se le pidió a esa
sesión).

### Reglas obligatorias

1. **Antes de empezar a trabajar, toda sesión (Nube o Local) lee este
   archivo completo**, en particular "🚦 Próximo punto de entrada" --
   es la única fuente de verdad sobre en qué estado está el proyecto.
   Este archivo tiene que alcanzar por sí solo para que una sesión nueva
   retome el proyecto sin que Selva tenga que reconstruirle el contexto.
2. **Después de cualquier cambio de código o corrida real relevante, la
   sesión que lo hizo actualiza este archivo y lo pushea antes de
   terminar** -- nunca deja el estado real solo en su propia cabeza, en
   un log, o en un archivo de resultados que ninguna otra sesión vaya a
   leer.
3. Si una sesión detecta que la otra trabajó en paralelo sin coordinarse
   (ya pasó una vez, ver Fase A/B más abajo), hace `git pull`, revisa qué
   se hizo, y lo deja explícito acá -- nunca lo descarta ni lo duplica
   sin decirlo.

### Para arrancar una sesión nueva (Nube o Local)

No hace falta clonar nada nuevo ni crear otro repositorio -- mismo
repositorio, misma carpeta, misma rama para las dos:

- **Carpeta local de Selva**: `alibaba-catalog/` dentro del repo
  `WildSoft` (en su compu, `...\WildSoft\AlibabaComparador\alibaba-catalog`).
- **Rama de trabajo**: `claude/alibaba-mercado-libre-comparator-x0imwm`
  (la única que se usa en este proyecto).
- Para una sesión Local nueva: abrir Claude Code apuntando a esa misma
  carpeta que Selva ya tiene clonada -- no hace falta "empezar" nada,
  el historial completo ya está ahí.
- Lo primero que cualquier sesión nueva hace, Nube o Local: `git pull` y
  leer este archivo completo antes de tocar código.

## 🚦 Próximo punto de entrada (leer esto primero)

**Fase A (calibración), Fase B (corrida en lote de Match Mode) y Fase 3
(filtro económico, ya con tipo de cambio MEP automático) están
implementadas y con tests (269/269).** Ya no falta ninguna decisión de
negocio para poder correr el filtro económico -- la usuaria confirmó
dólar MEP como referencia (ver sección 10). **La navegación real contra
ML/Alibaba (CAPTCHA, login) sigue siendo exclusivamente de la
usuaria/Local, en cualquier entorno de Nube.** El bloqueo de red general
que impedía siquiera consultar el dólar MEP desde Nube era específico
del entorno "Default" (nivel Trusted) -- ver el nuevo entorno "WildSoft"
(Full + Chromium listo) en la sección de arriba "Nube tiene dos variantes
de entorno". Una sesión de Nube en WildSoft debería poder verificar el
fetch del MEP real y que Chromium lanza bien, **pero esto todavía no se
confirmó con una corrida real** (pendiente). Ningún código de este
proyecto se probó todavía contra la API real de dolarapi.com ni contra
una ficha de Alibaba real con escalones de precio -- toda la cobertura
de tests usa HTTP y HTML simulados.

```powershell
cd alibaba-catalog\collector_alibaba
python orquestador_matching_lote.py --login   # solo si hace falta loguearse de nuevo
python orquestador_matching_lote.py           # Fase 2: Match Mode en lote, 10 candidatos por default

python orquestador_filtro_economico.py        # Fase 3: filtro económico real, ya sin --tipo-cambio manual
python orquestador_filtro_economico.py --login
```

`orquestador_matching_lote.py` selecciona sola hasta 10 candidatos
`demanda_confirmada` (variados por tipo de producto cuando es posible),
abre un único Chrome para los 10, sigue adelante si un candidato puntual
falla, y al final imprime un resumen con conteos por categoría y una
lista de "dudosos" (MATCH_PROBABLE o candidatos vetados) para revisar a
mano. Ver la sección "Fase B" más abajo para el detalle de diseño.

`orquestador_filtro_economico.py` toma todos los candidatos que quedaron
en estado `con_comparable` (es decir, con un match de Alibaba ya elegido
por Match Mode), consulta el dólar MEP una vez al arrancar, abre la ficha
de Alibaba de cada uno, calcula ratio/diferencia y guarda el resultado.
**Ya no recibe el tipo de cambio por parámetro manual**: lo busca solo en
cada corrida y, si no lo puede verificar, los candidatos en ARS quedan en
`indeterminado` en vez de asumir un valor. Ver sección 10 para el detalle
completo (reglas, esquema, limitaciones).

**Nota operativa importante, encontrada durante la validación**: el perfil
de Chrome (`.perfil_chrome_collector`) puede acumular "mala reputación"
ante el CAPTCHA de Alibaba después de varios intentos fallidos seguidos —
no es un problema del código. Si aparece el slider CAPTCHA de forma
persistente incluso resolviéndolo a mano, la solución que funcionó fue
crear un perfil nuevo (renombrar el viejo, dejarlo como respaldo/muestra
para comparar) y calentarlo de cero con un Chrome manual antes de volver
a correr el script. Ver sección 4 para el detalle.

### Resumen de los 5 casos reales

| # | Candidato ML | Resultado | ¿Esperado? |
|---|---|---|---|
| 1 | Cepillo eléctrico multifunción piso | `SIN_MATCH_CONFIABLE` (0.59, por muy poco) | Razonable, aunque limitado por falta de imagen |
| 2 | Cepillo de mano para lavar autos | `MATCH_PROBABLE` (0.61) | Sí -- match real plausible |
| 3 | Cepillo eléctrico 8-en-1 | `MATCH_ALTO` (0.88, con imagen real funcionando) | Sí -- primer match confirmado con las 3 señales activas |
| 4 | Set 4 cepillos "Oh My Shop" | `SIN_MATCH_CONFIABLE` (0.56-0.60) | Inconcluso -- no probó un negativo genuino (selección por fallback) |
| 5 | Camiseta oficial Boca Juniors | `MATCH_PROBABLE` (0.75) | **NO -- falso positivo real.** Esperado: `SIN_MATCH_CONFIABLE` |

### Fase A -- calibración dirigida por evidencia real (✅ implementada)

Los 5 hallazgos de la batería, en el orden confirmado por la usuaria
(1 → 2 → 3 → 4 → 5), cada uno corregido y con regresión sobre los 5
casos reales (`tests/test_matcher_regresion_casos_reales.py`, usa los
textos y scores de texto/imagen REALES ya medidos, no fakes):

1. **Atributo esencial nuevo: `identidad`** (`atributos_matching.py`,
   `CANON_IDENTIDAD`) -- distingue `licenciado_oficial` de
   `generico_personalizable` a partir de señales textuales ("oficial",
   "licencia oficial" vs. "custom", "personalizable", "logo printing",
   "réplica"). Corrige el falso positivo real del Caso 5.
2. **`CANON_CATEGORIA` ampliado** con camiseta/jersey/remera/playera/
   polera/shirt/t-shirt.
3. **Cantidad de piezas ampliada**: ahora reconoce "Set N" (sin
   preposición), "Set of N" (inglés) y "N accesorios", además de los
   patrones que ya existían.
4. **`_combinar_score` re-normaliza cuando falta imagen de un lado**
   (`imagen_disponible`), igual que ya hacía con la cobertura de
   atributos -- la ausencia de imagen ya no cuenta como "muy distinta"
   a valor 0.0 con el peso completo.
5. **Tope de confianza para `MATCH_ALTO`** (`_categorizar`): al recalcular
   los 5 casos reales con los puntos 1-4 aplicados, apareció sobre-confianza
   real -- texto muy similar + un solo atributo débil alcanzaba MATCH_ALTO
   apenas se excluía el peso de la imagen ausente. Fix: `MATCH_ALTO` exige
   que las TRES señales se hayan podido comparar de verdad (imagen
   disponible en ambos lados Y cobertura de atributos > 0); con menos
   señales, el techo queda en `MATCH_PROBABLE` aunque el score numérico
   sea alto.

**Resultado de la regresión sobre los 5 casos reales** (categoría antes →
después de la Fase A):

| # | Antes | Después | Motivo del cambio |
|---|---|---|---|
| 1 | `SIN_MATCH_CONFIABLE` (0.59) | `MATCH_PROBABLE` | Ya no penaliza la imagen ausente como "muy distinta"; el tope de A5 evita que llegue a ALTO con evidencia delgada |
| 2 | `MATCH_PROBABLE` (0.61) | `MATCH_PROBABLE` | Mismo candidato, mismo resultado (el score interno subió, la categoría no cambia) |
| 3 | `MATCH_ALTO` (0.88) | `MATCH_ALTO` | Sin cambios -- tenía imagen real disponible |
| 4 | `SIN_MATCH_CONFIABLE` | `MATCH_PROBABLE` (candidato #2) | El candidato #1 ahora se vetea por cantidad de piezas (4 vs. 3); el matcher prueba el #2 (ajuste #1) y ese sí alcanza el umbral |
| 5 | `MATCH_PROBABLE` (0.75, falso positivo) | `SIN_MATCH_CONFIABLE` | Vetado por `identidad` -- el fix que motivó toda la Fase A |

### Fase B -- corrida automática de múltiples candidatos (✅ implementada, sin correr todavía)

`orquestador_matching_lote.py` reemplaza el patrón de scripts
`_validar_casoN.py` (que ya no se van a seguir creando, como se pidió):

- **Selección automática** (`seleccionar_candidatos_lote`): hasta 10
  candidatos `demanda_confirmada`, priorizando variedad de tipo de
  producto (reusa el mismo `CANON_CATEGORIA` del matcher -- nunca más de
  2 candidatos de la misma categoría reconocida en la primera pasada,
  completa con lo que quede si no hay variedad suficiente). La usuaria no
  elige ni interviene en la selección.
- **Un solo proceso continuo**: candidato ML → búsqueda Alibaba → fichas
  → matching → decisión → persistencia → siguiente candidato, todo sobre
  el mismo Chrome y el mismo par de embedders CLIP (no se recarga el
  modelo por candidato).
- **Sigue ante errores, conserva progreso**: un error en un candidato
  puntual se registra (`procesar_lote`) y el lote continúa -- nunca se
  corta todo el proceso. El progreso ya queda conservado por el mismo
  mecanismo de siempre: `procesar_candidato_matching` persiste en
  `matching_alibaba` y actualiza `candidatos_ml.estado` recién al
  terminar cada candidato, así que uno que falla a mitad de camino sigue
  en `demanda_confirmada` y una corrida posterior del lote lo vuelve a
  elegir solo -- no hace falta ningún checkpoint aparte.
- **Solo se pausa ante un CAPTCHA/bloqueo real** que de verdad necesite
  una persona -- mismo `pausar_por_bloqueo_y_continuar` de siempre.
- **Resumen final**: conteos por categoría + lista de "dudosos"
  (`MATCH_PROBABLE`, o candidatos que quedaron vetados en el camino) para
  revisión manual -- nunca se asume que todo lo que no dio error está
  necesariamente bien.

**Pendiente**: correr `orquestador_matching_lote.py` de verdad (ver 🚦
arriba) y revisar el resumen + los casos dudosos antes de decidir
cualquier otra cosa (más calibración, ampliar la muestra de ML, o recién
ahí considerar el filtro económico).

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

#### Caso 5 (2026-09-11) — "gemelo tramposo" real, falso positivo confirmado del matcher

- **Objetivo**: encontrar automáticamente un candidato con una razón
  *estructural* (no solo "tiene una marca") para esperar ausencia de
  equivalente en Alibaba. `_validar_caso5.py` no encontró ninguno en la
  base existente -- se amplió la muestra corriendo
  `orquestador_demanda_ml.py "camiseta boca juniors"` (Fase 1, sin
  cambios), que confirmó 3 candidatos nuevos con demanda real. El
  heurístico de selección eligió correctamente el único que decía
  "Boca Juniors" completo (no "Boca Jr" ni solo "Boca"): `MLAU3892224756`
  — "Camiseta Oficial Boca Juniors Ranglan 2026 + Short", categoría
  `merchandising_licenciado` (mercadería con licencia oficial de club).
- **Decisión esperada**: `SIN_MATCH_CONFIABLE` (una camiseta con licencia
  oficial no tiene un equivalente real en un catálogo de manufactura
  genérica sin marca).
- **Decisión real: `MATCH_PROBABLE` (0.75).** Candidato de Alibaba
  elegido: "Custom Cross-Border Football Shorts and Jerseys **with Logo
  Printing** Soccer Club Uniforms for Various Football Matches" --
  literalmente una fábrica que imprime el logo que el comprador pida,
  para cualquier club. Texto 0.71, imagen 0.81 (dos fotos de camisetas de
  fútbol, visualmente parecidas), **atributos con 0% de cobertura** -- ni
  siquiera se comparó `categoria` (ver hallazgo abajo), así que no hubo
  ninguna oportunidad de veto.
- **Es un falso positivo real, no un resultado razonable dado la
  evidencia disponible** (a diferencia de los Casos 1 y 4): texto e
  imagen dominaron el score sin que hubiera cobertura suficiente de
  atributos esenciales para frenarlo -- exactamente el escenario que la
  usuaria pidió prevenir desde el diseño original ("una similitud visual
  alta con una especificación esencial incompatible debe poder impedir
  un match"), salvo que la especificación esencial que falta acá
  (identidad/licencia/originalidad) todavía no existe como tipo de
  atributo en el sistema.

**Problema pendiente registrado, sin corregir todavía**: el matcher
necesita poder representar identidad/licencia/originalidad/
personalización como atributo esencial -- ver "Hallazgos consolidados de
calibración" arriba, punto 1 (prioridad alta).

**No se corrieron más casos manuales después de este** -- instrucción
explícita de la usuaria. La batería de validación real queda cerrada acá
(5 casos), con el próximo paso propuesto arriba.

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

1. ✅ Validación real de Match Mode con navegación en vivo (5 casos, ver
   arriba) — cerrada.
2. ✅ Fase A: calibración dirigida por esos 5 casos (identidad como
   atributo esencial, etc.) — implementada, con regresión sobre los
   casos reales.
3. ✅ Fase B: corrida automática en lote — implementada, pendiente de
   correr con datos reales a gran escala (no bloqueante para lo que
   sigue).
4. ✅ Filtro económico (Fase 3, ×2.5 / USD 10, tipo de cambio dólar MEP
   automático) — implementado con tests, sin ninguna decisión de negocio
   pendiente. Ver sección 10. Pendiente: correrlo con datos reales -- eso
   solo lo puede hacer la usuaria/Local, esta sesión de Nube no tiene
   acceso a un navegador real ni a internet en general.
5. Segunda etapa de análisis + shortlist final (`ESTADOS_CANDIDATO` ya
   define `segunda_etapa`/`finalista`, sin lógica que los use todavía) —
   no empezada.
6. Si el diccionario de categorías/materiales o de marcas locales resulta
   demasiado grueso al correr con más datos reales, ampliarlo con los
   términos que aparezcan — no antes, para no ajustar a ciegas.
7. Pendiente menor, no bloqueante: si aparece evidencia real de un
   producto de Alibaba con escalones de precio por cantidad
   (`productLadderPrices`), confirmar el nombre real de los campos de
   cantidad/precio por escalón (hoy solo se preserva el JSON crudo sin
   interpretarlo — ver sección 10).

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

**269/269 tests pasan** (`pytest` desde la raíz de `alibaba-catalog/`).
Incluye la validación real (5 casos reales, ver 🚦), la Fase A de
calibración con regresión sobre esos 5 casos reales
(`test_matcher_regresion_casos_reales.py`, usa scores de texto/imagen
REALES ya medidos con CLIP, no fakes), la Fase B
(`test_orquestador_matching_lote.py`) y la Fase 3 / filtro económico
(`test_filtro_economico.py`, `test_orquestador_filtro_economico.py`, más
los tests nuevos en `test_parser_ficha_alibaba.py` y
`test_db_sourcing.py` — ver sección 10). El resto de los tests de
matching usa embedders fake (deterministas, sin red).

```bash
cd alibaba-catalog
pip install -r requirements.txt   # trae numpy, sentence-transformers, Pillow (nuevo)
pytest
```

## 10. Fase 3 — Filtro económico (implementado, pendiente de una decisión de negocio)

**Objetivo:** cerrar el flujo completo demanda real (ML) → match
adecuado (Alibaba, Match Mode) → ¿vale la pena económicamente? Reglas de
negocio dadas por la usuaria: relación mínima ×2.5 **y** diferencia
mínima de USD 10 (las dos condiciones son obligatorias, confirmado con su
propio ejemplo: Alibaba USD 4.20/u a 20u vs. ML USD 18 → ratio 4.29×,
diferencia USD 13.80 → viable).

### Archivos nuevos

- `collector_alibaba/filtro_economico.py` — lógica pura, sin
  navegación. `resolver_precio_alibaba(datos_ficha)` decide qué precio
  de Alibaba usar (precio único ya verificado por el parser existente, o
  "hay escalones pero no están confirmados" preservando el dato crudo, o
  "no disponible") y `evaluar_viabilidad(...)` aplica las dos reglas y
  devuelve un resultado con toda la evidencia (`ResultadoViabilidad`).
- `collector_alibaba/orquestador_filtro_economico.py` — orquestador con
  navegación real: toma los candidatos en estado `con_comparable`
  (`db.obtener_candidatos_pendientes_de_viabilidad`, nueva), abre la
  ficha de Alibaba elegida por Match Mode, parsea, evalúa viabilidad,
  persiste evidencia completa y actualiza el estado del candidato. Reusa
  `_abrir_pagina_alibaba`/`goto_seguro`/`esperar_entre_fichas` ya
  existentes — ninguna infraestructura de navegación nueva.
- Tests: `test_filtro_economico.py` (16, lógica pura) y
  `test_orquestador_filtro_economico.py` (8, con navegación fake).

### Decisiones tomadas

- **Las dos reglas son AND, no OR** — un candidato con ratio alto pero
  diferencia chica (o viceversa) es `no_viable`. Verificado con tests
  específicos para cada combinación.
- **`MATCH_PROBABLE` que pasa las reglas económicas no se descarta**:
  queda como `viable_dudoso` (candidato sigue en `precio_verificado`,
  para revisión), mientras que `MATCH_ALTO` que pasa las reglas queda
  `viable`. Solo `MATCH_ALTO`/`MATCH_PROBABLE` entran al filtro —
  cualquier otra categoría de Match Mode es `indeterminado`.
- **Nunca se asume un valor cuando falta evidencia** (extiende la regla
  ya usada en todo el proyecto): precio de Alibaba no verificado, ML sin
  precio, moneda ARS sin tipo de cambio, o moneda desconocida → siempre
  `indeterminado`, nunca `no_viable` ni un número inventado. Esto reusa
  los estados que ya existían en `ESTADOS_CANDIDATO`
  (`descartado_no_verificado` para "no pude verificar",
  `descartado_filtro_economico` para "sí lo verifiqué y no es viable",
  `precio_verificado` para los dos viables) — no hizo falta agregar
  estados nuevos.
- **El precio de Alibaba usado siempre lleva su cantidad asociada**
  (`cantidad_asociada`/`moq_valor`), nunca un precio suelto sin saber a
  qué escalón corresponde.
- **Escalones de precio por cantidad (`productLadderPrices`) se
  preservan crudos, sin interpretar**: el parser confirmó que el campo
  real se llama así (visto en `globalDataKeys` del HTML real), pero
  ningún producto real visto hasta ahora tenía escalones, así que no hay
  evidencia real del nombre de los campos de cantidad/precio dentro de
  cada escalón. En vez de adivinar esos nombres, se guarda la lista tal
  cual llega (`precio_ladder_crudo`) y el caso se marca
  `no_verificado`/`indeterminado` hasta que aparezca un caso real que
  permita confirmar el esquema.
- **Toda la evidencia queda en `alibaba_comparables`**, no solo el
  resultado final: precio de Alibaba y su cantidad, fuente del precio,
  escalones crudos (si los hay, como JSON), precio de ML original y su
  moneda, tipo de cambio usado, precio de ML ya en USD, ratio,
  diferencia, categoría de match y resultado/motivo de viabilidad. Se
  puede reconstruir de dónde salió cualquier cálculo sin volver a
  navegar.

### ✅ Decisión de negocio resuelta: dólar MEP, consultado en vivo en cada corrida

La usuaria confirmó **dólar MEP** como referencia (2026-09-12), con estos
requisitos explícitos, todos implementados:

- **Puede variar entre corridas** -- `collector_alibaba/tipo_cambio.py`
  (`obtener_dolar_mep()`) consulta `https://dolarapi.com/v1/dolares/bolsa`
  (cotización de venta) en vivo cada vez que se llama. No hay ningún
  valor numérico hardcodeado en el código.
- **Se consulta UNA vez por corrida completa** (no por candidato) en
  `ejecutar_filtro_economico_real` -- todos los candidatos de una misma
  corrida comparten el mismo valor/fuente/fecha, evitando mezclar tasas
  distintas dentro de un mismo lote.
- **Queda guardado junto con cada cálculo**: `alibaba_comparables` ahora
  tiene `tipo_cambio_usado` (valor), `tipo_cambio_fuente` (URL de la
  API) y `tipo_cambio_fecha_referencia` (fecha que la propia fuente
  reporta para ese valor, distinta de `obtenido_en` que es cuándo MUTE la
  consultó).
- **Sin fallback silencioso a otra cotización**: si `dolarapi.com` no
  responde, responde con error, o la respuesta no tiene un valor de venta
  interpretable, `TipoCambioResuelto.disponible=False` explícito -- nunca
  se prueba con oficial/blue/tarjeta como "mejor que nada". Con
  `disponible=False`, cualquier candidato con precio de ML en ARS queda
  `indeterminado` en esa corrida (los candidatos en USD no se ven
  afectados, no necesitan tipo de cambio).
- **La API se eligió por practicidad** (dolarapi.com es pública, sin
  clave, y expone `bolsa` como el nombre que usa para MEP) -- no hay
  ninguna decisión de negocio nueva escondida ahí, es solo la fuente
  técnica del dato que la usuaria ya definió.

### 🔴 Limitación nueva descubierta al implementar esto: esta sesión (Nube) no puede verificarlo con datos reales

Al intentar probar `obtener_dolar_mep()` contra la API real desde esta
sesión en la nube, la conexión fue rechazada por la política de red del
propio sandbox de esta sesión (permite solo un puñado de hosts de
infraestructura -- GitHub, PyPI, npm -- y bloquea internet en general,
incluido `dolarapi.com`; se confirmó que hasta `google.com` está
bloqueado). Esto es independiente del problema de siempre (esta sesión
tampoco tiene un navegador real para Alibaba/CAPTCHA) -- son dos
bloqueos distintos que coinciden en el mismo lugar: **la corrida real
del filtro económico (`orquestador_filtro_economico.py` sin mockear) solo
se puede hacer desde la máquina de la usuaria, nunca desde esta sesión de
Nube.** Todo lo demás (armar el módulo, la integración, el esquema, los
269 tests) sí se hizo y se probó acá, con HTTP y HTML simulados -- ver
`test_tipo_cambio.py` para la cobertura de `obtener_dolar_mep` (éxito,
error de red, HTTP 4xx/5xx, respuesta sin campo `venta`, valor no
numérico o ≤0 -- en todos los casos de falla se verifica que nunca se
reintenta contra otra fuente).

### Limitaciones conocidas que siguen abiertas

- No se corrió todavía con datos reales de navegación ni contra la API
  real de dólar MEP — está probado con fixtures/fakes deterministas, no
  con una corrida real completa. Ver limitación de arriba.
- No se validó con una ficha de Alibaba real que tenga escalones de
  precio.
- `proveedor`, `variante`, `dimensiones`, `peso_gramos` en
  `alibaba_comparables` siguen sin poblarse — el parser nunca los
  extrajo; es un hueco preexistente, no algo que esta fase debía cerrar.
- El esquema real de `productLadderPrices` (nombres de campo de cantidad
  y precio por escalón) sigue sin confirmar con evidencia real, como se
  explicó arriba.
