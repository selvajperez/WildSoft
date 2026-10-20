import { defineCollection, reference, z } from 'astro:content';

// Relaciones entre publicaciones: cada entrada puede apuntar a otras por su
// slug, sin copiar su contenido. La relación se lee en ambos sentidos (ver
// src/lib/relacionados.ts), así que alcanza con declararla de un solo lado.
const relacionados = z
  .object({
    notas: z.array(reference('notas')).default([]),
    lab: z.array(reference('lab')).default([]),
    casos: z.array(reference('casos')).default([]),
  })
  .default({});

const notas = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.date(),
    tags: z.array(z.string()),
    heroImage: z.string(),
    siguienteLabel: z.string().optional(),
    siguientePeriodo: z.string().optional(),
    siguienteTexto: z.string().optional(),
    siguienteHref: z.string().optional(),
    siguienteLinkTexto: z.string().optional(),
    relacionados,
  }),
});

// Experimentos de WildSoft Lab (automatización y extracción de datos).
// Un experimento = un archivo en src/content/lab/. `stats` y `pasos` son
// opcionales: si existen, la página los muestra como tira de números y como
// recorrido del flujo. `app` enlaza la aplicación publicada. `repo` también es opcional: un repositorio privado
// no se enlaza (el visitante vería un 404).
const lab = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string(),
    estado: z.enum(['en-marcha', 'en-pausa', 'explorando', 'terminado']),
    fecha: z.date(),
    tags: z.array(z.string()),
    heroImage: z.string(),
    stack: z.array(z.string()).default([]),
    stats: z.array(z.object({ valor: z.string(), etiqueta: z.string() })).default([]),
    pasos: z.array(z.object({ titulo: z.string(), texto: z.string() })).default([]),
    repo: z.string().url().optional(),
    repoPrivado: z.boolean().default(false),
    // Opcionales: enlace a la aplicación publicada y título de la tira de
    // números (por ejemplo, para aclarar la fecha de los datos).
    app: z.string().url().optional(),
    statsTitulo: z.string().optional(),
    relacionados,
  }),
});

// Casos de WildSoft Lab: historias reales contadas como novela gráfica de
// lectura vertical. Un caso = un archivo YAML en src/content/casos/ y sus
// imágenes en src/assets/casos/<slug>/ (rutas relativas al YAML).
// - Un caso con `publicado: false` solo se ve con `npm run dev`: no entra en
//   el build de producción ni en los listados.
// - Un acto se cuenta con `paginas` (páginas completas de historieta, con los
//   textos ya dibujados) o con `escenas` (una imagen por escena y los textos
//   en el YAML). Un mismo acto usa una u otra forma, no las dos.
// - Un acto `en-preparacion` se anuncia en el índice, pero su contenido no se
//   muestra. Si el caso está publicado, cada acto publicado necesita sus
//   imágenes y su `alt`: si faltan, el build falla (ver src/lib/casos.ts).
const casos = defineCollection({
  type: 'data',
  schema: ({ image }) => {
    const texto = z.object({
      tipo: z.enum(['narracion', 'dialogo']),
      personaje: z.string().optional(), // solo diálogos
      texto: z.string(),
    });

    const escena = z.object({
      id: z.string().regex(/^[a-z0-9-]+$/, 'el id de la escena va en minúsculas y guiones'),
      titulo: z.string().optional(),
      imagen: image().optional(),
      alt: z.string().optional(),
      // completo: ocupa todo el ancho. medio / tercio: dos o tres escenas
      // seguidas comparten fila en computadoras; en celulares se apilan.
      ancho: z.enum(['completo', 'medio', 'tercio']).default('completo'),
      textos: z.array(texto).default([]),
    });

    // Página completa de novela gráfica: se muestra entera, sin recortes, y
    // los textos que ya tiene dibujados no se repiten en la página web.
    const pagina = z.object({
      imagen: image(),
      alt: z.string(),
    });

    return z.object({
      title: z.string(),
      subtitulo: z.string(),
      description: z.string(),
      lugar: z.string(),
      epoca: z.string(),
      fecha: z.date(), // última actualización
      tags: z.array(z.string()).default([]),
      publicado: z.boolean().default(false),
      portada: image().optional(),
      portadaAlt: z.string().optional(),
      // Identidad visual propia del caso. Solo cambia el interior de la
      // novela gráfica; cabecera, pie y tipografías siguen siendo las del sitio.
      tema: z
        .object({
          fondo: z.string().default('#151612'),
          papel: z.string().default('#FBF2E2'),
          tinta: z.string().default('#151612'),
          acento: z.string().default('#EC7323'),
        })
        .default({}),
      // Por qué este caso está en el Lab: la conexión con datos, tecnología y
      // sus consecuencias sociales. Se muestra antes del primer acto.
      contexto: z.array(z.string()).default([]),
      actos: z
        .array(
          z.object({
            numero: z.string(), // "I", "II", "III"
            titulo: z.string(),
            bajada: z.string().optional(),
            estado: z.enum(['publicado', 'en-preparacion']),
            paginas: z.array(pagina).default([]),
            escenas: z.array(escena).default([]),
          }).refine((a) => a.paginas.length === 0 || a.escenas.length === 0, {
            message: 'un acto usa `paginas` o `escenas`, no las dos',
          }),
        )
        .min(1),
      // Material complementario debajo de la historieta (infografías,
      // presentaciones). Cada pieza es una imagen (se muestra entera y se
      // puede ampliar) o un documento PDF (se enlaza). Ambos con ruta relativa
      // a este YAML. Una pieza sin imagen ni archivo es un espacio reservado:
      // solo se ve en desarrollo, y un caso publicado no compila con él.
      infografias: z
        .object({
          titulo: z.string(),
          items: z
            .array(
              z.object({
                titulo: z.string(),
                imagen: image().optional(),
                alt: z.string().optional(),
                archivo: z.string().endsWith('.pdf').optional(),
                detalle: z.string().optional(), // p. ej. «Presentación de 15 diapositivas»
              }),
            )
            .default([]),
        })
        .optional(),
      fuentes: z
        .array(
          z.object({
            // documental: expedientes, archivos, prensa de época.
            // prensa: artículos periodísticos o de divulgación actuales.
            tipo: z.enum(['documental', 'bibliografia', 'prensa']),
            autor: z.string().optional(),
            titulo: z.string(),
            detalle: z.string().optional(), // editorial, archivo, publicación
            anio: z.string().optional(),
            url: z.string().url().optional(),
            nota: z.string().optional(), // por qué importa esta fuente
          }),
        )
        .default([]),
      // Aclaración que encabeza la sección Fuentes (p. ej., diferencias entre
      // las fuentes o el carácter de la reconstrucción).
      notaFuentes: z.string().optional(),
      // Conexiones del caso con otros contenidos del sitio, agrupadas por eje.
      // Usan las mismas referencias que `relacionados` y, como ellas, se leen
      // en los dos sentidos: la página enlazada muestra el caso sola. Un eje
      // sin contenidos enlazados no se muestra.
      conexiones: z
        .array(
          z.object({
            eje: z.string(),
            descripcion: z.string().optional(),
            notas: z.array(reference('notas')).default([]),
            lab: z.array(reference('lab')).default([]),
            casos: z.array(reference('casos')).default([]),
          }),
        )
        .default([]),
      relacionados,
    });
  },
});

export const collections = { notas, lab, casos };
