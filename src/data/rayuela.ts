// Rayuela de datos de WildSoft Lab: las cinco etapas de la arquitectura y
// el recorrido de cada herramienta por ellas.
//
// Para sumar una herramienta nueva alcanza con agregar un objeto a
// `proyectos`: el componente arma el selector, ilumina las casillas, anima
// el recorrido y suma el proyecto a la vista "Por etapa" sin tocar nada más.
//
// - `recorrido` va en el orden en que la herramienta pasa por las etapas.
//   No tiene que ser lineal ni completo: solo se listan las etapas que la
//   herramienta realmente usa.
// - `experimento` es el slug de su ficha en src/content/lab/. Si se indica,
//   el build verifica que exista. Sin ficha, el panel muestra "Ficha en
//   preparación". `enlace` sirve para una ficha que vive fuera del Lab.

export type EtapaId =
  | 'extraccion'
  | 'normalizacion'
  | 'almacenamiento'
  | 'analisis'
  | 'automatizacion';

export interface Etapa {
  id: EtapaId;
  numero: number;
  nombre: string;
  // Opcional: el nombre con un guion suave (­) donde puede cortarse si
  // la casilla es angosta (las casillas de a par en el celular).
  corte?: string;
  accion: string;
  descripcion: string;
}

export interface PasoRecorrido {
  etapa: EtapaId;
  texto: string;
}

export interface ProyectoRayuela {
  id: string;
  nombre: string;
  subtitulo?: string;
  resumen: string;
  experimento?: string;
  enlace?: { href: string; texto: string };
  recorrido: PasoRecorrido[];
}

export const etapas: Etapa[] = [
  {
    id: 'extraccion',
    numero: 1,
    nombre: 'Extracción',
    accion: 'Obtener datos',
    descripcion:
      'Entrar a la fuente y traer los datos tal como están publicados: listados, vidrieras y fichas.',
  },
  {
    id: 'normalizacion',
    numero: 2,
    nombre: 'Normalización',
    accion: 'Limpiar y transformar',
    descripcion:
      'Convertir el texto crudo en campos comparables: montos, unidades, categorías y respuestas de sí o no.',
  },
  {
    id: 'almacenamiento',
    numero: 3,
    nombre: 'Almacenamiento',
    corte: 'Almacena­miento',
    accion: 'Guardar información',
    descripcion:
      'Conservar lo obtenido de forma que se pueda volver a consultar y comparar entre una corrida y la siguiente.',
  },
  {
    id: 'analisis',
    numero: 4,
    nombre: 'Análisis',
    accion: 'Encontrar patrones',
    descripcion:
      'Ordenar, puntuar y comparar para que los datos respondan una pregunta concreta.',
  },
  {
    id: 'automatizacion',
    numero: 5,
    nombre: 'Automatización',
    accion: 'Ejecutar y monitorear procesos',
    descripcion:
      'Que el proceso corra de punta a punta y se detenga o avise cuando algo no sale como se esperaba.',
  },
];

export const proyectos: ProyectoRayuela[] = [
  {
    id: 'jsoneta',
    nombre: 'La JSONeta',
    subtitulo: 'Seguimiento de ofertas de Mercor',
    resumen:
      'Reúne las oportunidades publicadas en Mercor en un solo tablero para filtrarlas y llevar el seguimiento de cada postulación.',
    recorrido: [
      {
        etapa: 'automatizacion',
        texto:
          'Un solo archivo de arranque ejecuta la actualización completa. Si el recorrido no termina de forma segura, no reemplaza la base principal.',
      },
      {
        etapa: 'extraccion',
        texto:
          'Con Playwright recorre página por página el listado de oportunidades hasta el final de la paginación y después abre el detalle de cada oferta.',
      },
      {
        etapa: 'normalizacion',
        texto:
          'Con expresiones regulares convierte el texto en campos: rango y unidad de pago, inglés requerido, entrevista, restricción de ubicación y años de experiencia.',
      },
      {
        etapa: 'almacenamiento',
        texto:
          'Fusiona cada corrida con la base anterior en un JSON con escritura atómica y copia de respaldo, y solo enriquece las ofertas nuevas. El seguimiento de cada postulación queda guardado en el navegador.',
      },
    ],
  },
  {
    id: 'mercado-libre',
    nombre: 'Extractor de Mercado Libre',
    subtitulo: 'SourcingScraper',
    resumen:
      'Un radar de demanda que recorre Mercado Libre sin que nadie elija un producto y guarda un histórico que no se pisa.',
    experimento: 'sourcing-scraper',
    recorrido: [
      {
        etapa: 'extraccion',
        texto:
          'Recorre con Playwright las vidrieras de 13 categorías y abre la ficha de cada candidato con señal fuerte de demanda.',
      },
      {
        etapa: 'normalizacion',
        texto:
          'Interpreta las dos estructuras de carrusel de las vidrieras y extrae de cada ficha las unidades vendidas, el precio y la descripción.',
      },
      {
        etapa: 'almacenamiento',
        texto:
          'Guarda cada aparición y cada observación en una base SQLite histórica donde nada se pisa.',
      },
      {
        etapa: 'analisis',
        texto:
          'Combina la demanda confirmada, comprimida con logaritmo, con una aptitud comercial en un puntaje estable entre corridas.',
      },
      {
        etapa: 'automatizacion',
        texto:
          'Una corrida recorre las categorías sola, con pausas de ritmo humano. Si aparece un bloqueo o un CAPTCHA, se detiene y espera a una persona.',
      },
    ],
  },
];
