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
  components/
    Header.astro             # logo + navegación (desktop y menú mobile)
    Hero.astro
    Proyectos.astro
    ComoConstruyo.astro
    Recorrido.astro
    Notas.astro
    Contacto.astro
    Footer.astro
  content/
    config.ts                # esquema de la colección "notas"
    notas/*.md                # una nota por archivo (frontmatter + cuerpo)
  pages/
    index.astro               # ensambla la home
    notas/index.astro          # listado de Notas
    notas/[slug].astro         # página de una nota (a partir de content/notas)
  styles/global.css          # paleta, tipografías, estilos base
public/
  images/                    # logo e ilustraciones aprobadas (WildFox)
  fonts/                     # ver README.txt para agregar Glacial Indifference
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
Fonts. Glacial Indifference tiene licencia propia y no se distribuye en este
repo — instrucciones para agregarla en `public/fonts/README.txt` (mientras
tanto, el sitio usa Poppins como reemplazo visual).

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
