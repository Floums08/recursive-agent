# Arquitectura, puesta en marcha y mejora diaria

Recursive Workbench es un laboratorio local para proponer cambios pequeños, medirlos y conservar los que mejoran un contrato de evaluación. Está especializado en tres tipos de trabajo: aplicaciones, documentación y definiciones de flujos. Esta versión inicia una base extensible; no es una inteligencia que se entrene a sí misma ni un servicio de producción desplegado.

El aprendizaje ocurre en dos superficies: archivos candidatos y lecciones asociadas a experimentos aceptados. Los pesos del modelo no cambian. Una mejora del benchmark tampoco implica una mejora general del modelo.

## 1. Qué hace esta versión

1. Lee una configuración propiedad del operador y archivos UTF-8 de rutas permitidas.
2. Construye una copia temporal con esos archivos, excluyendo rutas conocidas de credenciales; el operador debe revisar también el contenido de los archivos permitidos.
3. Evalúa el punto de partida en dos particiones: train y holdout.
4. Pide una propuesta al proveedor demo, manual u Ollama. El contexto contiene archivos permitidos, fallos de train y lecciones anteriores; no los resultados holdout.
5. Valida la propuesta: dominio, rutas, tamaño, esquema y ausencia de archivos protegidos.
6. Aplica la propuesta a otra copia temporal y ejecuta las mismas evaluaciones.
7. Acepta internamente solo si mejora ambas particiones y conserva los comportamientos que ya funcionaban.
8. Entrega candidate/, patch.diff, propuestas e informes. Conserva lecciones de las candidaturas aceptadas.

**El original permanece intacto.** «Aceptado» significa que la copia candidata superó este contrato; no significa desplegado, publicado en GitHub, mergeado o autorizado para escribir en un CRM. El propio motor comprueba al final que la fuente no haya cambiado.

El proveedor demo usa reparaciones prefijadas. Sirve para observar el mecanismo sin APIs, Docker ni costes de modelo. No demuestra creatividad, capacidad general de programación ni integración real con Make, HubSpot o Dataverse.

## 2. Separación de responsabilidades

| Función | Responsable actual | Límite |
| --- | --- | --- |
| Elegir el problema y definir éxito | Operador con playbooks | Debe aportar un caso reproducible. |
| Proponer un cambio | Proveedor demo, JSON manual u Ollama | Solo texto y archivos permitidos; sin comandos de ejecución. |
| Preparar candidato | Motor | Copia aislada; no edita el proyecto original. |
| Medir | Evaluador sintético o evaluador Docker del operador | Mismo contrato antes/después; fuera de las rutas editables. |
| Aceptar una candidatura | Gate determinista | Exige mejora medible en ambas particiones y ausencia de regresiones. |
| Guardar aprendizaje | Motor | Solo lecciones aceptadas, con hashes de evidencia. |
| Aplicar a un proyecto o producción | Operador | Fuera del alcance automático de este MVP. |

Esta separación recoge la idea de un Actor y un Verifier independientes de RSIAgent y la medición de experiencias de recursive-improve. Aquí no existe todavía un agente Curriculum autónomo ni un crítico LLM separado. Un evaluador determinista bien construido puede ser más útil que otro modelo diciendo «parece correcto».

## 3. Probar la demostración

Requisito: Python 3.11 o posterior. Ejecuta desde la carpeta del proyecto. El núcleo utiliza la biblioteca estándar; no necesitas instalar dependencias con pip para esta prueba.

    python --version
    python -m recursive_workbench demo --output demo
    python -m recursive_workbench inspect demo/agent.json
    python -m recursive_workbench run demo/agent.json --provider demo

En Windows, si no existe el comando python, puedes usar py -3.11 en su lugar. La salida del run identifica la carpeta del experimento. Abre su report.md para leer el resumen y patch.diff para ver cambios concretos. Para leer un informe JSON desde la consola:

    python -m recursive_workbench report RUTA_DEL_RUN/report.json

Sustituye RUTA_DEL_RUN por la ruta real que haya devuelto la ejecución. Los resultados están debajo de la carpeta .recursive-state junto a agent.json, no dentro del workspace.

