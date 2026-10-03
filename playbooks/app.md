# Playbook: mejora de aplicaciones

Este documento guía al operador y al proveedor de propuestas. No es una skill personal instalada ni modifica permisos del motor. Dominio de propuesta: app.

## Entrada mínima

- Una historia de usuario concreta con comportamiento esperado y observado.
- Archivos UTF-8 estrictamente necesarios y autorizados.
- Un caso que reproduce el fallo y casos existentes que no deben romperse.
- Restricciones: API pública, idiomas, tamaño de pantalla, permisos, compatibilidad y presupuesto.

Ejemplo adecuado: «La calculadora trunca céntimos y calcula impuestos antes del descuento; corregirlo según estas reglas y conservar cantidades nulas y devoluciones». Ejemplo demasiado amplio: «Haz toda la app mejor».

## Secuencia

1. Reproduce el problema con una entrada concreta. Distingue defecto de producto, defecto de test y problema del entorno.
2. Formula una hipótesis causal de una frase: qué condición produce el fallo y qué cambiaría el resultado.
3. Localiza el cambio mínimo. No hagas una migración arquitectónica mientras corriges un redondeo.
4. Pide al evaluador del operador que añada casos límite antes de generar el candidato, si falta cobertura. El proponente no puede modificar el evaluador protegido.
5. Devuelve una propuesta JSON con los cuatro campos del contrato y archivos completos. Usa domain: app.
6. Revisa baseline/candidato y el diff. Comprueba que los tests validan resultados de usuario y no simplemente reproducen la implementación.
7. Solo después de la aceptación interna, prueba manualmente el recorrido y tramita una rama/PR en el proyecto real.

## Evaluación útil

| Área | Casos a considerar |
| --- | --- |
| Función principal | Camino normal, valores límite, entradas inválidas y errores explicables. |
| Datos | Duplicados, precisión, zonas horarias, ordenación, persistencia y recuperación. |
| Seguridad | Autorización por usuario/cliente, validación y ausencia de secretos en salida. |
| UX | Teclado, foco, mensajes de error, móvil, estados de carga/vacío y accesibilidad. |
| Integración | Timeout, respuesta parcial, schema desconocido y fallo de dependencia. |

Cada caso debe establecer entrada, salida esperada y evidencia. Las verificaciones visuales o de accesibilidad requieren herramientas y criterios propios; la demo actual no las realiza.

## Rechazar o escalar

Rechaza cambios que alteran datos sin migración/recuperación, rebajan un test para aprobar, añaden dependencias innecesarias o requieren acceso fuera de allowed_paths. Si no hay forma de comprobar un requisito, declara esa incertidumbre; no inventes un PASS.

Una buena lección sería: «En la política de precios v1, aplicar descuento antes del IVA y redondear en el punto definido evita la discrepancia del caso X». Una mala lección sería: «Siempre redondear cada operación»; puede romper otros sistemas.

## Límite del MVP

La propuesta edita archivos de texto, sin eliminaciones ni ejecución de comandos. Para ejecutar código candidato debes disponer de un evaluador Docker confiable con dependencias ya preparadas y sin secretos. El score de la demo no certifica que una aplicación esté lista para producción.
