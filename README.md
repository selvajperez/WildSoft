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
  layouts/BaseLayout.astro   # <head>, fuentes, favicon
  components/
    Header.astro             # logo + navegación (desktop y menú mobile)
    Hero.astro
    Proyectos.astro
    ComoConstruyo.astro
    Recorrido.astro
    Notas.astro
    Contacto.astro
    Footer.astro
  pages/index.astro          # ensambla la home
  styles/global.css          # paleta, tipografías, estilos base
public/
  images/                    # logo e ilustraciones aprobadas (WildFox)
  fonts/                     # ver README.txt para agregar Glacial Indifference
  favicon.png
```

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