La demostración presenta tres problemas sintéticos: cálculo de precios, documentación operativa y un flujo de leads con duplicados/reintentos. El evaluador interpreta JSON y texto para simular casos; no ejecuta una aplicación industrial ni llama a servicios externos.

## 4. Trabajar con un asistente y una propuesta manual

Puedes usar el modelo o asistente de tu elección sin integrar una API. Primero genera su contexto:

    python -m recursive_workbench prompt demo/agent.json --output prompt.txt

Revisa prompt.txt antes de compartirlo. Las rutas permitidas reducen la superficie, pero **no existe un detector universal de datos personales o secretos**: un archivo permitido puede contener información sensible. Usa ejemplos anonimizados.

Pide al asistente que devuelva exclusivamente un JSON con estas cuatro propiedades:

    {
      "hypothesis": "Explicación comprobable de un único problema y su solución",
      "domain": "app",
      "changes": [
        {
          "path": "app/pricing.json",
          "content": "{\"rounding\":\"half_up\",\"tax_after_discount\":true}\n"
        }
      ],
      "lesson": "Hipótesis de aprendizaje limitada a esta configuración y sus pruebas"
    }

Guárdalo como proposal.json fuera del workspace. El ejemplo ilustra el formato; los valores concretos deben ajustarse al contrato del proyecto y a sus pruebas. Cada content es el archivo completo de reemplazo, no un fragmento de diff. No se permiten eliminaciones ni órdenes shell en la propuesta.

Configura max_iterations a 1 cuando revises una única propuesta manual: volver a leer el mismo archivo no genera una alternativa nueva.

    python -m recursive_workbench run demo/agent.json --provider manual --proposal proposal.json

Un JSON válido no garantiza aceptación. La propuesta puede ser rechazada porque no mejora el score, rompe un caso, cambia el contrato o no supera una prueba crítica.

Los playbooks de esta entrega son instrucciones de trabajo para leer y proporcionar al asistente cuando corresponda. No se instalan como skills personales y no debe suponerse que el proveedor los carga automáticamente.

## 5. Usar un modelo servido por Ollama

El proveedor llama a un servidor Ollama mediante /api/chat. Necesitas un servidor en marcha y un modelo ya disponible en él. Este proyecto no descarga modelos, no arranca el servicio y no incluye pesos de modelos.

    python -m recursive_workbench run demo/agent.json --provider ollama --model NOMBRE_DEL_MODELO --base-url http://127.0.0.1:11434

Sustituye NOMBRE_DEL_MODELO por el identificador exacto de tu instalación. Empieza con una iteración y una selección pequeña de archivos. El proveedor espera JSON estructurado; un modelo que devuelve explicaciones o campos adicionales puede producir rechazos de esquema.

La configuración predeterminada apunta a loopback. Si seleccionas un servidor HTTPS remoto, los archivos permitidos se transmiten a ese servidor; decide conscientemente qué datos puede recibir. No se persisten credenciales del proveedor. La versión actual impone límites de tiempo y tamaño, pero **no contabiliza euros facturados ni aplica una reserva monetaria**. Un servidor remoto puede tener costes ajenos al motor.

El timeout de Ollama es un límite de inactividad de socket, no una cancelación global exacta. El motor no acepta evaluaciones completadas después de max_seconds, pero una llamada en curso o la limpieza de Docker pueden retrasar el retorno del proceso. No interpretes el presupuesto como una garantía de finalización al milisegundo.

## 6. Configurar un proyecto real pequeño

Crea una carpeta de experimento con agent.json y, al lado, un directorio workspace que contenga exclusivamente archivos de prueba. No apuntes el primer experimento a un repositorio de cliente completo.

    {
      "version": 1,
      "name": "piloto-documentacion",
      "workspace": "workspace",
      "allowed_paths": ["docs/"],
      "evaluator": {"kind": "builtin-demo"},
      "max_iterations": 1,
      "max_seconds": 300,
      "max_candidate_bytes": 100000,
      "max_workspace_bytes": 500000,
      "min_improvement": 0.01,
      "max_regression": 0.0
    }

Esta configuración enseña los límites, pero builtin-demo **solo evalúa las fixtures de la demo**. Para otro proyecto debes sustituirlo por un evaluador Docker propio y aportar sus casos antes de esperar resultados útiles. Un evaluador genérico de cantidad de palabras o número de tests verdes puede premiar cambios que empeoren la experiencia real.

