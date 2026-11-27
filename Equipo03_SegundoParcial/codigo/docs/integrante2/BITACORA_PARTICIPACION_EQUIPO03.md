# Bitácora de Participación — Equipo 03 (Bienestar Nexum)

**Materia:** Integración de Aplicaciones Computacionales · UDEM  
**Integración y compilación de bitácoras:** Integrante 2  
**Instrucción de entrega:** Cuatro medias páginas (una por integrante) revisadas por todo el equipo antes de la entrega final.

---

## 1. Media página — Integrante 2 · Integrante 2
**Responsabilidad:** Seguridad Avanzada, Contratos JSON/OpenAPI/XSD, Capa Común (`comun-node` / `comun`), 6 Microservicios Node.js y Recuperación ante Fallos.

- **12–13 de octubre de 2026 (Parcial 1–2):** Diseñé e implementé los modelos de PostgreSQL (`04_catalogos_crud.sql`) y MongoDB (`solicitudes_apoyo`, `eventos_proceso`, índices y agregaciones), construí `catalog-service` (`8103`) y `main-process-service` (`8104`) con dualidad JSON/XML, Swagger OpenAPI 3.0.3 y 29 pruebas iniciales, además de homologar los contratos XSD.
- **15 de noviembre de 2026 (Integración Parcial 2):** Implementé el conjunto completo de **6 microservicios Node.js** (`catalog`, `main-process`, `survey`, `indicators`, `support`, `organizational` en puertos `8103, 8104, 8112, 8113, 8116, 8117`), `comun-node` (`Proxy` estricto de permisos, parser `cuerpoXml`, umbral $k \ge 5$, regla D-01) y la migración `017_endurecimiento_privacidad_node.sql`.
- **17 de noviembre de 2026 (Tercer Parcial — Seguridad y Fallos):** Desarrollé la migración `018_tercer_parcial_seguridad_y_buckets.sql` (`usuarios.fn_restablecer_contrasena` `SECURITY DEFINER` y 6 códigos de bitácora), el flujo OTP en `auth-service`, defensa anti-XXE en Python y Node, adaptador dual local/GCS con URLs firmadas y 10 metadatos, `notificar_evento_interno` HMAC-SHA256, timeouts SQL (`PG_STATEMENT_TIMEOUT_MS=5000`), sondas `/health/live` + `/health/ready`, generación de contratos JSON Schema y la suite `test_seguridad_y_fallos_t3.py` (13/13).
- **24–25 de noviembre de 2026 (Compatibilidad GCP y Redis):** Alineé `documents-service` y `reports-service` con el despliegue GCP (`nexum-610248-evidencias`, `GCS_BUCKET`, `/archivos/<sha256>/url`, `CONNECTION LIMIT 80`, semillas `91–94`), corregí el límite de reintentos en `comun-node/src/redis.js` para lograr autorecuperación sin `docker restart`, y validé los 24 microservicios + caída real de Redis en Docker.
- **26 de noviembre de 2026 (Entrega Final):** Integré la rama común con `analitica`, Locust y monitoreo (`cf42fff`), redacté los capítulos técnicos de Contratos JSON, Swagger, Seguridad, Diseño de Redis y Plan de Pruebas Auth/Roles, preparé láminas, guion de ensayo y compilé esta bitácora grupal.

---

## 2. Media página — Integrante 1
**Responsabilidad:** Infraestructura GCP, Identidad/RBAC base, Consentimiento, Gobernanza, Contenedores y Monitoreo.

> *(Espacio listo para pegar la media página confirmada por el Integrante 1 con sus fechas y entregas: `auth-service`, `users-service`, `consent-service`, `privacy-service`, `audit-service`, `data-governance-service`, creación de VM `nexum-equipo03`, IP estática `34.41.26.94`, firewall `nexum-https`, bucket `nexum-610248-evidencias`, Caddy HTTPS, `docker-compose.gcp.yml`, migración `022`, panel de monitoreo e integración final).*

---

## 3. Media página — Integrante 3 () · Integrante 3
**Responsabilidad:** Algoritmo Complejo (`analitica`), Privacidad Diferencial, Tendencias, Grandes Volúmenes y Pruebas de Carga Locust.

> *(Espacio listo para pegar la media página confirmada por Integrante 3 con sus fechas y entregas: `queries-service`, `reports-service`, `algorithms-service`, `trends-service`, `interventions-service`, `export-service`, paquete `analitica` —agrupamiento, anomalías y tendencia Theil-Sen/Mann-Kendall—, `exigir_tiempo` 20 s, migraciones `019`–`021`, `scripts/datos_masivos.py`, `scripts/rendimiento.py`, `pruebas/carga/locustfile.py`, documento `Algoritmo_Complejo_Equipo03.md` y corrida en la VM).*

---

## 4. Media página — Integrante 4 () · Integrante 4
**Responsabilidad:** Clientes Web, Móvil Android y Escritorio XML, Documentos/Buckets, Notificaciones, Sincronización y Monitoreo.

> *(Espacio listo para pegar la media página confirmada por Integrante 4 con sus fechas y entregas: `documents-service`, `notifications-service`, `sync-service`, `configuration-service`, `monitoring-service`, `integration-service`, portal web `apps/web/`, app Android Kotlin `apps/movil/`, app Escritorio Tkinter XML `apps/escritorio/`, corrección de `evidencias.py`, registro de incidencias y manuales).*
