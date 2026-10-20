import { getCollection } from 'astro:content';
import { casoVisible, type Caso } from './casos';

type Coleccion = 'notas' | 'lab' | 'casos';

export interface Lectura {
  tipo: 'Nota' | 'Lab' | 'Caso';
  titulo: string;
  descripcion: string;
  href: string;
}

type Refs = Caso['data']['relacionados'];

const clave = (c: Coleccion, s: string) => `${c}/${s}`;
const refsDe = (r: Refs) => [
  ...r.notas.map((x) => clave('notas', x.slug)),
  ...r.lab.map((x) => clave('lab', x.slug)),
  ...r.casos.map((x) => clave('casos', x.id)),
];

// En un caso, las conexiones por eje cuentan como relaciones declaradas.
const refsDelCaso = (caso: Caso): Refs => ({
  notas: [...caso.data.relacionados.notas, ...caso.data.conexiones.flatMap((c) => c.notas)],
  lab: [...caso.data.relacionados.lab, ...caso.data.conexiones.flatMap((c) => c.lab)],
  casos: [...caso.data.relacionados.casos, ...caso.data.conexiones.flatMap((c) => c.casos)],
});

async function getEntradas() {
  const [notas, lab, casos] = await Promise.all([
    getCollection('notas'),
    getCollection('lab'),
    getCollection('casos', casoVisible),
  ]);

  return [
    ...notas.map((e) => ({
      coleccion: 'notas' as const,
      slug: e.slug,
      relacionados: e.data.relacionados,
      lectura: { tipo: 'Nota', titulo: e.data.title, descripcion: e.data.description, href: `/notas/${e.slug}` } as Lectura,
    })),
    ...lab.map((e) => ({
      coleccion: 'lab' as const,
      slug: e.slug,
      relacionados: e.data.relacionados,
      lectura: { tipo: 'Lab', titulo: e.data.title, descripcion: e.data.description, href: `/lab/${e.slug}` } as Lectura,
    })),
    ...casos.map((e) => ({
      coleccion: 'casos' as const,
      slug: e.id,
      relacionados: refsDelCaso(e),
      lectura: {
        tipo: 'Caso',
        titulo: `${e.data.title} — ${e.data.subtitulo}`,
        descripcion: e.data.description,
        href: `/lab/casos/${e.id}`,
      } as Lectura,
    })),
  ];
}

// Junta las lecturas relacionadas con una entrada en los dos sentidos: las que
// ella declara en `relacionados` y las que la declaran a ella. Así cada
// relación se escribe una sola vez y ninguna página copia contenido de otra.
export async function getRelacionados(coleccion: Coleccion, slug: string): Promise<Lectura[]> {
  const entradas = await getEntradas();
  const propia = clave(coleccion, slug);
  const actual = entradas.find((e) => clave(e.coleccion, e.slug) === propia);
  const declaradas = new Set(actual ? refsDe(actual.relacionados) : []);

  return entradas
    .filter((e) => {
      const k = clave(e.coleccion, e.slug);
      return k !== propia && (declaradas.has(k) || refsDe(e.relacionados).includes(propia));
    })
    .map((e) => e.lectura);
}

// Las conexiones de un caso, eje por eje, con sus lecturas. Los ejes que
// todavía no tienen contenidos enlazados quedan afuera.
export async function getConexiones(caso: Caso) {
  const entradas = await getEntradas();
  const porClave = new Map(entradas.map((e) => [clave(e.coleccion, e.slug), e.lectura]));
  return caso.data.conexiones
    .map((c) => ({
      titulo: c.eje,
      bajada: c.descripcion,
      lecturas: refsDe(c).flatMap((k) => porClave.get(k) ?? []),
    }))
    .filter((g) => g.lecturas.length > 0);
}
