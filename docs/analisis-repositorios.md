# Análisis de los repositorios de referencia

Inspección estática realizada el 3 de octubre de 2026 mediante el plugin GitHub. Los programas upstream no se ejecutaron ni se reprodujeron sus benchmarks. Los hallazgos se refieren exclusivamente a las revisiones fijadas abajo; futuras versiones pueden corregirlos.

| Proyecto | Commit inspeccionado | Qué aporta |
| --- | --- | --- |
| [kayba-ai/recursive-improve](https://github.com/kayba-ai/recursive-improve/tree/9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3) | 9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3 | Captura de experiencias, métricas, skills de análisis y ciclos keep/revert. |
| [AetherLabsAI/RSIAgent](https://github.com/AetherLabsAI/RSIAgent/tree/4d7ef43770dda341fccd9a5743db92407687c615) | 4d7ef43770dda341fccd9a5743db92407687c615 | Roles separados, exploración amplia/profunda, memoria durable y evaluación aislada. |

Ambos repositorios declaran Apache-2.0. Se verificó el archivo LICENSE. Las dependencias y los assets de benchmark conservan sus propios términos. Nuestro MVP es una implementación independiente inspirada en los patrones; no necesita redistribuir imágenes de VM o datasets de esos proyectos.

## recursive-improve: práctico para aprender de trazas

Su centro operativo es una skill para un agente de programación. La biblioteca Python instrumenta llamadas, calcula métricas, almacena experiencias y ofrece utilidades de ramas/worktrees. El propio motor evolve se describe como herramientas de apoyo a la skill, no como una inteligencia autónoma completa.

La secuencia útil es: observar tareas reales → encontrar la causa del problema → proponer un cambio pequeño → comparar → conservar o revertir. También es acertado distinguir fallos que requieren arreglar código de los que requieren instrucciones o contexto mejores.

Referencias: [skill principal](https://github.com/kayba-ai/recursive-improve/blob/9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3/recursive_improve/data/SKILL.md), [bucle ratchet](https://github.com/kayba-ai/recursive-improve/blob/9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3/recursive_improve/data/RATCHET_SKILL.md).

### Problemas detectados por lectura del código

Estos son hallazgos estáticos, no incidentes observados ni pruebas de explotación. Son razones para revisar los componentes antes de una operación desatendida.

| Hallazgo | Efecto esperado por lectura | Respuesta en nuestro diseño |
| --- | --- | --- |
| clean_success recibe todos los detectores y detect_token_usage se activa cuando hay tokens registrados. | Una traza exitosa con consumo normal puede quedar clasificada como no limpia. | Éxito definido mediante casos observables y métricas explícitas. |
| El composite de benchmark promedia tasas sin invertir siempre las que representan fallos. | Subir una tasa de error puede subir ese composite. No es una afirmación sobre todos los scorers ratchet. | Todas las métricas deben declarar implícitamente la misma dirección: mayor es mejor. |
| El scorer omite métricas ausentes y reescala pesos; algunos errores de evaluación se absorben. | Puede producirse un score parcial sin la cobertura prevista. | Rechazo ante contrato inconsistente, métricas/casos ausentes o valores no finitos. |
| La misma skill puede escribir el evaluador y repetir esa etapa durante la optimización. | El candidato puede cambiar el criterio con el que será comparado. | Configuración/evaluador fuera de las rutas editables por la propuesta. |
| Una sesión sin excepción se marca exitosa por defecto. | No equivale necesariamente a cumplir el objetivo del usuario. | Los casos comprueban resultados; ausencia de excepción es solo telemetría. |
| Git usa git add -A y limpieza de archivos no versionados en revert. | En un checkout compartido puede incluir o descartar trabajo ajeno al experimento. | Copias temporales; el original no se modifica. |
| Trazas completas sin frontera de redacción y dashboard en 0.0.0.0. | Datos sensibles pueden almacenarse o exponerse si se despliega sin protección. | MVP sin dashboard ni captura general de sesiones; se exige selección y anonimización de archivos. |

Fuentes: [detectores](https://github.com/kayba-ai/recursive-improve/blob/9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3/recursive_improve/eval/detectors.py), [runner](https://github.com/kayba-ai/recursive-improve/blob/9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3/recursive_improve/eval/runner.py), [benchmark](https://github.com/kayba-ai/recursive-improve/blob/9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3/recursive_improve/benchmark.py), [scorer](https://github.com/kayba-ai/recursive-improve/blob/9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3/recursive_improve/ratchet/scorer.py), [motor ratchet](https://github.com/kayba-ai/recursive-improve/blob/9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3/recursive_improve/ratchet/engine.py), [operaciones Git](https://github.com/kayba-ai/recursive-improve/blob/9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3/recursive_improve/ratchet/git_ops.py), [sesiones](https://github.com/kayba-ai/recursive-improve/blob/9cf4b85ef6ef66d37ea3c452f49114ff7db1b1a3/recursive_improve/capture/session.py).

Hay además límites de telemetría: instrumentación de OpenAI Chat Completions, no Responses API; ausencia de acumulación completa de streaming en las funciones inspeccionadas; deduplicación basada en una porción corta de mensajes; detección heurística de loops y recuperación. Son señales diagnósticas que necesitan contexto, especialmente cuando repetir lecturas o ejecutar tests fallidos es trabajo normal.

## RSIAgent: valioso por su arquitectura experimental

El framework mantiene fijos los parámetros de los modelos. Aprende procedimientos, scripts y lecciones reutilizables en memoria. El Curriculum selecciona práctica; el Actor trabaja y destila; el Verifier comprueba de forma independiente; el harness impone fronteras y persistencia.

Su exploración amplia ejecuta ramas desde una misma memoria inicial y solo consolida después de completar la verificación de toda la ola. Su exploración profunda alterna intentos del objetivo con prácticas dirigidas. La ejecución de evaluación utiliza una memoria congelada, sin currículo ni nuevas escrituras de aprendizaje.

El verificador trabaja con aislamiento de filesystem/namespaces o con un espejo protegido por rollback QEMU, ocultando memoria privada del Actor. Sin embargo, el propio proyecto advierte que el rollback local no revierte cambios a servicios externos compartidos. Para un CRM real, esa distinción es decisiva.

Referencias: [arquitectura](https://github.com/AetherLabsAI/RSIAgent/blob/4d7ef43770dda341fccd9a5743db92407687c615/docs/ARCHITECTURE.md), [máquina de estados](https://github.com/AetherLabsAI/RSIAgent/blob/4d7ef43770dda341fccd9a5743db92407687c615/core/self_evolving_loop.py), [runtime del verificador](https://github.com/AetherLabsAI/RSIAgent/blob/4d7ef43770dda341fccd9a5743db92407687c615/core/verifier_runtime.py), [barrera de ola](https://github.com/AetherLabsAI/RSIAgent/blob/4d7ef43770dda341fccd9a5743db92407687c615/explore/phase1_wave.py).

La memoria utiliza hashes canónicos, validación de rutas, rechazo de symlinks, controles de completitud, instalación atómica y recuperación. Los estados de fallo, incertidumbre o infraestructura no se convierten automáticamente en éxito. Son patrones que merecen conservarse.

Referencias: [persistencia y protocolos](https://github.com/AetherLabsAI/RSIAgent/blob/4d7ef43770dda341fccd9a5743db92407687c615/explore/practice_loop.py), [evaluación final](https://github.com/AetherLabsAI/RSIAgent/blob/4d7ef43770dda341fccd9a5743db92407687c615/benchmarks/osworld/task.py).

### Lo que sus cifras demuestran y lo que no

| Benchmark reportado | Sin RSI | Con RSI | Alcance declarado |
| --- | ---: | ---: | --- |
| OSWorld 2.0 offline | 71,97 % | 78,98 % | 82 tareas; 41 resultados RSI y 41 baselines retenidas. |
| Agents' Last Exam | 83,75 % | 84,82 % | 67 tareas; 19 entradas RSI y 48 baselines retenidas. |

Son puntuaciones medias de crédito parcial reportadas por el manuscrito. Incluyen reintentos/checkpoints seleccionados, presupuestos diferentes y algunas variantes o recalificaciones locales. No son una repetición emparejada de todas las tareas ni una auditoría nueva de resultados de la versión pública. La documentación lo reconoce expresamente. La cohorte OSWorld histórica de 82 tampoco equivale a las 108 tareas del runner actual.

Estas cifras justifican investigar el método, pero no permiten prometer un incremento concreto en tus aplicaciones. Fuente: [alcance y reporte de resultados](https://github.com/AetherLabsAI/RSIAgent/blob/4d7ef43770dda341fccd9a5743db92407687c615/docs/PAPER.md).

Su infraestructura de referencia usa Linux/Docker/KVM y máquinas de escritorio grandes: ALE anuncia aproximadamente 167 GiB para Linux y 157 GiB para Windows, además del espacio de trabajo. Los perfiles permiten hasta 2.000 iteraciones y 86.400 segundos como watchdog. Esto es razonable como plataforma experimental especializada, pero requiere acotación para un laboratorio cotidiano de código y automatización.

Fuentes: [README fijado](https://github.com/AetherLabsAI/RSIAgent/blob/4d7ef43770dda341fccd9a5743db92407687c615/README.md), [perfil Actor](https://github.com/AetherLabsAI/RSIAgent/blob/4d7ef43770dda341fccd9a5743db92407687c615/config/roles/actor.yaml), [reporte de validación](https://github.com/AetherLabsAI/RSIAgent/blob/4d7ef43770dda341fccd9a5743db92407687c615/docs/RELEASE.md).

## Decisión para Recursive Workbench

Adoptamos la idea de aprendizaje basado en evidencia, cambios pequeños, responsabilidades separadas y memoria contextualizada. Implementamos primero un motor comprensible y comprobable, tres dominios y proveedores intercambiables. No integramos las dos plataformas completas ni ejecutamos sus agentes con acceso a cuentas del usuario.

La versión inicial es más estrecha: no captura automáticamente todas tus sesiones, no programa tareas diarias, no abre PRs, no conecta con CRM, no hace cambios de infraestructura y no se modifica a sí misma. El valor inmediato es poder comprobar la disciplina propuesta en una demo y preparar el primer evaluador real.

La siguiente inversión debería ser un buen conjunto de tareas reales y un evaluador difícil de engañar. Añadir más agentes o una interfaz antes de eso no resuelve el principal riesgo: optimizar una señal que no representa la calidad útil.
