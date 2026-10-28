---
title: "Debido proceso tecnológico: cuando el código decide sin escucharnos"
description: "Síntesis en castellano del artículo de Danielle Keats Citron (2008), una de las bases del análisis de la exclusión automatizada."
pubDate: 2026-10-27
tags: ["Ética", "Algoritmos", "Decisiones automatizadas", "Lecturas"]
heroImage: "/images/notas/debido-proceso-tecnologico-hero.svg"
---

Una red social borra una foto porque *podría* incluir un símbolo prohibido. Un sistema de selección descarta un CV porque los títulos tienen letras espaciadas. En los dos casos decide una máquina, nadie explica nada y la carga de demostrar que no hubo falta queda del lado de quien fue descartado.

Buscando quién había pensado esto con rigor, llegué a un artículo de 2008 que sigue siendo referencia: *Technological Due Process*, de la jurista estadounidense **Danielle Keats Citron**. Analiza sistemas del Estado, no plataformas privadas, pero el mecanismo que describe es exactamente el mismo.

## La tesis en una línea

Los sistemas automatizados toman decisiones que afectan derechos sin respetar las dos garantías básicas del debido proceso: **saber de qué se nos acusa y poder ser oídos**. Hace falta reconstruir esas garantías para la era del software.

## Cinco ideas centrales

### 1. El código también legisla

Traducir una norma a código nunca es neutral. Los lenguajes de programación tienen menos matices que el lenguaje humano, y quien programa interpreta la norma mientras la escribe. Además, el código prefiere las preguntas de sí o no. Una regla con seis excepciones encadenadas tiende a quedar reducida a la regla general.

El caso que Citron documenta es el sistema de beneficios sociales de Colorado (CBMS). Entre 2004 y 2007 se le incorporaron más de novecientas reglas incorrectas: negó cobertura médica a pacientes con cáncer de mama aplicando límites de ingreso que ninguna ley establecía, y rechazó a embarazadas en contra de la normativa federal. Nadie votó esas reglas. Las creó, sin proponérselo, la traducción a código.

Hay una forma todavía más silenciosa de legislar: lo que el sistema **no ofrece**. Un formulario web de Florida no incluía la opción para que un familiar pidiera asistencia en nombre de un niño. La ley lo permitía; el menú desplegable, no. Y como el formulario era la única vía, el menú ganó.

### 2. Sin aviso, no hay defensa

Para defenderse, primero hay que saber qué se decidió y por qué. Muchos sistemas cortaban beneficios sin aviso previo, o enviaban notificaciones que solo decían "elegibilidad denegada". Una familia de Colorado recibió setenta y una notificaciones contradictorias en seis meses. En la lista de exclusión aérea de EE. UU., las personas ni siquiera podían saber si estaban incluidas.

Una defensa sin conocer los fundamentos de la acusación no es una defensa. Es, como cita la autora de un fallo judicial, una escena de Kafka.

### 3. El "humano en el circuito" no alcanza

La respuesta habitual es que una persona revisa lo que propone la máquina. Citron muestra que en la práctica eso protege poco. Las personas tienden a confiar en la computadora incluso cuando sospechan que falla. A esto se lo llama **sesgo de automatización**: la sugerencia del sistema se convierte de hecho en la decisión final.

En el caso de la lista de exclusión aérea, más de la mitad de las coincidencias enviadas a revisión entre 2003 y 2006 eran identificaciones erróneas, muchas por simple similitud de nombres. Hubo un niño de cuatro años al que no dejaron abordar. Y ese sesgo no descalifica a nadie: un revisor puede ser perfectamente imparcial entre personas y, al mismo tiempo, parcial a favor de la máquina.

### 4. Sin rastro, no hay revisión

Varios de estos sistemas no guardaban registro de auditoría: qué datos se usaron y qué regla se aplicó en cada caso. Según la autora, los diseñadores podían haberlo incluido y eligieron no hacerlo. Sin ese rastro, ni el afectado ni el propio organismo pueden saber si el error estuvo en los datos, en la regla o en ambos. Y si no se puede ubicar el error, no se puede corregir.

### 5. El costo está mal calculado

El análisis jurídico clásico pondera el costo de una garantía adicional contra el beneficio de evitar errores en *un* caso. Con sistemas automatizados la cuenta cambia: entender la lógica del sistema tiene un costo alto, pero se paga una sola vez, mientras que el beneficio de corregirla se multiplica en miles de decisiones. Medido caso por caso, auditar el algoritmo siempre parece caro. Medido en conjunto, es barato.

## Lo que propone

- **Decidir qué no automatizar.** Lo que exige juicio humano y ponderación de circunstancias no debería quedar en manos de reglas rígidas.
- **Avisos con fundamentos reales**, generados a partir del registro de cada decisión.
- **Registros de auditoría obligatorios**, que no se puedan alterar.
- **Formar a quienes revisan** para que reconozcan el sesgo de automatización, y exigirles que expliquen por qué se apoyan en la decisión del sistema.
- **Transparencia y pruebas**: código abierto al escrutinio público, sistemas testeados antes de implementarse y participación ciudadana en su diseño.

## Por qué sigue vigente

El artículo es de 2008: antes de las redes sociales masivas, de los filtros automáticos de CV y de la IA generativa. Y sin embargo describe con precisión lo que hoy vemos a diario: una sanción que se aplica primero y se revisa después, una explicación genérica en lugar de un fundamento, y la presunción de que la máquina tiene razón.

La pregunta de fondo que deja no es técnica: **¿quién paga el costo de que el sistema se equivoque?** Mientras la respuesta sea "la persona descartada", el sistema no tiene ningún incentivo para equivocarse menos.

---

## Fuente

Citron, D. K. (2008). Technological Due Process. *Washington University Law Review*, 85(6), 1249–1313.

- Acceso abierto en el repositorio de la revista: [openscholarship.wustl.edu/law_lawreview/vol85/iss6](https://openscholarship.wustl.edu/law_lawreview/vol85/iss6/)
- Texto completo (PDF): [journals.library.wustl.edu](https://journals.library.wustl.edu/lawreview/article/6697/galley/23530/view/)
- También en SSRN: [ssrn.com/abstract=1012360](https://ssrn.com/abstract=1012360)

*Síntesis y traducción propias. El artículo original está en inglés.*
