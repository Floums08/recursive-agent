# Playbook: documentación técnica y funcional

Este documento se usa como guía del operador/proveedor, no se instala como skill personal. Dominio de propuesta: docs.

## Objetivo

Conseguir que otra persona complete una tarea o entienda una decisión sin depender del autor. La longitud, cantidad de títulos o tono convincente no bastan para medir calidad.

## Entrada mínima

- Audiencia: usuario de negocio, administrador, desarrollador o soporte.
- Fuente autoritativa y versión: código, esquema, decisión aprobada o contrato API.
- Tarea que la persona debe poder realizar.
- Errores frecuentes, prerrequisitos, permisos y resultado final esperado.

## Secuencia

1. Identifica qué afirmaciones están respaldadas por fuentes y cuáles faltan. Marca las desconocidas como pendientes de verificación.
2. Describe primero el resultado esperado y las condiciones para empezar.
3. Escribe pasos numerados, con una acción por paso y el punto exacto de ejecución: herramienta, archivo, endpoint o menú si está verificado.
4. Incluye un ejemplo coherente y un método para comprobar el resultado. No uses credenciales reales en ejemplos.
5. Explica el error más probable, cómo reconocerlo y cómo recuperar. Distingue fallo de permisos, datos e infraestructura.
6. Devuelve un único cambio limitado en formato JSON, con domain: docs.
7. Pide a una persona que no conozca la solución que siga la guía. Registra dónde se atasca y el tiempo que tarda.

## Contrato de calidad

| Criterio | Cómo verificarlo |
| --- | --- |
| Exactitud | Cada afirmación relevante coincide con la fuente y su versión. |
| Ejecutabilidad | Los pasos o comandos completan la tarea en un entorno de prueba. |
| Trazabilidad | Enlaces internos válidos; referencias al componente/decisión relevante. |
| Cobertura | Prerrequisitos, permisos, pasos, comprobación y recuperación. |
| Claridad | Otra persona encuentra y completa el procedimiento sin explicación oral. |
| Consistencia | Nombres de campos/estados coherentes entre documentación y aplicación. |

Un verificador de encabezados sirve como control estructural, no como prueba de exactitud. Cuando una fuente no está disponible, no sustituyas el dato por una afirmación plausible.

## Ejemplo de mejora

Problema: «La guía dice ejecutar la sincronización, pero no explica dónde, con qué permisos ni cómo detectar duplicados». Mejora limitada: añadir prerrequisitos, comando/menú verificado, ejemplo anonimizado, identificador de ejecución, recuento esperado y procedimiento de diagnóstico.

La lección debe indicar audiencia, versión y evidencia: «La guía de sincronización v2 necesitaba un recuento antes/después para que soporte detectara duplicados». Evita convertirla en «Toda documentación siempre necesita una tabla».

## Límite del MVP

Se editan documentos de texto UTF-8. No se renderizan ni verifican Word/PDF/Slides, no se comprueba automáticamente la interfaz de un servicio y no se ejecutan enlaces externos por defecto. Esas capacidades deben añadirse al evaluador antes de declararlas cubiertas.
