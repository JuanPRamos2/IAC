# Bitácora de participación — Emiliano y Gerardo

**Expediente NEXUM — Equipo 03 · Tercer parcial y entrega final**

> Ricardo junta las cuatro medias páginas. Éstas son las dos nuestras.
> Las fechas de las corridas en la máquina virtual quedan pendientes de
> llenar cuando se hagan; todo lo demás está hecho y verificado.

---

## Emiliano Pascual Piñales Sánchez (#657657)

**Responsabilidad:** algoritmos, bases de datos y pruebas de rendimiento.

| Fecha | Qué |
|---|---|
| nov 2026 | **Algoritmo complejo.** Paquete `analitica`, expuesto en `GET /api/v1/algoritmos/analisis`. Cinco etapas: perfiles, agrupamiento k-medias con siembra k-means++ y *k* por silueta, desplazamiento de grupos, anomalías, tendencia con Theil-Sen y Mann-Kendall, y priorización por reglas. Sin numpy ni scipy, a propósito. |
| nov 2026 | **Generador de datos masivos.** 26 526 empleados, 136 unidades, 206 231 respuestas, 1 031 155 valores, 8 314 agregados. Con señal inyectada y anotada antes de correr el detector, para poder medir si lo encuentra. |
| nov 2026 | **Validación contra verdad inyectada**, que encontró **cuatro defectos del algoritmo**: k-medias agrupaba las unidades deterioradas y dentro de su grupo parecían normales; con ruido bajo todo salía significativo y marcaba 36 hallazgos de 0.12 puntos; el nivel salía de un promedio que diluía las señales fuertes; y «empeorar» se confundía con «bajar», así que una mejora en carga contaba como deterioro. |
| nov 2026 | **Tres hallazgos de rendimiento en PostgreSQL**, con su causa: un índice inerte porque el `ORDER BY` de una vista tenía una tercera clave; una subconsulta correlacionada sin índice que recorría una tabla 1 372 veces; y el panel de monitoreo reteniendo un obrero de gunicorn 1.4 s. Migración **018** con siete índices, cada uno con su motivo y su medición. |
| nov 2026 | **Seis índices que faltaban en MongoDB**, encontrados con análisis estático de las 44 consultas del código, porque MongoDB no está en el ambiente de medición. Cuatro de los seis eran ordenamientos sin índice, que es el caso que no se degrada sino que falla. |
| nov 2026 | **Pruebas de carga con Locust.** Tres corridas descartadas antes de la buena, con 34.6 %, 37.9 % y 42.0 % de error: medían el limitador, no el sistema. Corrida realista: p95 de 40 ms, 0.02 % de errores, recuperación inmediata. Corrida de esfuerzo: 197 pet/s, cero errores 5xx. |
| nov 2026 | **Consumo de recursos.** Medido en el backend de PostgreSQL, no en el cliente. CPU ≈ reloj en las seis consultas, cero derrames a `work_mem`, y el cálculo de agregados al 99 % de CPU: limitado por cómputo, no por disco. |
| nov 2026 | **Corte de 20 segundos por petición**, con su explicación: el análisis se detiene y no guarda un resultado a medias. |
| nov 2026 | **Tres errores de medición propios, corregidos**: el banco medía una unidad al azar (dos corridas daban 15.85 ms y 226.41 ms del mismo camino); la medición de CPU no superaba la resolución del reloj del kernel; y el conteo de filas leía estimaciones que decían 0 y 5 para tablas de 1 031 155 y 8 299 filas. |
| nov 2026 | **Capítulos del expediente**: modelo de agregados e índices, algoritmos, resultados de Locust, resultados de rendimiento, y las reglas de *k* mínimo 5 y ruido. |
| **pendiente** | Correr el generador y Locust **en la máquina virtual**, contra `https://34.41.26.94.sslip.io`, y guardar la salida y el CSV. |

---

## Gerardo Quiroga Ramírez (#650313)

**Responsabilidad:** aplicaciones cliente, evidencias, avisos, monitoreo e
integración completa.

