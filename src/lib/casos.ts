import { posix } from 'node:path';
import { getCollection, type CollectionEntry } from 'astro:content';

export type Caso = CollectionEntry<'casos'>;

// Un borrador (`publicado: false`) solo existe en `npm run dev`: en el build
// de producción no genera página ni aparece en listados o relacionados.
export function casoVisible(caso: Caso): boolean {
  return caso.data.publicado || import.meta.env.DEV;
}

export async function getCasosVisibles(): Promise<Caso[]> {
  const casos = await getCollection('casos', casoVisible);
  casos.forEach(validarCaso);
  return casos.sort((a, b) => b.data.fecha.valueOf() - a.data.fecha.valueOf());
}

// Un caso publicado no puede salir a medio hacer: cada acto publicado necesita
// contenido; cada página, escena o infografía, su imagen (o su PDF) y su alt.
function validarCaso(caso: Caso) {
  if (!caso.data.publicado) return;
  const faltan = caso.data.actos
    .filter((acto) => acto.estado === 'publicado')
    .flatMap((acto) => {
      if (acto.paginas.length === 0 && acto.escenas.length === 0) return [`Acto ${acto.numero} (vacío)`];
      return [
        ...acto.paginas.flatMap((p, i) => (p.alt.trim() ? [] : [`Acto ${acto.numero} / página ${i + 1}`])),
        ...acto.escenas
          .filter((e) => !e.imagen || !e.alt?.trim())
          .map((e) => `Acto ${acto.numero} / ${e.id}`),
      ];
    })
    .concat(
      (caso.data.infografias?.items ?? [])
        .filter((i) => !(i.imagen && i.alt?.trim()) && !i.archivo)
        .map((i) => `Infografía «${i.titulo}»`),
    );
  if (faltan.length > 0) {
    throw new Error(
      `El caso "${caso.id}" está publicado, pero falta imagen o alt en: ${faltan.join(', ')}. ` +
        'Completá lo que falta o volvé a poner `publicado: false`.',
    );
  }
}

// Los PDF de las infografías se escriben en el YAML con ruta relativa a él,
// como las imágenes. Se sirven en /lab/casos/<caso>/<archivo>.pdf solo si el
// caso es visible (ver src/pages/lab/casos/[slug]/[archivo].ts), así que un
// borrador no deja copias en el sitio publicado.
export function archivoDelCaso(caso: Caso, archivo: string) {
  return {
    ruta: posix.normalize(posix.join('src/content/casos', archivo)),
    url: `/lab/casos/${caso.id}/${posix.basename(archivo)}`,
  };
}