Las rutas son relativas a agent.json. Los directorios de allowed_paths llevan barra final. El motor excluye rutas protegidas como tests, evaluadores, secretos, archivos ocultos, AGENTS.md, SKILL.md y configuración del agente. También rechaza traversal y symlinks. Conviene autorizar pocos archivos concretos o un subdirectorio pequeño.

No se soportan binarios, PDFs ni imágenes como propuestas directas. Para documentación Word/PDF, una ampliación futura debe incorporar generación, renderizado y evaluación visual; añadir el archivo a allowed_paths no proporciona esa capacidad.

### Configurar un evaluador Docker

Requisitos: Docker disponible y una imagen confiable ya descargada por el operador. El runner usa --pull never, por lo que no descarga imágenes automáticamente. Se recomienda fijar la imagen por digest una vez validada.

Crea un directorio trusted-evaluation al lado de agent.json y workspace, nunca dentro de workspace ni como uno de sus directorios padre. Escribe evaluate.py con los casos del proyecto. La configuración exacta es:

    "evaluator": {
      "kind": "docker",
      "image": "python:3.12-alpine",
      "evaluator_dir": "trusted-evaluation",
      "command": ["python", "/evaluator/evaluate.py"],
      "timeout_seconds": 30,
      "max_output_bytes": 1000000,
      "memory_mb": 256,
      "cpus": 1,
      "pids_limit": 64
    }

El contenedor recibe /workspace y /evaluator de solo lectura y RECURSIVE_SPLIT con train u holdout. El script lee los archivos de /workspace y escribe exclusivamente el JSON del contrato en stdout, sin logs ni Markdown. Debe conservar la identidad de la suite y los casos entre baseline y candidato. Los archivos del evaluador necesitan permisos de lectura para el usuario no privilegiado 65534.

El runner aplica red deshabilitada, raíz de solo lectura, límites de memoria/CPU/procesos, ausencia de capabilities y no-new-privileges. No reenvía tokens del entorno. command es una lista fija de argumentos, no una orden shell generada por el modelo. La imagen debe contener las dependencias necesarias; no intentes instalarlas desde internet durante la evaluación.

Para probar únicamente el transporte, examples/docker_evaluator.py es una plantilla que envuelve los mismos casos sintéticos. Copia ese archivo como trusted-evaluation/evaluate.py y recursive_workbench/evaluators.py como trusted-evaluation/demo_checks.py. **Ese ejemplo no proporciona tests genéricos de aplicaciones reales.** Debes sustituir la lógica por tu contrato antes de medir otro proyecto.

La validación de esta entrega ha superado 59 pruebas automatizadas; la invocación Docker se cubrió mediante pruebas simuladas, sin ejecutar un contenedor real en este entorno. Consulta docs/validacion.md para el alcance exacto de la verificación realizada.

### Contrato de evaluación

Cada evaluación devuelve un JSON con suite_id, metrics, cases y critical_pass. Todos los indicadores deben ser números finitos entre 0 y 1, con mayor valor equivalente a mejor resultado. Las métricas pesan lo mismo en la media. Coste o latencia no se pueden introducir directamente como «más es mejor»: normalízalos con umbrales fijos o mantenlos como telemetría.

    {
      "suite_id": "mi-contrato-v1-train",
      "metrics": {"functional_quality": 0.75},
      "cases": {
        "duplicate_request": {"passed": true, "detail": "Una sola salida"},
        "expired_token": {"passed": false, "detail": "Error no explicado"}
      },
      "critical_pass": true
    }

Baseline y candidato deben conservar exactamente suite_id y nombres de métricas/casos en cada partición. Un caso que pasaba no puede fallar después. critical_pass del candidato debe ser true. Cada métrica respeta max_regression y la media debe superar min_improvement, tanto en train como en holdout. Un empate se rechaza.

Consecuencia práctica: si holdout ya vale 1, una corrección que solo mejora train no puede pasar el gate actual. Es una política deliberadamente estricta del MVP, no una prueba de que el cambio sea inútil. No la rebajes a posteriori para aprobar una candidatura concreta: revisa el contrato en un experimento nuevo, desde una nueva baseline.

