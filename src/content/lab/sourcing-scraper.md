---
title: "SourcingScraper: un radar de demanda para Mercado Libre"
description: "Un experimento de extracción de datos que recorre Mercado Libre sin que nadie elija un producto, confirma qué se vende de verdad y guarda un histórico que no se pisa."
estado: "en-marcha"
fecha: 2026-10-11
tags: ["Extracción de datos", "Automatización", "SQLite"]
heroImage: "/images/lab/sourcing-scraper-hero.svg"
stack: ["Python", "Playwright", "BeautifulSoup", "SQLite", "sentence-transformers", "pytest"]
repoPrivado: true
stats:
  - valor: "470"
    etiqueta: "tarjetas de producto extraídas en una corrida (466 productos únicos)"
  - valor: "220"
    etiqueta: "con la insignia «Más vendido» en el momento de la detección"
  - valor: "55 / 55"
    etiqueta: "fichas abiertas que confirmaron demanda real"
  - valor: "0"
    etiqueta: "bloqueos, CAPTCHA o errores durante la corrida completa"
pasos:
  - titulo: "Descubrir"
    texto: "Recorre las vidrieras de 13 categorías de Mercado Libre. Nadie elige un producto ni una palabra de búsqueda."
  - titulo: "Confirmar"
    texto: "Abre la ficha de cada candidato con señal fuerte y verifica las unidades vendidas contra un umbral."
  - titulo: "Recordar"
    texto: "Guarda cada aparición y cada observación en una base SQLite donde nada se pisa."
  - titulo: "Puntuar"
    texto: "Combina demanda real y aptitud comercial en un puntaje estable entre corridas."
---

## Qué quería resolver

Encontrar qué productos tienen demanda real suele empezar por una persona que elige qué buscar. Eso condiciona el resultado desde el primer paso: se encuentra lo que ya se estaba mirando.

La pregunta de este experimento fue otra: ¿se puede entrar a Mercado Libre sin elegir nada, descubrir lo que ya se vende mucho y guardar la evidencia de una forma que sirva dentro de un mes? El resultado es un radar que recorre categorías, confirma la demanda en cada ficha y deja un histórico.

## Medir antes de decidir

Un sistema que elige candidatos tiene la tentación de agruparlos, para no quedarse con diez variantes del mismo producto. Probé tres maneras de hacerlo, cada una contra los 59 candidatos reales que había confirmado hasta ese momento. Ninguna sobrevivió.

- **Un diccionario de categorías por nombre** reconoció una categoría en 10 de los 59 nombres. Con ese cubrimiento, agrupar era casi no agrupar.
- **La categoría de donde se descubrió el producto** resultó ser una etiqueta de dónde apareció, no de qué es. Una yogurtera eléctrica figuraba en Electrodomésticos y también en Cámaras.
- **La similitud entre títulos con embeddings** parecía lo más sofisticado y fue lo más engañoso. Dos productos sin relación, unas tijeras de poda y una estantería, puntuaron 0,936. Varios pares de cepillos que sí eran parecidos puntuaron entre 0,902 y 0,924. No existía un umbral seguro.

> Una señal tiene que ser cierta para ser explicable.

En lugar de insistir con un cuarto intento, eliminé el agrupamiento. El ranking quedó en una sola señal que se puede explicar con una frase: las unidades vendidas confirmadas en la ficha.

## Lo que el navegador enseñó

Mercado Libre no entrega siempre el mismo HTML. Tres cosas que no estaban en ninguna documentación y aparecieron en la primera corrida real:

- **El contenedor llega vacío.** Las vidrieras de categoría vienen primero como un esqueleto y los productos se cargan después con JavaScript. Esperar a que exista el contenedor daba un falso «ya cargó». Hay que esperar a que aparezca el primer producto.
- **Hay dos estructuras de carrusel.** En cuatro categorías los productos viven en un componente distinto del que se había observado primero. La corrida inicial devolvió cero tarjetas para seis categorías; en esas cuatro la causa no era el tiempo de carga sino el contenedor.
- **Dos categorías no tienen vidriera de productos.** Mascotas y Hogar y Muebles muestran marcas y navegación, nada más. No es un error para corregir: ese contenido no existe.

## Puntuar sin excluir

La demanda sola ordena mal. Un producto con 250.000 unidades vendidas aplasta a cualquier otra señal si se la suma tal cual. Para que eso no pase, la demanda se comprime con logaritmo y se lleva a una escala fija, anclada al umbral de confirmación y a un techo de un millón. No depende de qué otros productos haya en la base, así que el mismo producto recibe el mismo puntaje en cualquier corrida.

La segunda capa es una aptitud comercial: puntúa si un producto es chico o liviano y resta puntos a categorías con fricción real, como la cosmética o las baterías. **Puntúa y no excluye**: ninguna regla descarta un producto por sí sola. Con ese esquema, el producto de 250.000 unidades pasó del primer puesto al quinto.

## Reglas que me puse

- **Un bloqueo no se esquiva.** Si aparece un CAPTCHA, el sistema pausa y espera a una persona. Nunca intenta resolverlo.
- **Ritmo humano.** Pausas aleatorias entre una página y la siguiente.
- **Nada de sesiones en el repositorio.** Los perfiles del navegador y las bases de datos no se versionan.
- **Tests con HTML real.** 302 tests, con páginas capturadas de verdad como fixtures donde importa, no simulaciones.

## Dónde están los límites

Una pausa humana no funciona si el sistema corre sin una terminal interactiva: en ese caso, el bloqueo corta el candidato en lugar de esperar. Las vidrieras son una selección curada por la plataforma, no el catálogo completo, y pueden cambiar según la sesión. La lista de categorías es fija. Y el lado de Alibaba, el matching de productos y el filtro económico, está implementado pero en pausa mientras el foco sigue en la demanda.
