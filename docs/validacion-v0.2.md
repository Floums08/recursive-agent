# Validación de la versión 0.2

Fecha: 3 de octubre de 2026. Runtime local: Python 3.12.14.

## Implementado y comprobado

- Motor de experimentación integrado con un arreglo al presupuesto de propuestas: el límite configurado llega al proveedor, incluso por encima de 100 kB, y no puede ampliarse mediante opciones de llamada.
- Planificador local de espacios laborales seleccionados, con fuentes, fechas, identidad estable, feedback, reapertura por evidencia nueva y hasta tres prioridades.
- Diversificación por espacio y ordenación por observación reciente cuando las puntuaciones empatan; esa fecha no convierte una observación en vigente.
- JSON estricto, errores de datos visibles, exclusión de espacios personales y salidas privadas fuera del código y de la fuente.
- Ejemplos ficticios, instrucciones de uso y 16 tareas genéricas de desarrollo con sus issues.

## Pruebas locales

`python3 -m unittest discover -s tests -q`: **96 pruebas aprobadas**, ninguna omitida.

| Grupo | Pruebas |
|---|---:|
| Motor | 32 |
| Evaluadores | 13 |
| Proveedores | 16 |
| Planificador | 35 |

El conector HTTP se comprueba con un servidor temporal en loopback. La demostración CLI completa los tres candidatos sintéticos sin modificar su fuente. El planificador CLI funciona con el ejemplo ficticio distribuido y rechaza salidas dentro del repositorio público.

Una revisión independiente detectó que una referencia vacía podía contarse como evidencia. Se corrigió y se añadió una prueba: un registro sin referencia utilizable se deriva a verificación, aunque sus campos de estado afirmen vigencia.

## Límites

No se han validado inferencias con un modelo real ni ejecución con un daemon Docker. Las comprobaciones Docker siguen siendo simuladas. La lectura de estados de conocimiento no equivale a comprobar todos los originales, todas las conversaciones, APIs o despliegues. El planificador no ejecuta las recomendaciones.

CI está configurada en Python 3.11 y 3.12 con acceso de lectura y datos sintéticos. Los resultados de GitHub Actions, cuando terminen, son la evidencia del entorno remoto; esta nota describe las pruebas locales. Ningún workflow de este repositorio consulta conocimiento privado o publica planes de clientes.
