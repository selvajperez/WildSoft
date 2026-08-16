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

export const collections = { notas };
