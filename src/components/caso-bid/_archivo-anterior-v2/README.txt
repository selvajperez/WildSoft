Version anterior del caso de estudio (9 escenas), la que reemplazo a la
version editorial original (ver ../_archivo-anterior/).

Reemplazada por la version actual (ver src/components/caso-bid/) que sigue
el mockup aprobado de una sola pieza: encabezado con datos del programa,
tres pasos (Comprender / Conectar / Construir), rol y responsabilidades,
metodologia documentada en 8 etapas, fuentes documentadas y resultado.
Los datos factuales (Decreto 691/2016, PMGM - Prestamo BID N. 1855/OC-AR,
cronograma, gestores documentales evaluados, arquitectura en 3 capas, etc.)
se mantienen identicos a esta version anterior; solo cambia la estructura
visual y de navegacion (se elimina el carrusel de wireframes y los
lightbox de documentos, no contemplados en el nuevo mockup).

Lightbox.astro NO se archivo aqui: sigue en uso por
src/pages/proyectos/purissimus.astro, ajeno a este rediseno.

Para restaurar esta version: mover estos archivos .astro de vuelta a
src/components/caso-bid/ y actualizar los imports en
src/pages/proyectos/redeterminacion-precios.astro.
