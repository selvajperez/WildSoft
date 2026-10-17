---
title: "Analizador exploratorio de datos: de Kaggle a Power BI"
description: "Un notebook de Python que prepara un dataset, busca relaciones entre sus variables, las convierte en candidatos de hallazgo con evidencia y evalúa si el dataset merece un caso de Power BI."
estado: "en-marcha"
fecha: 2026-10-17
tags: ["Análisis exploratorio", "Python", "Power BI"]
heroImage: "/images/lab/analizador-exploratorio-hero.svg"
stack: ["Python", "pandas", "Google Colab", "Power BI"]
statsTitulo: "Una corrida de prueba con el dataset Adidas US Sales, en números"
stats:
  - valor: "9.637"
    etiqueta: "filas y 13 columnas revisadas, sin nulos ni duplicados"
  - valor: "14"
    etiqueta: "relaciones entre variables que superaron los umbrales"
  - valor: "4"
    etiqueta: "candidatos de hallazgo de nivel medio; los otros 10, exploratorios"
  - valor: "9 / 10"
    etiqueta: "Portfolio Score: «muy apto para portfolio»"
pasos:
  - titulo: "Proponer"
    texto: "Cada sábado, una tarea semanal sugiere tres datasets de Kaggle. Una persona elige uno y lo descarga."
  - titulo: "Preparar"
    texto: "Estandariza columnas, fechas y categorías, y arma un perfil de calidad del dataset."
  - titulo: "Explorar"
    texto: "Mide relaciones entre variables y las convierte en candidatos de hallazgo con su evidencia."
  - titulo: "Evaluar"
    texto: "Ordena los hallazgos y calcula un Portfolio Score para decidir si el dataset merece un caso."
---

## Qué quería resolver

Antes de construir un informe en Power BI hay dos preguntas que conviene responder rápido: ¿este dataset sirve para un caso de análisis?, y si sirve, ¿por dónde empezar a mirar? Contestarlas a mano, dataset por dataset, lleva horas de exploración que muchas veces terminan en «no daba».

El analizador es un notebook de Python que hace esa primera lectura siempre de la misma manera. No reemplaza el análisis: lo ordena, y deja preguntas concretas para trabajar después.

## Tres partes, tres responsables

El flujo completo tiene tres piezas distintas, y conviene no confundirlas:

- **La búsqueda semanal.** Una tarea programada propone tres datasets de Kaggle cada sábado. Solo propone: elegir cuál usar y descargarlo es una decisión manual.
- **El analizador de Python.** Un notebook en Google Colab que se ejecuta celda por celda sobre el archivo elegido. La ruta del archivo se indica a mano.
- **El informe.** Con los resultados del analizador, el trabajo sigue en Power BI: los KPI, el modelo de datos y las visualizaciones se construyen ahí, con Claude como apoyo en la construcción del informe y las decisiones a cargo de una persona.

## Cómo funciona el analizador

**Preparar sin adivinar.** Estandariza los nombres de las columnas, detecta las columnas de fecha (cuando al menos el 70 % de los valores se pueden leer como fecha) y unifica las categorías en minúsculas. Después arma un perfil de calidad con nulos, duplicados y valores únicos, y asigna a cada columna un rol probable: identificador, fecha, categórica, numérica o texto. Los nulos y los duplicados se informan; no se borran ni se completan.

**Buscar relaciones con medidas comparables.** Para una variable numérica frente a una categórica usa eta cuadrado y conserva las relaciones desde 0,05. Entre dos variables numéricas usa la correlación y conserva las que llegan a 0,30 en valor absoluto. Antes, puntúa el potencial de cada variable para métricas, segmentaciones o análisis temporal.

**Candidatos, no conclusiones.** Cada relación se redacta en lenguaje natural como un candidato de hallazgo y se acompaña con su evidencia: los promedios por grupo o el valor de la correlación. Después se ordenan por puntaje, se descartan los pares redundantes (una variable y su versión «_label») y se clasifican como hallazgo fuerte, medio o exploratorio. Se puede indicar una variable objetivo para darle más peso a lo que la involucra.

> Una correlación es una pregunta bien hecha, no una respuesta.

**Evaluar el dataset.** El último paso es un Portfolio Score sobre 10: suma puntos por volumen de registros, variedad de columnas, métricas, variables para segmentar, fechas y hallazgos con potencial. El resultado va de «poco apto» a «muy apto para portfolio».

Todo es descriptivo y exploratorio. El analizador no entrena ni aplica modelos predictivos.

## Un caso de aplicación: Estambul

El análisis del mercado inmobiliario de Estambul siguió este flujo: un dataset de casi 25.000 propiedades que terminó en una herramienta de Market Intelligence en Power BI. Los números de esta página corresponden a la corrida de prueba con Adidas US Sales, no a Estambul. El caso completo está en [Real Estate Market Intelligence — Istanbul](/proyectos/istanbul-real-estate-market-intelligence).

## También para estudiar

El analizador se probó con distintos datasets y también sirvió como herramienta de estudio para Bases de Datos I y Análisis de Datos I, en la Universidad de la Ciudad: cada paso del notebook es un concepto que se puede ver funcionando sobre datos reales.

## Dónde están los límites

- **No corre solo.** La búsqueda semanal es automática; la elección, la descarga y la ejecución del notebook no.
- **Sin variable objetivo, nada llega a «fuerte».** El puntaje máximo de un hallazgo sin variable objetivo es 5 y el nivel «fuerte» empieza en 6. Por eso, en la práctica, el Portfolio Score de un dataset sin objetivo llega como mucho a 9.
- **Un identificador que se repite puede pasar por métrica.** Las columnas de ID se reconocen por su nombre y por ser casi únicas. Un código que se repite mucho, como el de un minorista, queda entre las variables numéricas y puede generar relaciones sin sentido. Por eso cada candidato se revisa antes de usarlo.
- **Las secciones de ETL y storytelling son el trabajo que sigue.** En el notebook son títulos sin código: esa parte se resuelve en Power BI.
