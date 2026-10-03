# Plan de mejora diaria

El objetivo es que el agente ayude a terminar trabajo útil: encontrar la información correcta, comprobar el estado real, preparar cambios pequeños y conservar las lecciones que funcionaron.

El [catálogo de tareas](../backlog/tasks.json) contiene **16 desarrollos previstos**. Todos tienen estado `planned`: disponer del backlog o de una issue no significa que la capacidad esté implementada, conectada o programada. Los comandos y funciones disponibles se describen en el [README](../README.md). El catálogo amplía progresivamente esa base.

## Un ciclo corto cada día

1. **Comprobar las fuentes.** Leer únicamente ámbitos autorizados y registrar versión, antigüedad y cobertura. Si no hay datos recientes, indicar qué no se pudo comprobar.
2. **Preparar hasta tres resultados.** Elegir próximas acciones por impacto, esfuerzo y dependencias. Cada una debe decir qué entregar, cómo comprobarlo y cuál es el siguiente paso.
3. **Ejecutar una mejora acotada.** Trabajar sobre un candidato aislado, conservar la base y comprobar el criterio de aceptación. Detenerse cuando el presupuesto se agota o la evidencia no permite seguir.
4. **Revisar y registrar.** Conservar el resultado, las pruebas, los límites y la decisión. Una propuesta rechazada también aporta información sobre lo que no funciona.

Los tres resultados diarios pueden cubrir estas necesidades, si existe evidencia suficiente:

| Foco | Pregunta que resuelve | Salida esperada |
|---|---|---|
| Entrega | ¿Qué puedo terminar y comprobar hoy? | Una acción con criterio de aceptación y dependencias |
| Fiabilidad | ¿Qué fallo o incertidumbre bloquea el trabajo? | Una reproducción, diagnóstico o prueba concreta |
| Conocimiento | ¿Qué información evitará repetir trabajo? | Una fuente revisada, guía corregida o lección comprobada |

No es obligatorio llenar los tres espacios. Una lista vacía y bien justificada es preferible a inventar urgencias o compromisos.

## Orden de implementación

| Etapa | Tareas | Condición para avanzar |
|---|---|---|
| Base de confianza | RA-005, RA-001, RA-002, RA-003 | Separación probada; fuentes fechadas; candidatos trazables; estados revalidados |
| Planificación y seguimiento | RA-004, RA-015, RA-016 | Prioridades explicables; presupuesto y registro de resultados verificables |
| Desarrollo y documentación | RA-006, RA-007, RA-008 | Cambios aislados; pruebas reproducibles; documentación e impacto con evidencia |
| Flujos y entrega | RA-011, RA-012, RA-013 | Replay sin efectos externos; contratos comprobados; demo reproducible |
| Curación y reutilización | RA-009, RA-010, RA-014 | Decisiones de clasificación reversibles; extracción útil; procedimientos probados en casos nuevos |

Cada tarea incluye objetivo, pasos, criterios de aceptación, métrica, dependencias y límite de automatización. Las dependencias describen capacidades necesarias; al implementar, se debe comprobar cuáles están disponibles y cuáles siguen pendientes.

## Cómo usar el conocimiento privado

El contenido histórico puede contener requisitos antiguos, propuestas, borradores, decisiones sustituidas y afirmaciones de ejecución sin pruebas. El agente debe conservar su naturaleza y fecha.

- Un **candidato** es una propuesta pendiente de revisión.
- Una **tarea aceptada** expresa una decisión vigente y conserva su evidencia.
- Un **resultado comprobado** cumple criterios de aceptación con pruebas adecuadas.
- Un **estado desconocido** identifica lo que no pudo verificarse.

Un mensaje que dice «terminado» no basta para cerrar una tarea. El agente debe contrastar la revisión, el archivo, la ejecución o la prueba correspondiente. Del mismo modo, una petición histórica no demuestra que la función siga pendiente.

Las referencias privadas, informes operativos y decisiones humanas permanecen en un destino privado autorizado. El repositorio público contiene código, esquemas, métodos genéricos y ejemplos sintéticos. Una exportación pública requiere un conjunto explícito de campos permitidos y una comprobación de separación entre proyectos.

## Revisión semanal

Revisar qué entregas se aceptaron, qué errores se repitieron, qué regresiones aparecieron y cuánto trabajo requirió corregirlas. Medir tiempo o coste solo cuando existe una observación fiable; mostrar `desconocido` para el resto.

Elegir una mejora de proceso por semana: una prueba que faltaba, una guía confusa, una fuente obsoleta o un procedimiento repetitivo. Comparar la situación anterior con el candidato usando un presupuesto equivalente y casos reservados. Promover únicamente cambios que cumplan los criterios obligatorios y mantengan la calidad fuera del ejemplo original.

El agente no debe ampliar su propio presupuesto, modificar permisos ni alterar evaluadores para conseguir una aprobación. La mejora de instrucciones y procedimientos se prepara como una propuesta versionada y revisable.

## Qué significa automatizar este plan

La cadencia de una tarea expresa cuándo conviene ejecutarla; **no activa por sí sola un horario**. Un job debe indicar fuentes, destino privado, presupuesto y comportamiento ante fallos. Su registro distingue programado, iniciado, finalizado y resultado aceptado.

La lectura y preparación de propuestas pueden automatizarse dentro del alcance autorizado. Cambiar compromisos, activar workflows, escribir datos operativos, publicar, desplegar o contactar personas son acciones separadas, sujetas a la autorización concreta del trabajo. Cada ejecución informa qué pudo comprobar y qué quedó pendiente.
