# Validación de la entrega 0.1

Fecha: 3 de octubre de 2026. Python 3.12.14. Implementación original; no se ejecutaron los repositorios upstream.

## Resultado observado

`python3 -m unittest discover -s tests -q`: **59 pruebas aprobadas**, ninguna omitida, 0 errores. Las pruebas HTTP usan un servidor simulado en 127.0.0.1; no solicitan inferencia real.

| Grupo | Pruebas | Alcance |
|---|---:|---|
| Motor | 30 | Aceptación/rechazo, métricas, regresiones, rutas, límites, memoria, bloqueo concurrente y demo integrada |
| Evaluadores | 13 | Cálculos, reintentos, duplicados, documentación, contratos JSON y adaptador Docker con procesos simulados |
| Proveedores | 16 | JSON manual, demo, solicitud HTTP real a servidor simulado, redirecciones, proxies, límites y timeout |

Ejecución separada de CLI: `python3 -m recursive_workbench demo --output demo-validation`. Se aceptaron tres propuestas sucesivas: app, docs y workflow. Los 11 casos de entrenamiento y 13 casos de validación terminan aprobados. Los archivos originales permanecen sin cambios.

| Métrica sintética | Entrenamiento inicial | Validación inicial | Final en ambos grupos |
|---|---:|---:|---:|
| App | 33,3 % | 25 % | 100 % |
| Documentación | 0 % | 0 % | 100 % |
| Workflow | 33,3 % | 40 % | 100 % |

Estos porcentajes prueban que el mecanismo reconoce reparaciones predeterminadas. **No son resultados de un modelo ni una medida de productividad, capacidad general o preparación para producción.**

También se ejecutaron `inspect` y `prompt`, comprobando la generación de contexto con el esquema de propuesta para el modo manual.

## Defectos encontrados y corregidos durante QA

1. Finalización prematura cuando las métricas eran 1 pero existía un fallo crítico.
2. Finalización prematura cuando algún caso individual fallaba pese a métricas de 1.
3. Posible aceptación de una evaluación final recibida después del presupuesto temporal.
4. Posible redirección de escrituras mediante un enlace simbólico en la carpeta de ejecuciones.

Cada corrección tiene una prueba que reproduce la condición defectuosa y comprueba su rechazo.

## Lo que falta comprobar

- Inferencia con un modelo real de Ollama y calidad de sus propuestas.
- Ejecución Docker: el CLI/daemon no estaba disponible. Las comprobaciones del adaptador son pruebas simuladas de argumentos, límites, JSON y limpieza.
- Tests sobre una aplicación real, pipelines CI y APIs de clientes.
- Aislamiento frente a código hostil capaz de intentar engañar el protocolo del evaluador. Docker limita ejecución y recursos; no garantiza por sí solo la integridad semántica de una nota emitida por un evaluador mal diseñado.
- Repeticiones estadísticas, medida de tokens consumidos, coste monetario y tiempo ahorrado.

El timeout HTTP es de inactividad del socket. El motor bloquea la aceptación de resultados fuera de plazo, pero todavía no implementa una cancelación global estricta de llamadas de red que mantienen actividad.

## Publicación de la versión 0.1

Este informe conserva la validación histórica de la entrega 0.1 en ZIP. La versión 0.2 integra el código en recursive-agent y añade el planificador de conocimiento; consulta validacion-v0.2.md para el resultado de esa entrega.