### Regresión visible y evaluación reservada

El nombre holdout del protocolo significa «partición no enviada al proveedor durante este run». En la demo, sus casos y código se distribuyen públicamente: **no es un conjunto secreto ni una prueba de generalización independiente**. Además, su uso repetido para aceptar candidatos puede llevar a adaptarse indirectamente a él.

Para medir progreso de forma más convincente, mantiene un tercer conjunto privado fuera del repositorio/contexto accesible al proponente, bajo control de otra persona o servicio. Úsalo periódicamente para medir una versión congelada, sin dar sus detalles al ciclo de optimización. Conserva versión, hashes, fallos y presupuesto; no selecciones solo el mejor intento.

## 7. Rutina diaria de 20–40 minutos

La versión 0.2 incorpora un [planificador de conocimiento](second-brain-adapter.md) y un [backlog de capacidades](plan-mejora-diaria.md). El CLI se ejecuta bajo demanda. Una revisión programada en ChatGPT se configura por separado y entrega un informe privado; no programa despliegues ni modificaciones del conocimiento desde GitHub Actions.

| Paso | Qué hacer | Evidencia que guardar |
| --- | --- | --- |
| 1. Recoger | Revisar 5–10 tareas terminadas, errores y correcciones humanas. Anonimizar datos. | Tarea, resultado esperado, resultado real, tiempo perdido. |
| 2. Priorizar | Elegir un fallo frecuente y costoso que admita una prueba reproducible. | Una hipótesis causal y un resultado observable. |
| 3. Fijar contrato | Escribir el caso de regresión y mantener pruebas previas. Separar práctica de evaluación reservada. | Suite versionada; criterios y límites antes de proponer cambios. |
| 4. Medir baseline | Ejecutar el contrato sobre el estado actual. Confirmar que reproduce el problema. | Reporte con fallos y score inicial. |
| 5. Proponer | Una modificación pequeña en un dominio; leer su playbook. | proposal.json con hipótesis y archivos completos. |
| 6. Comparar | Ejecutar con mismo modelo, casos, herramientas y presupuesto. | Informe de ambas particiones, incluso si se rechaza. |
| 7. Revisar | Leer diff, casos y lección. Probar manualmente el recorrido del usuario. | Decisión de aceptación humana y limitaciones. |
| 8. Incorporar | Aplicar solo el cambio revisado al proyecto, mediante una rama/PR y sus controles habituales. | Commit, vínculo al experimento y plan de reversión. |

El objetivo diario es aprender algo válido. **«No promover ningún cambio» es un resultado correcto** si no existe evidencia suficiente. No acumules instrucciones solo porque suenan razonables.

Cada ejecución vuelve a partir del workspace original. candidate/ contiene la mejor copia de ese run, no se convierte automáticamente en la base del día siguiente. Después de revisar, incorpora expresamente el cambio en tu copia de trabajo o en una rama del proyecto; entonces la siguiente ejecución medirá esa nueva base. La memoria se separa por configuración/proyecto y conserva lecciones recientes, pero no sustituye aplicar el código aprobado.

### Plan de las primeras dos semanas

| Día | Trabajo útil |
| --- | --- |
| 1 | Ejecutar demo, leer diff e identificar por qué se acepta o rechaza. |
| 2 | Seleccionar un proyecto y 5 casos reales anonimizados de un único dominio. |
| 3 | Construir un evaluador determinista con un fallo reproducible y un caso crítico. |
| 4 | Proponer manualmente una corrección pequeña; conservar todos los resultados. |
| 5 | Añadir un caso límite y comprobar que no rompe lo aceptado. |
| 6–7 | Medir tiempo de revisión y aceptación humana; eliminar métricas fáciles de manipular. |
| 8 | Probar Ollama con exactamente el mismo contrato y presupuesto. |
| 9 | Comparar costes operativos y rechazos de formato del proveedor. |
| 10 | Incorporar una segunda categoría de tareas si la primera ya produce valor. |
| 11–12 | Probar un conjunto reservado nuevo, sin convertir sus respuestas en instrucciones. |
| 13 | Revisar lecciones obsoletas, contradictorias o demasiado generales. |
| 14 | Decidir si merece activar experimentos periódicos; mantener aplicación/producción bajo controles separados. |

