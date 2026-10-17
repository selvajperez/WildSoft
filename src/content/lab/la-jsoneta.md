---
title: "La JSONeta: todas las oportunidades de Mercor en un solo tablero"
description: "Un experimento que recorre el listado de oportunidades de Mercor, convierte cada oferta en datos filtrables y permite llevar el seguimiento de cada postulación."
estado: "en-marcha"
fecha: 2026-10-17
tags: ["Extracción de datos", "Automatización", "Seguimiento"]
heroImage: "/images/lab/la-jsoneta-hero.svg"
stack: ["JavaScript", "Node.js", "Playwright", "JSON", "Vercel"]
app: "https://la-jsoneta.vercel.app/"
statsTitulo: "La base al 9 de octubre de 2026, en números"
stats:
  - valor: "343"
    etiqueta: "ofertas registradas entre el 26/09 y el 09/10/2026"
  - valor: "220"
    etiqueta: "publicadas en la última corrida de esa copia"
  - valor: "123"
    etiqueta: "que dejaron de publicarse: quedaron marcadas, no borradas"
  - valor: "0"
    etiqueta: "ofertas con error de enriquecimiento en esa copia"
pasos:
  - titulo: "Recorrer"
    texto: "Entra al listado de oportunidades y avanza página por página hasta que no hay más."
  - titulo: "Enriquecer"
    texto: "Abre el detalle de cada oferta nueva y extrae requisitos, pago, idioma, ubicación y etapas de postulación."
  - titulo: "Fusionar"
    texto: "Une la corrida nueva con la base anterior sin perder historia."
  - titulo: "Seguir"
    texto: "Un tablero para filtrar las ofertas y anotar el estado de cada postulación."
---

## Qué quería resolver

La JSONeta nació para identificar oportunidades laborales compatibles sin tener que revisar cientos de fichas de forma individual.

Mercor publica sus oportunidades en un listado paginado, y los detalles que deciden si una oferta conviene viven dentro de cada ficha: el pago, el idioma, la ubicación, si hay una entrevista. La JSONeta junta todo en un solo lugar: cada oferta pasa a ser un registro con campos que se pueden filtrar, y cada postulación tiene su propio seguimiento.

## Cómo funciona

**Recorrido completo o nada.** Con Playwright, el sistema avanza por el listado hasta que el botón «Next» desaparece o se deshabilita, con un límite de seguridad de 100 páginas. Si el recorrido no termina de forma segura, **no reemplaza la base principal**: deja un archivo aparte, solo para diagnóstico. Una corrida a medias nunca pisa datos buenos.

**Del texto a los campos.** Cada ficha llega como texto libre. Con expresiones regulares se extraen el rango y la unidad de pago, los años de experiencia, las horas semanales, la restricción de ubicación, los requisitos de idioma, si se pide inglés oral y si la postulación incluye una entrevista. Lo que no se puede leer con certeza queda vacío, sin adivinar.

**Una historia que no se borra.** Cada corrida se compara con la anterior usando el identificador de Mercor de cada oferta. Las que siguen publicadas se actualizan; las que desaparecieron se marcan como inactivas y conservan la fecha en que dejaron de verse. La escritura es atómica y siempre queda una copia de respaldo.

**Solo lo nuevo.** El enriquecimiento es incremental: abre únicamente las fichas que faltan o que dieron error, sin volver a las que ya están procesadas.

## El tablero

La versión web permite buscar por texto y filtrar por pago mínimo, restricción de ubicación, inglés, entrevista, experiencia máxima y estado de seguimiento. Cada oferta tiene su ficha de seguimiento: estado (sin revisar, revisar, aplicar, aplicado, no seleccionada, descartado), fecha de postulación, próximo paso, fecha de seguimiento y notas.

## Lo que cambió en el camino

- **El final de la paginación.** La primera versión no sabía con certeza cuándo terminaba el listado. Se agregó una lógica que distingue un final normal de una página incompleta.
- **Enriquecimiento incremental.** Al principio se volvía a procesar todo en cada corrida; después pasó a procesar solo lo que faltaba.
- **Windows.** La versión local 1.1 corrigió un error por el que el servidor no encontraba sus propios archivos en Windows.
- **Identidad por ID.** Las ofertas pasaron a identificarse por su ID de Mercor, que es el mismo en las distintas URLs de la plataforma. Además se sumó el estado «no seleccionada».

## Dónde están los límites

El recorrido usa un perfil propio del navegador y corre con la ventana visible, así que hoy necesita una computadora y una persona que lo ejecute. En la versión web, el seguimiento queda guardado en el navegador: no se sincroniza entre dispositivos. Y los datos publicados son una copia fechada, no una lectura en vivo.

## Qué sigue

Estamos trabajando en la persistencia de datos y en la autenticación con Supabase, para que el seguimiento deje de depender de un solo navegador.
