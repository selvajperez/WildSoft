import { defineCollection, z } from 'astro:content';

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
  }),
});

// Experimentos de WildSoft Lab (automatización y extracción de datos).
// Un experimento = un archivo en src/content/lab/. `stats` y `pasos` son
// opcionales: si existen, la página los muestra como tira de números y como
// recorrido del flujo. `repo` también es opcional: un repositorio privado
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
  }),
});

export const collections = { notas, lab };