## 8. Niveles de evolución

| Nivel | Alcance | Estado |
| --- | --- | --- |
| 0 | Demo sintética reproducible y comparación de candidaturas | Implementado. |
| 1 | JSON manual u Ollama, contratos propios en Docker, revisión de diff | Base implementada; cada proyecto necesita su evaluador. |
| 2 | Experiencias reales instrumentadas, redacción de secretos, métricas de utilidad y costes | Trabajo siguiente; no incluido automáticamente. |
| 3 | Experimentos periódicos en ramas aisladas, PRs de borrador y revisión independiente | Evolución propuesta; no activada. |
| 4 | Cambios al propio motor bajo tests externos, evaluador protegido y evaluación reservada | Evolución futura, con otro proceso de aprobación. |

No se permite al candidato modificar el gate para lograr aprobarse. Tampoco hay garantía de mejora monótona fuera de los casos medidos. Las lecciones son hipótesis contextualizadas; no son nuevas instrucciones con autoridad sobre el operador.

## 9. Qué revisar antes de usarlo en un cliente

- Una tarea real y estrecha, con datos anonimizados y aceptación observable.
- Evaluador revisado que falle cuando el objetivo no se cumple, y no solo cuando hay una excepción.
- Ejecución confinada; el proyecto candidato puede contener código hostil o defectuoso.
- Pruebas de duplicados, reintentos, límites, errores de API y permisos para cualquier automatización.
- Sin credenciales de producción en el workspace ni en fixtures; las salidas y propuestas también pueden contener datos del cliente.
- Presupuesto operativo del proveedor y del equipo, separado del límite técnico de segundos/iteraciones.
- Revisión humana del cambio final y posibilidad de volver al commit anterior.

El confinamiento Docker reduce riesgos, pero no constituye una certificación contra escapes ni protege un Docker daemon expuesto. El evaluador, la imagen y el host forman parte del entorno de confianza del operador.

## 10. Publicar tú mismo solo el código en un repositorio privado

El código reutilizable de la versión 0.2 se mantiene en Floums08/recursive-agent. Para mantener una copia propia privada, puedes seguir el procedimiento de abajo en un repositorio separado. No publiques datos de conocimiento ni informes de clientes en un repositorio público.

Desde la carpeta del proyecto, en una copia de trabajo dedicada:

    git init
    git switch -c main
    git status --short

Revisa .gitignore y los archivos. Excluye .recursive-state/, prompts con datos reales, propuestas de clientes, entornos .env, tokens y directorios de experimentos privados. Un repositorio privado sigue siendo un lugar inadecuado para credenciales y datos innecesarios de clientes.

Añade solo las rutas de código/documentación revisadas; evita un git add -A indiscriminado si ya ejecutaste experimentos dentro de esa carpeta. Para los archivos fuente de esta entrega:

    git add recursive_workbench docs playbooks tests examples
    git add README.md pyproject.toml .gitignore IMPLEMENTATION_CONTRACT.md

Comprueba el contenido exacto antes del commit:

    git diff --cached --stat
    git diff --cached
    git commit -m "Initial measured improvement workbench"
    git remote add origin https://github.com/TU_USUARIO/recursive-workbench.git
    git push -u origin main

Sustituye TU_USUARIO y el nombre por los del repositorio privado real. Estos comandos son instrucciones para el operador, no acciones ejecutadas por esta entrega. Los resultados de cliente y la memoria requieren su propio almacenamiento privado, retención y control de acceso.

## 11. Cómo saber si mejora de verdad

Controla semanalmente cuatro resultados separados: porcentaje de tareas aceptadas por una persona, regresiones introducidas, tiempo total hasta entregar y coste por tarea aceptada. Conserva también número de propuestas rechazadas y errores de infraestructura. Si aumenta el score pero empeora el trabajo del usuario, debes revisar el contrato.

Para comparar versiones, utiliza tareas y presupuestos emparejados y, si el modelo es variable, varias repeticiones. Reporta dispersión y todos los intentos. Una única subida de tres puntos en unos pocos ejemplos es una señal para investigar, no una demostración de progreso general.
