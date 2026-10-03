# Planificador diario desde un Second Brain

El comando `daily` lee una copia local de conocimiento de trabajo, identifica elementos que requieren revisión y produce un plan privado. No ejecuta las tareas ni modifica la base de conocimiento. El código y los ejemplos son públicos; los datos reales y los planes deben permanecer fuera de este checkout.

## Prueba sin datos reales

Desde la raíz del repositorio:

```bash
python -m recursive_workbench daily --brain-root examples/brain-demo --vault demo-work --output ../daily-demo-output --date 2026-10-03
```

El ejemplo es ficticio. El resultado contiene como máximo tres elementos de foco y una lista secundaria, con procedencia y razones de prioridad. La fecha fija hace reproducible la prueba; en uso normal se omite para utilizar la fecha de Europe/Madrid.

## Conectar tu copia privada

1. Clona tu repositorio privado de conocimiento en una carpeta separada. La aplicación no solicita credenciales, no descarga fuentes y no inicia sesiones por sí misma.
2. Actualiza esa copia con tu procedimiento normal, preservando cambios locales.
3. Abre `workspace.json` e identifica los IDs de los espacios laborales que quieres revisar.
4. Ejecuta el planificador pasando cada espacio de forma explícita:

```bash
python -m recursive_workbench daily \
  --brain-root /ruta/privada/knowledge-workspace \
  --vault espacio-laboral-1 \
  --vault espacio-laboral-2 \
  --output /ruta/privada/planes
```

La carpeta de salida debe estar fuera del código público y fuera de la base de conocimiento de entrada. El comando rechaza destinos que puedan sobrescribir esas fuentes. No copies los resultados a issues públicos ni a artefactos de Actions.

El adaptador consume `workspace.json` y los `state.json` de los espacios seleccionados. No recorre automáticamente las conversaciones completas, los adjuntos binarios, otros repositorios enlazados ni fuentes remotas. Esa cobertura parcial se debe mantener visible.

## Qué significa una tarea

- **Candidato histórico:** verificar si sigue vigente antes de planificar trabajo.
- **Decisión contradictoria o con evidencias insuficientes:** resolver la contradicción y aportar una fuente actual.
- **Tarea aprobada vigente:** recomendar su siguiente paso; esto no concede permisos para ejecutarlo.
- **Completada, rechazada o sustituida:** excluir de nuevas prioridades cuando su estado lo indique.

Cada elemento conserva identidad estable y una huella de evidencia. Dos espacios que usen el mismo ID de registro no deben confundirse. La prioridad es una regla transparente para ordenar trabajo, no una predicción de valor económico.

El importador no demuestra que un documento fuente original exista o que una integración se haya desplegado. Las referencias copiadas del registro se presentan como referencias, no como una nueva verificación de su contenido.

## Cerrar o aplazar un elemento

Crea un archivo de feedback fuera del repositorio. Copia el `id` y `evidence_hash` exactos del resultado:

```json
{
  "schema_version": 1,
  "tasks": {
    "ID_DEL_PLAN": {
      "status": "closed",
      "evidence_hash": "HASH_DEL_PLAN"
    }
  }
}
```

Vuelve a ejecutar con `--feedback /ruta/privada/feedback.json`. Un cierre con evidencia sin cambios se respeta. Si cambia la evidencia, el plan puede reabrir expresamente la revisión; no se presenta como si nunca se hubiera resuelto. Para aplazar, usa `status: "snoozed"` y `until: "AAAA-MM-DD"` según el esquema del módulo.

## Operación diaria

El CLI es una ejecución puntual. La revisión programada en ChatGPT, cuando esté activada por el propietario, utiliza las conexiones autorizadas y entrega su resultado privado en la conversación. No necesita copiar el conocimiento a GitHub Actions. El workflow público de CI ejecuta exclusivamente pruebas y ejemplos sintéticos.

No hay sincronización automática de feedback entre el CLI, ChatGPT y GitHub Issues. Las issues del repositorio describen capacidades por desarrollar; los planes diarios privados describen trabajo concreto sobre fuentes seleccionadas.
