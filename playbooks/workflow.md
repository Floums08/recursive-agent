# Playbook: automatización de flujos

Guía del operador/proveedor; no es una skill instalada ni un conector activo. Dominio de propuesta: workflow.

## Entrada mínima

- Evento disparador y esquema del payload, con ejemplo anonimizado.
- Sistema origen/destino y resultado observable.
- Clave de idempotencia y regla de negocio para duplicados.
- Política de reintentos, fallos permanentes y revisión humana.
- Permisos requeridos y entorno de pruebas disponible.

Especifica si dos formularios similares representan un mismo evento repetido o dos leads distintos. Deduplicar por email indiscriminadamente puede eliminar eventos legítimos. La clave debe corresponder al evento/operación de negocio acordado.

## Secuencia

1. Dibuja el flujo como estados: recibido, validado, pendiente, ejecutado, reintento y fallo definitivo. Define qué evidencia permite cambiar de estado.
2. Reproduce un fallo: webhook duplicado, timeout después de escribir, respuesta 429, credencial caducada o payload incompleto.
3. Fija antes de proponer el comportamiento esperado y el máximo de efectos externos.
4. Diseña una corrección pequeña de la definición/configuración, con domain: workflow.
5. Ejecuta una simulación sin credenciales ni conexión al sistema real.
6. Comprueba idempotencia y trazabilidad, incluyendo el caso «el proveedor escribió, pero la respuesta se perdió».
7. Después de revisión, prueba con cuentas y datos de test del conector concreto. La simulación no reemplaza una prueba de integración.
8. La activación del flujo y sus escrituras requieren un despliegue separado, observación y reversión/compensación definida.

## Casos mínimos

| Caso | Resultado esperado que hay que definir |
| --- | --- |
| Evento válido | Una sola operación de negocio; correlación conservada. |
| Mismo evento repetido | Mismo resultado lógico, sin duplicar efectos. |
| Segundo evento legítimo del mismo contacto | Se procesa cuando la regla lo requiere. |
| HTTP 429 o fallo temporal | Reintento acotado, con espera y respeto de Retry-After si aplica. |
| Error permanente | Sin bucle infinito; estado visible para diagnóstico. |
| Timeout tras posible escritura | Consulta/reconciliación antes de repetir una operación no idempotente. |
| Credencial caducada | Fallo explícito; no se registran tokens. |
| Payload nuevo o incompleto | Validación y ruta definida; no se inventan datos obligatorios. |
| Volumen superior al esperado | Límite/concurrencia y cola definidos. |

## Reglas de diseño

No uses «reintentar todo» como solución universal. Los errores de autorización, schema o negocio suelen requerir una acción distinta de esperar. No marques routing_complete antes de disponer de evidencia de la operación acordada.

La trazabilidad debería asociar event_id, correlation_id, clave de idempotencia, paso, intento, timestamp y resultado, sin almacenar datos personales innecesarios. Decide retención y acceso antes de recoger payloads completos.

Un rollback local no deshace un email enviado ni una escritura en HubSpot, Make o Dataverse. Define compensaciones específicas cuando sean posibles y deriva a una persona cuando no lo sean.

## Límite del MVP

La demostración simula deduplicación/reintentos mediante configuración JSON. No importa escenarios Make/n8n, no configura Power Automate, no crea registros CRM y no envía mensajes. Cada plataforma necesita un adaptador y un evaluador de integración propios.
