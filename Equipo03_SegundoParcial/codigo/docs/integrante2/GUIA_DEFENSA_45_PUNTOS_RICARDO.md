# Guía de Defensa Individual (45 Puntos) y Demostración en Vivo — Ricardo Sánchez (#583928)

**Propósito:** Preparar a **Ricardo Arath Sánchez Aguirre (#583928)** (Integrante 2) para responder con precisión las **3 preguntas individuales de 15 pts c/u (45 pts)** —incluyendo preguntas sobre módulos de sus compañeros— y ejecutar sin tropiezos el **guion de tolerancia a fallos en vivo**.  
**Regla de oro en la defensa:** Citar únicamente rutas, tablas, funciones y comportamientos reales del repositorio (`Equipo03_SegundoParcial/codigo/`).

---

## 1. Mapa Completo del Sistema (Qué hizo cada integrante y dónde está en el código)

### 1.1 Resumen de los 4 integrantes

| Integrante | Responsabilidad principal en el código | Servicios / Componentes clave |
|---|---|---|
| **I1 — Juan Pablo Ramos (#610248)** | Identidad, RBAC, consentimiento, privacidad, auditoría, gobernanza, ambientes Docker/Nginx/CI y preparación Cloud | **6 servicios Python:** `auth-service` (`8101`), `users-service` (`8102`), `consent-service` (`8110`), `privacy-service` (`8111`), `audit-service` (`8118`), `data-governance-service` (`8119`). **Infra:** `infra/compose/*.yml`, `infra/nginx/*.conf`, `.github/workflows/ci.yml` y `microservicios.yml`. |
| **I2 — Ricardo Arath Sánchez (#583928)** | **6 microservicios en Node.js**, paridad `comun-node/`, contratos OpenAPI/JSON/XSD, seguridad avanzada y pruebas de seguridad/fallos | **6 servicios Node.js:** `catalog-service` (`8103`), `main-process-service` (`8104`), `survey-service` (`8112`), `indicators-service` (`8113`), `support-service` (`8116`), `organizational-service` (`8117`). **Capa:** `apps/microservicios/comun-node/`, `contratos/`, `db/migraciones/017_*.sql` y `018_*.sql`, `pruebas/test_seguridad_y_fallos_t3.py`. |
| **I3 — Emiliano Pascual Piñales (#657657)** | Analítica protegida, algoritmos de riesgo, tendencias contra ruido, intervenciones, exportación y grandes volúmenes | **6 servicios Python:** `queries-service` (`8107`), `reports-service` (`8108`), `algorithms-service` (`8109`), `trends-service` (`8114`), `interventions-service` (`8115`), `export-service` (`8121`). **Motor SQL:** `agregado.fn_ruido_laplace`, `agregado.fn_calcular_agregado_protegido`, `riesgo.fn_evaluar_unidad`. **Volumen:** `db/semilla/02_volumen_sintetico.sql` y `pruebas/test_limite_de_consumo.py`. |
| **I4 — Gerardo Quiroga (#650313)** | Documentos/buckets, notificaciones, sincronización offline, configuración, monitoreo, integración XSD y clientes | **6 servicios Python:** `documents-service` (`8105`), `notifications-service` (`8106`), `sync-service` (`8120`), `configuration-service` (`8122`), `monitoring-service` (`8123`), `integration-service` (`8124`). **Clientes:** Web (`apps/web/`, `:8000`), Escritorio (`apps/escritorio/`, XML), Móvil Android (`apps/movil/`, Kotlin JSON). |

### 1.2 Qué debes saber explicar del módulo de cada compañero

#### A. Módulo de I1 (Infraestructura, GCP/GCE/GCS, Caddy/Nginx, Monitoreo y Seguridad Base)
- **Ambientes aislados y semillas ordenadas:** `scripts/ambiente.sh` combina `infra/compose/docker-compose.base.yml` + `docker-compose.{developer|staging|production}.yml` + `docker-compose.microservicios.yml`. En `docker-compose.yml`, `docker-compose.developer.yml` y `docker-compose.staging.yml`, las migraciones `001`–`022` corren antes de `90_permisos.sh` y las semillas van como `91_semilla.sql`–`94_semilla.sql`. En `production`, CI (`.github/workflows/ci.yml`) verifica que `datos` (PostgreSQL) **no publique puertos** y exige `VERSION` explícita.
- **Despliegue real en GCP (`nexum-equipo03`, `us-central1-a`):**
  - `docker-compose.gcp.yml` se aplica encima de `docker-compose.yml` (`docker compose -f docker-compose.yml -f docker-compose.gcp.yml up -d --build`): cierra todos los puertos públicos de bases y los 24 microservicios (`ports: !reset []`), restringe `web` a `127.0.0.1:8000:8000` con `/mnt/evidencias:/var/lib/bienestar/evidencias`, y monta en `documents-service` la llave de cuenta de servicio (`/opt/nexum/signer.json:/run/gcp/signer.json:ro`) junto con `GCS_BUCKET=nexum-610248-evidencias` y `GOOGLE_APPLICATION_CREDENTIALS=/run/gcp/signer.json`.
  - `infra/caddy/Caddyfile` publica el portal en `34.41.26.94.sslip.io` con certificado TLS automático de Let's Encrypt y `reverse_proxy 127.0.0.1:8000`.
  - `infra/nginx/production.conf` documenta además la terminación TLS tras Cloud Load Balancing con cabeceras de seguridad (`Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`).
  - `documents-service/archivos.py` y `reports-service/app.py` aceptan indistintamente `GCS_BUCKET` o `GCS_BUCKET_NAME` con `ALMACEN_MODO=local|gcs` y firman URLs `v4` (`blob.generate_signed_url`) sin almacenar binarios en PostgreSQL ni MongoDB.
- **Menor privilegio y capacidad de conexiones en BD:** todos los servicios se conectan con el rol `bienestar_app` (nunca `postgres` ni `bienestar_motor`), configurado con `CONNECTION LIMIT 80` en `db/esquema/00_rol_aplicacion.sh` para soportar simultáneamente los 18 servicios Python (2 workers c/u), los 6 Node y el portal web (4 workers). `bienestar_app` no puede hacer `SELECT` sobre `autoreporte.respuesta_detalle` ni `DELETE` sobre `auditoria.bitacora`.
- **Monitoreo (`monitoring-service` `8123`):** consulta `/health/ready` y `/health/live` de los **24 servicios** (`LISTADO` en `monitoring-service/app.py`), detecta bucles de reinicio comparando el campo `instancia` (UUID generado al arrancar cada proceso en `comun/servicio.py` y `comun-node/src/servicio.js`) y evalúa alertas operativas como `PRESUPUESTO_AGOTADO`.

#### B. Módulo de I2 (Tu módulo — Backend Node.js, Seguridad y Contratos)
- **6 servicios en Node.js** (`8103, 8104, 8112, 8113, 8116, 8117`) con paridad total frente a los **18 de Python**: mismo `JWT_SECRETO`, misma sesión en Redis (`sesion:<jti>` y `revocado:<jti>`), misma consulta RBAC en vivo a `usuarios.perfil_permiso`, mismo sobre de error y misma serialización XML + anti-XXE. Además, `comun-node/src/redis.js` usa `estrategiaReintentoRedis` sin límite de 10 reintentos (backoff máx. 3000 ms) y `obtenerRedis()` recrea clientes que entren en estado `"end"`, garantizando autorecuperación tras reiniciar Redis.
- **Contratos:** **109** JSON Schemas en `contratos/json/`, **16** XSD en `contratos/xml/` (`http://nexum.com.mx/bienestar/v1`), OpenAPI 3.0.3 + Swagger UI local (`/docs`, sin CDN).
- **Seguridad Tercer Parcial:** rotación de refresh tokens, bloqueo por intentos fallidos, flujo OTP de recuperación (`POST /api/v1/auth/recuperar/solicitar` y `/confirmar` con SHA-256 en Redis, bloqueo a los 3 fallos, `usuarios.fn_restablecer_contrasena` `SECURITY DEFINER`, revocación de sesiones), bitácora de `ACCESO_DENEGADO` / `RATE_LIMIT_EXCEDIDO` / `ARCHIVO_RECHAZADO` / `URL_FIRMADA_GENERADA` (migración 018) y `notificar_evento_interno` firmado con HMAC-SHA256.

#### C. Módulo de I3 (Algoritmos, Privacidad Diferencial, Tendencias y Volumen)
- **Privacidad diferencial + umbral $k \ge 5$:** `agregado.fn_calcular_agregado_protegido` invoca `agregado.fn_ruido_laplace` dentro de PostgreSQL (bajo `bienestar_motor`). Si el grupo tiene $n < 5$ respuestas, publica `GRUPO_INSUFICIENTE` con valor `NULL` (en XML `xsi:nil="true"`).
- **¿Por qué `queries-service`, `algorithms-service` y `trends-service` no gastan épsilon?** Leen únicamente `agregado.resultado_protegido` ya publicado (`PUBLICADO`). Recalcular ruido al consultar agotaría el presupuesto $\varepsilon$ en cada recarga.
- **`algorithms-service` (`8109`) y paquete `analitica`:** ejecuta `riesgo.fn_evaluar_unidad` y expone `GET /api/v1/algoritmos/analisis` combinando agrupamiento, detección de anomalías contra grupo de pares y tendencia (Theil-Sen y Mann-Kendall) sobre agregados ya protegidos (`docs/Algoritmo_Complejo_Equipo03.md`), con corte seguro a `20 s` vía `comun/servicio.py::exigir_tiempo` (`503 TIEMPO_EXCEDIDO` sin escrituras parciales).
- **`trends-service` (`8114`):** exige mínimo 3 puntos (`MINIMO_PUNTOS = 3`) y solo clasifica un cambio entre campañas como real si $|\Delta| > b\sqrt{2}$ (donde $b$ es la escala de Laplace); nunca extrapola hacia el futuro.
- **Grandes volúmenes, rendimiento y Locust:** además de `02_volumen_sintetico.sql`, la rama integrada incluye `scripts/datos_masivos.py` (26,526 empleados, 206,231 respuestas, 1,031,155 valores de detalle), índices de la migración `021_analisis_complejo_y_rendimiento.sql`, mediciones en `scripts/rendimiento.py` (`docs/Rendimiento_y_Carga_Equipo03.md`), escenario Locust con 4 perfiles en `pruebas/carga/locustfile.py`, y `PG_STATEMENT_TIMEOUT_MS=5000`. *(Queda pendiente ejecutar la corrida final de Locust contra la URL pública de GCP para guardar el CSV).*

#### D. Módulo de I4 (Clientes Web, Escritorio, Android y 3 Flujos E2E)
- **Web (`apps/web/`, puerto `8000`):** Flask + Jinja2 + Gunicorn + Highcharts local. Módulos M01–M12. Guarda el JWT en cookie `HttpOnly` (`bienestar_sesion`). Si un microservicio cae (ej. `users-service`), degrada leyendo PostgreSQL (probado en `pruebas/test_degradacion_web.py`); si cae `notifications-service`, avisa explícitamente porque las notificaciones solo viven en MongoDB con TTL de 90 días.
- **Móvil Android (`apps/movil/`):** Kotlin + Jetpack Compose. Consume **exclusivamente JSON** contra 5 servicios (`auth`, `catalog`, `main-process`, `documents`, `notifications`). Toma fotos con `ACTION_IMAGE_CAPTURE`, **elimina metadatos EXIF** (GPS, modelo) antes de subir, y guarda el JWT y borrador en `EncryptedSharedPreferences` con `allowBackup="false"`.
- **Escritorio (`apps/escritorio/`):** Python + Tkinter (`cliente.py` separado de `app.py`). Consume **exclusivamente XML** y valida cada respuesta contra `contratos/xml/*.xsd` usando `lxml`, distinguiendo `xsi:nil="true"` ("suprimido") de `""` ("vacío").
- **3 Flujos End-to-End (E2E):**
  1. **Flujo Colaborador (Móvil / Web):** Login (`auth-service`) -> Ver campaña y cuestionario (`catalog-service` / `survey-service`) -> Responder encuesta sin `empleado_id` (`main-process-service` / `survey-service` -> `fn_registrar_autoreporte` + MongoDB) -> Levantar solicitud de apoyo (`support-service` / `main-process-service`) + adjuntar evidencia fotográfica sin EXIF (`documents-service`).
  2. **Flujo Especialista / Líder (Escritorio XML / Web):** Login -> Consultar tablero protegido con umbral $k \ge 5$ (`indicators-service` / `queries-service`) -> Evaluar riesgo y tendencias (`algorithms-service` / `trends-service`) -> Crear/aprobar plan organizacional (`interventions-service`) -> Atender solicitudes de apoyo (`support-service`) y consultar evidencias mediante URL firmada (`documents-service`).
  3. **Flujo Auditor / Administrador (Web / Servicios):** Administrar catálogos y unidades con plantilla $\ge 5$ (`catalog-service`, `organizational-service`) -> Verificar garantías `gobernanza.fn_verificar_garantias()` (`data-governance-service`) -> Revisar bitácora y `correlacion_id` (`audit-service`) -> Supervisar salud, alertas y reinicios (`monitoring-service`).

---

## 2. Banco de Preguntas Tipo Defensa (15 pts c/u) — Respuestas de 60 segundos

1. **¿Por qué un JWT con firma válida no basta en los 24 microservicios y qué pasa si Redis cae?**
   - *Respuesta:* Porque la revocación inmediata (en `logout`, rotación de refresh token o cambio de contraseña vía OTP) requiere estado compartido. `comun/seguridad.py::sesion_viva` y `comun-node/src/autenticacion.js::sesionViva` verifican que `revocado:{jti}` no exista y `sesion:{jti}` sí exista en Redis. Si Redis cae, los microservicios responden `503 DEPENDENCIA_NO_DISPONIBLE` (fail-closed) porque atienden clientes externos; en cambio el portal web (`apps/web/app/seguridad.py`) degrada aceptando firma/vigencia de la cookie `HttpOnly` para no dejar inoperante la UI.

2. **¿Cómo garantizan que quitarle un permiso a un rol o bloquear un usuario surta efecto de inmediato?**
   - *Respuesta:* Los permisos **no viajan dentro del JWT** (`_emitir` en `auth-service/app.py` solo incluye `sub`, `perfil_id`, `perfil`, `unidad_alcance`, `jti`, `tipo`). En cada petición, `@requiere_permiso` (Python) y `autorizar` (Node) consultan `usuarios.perfil_permiso JOIN usuarios.permiso`. Si falta el permiso, devuelven `403 SIN_PERMISO` y auditan `ACCESO_DENEGADO` en `auditoria.bitacora`.

3. **¿Cómo funciona la recuperación de acceso (OTP) sin permitir enumeración de cuentas ni escalación de privilegios?**
   - *Respuesta:* `POST /api/v1/auth/recuperar/solicitar` devuelve el mismo `200` genérico exista o no el correo. Si existe, genera un OTP de 6 dígitos con `secrets.randbelow`, guarda solo su SHA-256 en Redis (`recuperacion:<correo>`, TTL 600 s) y lo despacha por `notificar_evento_interno` (HMAC) y SMTP opcional. En `/recuperar/confirmar`, tras 3 códigos erróneos borra el OTP y responde `429 CODIGO_BLOQUEADO`. Al acertar, llama a `usuarios.fn_restablecer_contrasena` (`SECURITY DEFINER` de `bienestar_motor` en migración 018) para calcular bcrypt dentro de PostgreSQL y revoca todas las sesiones activas previas en Redis (`_revocar_sesiones_usuario`).

4. **¿Cómo protegen el sistema contra XXE, regla D-01 e inferencia de grupos pequeños?**
   - *Respuesta:* Contra XXE, `xmlizar.py::de_xml` y `cuerpoXml.js::deXml` rechazan `<!DOCTYPE` y `<!ENTITY` antes de parsear (`400`). Contra D-01, `main-process-service` rechaza `empleado_id` con `400 PRIVACIDAD_D01`, `mongo.py`/`mongo.js` validan recursivamente `CAMPOS_PROHIBIDOS` (`422 CAMPO_PROHIBIDO`) y `db/mongo/init.js` aplica `$jsonSchema` con `additionalProperties: false`. Contra inferencia, `organizational-service` exige `plantilla_declarada >= 5`, `indicators-service` suprime si $n < 5$ y `bienestar_app` no puede hacer `SELECT` en `autoreporte.respuesta_detalle`.

5. **¿Cómo manejan la subida y descarga de archivos en `documents-service` sin guardar binarios en BD ni exponer el bucket?**
   - *Respuesta:* `documents-service/archivos.py` tiene adaptador dual `ALMACEN_MODO=local|gcs` y lee tanto `GCS_BUCKET_NAME` como `GCS_BUCKET` (usado en `docker-compose.gcp.yml` con `nexum-610248-evidencias` y `/run/gcp/signer.json`). Valida tamaño (8 MB / 4 MB en apoyo), extensión permitida y **magic bytes** (`FIRMAS`, auditando `ARCHIVO_RECHAZADO` si se disfraza un `.exe` como `.pdf`), limpia nombres contra path traversal y guarda por hash SHA-256 (`.parcial` + rename atómico). MongoDB solo almacena los **10 metadatos de rúbrica** (`identificador, ruta, tipo, tamano, propietario, fecha, hash, nivel_privacidad, estado, metadatos`). Para descargar sin abrir el bucket al público, soporta tanto `GET /api/v1/documentos/archivos/<sha256>/url` (URL firmada v4 de GCS por 600 s, o `409 URL_NO_DISPONIBLE` sin bucket/llave) como `GET /api/v1/documentos/<documento_id>/url-firmada` (v4 GCS o HMAC-SHA256 local con TTL acotado); si caduca devuelve `403 URL_EXPIRADA`, si se altera la firma `403 FIRMA_INVALIDA`, y si el archivo se alteró en disco `409 ARCHIVO_ALTERADO`.

6. **¿Cómo evitan que una falla en un servicio satélite (notificaciones, bitácora, Redis de rate-limit o bucket) tumbe la operación principal?**
   - *Respuesta:* Aplicamos **aislamiento de fallos no esenciales**: `notificar_evento_interno` (Python/Node) tiene timeout de `1.5 s`, firma HMAC y captura toda excepción devolviendo `False`. `_registrar_acceso_denegado` y `registrarBitacora` capturan errores para que un fallo en `auditoria.bitacora` no convierta un `403` en `500`. `limite_consumo` deja pasar si Redis cae. Y `/health/ready` distingue dependencias opcionales (`200 degradado`) de esenciales (`503 no_listo`).

---

## 3. Guion Paso a Paso: Demostración de Tolerancia a Fallos en Vivo

> **Preparación previa:** Tener el stack arriba (`docker compose up -d --wait` o `./scripts/ambiente.sh developer arriba`) y una variable `TOKEN` con un JWT válido de administrador/especialista y `TOKEN_COLAB` de colaborador.

### Paso 1 — Detener un microservicio (`notifications-service`) y probar resiliencia
1. Detener `notifications-service`:
   ```bash
   docker compose stop notifications-service
   ```
2. Ejecutar una operación que dispare notificación interna (por ejemplo `POST /api/v1/auth/recuperar/solicitar` en `:8101` o registrar respuesta en `main-process-service` `:8104`).
3. **Qué señalar al evaluador:** la operación principal responde `200`/`201` con éxito porque `notificador.py` / `notificador.js` capturan el fallo de red sin lanzar excepción (`timeout=1.5s`). En logs aparece la advertencia `[NOTIFICADOR]`.
4. Verificar en `monitoring-service` (`GET http://localhost:8123/api/v1/monitoreo/salud` con Bearer) que `notifications-service` aparece caído sin tumbar a `monitoring-service`.
5. Volver a encender: `docker compose start notifications-service`.

### Paso 2 — Revocar token (`logout`) y probar rechazo inmediato en Python y Node
1. Validar que el token funciona en Node (`GET http://localhost:8103/api/v1/catalogos/campanias`) -> `200`.
2. Hacer `POST http://localhost:8101/api/v1/auth/logout` con ese token -> `200 {"revocado": true}`.
3. Volver a llamar a Python (`GET http://localhost:8101/api/v1/auth/validar`) y a Node (`GET http://localhost:8103/api/v1/catalogos/campanias`) con el **mismo token**:
   - **Qué señalar:** ambos responden inmediatamente `401` con `error.codigo == "SESION_REVOCADA"`, demostrando la revocación distribuida en Redis entre Python y Node.

### Paso 3 — Apagar Redis y contrastar fail-closed (microservicios) vs. degradación (portal web)
1. Detener Redis:
   ```bash
   docker compose stop cache
   ```
2. Llamar a un microservicio protegido (ej. `GET http://localhost:8103/api/v1/catalogos/unidades` con token válido):
   - **Qué señalar:** responde `503` `DEPENDENCIA_NO_DISPONIBLE` (fail-closed: ante la duda de si la sesión fue revocada, un API externa no abre).
3. Navegar en el portal web (`http://localhost:8000`) con sesión iniciada:
   - **Qué señalar:** el portal degrada de forma controlada validando firma/vigencia de la cookie `HttpOnly` (`apps/web/app/seguridad.py`) y registra advertencia en logs sin dejar al usuario sin pantalla.
4. Encender Redis: `docker compose start cache`.

### Paso 4 — Payload XML inválido / ataque XXE
1. Enviar payload XXE (`<!DOCTYPE` / `<!ENTITY`) a un servicio Node (`http://localhost:8103/api/v1/catalogos/unidades`) o Python con `Content-Type: application/xml`:
   ```bash
   curl -i -X POST http://localhost:8103/api/v1/catalogos/unidades \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/xml" \
     -d '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><unidad><nombre>&xxe;</nombre></unidad>'
   ```
2. **Qué señalar:** rechazo inmediato `400` (`XML_INSEGURO` en Node / `XML_MAL_FORMADO` en Python) antes de invocar al parser, sin fugas de archivos del servidor ni error `500`.

### Paso 5 — Archivo alterado (magic bytes / corrupción) y URL firmada expirada o alterada
1. **Magic bytes falsificados:** enviar bytes `MZ\x90\x00` (`.exe`) codificados en base64 con `nombre_archivo: "falso.pdf"` a `POST http://localhost:8105/api/v1/documentos/archivos`:
   - **Qué señalar:** responde `422 ARCHIVO_INVALIDO` y guarda evento `ARCHIVO_RECHAZADO` en `auditoria.bitacora`.
2. **URL firmada vigente vs. alterada vs. expirada:**
   - Subir un PDF real (`%PDF-1.7...`) -> `201` con `documento_id`.
   - Pedir `GET http://localhost:8105/api/v1/documentos/<documento_id>/url-firmada?ttl=15` -> devuelve URL firmada.
   - Consumir la URL tal cual dentro de 15 s -> `200` + header `X-Evidencia-Sello`.
   - Cambiar 1 carácter del query param `firma=...` -> `403 FIRMA_INVALIDA`.
   - Esperar 16 segundos y volver a consumir la URL original -> `403 URL_EXPIRADA`.

### Paso 6 — Intento sin permiso (`403 SIN_PERMISO`)
1. Llamar con `TOKEN_COLAB` (perfil Colaborador) a una ruta administrativa, p. ej. `GET http://localhost:8102/api/v1/usuarios` o `POST http://localhost:8103/api/v1/catalogos/unidades`:
   - **Qué señalar:** responde `403` con `error.codigo == "SIN_PERMISO"` y `correlacion_id`, y escribe automáticamente en `auditoria.bitacora` (`accion = 'ACCESO_DENEGADO'`, `resultado = 'RECHAZADO_PERMISO'`).

### Paso 7 — Simular timeout / dependencia opcional vs. esencial en `/health/ready`
1. Comprobar que `/health/live` responde `200` con `version_desplegada` e `instancia`.
2. Quitar permisos de escritura al almacén local de `reports-service` (donde `bucket` es `"opcional"`) o detener MongoDB (donde en `algorithms-service` es `"opcional"`):
   - **Qué señalar:** `GET /health/ready` responde `200` con `"estado": "degradado"` y `"degradado_por": ["mongodb"]`, manteniendo el servicio en rotación.
3. Si se detiene PostgreSQL (dependencia esencial), `GET /health/ready` responde `503` con `"estado": "no_listo"` y `"falta": ["postgresql"]`.
4. Explicar también `PG_STATEMENT_TIMEOUT_MS=5000` en `comun/datos.py` y `comun-node/src/entorno.js` para cortar consultas SQL bloqueadas a los 5 segundos.
5. **Prueba automatizada equivalente sin Docker:** ejecutar en vivo:
   ```bash
   python -m pytest Equipo03_SegundoParcial/codigo/pruebas/test_seguridad_y_fallos_t3.py -v -o addopts="" --noconftest
   ```
   (Demuestra los **13 casos** pasando en ~1.5 s).

### Paso 8 — Leer logs correlacionados y consultar `auditoria.bitacora`
1. Rastrear un `correlacion_id` recibido en la respuesta de error o cabecera `X-Correlacion-Id`:
   ```bash
   docker compose logs --tail=50 auth-service catalog-service documents-service | grep "<CORRELACION_ID>"
   ```
2. Consultar en PostgreSQL la evidencia inmutable de los rechazos y operaciones de seguridad:
   ```sql
   SELECT fecha_evento, actor_usuario_id, actor_perfil, accion, tipo_recurso,
          recurso_id, resultado, correlacion_id, direccion_origen
     FROM auditoria.bitacora
    ORDER BY fecha_evento DESC
    LIMIT 20;
   ```
3. **Qué señalar al cerrar:** todas las acciones de seguridad de la migración 018 (`ACCESO_DENEGADO`, `RATE_LIMIT_EXCEDIDO`, `ARCHIVO_RECHAZADO`, `URL_FIRMADA_GENERADA`, `RECUPERACION_SOLICITADA`, `RECUPERACION_CONFIRMADA`) quedan registradas con `correlacion_id` e IP de origen, y el rol `bienestar_app` tiene prohibido ejecutar `DELETE` sobre `auditoria.bitacora`.
