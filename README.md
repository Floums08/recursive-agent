# Recursive Agent · Workbench 0.2

Un agente experimental para mejorar aplicaciones, documentación y automatizaciones mediante propuestas pequeñas, pruebas reproducibles y memoria con evidencia. Python 3.11+, sin dependencias externas para la demo.

**Estado:** motor de mejora medible + planificador local de conocimiento. La demo prueba el ciclo con casos sintéticos; el planificador lee espacios laborales seleccionados y propone revisiones. No ejecuta tareas de clientes, envía mensajes ni modifica sistemas externos.

Repositorio: [Floums08/recursive-agent](https://github.com/Floums08/recursive-agent). Consulta [el backlog](backlog/tasks.json), [el plan de mejora diaria](docs/plan-mejora-diaria.md) y [el adaptador de conocimiento](docs/second-brain-adapter.md).

## Ejecutarlo en 2 minutos

1. Clona este repositorio y abre una terminal en la carpeta `recursive-agent`: `git clone https://github.com/Floums08/recursive-agent.git`.
2. Comprueba `python --version` (3.11 o superior). En Linux/macOS puedes usar `python3`.
3. Ejecuta:

```bash
python -m unittest discover -s tests -v
python -m recursive_workbench demo --output demo
```

La demo crea tres defectos controlados: cálculo de precios, manual incompleto y flujo de leads sin protección frente a duplicados/reintentos. Propone reparaciones predeterminadas y las evalúa. No llama a un modelo ni ejecuta código propuesto.

El comando muestra la ubicación de `report.json`. En la misma carpeta encontrarás `report.md`, `patch.diff` y `candidate/`. El proyecto original queda intacto. Revisa el diff antes de incorporar el candidato.

## Plan diario desde tu conocimiento

```bash
python -m recursive_workbench daily --brain-root examples/brain-demo --vault demo-work --output ../daily-demo-output --date 2026-10-03
```

Este ejemplo usa datos ficticios. Para tu copia privada, cambia la ruta y selecciona espacios laborales mediante `--vault`; guarda el resultado fuera de este repositorio. El plan distingue candidatos históricos, tareas actuales y estados cerrados; conserva identidad, fuentes y feedback. No convierte una solicitud antigua en permiso para actuar.

La revisión programada en ChatGPT es independiente del CLI. GitHub Actions ejecuta únicamente CI sobre código y ejemplos sintéticos: no dispone de acceso al conocimiento privado.

## Qué está implementado

- Ciclo acotado de propuesta → evaluación → aceptación/rechazo, con un máximo de 10 iteraciones y límites por configuración.
- Copias temporales; el modelo propone reemplazos de ficheros, sin comandos de sistema.
- Protección de rutas y nombres sensibles conocidos, con evaluador externo al alcance editable; rechazo de symlinks y de resultados incompletos. Los filtros por nombre no detectan todo secreto ni toda prueba: define el alcance explícitamente.
- Comparación por caso y por métrica. Exige mejora tanto en entrenamiento como en validación y bloquea regresiones en casos previamente aprobados.
- Memoria local por proyecto: solo lecciones de candidatos aceptados, con hashes de evidencia y alcance explícito.
- Proveedores `demo`, `manual` y `ollama`; exportación de contexto para usar con Codex o ChatGPT.
- Evaluación sintética sin ejecutar código; adaptador Docker para evaluaciones reales aisladas.
- Informes y diff revisables. Sin merge, publicación o despliegue automático.

## Usarlo con Codex / ChatGPT

```bash
python -m recursive_workbench prompt demo/agent.json --output prompt.txt
```

Abre `prompt.txt`, facilita ese contenido a tu asistente y guarda su respuesta JSON en `proposal.json`. El contexto contiene ficheros autorizados y fallos de entrenamiento; revisa que no haya datos de clientes antes de compartirlo.

```bash
python -m recursive_workbench run demo/agent.json --provider manual --proposal proposal.json --iterations 1
```

El modo manual evalúa una propuesta ya preparada. No llama a una API de ChatGPT y no usa automáticamente tu suscripción.

## Usarlo con un modelo local

Instala Ollama desde [ollama.com](https://ollama.com/), descarga un modelo adecuado para tu equipo y comprueba su nombre con `ollama list`. Con el servidor disponible:

```bash
python -m recursive_workbench run demo/agent.json --provider ollama --model NOMBRE_DEL_MODELO
```

El proveedor envía los archivos autorizados al endpoint configurado. El predeterminado es local (`127.0.0.1:11434`). Si eliges un endpoint HTTPS remoto, los datos salen de tu equipo. Este conector tiene pruebas con un servidor HTTP simulado; no se ha validado aquí contra un modelo Ollama real. El resultado depende del modelo, sus límites y el conjunto de pruebas.

## Aplicarlo a un proyecto real

No uses `builtin-demo` para valorar otra aplicación. Crea un proyecto de experimentación con `agent.json` fuera de `workspace/`, autoriza rutas concretas y configura un evaluador Docker externo. Consulta [la arquitectura y rutina diaria](docs/arquitectura-y-rutina.md), [el análisis de los repositorios](docs/analisis-repositorios.md) y el ejemplo `examples/docker_evaluator.py`.

El evaluador debe comprobar comportamiento real: casos de negocio, integraciones simuladas, regresiones y criterios de aceptación. Mantén una evaluación de transferencia que no se use para elegir mejoras. La validación repetida del MVP es una suite de regresión; no es un examen secreto independiente.

## Prioridades siguientes

Las capacidades pendientes se mantienen en `backlog/tasks.json` y sus issues asociadas. El catálogo distingue prioridad, cadencia, dependencias y criterios de aceptación. Tener una issue no significa que esa capacidad ya esté construida.

Empieza por revalidar fuentes, medir cobertura y cerrar pendientes con evidencia; continúa con regresiones, documentación de cambios e integraciones simuladas. Las tareas concretas de clientes permanecen en planes privados.

El CI ejecuta pruebas en Python 3.11 y 3.12. Los tests de proveedor usan un servidor HTTP local simulado; no requieren modelos ni claves. En Windows, el planificador puede necesitar `python -m pip install tzdata` para disponer de Europe/Madrid.

## Origen del diseño

Inspiración conceptual en [kayba-ai/recursive-improve](https://github.com/kayba-ai/recursive-improve) y [AetherLabsAI/RSIAgent](https://github.com/AetherLabsAI/RSIAgent), ambos Apache-2.0 según los commits revisados. Implementación propia: no depende de su código ni descarga/ejecuta sus paquetes.

No modifica pesos del modelo. Mejora artefactos y conserva lecciones verificadas dentro de un entorno y un presupuesto definidos.
