import { readFileSync } from 'node:fs';
import { posix } from 'node:path';
import type { APIRoute } from 'astro';
import { archivoDelCaso, getCasosVisibles } from '../../../../lib/casos';

// Los PDF de las infografías de cada caso: /lab/casos/<caso>/<archivo>.pdf.
// Como la página del caso, solo se generan para casos visibles.
export async function getStaticPaths() {
  const casos = await getCasosVisibles();
  return casos.flatMap((caso) =>
    (caso.data.infografias?.items ?? []).flatMap((item) =>
      item.archivo
        ? [{ params: { slug: caso.id, archivo: posix.basename(item.archivo) }, props: { ruta: archivoDelCaso(caso, item.archivo).ruta } }]
        : [],
    ),
  );
}

export const GET: APIRoute = ({ props }) =>
  new Response(readFileSync(props.ruta), { headers: { 'Content-Type': 'application/pdf' } });
