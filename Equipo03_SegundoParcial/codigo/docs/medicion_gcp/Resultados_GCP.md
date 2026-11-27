# NEXUM — Equipo 03 | Resultados de pruebas en GCP
Integrante 3
26 de noviembre de 2026 (hora de Monterrey; registros del 27 de noviembre en UTC).

## Alcance
Pruebas en la VM independiente maquina-nexum, proyecto integracion-505221, Ubuntu 22.04, 2 vCPU y 3.8 GiB de RAM. Se utilizó el ZIP del tercer parcial, con configuración Docker separada y una ruta de análisis agregada al portal de pruebas. Se levantaron diez microservicios, tres bases de datos y el portal. No se ha verificado equivalencia con los últimos commits del resto del equipo ni con el despliegue oficial. El acceso al portal de pruebas se hizo por túnel SSH. Los datos son sintéticos.

## Datos masivos y algoritmo
- Se generaron 120 unidades organizacionales, 25,365 empleados (23,314 con consentimiento), 12 campañas, 202,435 respuestas y 1,012,175 valores nuevos. Inserción de respuestas: 42.67 s.
- La generación se interrumpió en la fase de agregación. Se reanudó esa fase sin volver a insertar empleados ni respuestas. Se calcularon 7,920 agregados en 369.35 s; duración de la reanudación: 369.6 s.
- Totales después de la reanudación: 26,526 empleados (consulta de comprobación), 206,315 respuestas, 1,031,575 valores y 8,280 agregados; ruido medio 0.0369, mínimo 0.0127. Cinco unidades anómalas y cinco con deterioro inyectado según el registro del generador; no se verificó aquí la precisión de la detección contra la verdad inyectada.
- En el portal de pruebas: CAMP-M017, 110 unidades analizadas, 148.86 ms, origen calculado. La tabla muestra los niveles prioritario, atención e informativo, agrupamiento y puntaje. Esta medición no corresponde a una prueba del límite de 20 segundos.
- Durante la medición posterior se registraron 8,286 agregados; corresponde a otro momento de la ejecución.

## Locust — microservicios
| Métrica | Resultado |
|---|---:|
| Usuarios concurrentes máximos registrados | 140 |
| Peticiones | 5,297 |
| Fallos | 1 (0.02%) |
| Peticiones/s promedio | 10.6 |
| Promedio | 396.24 ms |
| Mediana | 20 ms |
| p95 | 1,600 ms |
| p99 | 12,000 ms |
| Máximo | 14,773.31 ms |

El único fallo fue HTTP 429 en el login, por lo que un usuario virtual no ejecutó sus tareas. Se cumple el criterio de errores < 1%; no se cumple p95 < 800 ms. El p95 del análisis sin caché fue 12,000 ms, tendencias de descensos 7,100 ms y consentimiento 7,000 ms. El historial confirma degradación con 140 usuarios y reducción de latencia al regresar a 10 usuarios: p95 de 14,000 ms en una muestra de alta carga y 70 ms en una muestra posterior de recuperación. No se determinó el límite máximo de capacidad. Se incluyen CSV completos y reporte HTML.

## Rendimiento e índices
- Tablero de una unidad: mediana 0.43 ms en los tres tamaños probados. En la medición del plan sobre la unidad grande: 0.39 ms, p95 0.40 ms.
- Función fn_calcular_agregado_protegido: mediana 40.23 ms.
- Índice ix_consent_vigente: 18.17 ms en el plan registrado, sin ordenamiento de toda la tabla.
- Comparación de consulta con y sin caché: 1.405 ms sin caché frente a 0.369 ms con caché (3.8x). Es una medición distinta de la latencia HTTP de Locust.
- Memoria pico del cliente del generador reanudado: 25.2 MB; cliente del script de rendimiento: 36.4 MB. Tamaño de base reportado tras agregados: 179 MB.
- Muestra puntual durante rendimiento: PostgreSQL 74.49% CPU / 208.5 MiB; Redis 0.14% / 7.348 MiB; algorithms-service 0.13% / 106.6 MiB. No son picos de toda la corrida; no se midió el proceso PostgreSQL individual dentro del contenedor.

## Pendientes y entrega
- Ejecutar Locust contra https://34.41.26.94.sslip.io con autorización/coordinación del responsable, guardar CSV y HTML. No se ha realizado esa prueba en esta sesión.
- Confirmar que los cambios del portal de pruebas y los scripts adaptados se integren con el repositorio final. No se han incorporado a GitHub ni se incluye aquí el código modificado de la VM.
- Incorporar estos resultados a los capítulos de Locust y rendimiento y a las láminas del equipo, distinguiendo las mediciones anteriores de las de esta VM. Confirmar la evidencia del análisis del despliegue oficial si el equipo exige una única instancia compartida.
- Explicar y demostrar el corte de 20 segundos conforme al guion del equipo; la prueba específica no se repitió en esta VM. Completar reflexión individual, bitácora y revisiones/ensayo compartidos.

## Evidencias
La carpeta capturas contiene las siete imágenes originales de la sesión. informes/nube contiene los once archivos originales del archivo descargado de la VM. Las cifras del informe se derivan de esos registros y de las comprobaciones de la sesión.