| Fecha | Qué |
|---|---|
| nov 2026 | **Tres procesos integrales de punta a punta**: autorreporte, del análisis a la intervención aprobada, y reporte con evidencia en el bucket. Cada uno verificado **capa por capa**: la fila en PostgreSQL consultada aparte, el documento en MongoDB, la caché con su contador, la acción en bitácora, la notificación sin cifras ni personas, y la visualización. |
| nov 2026 | **Los mismos procesos conducidos desde el portal** (10 casos): que cada uno tiene sus pantallas, que el perfil correcto entra, que el equivocado no y se le dice por qué, y que sin sesión no se abre ninguna. |
| nov 2026 | **Cuatro defectos de integración.** El especialista podía aprobar su propio plan → migración **019**, con el autor en la misma transacción que el plan (no en la bitácora: un control de acceso no puede depender de una escritura best-effort) y una segunda cuenta aprobadora, porque con un solo especialista el control habría bloqueado todas las aprobaciones. `documents-service` daba 500 con un error de Python filtrado. La ruta del blob se calculaba dos veces y coincidía por casualidad. Y cualquier camino de escritura podía romper la invariante de la jerarquía → migración **020**. |
| nov 2026 | **Validación de evidencias movida del portal al servicio.** Antes sólo el portal podía subir evidencia —el escritorio y el móvil hablan con los microservicios, no con el portal— y la validación era propiedad de una pantalla, no del sistema. |
| nov 2026 | **Google Cloud Storage**: firma de URLs con vencimiento, y comprobación de que el objeto exista antes de firmar. |
| nov 2026 | **Estado del bucket en las sondas de salud**, como dependencia opcional. Sin esto, con el almacén caído el servicio decía «listo», aceptaba una carga y dejaba un documento registrado cuyo archivo no existe. |
| nov 2026 | **Las sondas completan los siete elementos**: proceso, PostgreSQL, MongoDB, Redis, bucket, tiempo y versión. Y declaran lo que **no** usan, porque una clave ausente no puede significar a la vez «no tiene bucket» y «no se comprobó». |
| nov 2026 | **Historial de disponibilidad en el panel**: ventana de 60 minutos en cubetas de un minuto. `degradado` cuenta como disponible, `desconocido` no cuenta en ningún lado, las muestras se reportan junto al porcentaje, y sólo cuentan los sondeos reales. |
| nov 2026 | **Defecto en el panel web**: leía el estado del código HTTP en lugar del cuerpo, y por eso mostraba lo contrario de lo que pasaba — un servicio `degradado` (200) salía «Disponible» y uno `no_listo` (503) salía «Degradado». |
| nov 2026 | **Las seis situaciones de fallo**, incluida la que faltaba: una petición que excede el tiempo máximo. Tres límites escalonados —15 s en PostgreSQL, 20 s por petición, 30 s de gunicorn como última red—, verificado contra un servidor real: 503 con código, mensaje, `Retry-After` e identificador de correlación. |
| nov 2026 | **Capítulos del expediente**: mapa de los 24 microservicios, monitoreo, manual técnico de la laptop, manual de usuario por perfil, MongoDB, contratos XML del escritorio, y la mitad del diseño del bucket (el servicio que guarda y firma). |
| nov 2026 | **Registro de incidencias abierto** con las tres primeras. |
| **pendiente** | Emulador con `ana.perez` recorriendo la encuesta (variante `debug`); grabación del escritorio con Mariana en una pantalla que se vea en XML; grabación de una pantalla del portal que no sea el login y la bandeja de notificaciones; capturas de Swagger de la URL firmada y de evidencias con el archivo cargado. |

---

## Lo que hicimos los dos

- **629 pruebas**, de las cuales 627 pasan y 2 se omiten por el ambiente
  (sin Tkinter en este interprete; un compose que no monta semilla). Cero
  fallos.
- **Diecinueve defectos encontrados y corregidos**, ninguno visible con
  los datos de demostración.
- **Tres migraciones nuevas**: 018 (análisis complejo e índices), 019
  (cuatro ojos) y 020 (la invariante de la jerarquía pasa de comprobarse a
  impedirse).
- Un hábito que valió la pena y costó dos entregas aprenderlo:
  **verificar contra el documento de requisitos, no contra el resumen
  propio de los requisitos**. Las dos veces que dimos algo por terminado
  leyendo nuestro resumen, había hueco.
