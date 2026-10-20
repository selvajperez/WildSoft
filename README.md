# WildSoft — Home (Astro)

Implementación en Astro de la home de WildSoft, fiel a la maqueta desktop aprobada
(v02 + ajustes finales) y a su versión mobile, siguiendo el Manual de Identidad de
Marca y el documento de Contenido Web.

## Requisitos

- [Node.js](https://nodejs.org/) 18.20.8 o superior (recomendado: 20 LTS).

## Instalación

Desde esta carpeta (`07_WEB_ASTRO`):

```bash
npm install
```

## Ejecutar en local

```bash
npm run dev
```

Abrí el sitio en el navegador en la URL que indica la terminal (por defecto
`http://localhost:4321`).

## Compilar para producción

```bash
npm run build
npm run preview
```

## Estructura del proyecto

```
src/
  layouts/
    BaseLayout.astro         # <head>, fuentes, favicon
    NotaLayout.astro         # plantilla de página de nota (hero oscuro, cuerpo, cierre)
    LabLayout.astro          # plantilla de página de experimento (hero oscuro, números, pasos, cuerpo, ficha)
    CasoLayout.astro         # plantilla de novela gráfica vertical para los Casos del Lab
  components/
    Header.astro             # logo + navegación (desktop y menú mobile)
    Hero.astro
    Proyectos.astro
    LabDestacado.astro       # tarjeta destacada de WildSoft-Lab en la home (WildFox científico, enlaza a /lab)
    ComoConstruyo.astro
    Recorrido.astro
    Notas.astro
    Contacto.astro
    Footer.astro
    lab/                     # Hero, Principios y Experimentos de la portada /lab
    lab/rayuela/             # Rayuela de datos: mapa interactivo de etapas por proyecto
    casos/                   # Pagina, Escena, Fuentes, TarjetaCaso y LecturasRelacionadas (compartida con Notas y Lab)
  lib/
    casos.ts                 # casos visibles (borradores solo en dev) y control de imágenes faltantes
    relacionados.ts          # lecturas relacionadas entre Notas, Lab y Casos, en ambos sentidos
  data/
    rayuela.ts               # etapas de la arquitectura y recorrido de cada herramienta
  content/
    config.ts                # esquema de la colección "notas"
    notas/*.md                # una nota por archivo (frontmatter + cuerpo)
    lab/*.md                  # un experimento del Lab por archivo (frontmatter + cuerpo)
    casos/*.yaml              # un caso (novela gráfica) por archivo: actos, páginas o escenas, fuentes
  pages/
    index.astro               # ensambla la home
    notas/index.astro          # listado de Notas
    notas/[slug].astro         # página de una nota (a partir de content/notas)
    lab/index.astro            # portada de WildSoft Lab (experimentos de automatización y datos)
    lab/[slug].astro           # página de un experimento (a partir de content/lab)
    lab/casos/index.astro      # listado de Casos (vuelve a /lab si no hay ninguno publicado)
    lab/casos/[slug].astro     # página de un caso (a partir de content/casos)
    lab/casos/[slug]/[archivo].ts  # PDF de las infografías de un caso visible
  styles/global.css          # paleta, tipografías, estilos base
public/
  images/                    # logo e ilustraciones aprobadas (WildFox)
  fonts/                     # Glacial Indifference (woff2) + licencia OFL
  favicon.png
```

## Cómo agregar una nueva nota

1. Creá un archivo en `src/content/notas/tu-slug.md` con este frontmatter:
   ```yaml
   ---
   title: "Título de la nota"
   description: "Bajada corta (una frase)."
   pubDate: 2026-08-01
   tags: ["Etiqueta uno", "Etiqueta dos", "Etiqueta tres"]
   heroImage: "/images/notas/tu-imagen.svg"
   ---
   ```
2. Escribí el cuerpo en Markdown normal. Una línea `> así` se muestra como cita
   destacada (borde naranja); si querés cerrar la nota con una pregunta
   destacada, hacé que el **último** `>` del archivo sea esa pregunta — el
   estilo del último blockquote es distinto a propósito (centrado, sin borde).
3. Poné la imagen principal en `public/images/notas/`.
4. La nota aparece automáticamente en `/notas` y en `/notas/tu-slug`. Si
   corresponde, agregá a mano una tarjeta en `src/components/Recorrido.astro`
   igual a la de "1993 → 2026" para enlazarla desde el Recorrido.

## Cómo agregar un experimento al Lab

WildSoft Lab (`/lab`) es el espacio para experimentos de automatización y
extracción de datos. Cada experimento es un archivo, igual que una nota.

1. Creá `src/content/lab/tu-experimento.md` con este frontmatter:
   ```yaml
   ---
   title: "Nombre del experimento"
   description: "Una o dos frases: qué es y qué se aprendió."
   estado: "en-marcha"        # en-marcha | en-pausa | explorando | terminado
   fecha: 2026-10-11          # última actualización
   tags: ["Extracción de datos", "Automatización"]
   heroImage: "/images/lab/tu-experimento-hero.svg"
   stack: ["Python", "Playwright"]   # opcional
   repo: "https://github.com/usuario/repo"   # opcional; solo si es público
   repoPrivado: true                  # opcional; muestra "repositorio privado"
   app: "https://mi-app.vercel.app/"  # opcional; botón "Abrir la aplicación"
   statsTitulo: "La base al 9 de octubre de 2026, en números"  # opcional
   stats:                             # opcional: tira de números
     - valor: "470"
       etiqueta: "qué mide ese número"
   pasos:                             # opcional: recorrido del flujo
     - titulo: "Paso"
       texto: "Qué hace."
   ---
   ```
2. Escribí el cuerpo en Markdown: títulos `##`, listas, `**negrita**` y una
   cita `>` si hace falta.
3. Poné la ilustración principal (1200×630, fondo `#151612`) en
   `public/images/lab/`.
4. Aparece sola en `/lab` y en `/lab/tu-experimento`. **No enlaces un
   repositorio privado** (el visitante vería un 404): usá `repoPrivado: true`.

## Cómo sumar una herramienta a la rayuela de datos

La rayuela de `/lab` muestra qué etapas de la arquitectura (Extracción,
Normalización, Almacenamiento, Análisis, Automatización) usa cada
herramienta. Para sumar una, agregá un objeto a `proyectos` en
`src/data/rayuela.ts`; el componente no se toca:

```ts
{
  id: 'mi-herramienta',
  nombre: 'Mi herramienta',
  subtitulo: 'Opcional',
  resumen: 'Qué hace, en una frase.',
  experimento: 'mi-herramienta',   // opcional: slug en src/content/lab/
  recorrido: [                     // en orden, solo las etapas que usa
    { etapa: 'extraccion', texto: 'Qué hace en esta etapa.' },
    { etapa: 'almacenamiento', texto: '...' },
  ],
},
```

El recorrido no tiene que ser lineal ni completo. Si `experimento` apunta a
una ficha que no existe o una etapa se repite, el build falla con un mensaje
claro. Sin `experimento` (ni `enlace`), el panel muestra «Ficha en
preparación».

## Cómo agregar un caso (novela gráfica)

Los Casos de WildSoft Lab (`/lab/casos`) son historias reales contadas como
novela gráfica de lectura vertical. Cada caso es **un** archivo YAML y **una**
página: `src/content/casos/mi-caso.yaml` → `/lab/casos/mi-caso`. Tomá como
modelo `la-firma-de-lo-invisible.yaml`, que tiene comentado cada campo.

- **Actos.** Cada acto tiene `estado: publicado` o `en-preparacion` (se
  anuncia en el índice, sin mostrar contenido), y se cuenta de una de dos
  formas: `paginas` o `escenas`.
- **Páginas completas.** Si la ilustración es una página entera de historieta
  con los textos dibujados, va en `paginas` (`imagen` + `alt`). Se muestra
  entera, sin recortes, con el ancho de la pantalla hasta su tamaño real, y un
  enlace «Ampliar página» abre el original para leerla en el celular. Sus
  textos no se repiten en el YAML; el título del acto queda solo para lectores
  de pantalla y para el índice.
- **Escenas.** Si cada escena tiene su propia imagen, va en `escenas`. Cada escena
  tiene un `id`, un `titulo` opcional (las escenas con título se numeran), un
  `ancho` (`completo`, `medio` o `tercio`: en celulares siempre se apilan) y
  sus `textos` en orden: `narracion` (recuadro) o `dialogo` (globo, con
  `personaje` opcional).
- **Imágenes.** Una por página o por escena, en
  `src/assets/casos/mi-caso/` (ruta relativa al YAML, por ejemplo
  `../../assets/casos/mi-caso/acto-1/01-escena.webp`), con su `alt`. Astro
  genera versiones livianas para celular.
- **Borrador.** Con `publicado: false` el caso solo se ve con `npm run dev`
  (con la marca «Borrador»): no entra en el build ni en los listados. Al pasar
  a `true`, el build falla si a algún acto publicado le falta contenido, una
  imagen o un `alt`.
- **Identidad visual.** `tema` define fondo, papel, tinta y acento del
  interior de la novela. Cabecera, pie y tipografías siguen siendo las del sitio.
- **Infografías.** `infografias` (opcional) agrega una sección debajo de la
  historieta, con su `titulo` y sus `items`: cada uno es una imagen
  (`imagen` + `alt`, se muestra entera y se puede ampliar) o un PDF
  (`archivo`, se enlaza con su peso). Los PDF se guardan junto a las imágenes
  y se sirven en `/lab/casos/mi-caso/archivo.pdf` solo si el caso es visible.
- **Un solo acto.** Si el caso es una historieta completa, alcanza con un acto:
  la página omite el índice de actos y la numeración.
- **Ampliar.** «Ampliar página» abre la imagen a tamaño real en el Lightbox del
  sitio, donde se recorre deslizando (pensado para leer diálogos en el celular).
- **Fuentes.** `fuentes` lista fuentes documentales y bibliografía; la sección
  aparece cuando hay al menos una.
- **Lecturas relacionadas.** `relacionados` acepta slugs de `notas`, `lab` y
  `casos`. Las notas y los experimentos también tienen ese campo (opcional).
  La relación se declara de un solo lado y se muestra en las dos páginas; si
  un slug no existe, el build falla.

## Paleta y tipografías

Colores oficiales (Manual de Identidad, punto 3), definidos como variables CSS
en `src/styles/global.css`:

| Color | HEX |
|---|---|
| Naranja Zorro | `#EC7323` |
| Fondo Claro | `#FDEEDB` |
| Negro Profundo | `#151612` |
| Verde Musgo | `#71781A` |
| Crema | `#FBF2E2` |
| Gris Auxiliar | `#302F2E` |

Tipografías: **Glacial Indifference** (principal) y **Belleza** (secundaria,
frases destacadas y cierres). Belleza se carga automáticamente desde Google
Fonts. Glacial Indifference está incluida en `public/fonts/` (woff2 Regular y
Bold, licencia SIL OFL 1.1 en `OFL.txt`); Poppins queda como respaldo.

## Responsive

El corte mobile/desktop está en `760px` (media queries en cada componente).
La versión desktop reproduce la maqueta aprobada; la versión mobile reproduce
la maqueta mobile aprobada (columnas apiladas, ilustración de Proyectos
después de las 4 áreas, menú hamburguesa).

## Imágenes

Todas las ilustraciones y el logo son los archivos aprobados en
`Escritorio/WildSoft/02_PERSONAJE/APROBADOS` y
`Escritorio/WildSoft/05_REDES/WEB/Ilustraciones`, copiados sin alterar su
identidad visual (el logo se recortó su espacio transparente sobrante para
que se vea nítido en el header, sin tocar el diseño). Si reemplazás algún
archivo en `public/images/`, mantené el mismo nombre para que el sitio siga
funcionando.
