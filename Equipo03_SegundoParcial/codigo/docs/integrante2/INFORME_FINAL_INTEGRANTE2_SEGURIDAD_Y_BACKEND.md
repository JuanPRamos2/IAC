# Informe Técnico Final — Integrante 2: Seguridad, Contratos y Backend

**Proyecto:** Bienestar Nexum — Plataforma de Bienestar Laboral y Prevención de Burnout  
**Materia:** Integración de Aplicaciones Computacionales (IAC) · UDEM · Equipo 03  
**Integrante responsable:** **Ricardo Arath Sánchez Aguirre (#583928)** — Integrante 2  
**Alcance del documento:** Arquitectura de los 24 microservicios, detalle técnico de los 6 microservicios en Node.js y capa común (`comun` / `comun-node`), contratos JSON/XML/OpenAPI, autenticación y ciclo de sesión, seguridad avanzada, auditoría de operaciones/rechazos, pruebas verificadas y bitácora de incidencias resueltas.

---

## 1. Arquitectura de los 24 Microservicios y Capa Común

El backend de **Bienestar Nexum** está compuesto por **24 microservicios** independientes (puertos publicados en ambiente `developer`: `8101` a `8124`; dentro de la red privada de Docker Compose todos escuchan en el puerto interno `8000`). Dieciocho servicios están implementados en **Python (Flask)** y seis en **Node.js (Express)**, todos bajo un único contrato operativo y de seguridad.

### 1.1 Mapa completo de los 24 microservicios (`docker-compose.yml` y `apps/microservicios/README.md`)

| Puerto (`developer`) | Servicio | Lenguaje | Integrante | Responsabilidad principal |
|---:|---|---|---|---|
| `8101` | `auth-service` | Python | Juan Pablo (I1) | Emisión, renovación con rotación, validación, revocación Redis y recuperación OTP de JWT |
| `8102` | `users-service` | Python | Juan Pablo (I1) | Administración de usuarios, perfiles, permisos y alcance organizacional |
| `8103` | `catalog-service` | **Node.js** | **Ricardo (I2)** | Unidades organizacionales, instrumentos, versiones, reactivos, campañas y caché Redis |
| `8104` | `main-process-service` | **Node.js** | **Ricardo (I2)** | Proceso principal: captura de respuestas de encuesta (regla D-01) y solicitudes de apoyo |
| `8105` | `documents-service` | Python | Gerardo (I4) | Evidencias, avisos versionados, archivos en almacén dual (`local`/`gcs`) y URLs firmadas |
| `8106` | `notifications-service` | Python | Gerardo (I4) | Bandeja, preferencias, cola push y receptor HMAC `evento-interno` sin cifras decimales |
| `8107` | `queries-service` | Python | Emiliano (I3) | Lectura cacheada de agregados publicados y estado de presupuesto épsilon |
| `8108` | `reports-service` | Python | Emiliano (I3) | Generación, sellado SHA-256 y entrega de reportes organizacionales |
| `8109` | `algorithms-service` | Python | Emiliano (I3) | Motor de reglas de riesgo sobre agregados ya publicados (`riesgo.fn_evaluar_unidad`) |
| `8110` | `consent-service` | Python | Juan Pablo (I1) | Aviso de privacidad, otorgamiento y revocación de consentimiento sin borrado |
| `8111` | `privacy-service` | Python | Juan Pablo (I1) | Seudonimización y consulta de umbral mínimo $k$ (sin calcular ruido Laplace) |
| `8112` | `survey-service` | **Node.js** | **Ricardo (I2)** | Cuestionarios versionados, borradores en MongoDB y registro de respuesta única por campaña |
| `8113` | `indicators-service` | **Node.js** | **Ricardo (I2)** | Indicadores de bienestar agregados protegidos ($k \ge 5$) e histórico organizacional |
| `8114` | `trends-service` | Python | Emiliano (I3) | Análisis longitudinal entre campañas filtrando señal real contra ruido ($b\sqrt{2}$) |
| `8115` | `interventions-service` | Python | Emiliano (I3) | Planes de intervención organizacional, aprobaciones, seguimiento y evaluación |
| `8116` | `support-service` | **Node.js** | **Ricardo (I2)** | Ciclo de vida confidencial de solicitudes de apoyo emocional contra seudónimo |
| `8117` | `organizational-service` | **Node.js** | **Ricardo (I2)** | Organigrama empresarial, árbol jerárquico con CTE recursivo y plantilla mínima $\ge 5$ |
| `8118` | `audit-service` | Python | Juan Pablo (I1) | Consulta de bitácora inmutable y trazabilidad por `correlacion_id` |
| `8119` | `data-governance-service` | Python | Juan Pablo (I1) | Minimización, políticas de retención, verificación de garantías y baja lógica |
| `8120` | `sync-service` | Python | Gerardo (I4) | Sincronización idempotente de lotes capturados sin red (aplicación renglón por renglón) |
| `8121` | `export-service` | Python | Emiliano (I3) | Egreso controlado de agregados protegidos con verificación de fuga y bitácora |
| `8122` | `configuration-service` | Python | Gerardo (I4) | Administración de parámetros de privacidad, umbral $k$ y presupuestos épsilon |
| `8123` | `monitoring-service` | Python | Gerardo (I4) | Sondas agregadas de salud, latencia interna, alertas y supervisión de reinicios (`instancia`) |
| `8124` | `integration-service` | Python | Gerardo (I4) | Puerta todo-o-nada hacia sistema corporativo con validación XSD (`integracion.xsd`) |

### 1.2 Detalle técnico de los 6 microservicios en Node.js (Integrante 2)

Los seis servicios bajo responsabilidad de Ricardo Arath Sánchez Aguirre utilizan **Express** (ESM) sobre la biblioteca compartida `@bienestar/comun` (`apps/microservicios/comun-node/`):

1. **`catalog-service` (`apps/microservicios/catalog-service/`, puerto `8103`):**
   - **Rutas (`/api/v1/catalogos/...`):** CRUD lógico de unidades (`/unidades`), instrumentos (`/instrumentos`), versiones (`/instrumentos/:id/versiones`), reactivos (`/reactivos` y asociación a versiones), campañas (`/campanias`) y lectura de `/dimensiones`, `/fuentes`, `/parametros` definidos en `src/rutas/catalogo.rutas.js`.
   - **Controles:** exige autenticación JWT (`autenticar`) y `limiteConsumo(240, 60)` para todo el router porque la estructura organizacional es información sensible; distingue permisos de lectura (`LEER`) frente a permisos administrativos por entidad (`UNIDAD_ADMIN`, `INSTRUMENTO_ADMIN`, `CAMPANIA_ADMIN`). Incorpora caché en Redis con TTL configurable (`CATALOGO_CACHE_TTL_SEG`, 300 s por defecto).

2. **`main-process-service` (`apps/microservicios/main-process-service/`, puerto `8104`):**
   - **Rutas (`/api/v1/...`):** `POST /encuestas/respuestas`, `GET /encuestas/agregados/resumen`, `GET /encuestas/respuestas/propias`, `POST /solicitudes-apoyo`, `GET /solicitudes-apoyo`, `PATCH /solicitudes-apoyo/:id/estado` y `GET /eventos-proceso` (`src/rutas/proceso.rutas.js`).
   - **Controles:** límite estricto de escritura `limiteConsumo(60, 60)`; aplicación explícita de **regla D-01** en `src/servicios/proceso-encuesta.servicio.js` (rechaza `400 PRIVACIDAD_D01` si `"empleado_id" in cuerpo`); registro en PostgreSQL mediante `autoreporte.fn_registrar_autoreporte` (`SECURITY DEFINER`) y espejo documental/trazabilidad en MongoDB (`respuestas_encuesta`, `eventos_proceso`) + aviso asíncrono resiliente con `notificarEventoInterno`. Separa estrictamente `APOYO_SOLICITAR` de `APOYO_ATENDER`.

3. **`survey-service` (`apps/microservicios/survey-service/`, puerto `8112`):**
   - **Rutas (`/api/v1/cuestionarios...`):** listado (`GET /cuestionarios`), detalle con reactivos y escalas (`GET /cuestionarios/:id`), recuperación/guardado de borrador temporal en MongoDB (`GET/PUT /cuestionarios/:id/borrador`) y captura definitiva (`POST /cuestionarios/:id/respuestas`).
   - **Controles:** previene respuestas duplicadas por `(seudonimo_id, campania_id)` (regla **RN-01**), verifica regla D-01 (`verificarSinIdentidad`) antes de persistir borradores o espejos, invoca `autoreporte.fn_registrar_autoreporte` y despacha notificación interna `CONFIRMACION_RECIBIDA` sin bloquear la transacción ante caída de `notifications-service`.

4. **`indicators-service` (`apps/microservicios/indicators-service/`, puerto `8113`):**
   - **Rutas (`/api/v1/indicadores...`):** catálogo (`GET /indicadores`), agregados protegidos (`GET /indicadores/agregados`), histórico temporal (`GET /indicadores/historico`) y consolidación (`POST /indicadores/calcular`).
   - **Controles:** valida alcance jerárquico del actor (`validarAlcanceUnidad` en `comun-node/src/alcance.js`), lee resultados protegidos desde PostgreSQL (`agregado.resultado_protegido`) o caché documental (`indicadores_organizacionales`) y suprime cualquier valor cuyo `n_observaciones < 5` o `estado_publicacion !== "PUBLICADO"` devolviendo `valor: null` y `suprimido_por_umbral: true` (regla de umbral $k \ge 5$). Audita `REPORTE_GENERADO` con resultado `GRUPO_INSUFICIENTE` o `EXITO`.

5. **`support-service` (`apps/microservicios/support-service/`, puerto `8116`):**
   - **Rutas (`/api/v1/apoyo/solicitudes...`):** alta voluntaria (`POST /apoyo/solicitudes`), listado exclusivo para especialistas (`GET /apoyo/solicitudes`), detalle con control de propietario vs especialista (`GET /apoyo/solicitudes/:id`), cambio de estado con máquina de transiciones validada (`PUT /apoyo/solicitudes/:id/estado`) y seguimiento (`POST /apoyo/solicitudes/:id/mensajes`).
   - **Controles:** resuelve el `seudonimo_id` desde la sesión (`contextoOperativo`) —nunca desde el cuerpo cliente—, exige longitud mínima de mensaje (8 caracteres, máx. 1000) y aplica el aislamiento reforzado por la migración `017_endurecimiento_privacidad_node.sql` (el perfil `ADMINISTRADOR` no tiene `APOYO_ATENDER`).

6. **`organizational-service` (`apps/microservicios/organizational-service/`, puerto `8117`):**
   - **Rutas (`/api/v1/organizacion/unidades...`):** listado filtrado por alcance, detalle, árbol jerárquico completo mediante CTE recursivo (`WITH RECURSIVE arbol`), alta (`POST`), modificación (`PUT`) y baja lógica (`DELETE`).
   - **Controles:** exige `plantilla_declarada >= 5` al crear/modificar unidades para impedir ataques de inferencia por grupos pequeños y valida ausencia de dependencias activas antes de la baja lógica.

### 1.3 Paridad de la capa común Python (`comun/`) y Node.js (`comun-node/`)

| Capacidad compartida | Implementación Python (`apps/microservicios/comun/comun/`) | Implementación Node.js (`apps/microservicios/comun-node/src/`) |
|---|---|---|
| Fábrica, correlación, cabeceras y sondas | `servicio.py` (`crear_servicio`, `responder`, `pagina`, `sobre_pagina`, `limite_consumo`, `cuerpo_peticion`) | `servicio.js` (`crearServicio`, `responder`, `pagina`, `sobrePagina`, `limiteConsumo`, `helmet`, `cors`) + `correlacion.js` |
| Autenticación JWT + Redis | `seguridad.py` (`leer_token`, `decodificar`, `sesion_viva`, `requiere_token`) | `autenticacion.js` (`leerToken`, `decodificar`, `sesionViva`, `autenticar`) |
| Autorización RBAC + bitácora 403 | `seguridad.py` (`requiere_permiso`, `_registrar_acceso_denegado`) | `autorizacion.js` (`permisosDe`, `autorizar`, `requierePermiso`) + `catalogos-auditoria.js` (`Proxy` estricto) |
| Manejo estándar de errores | `errores.py` (`ErrorApi`, `cuerpo_error`, `responder_error`, `registrar_manejadores`) | `errores.js` (`ErrorApi`, `HttpError`, `cuerpoError`, `responderError`, `registrarManejadores`) |
| Serialización y anti-XXE XML | `xmlizar.py` (`a_xml`, `de_xml`, `_PATRON_XXE`) | `xmlizar.js` (`aXml`) + `cuerpoXml.js` (`deXml`, `cuerpoXml`, `PATRON_XXE`) |
| Acceso PostgreSQL + timeout | `datos.py` (`PG_STATEMENT_TIMEOUT_MS=5000`, `ThreadedConnectionPool`) | `postgres.js` + `entorno.js` (`statementTimeoutMs: 5000`) + `pg-errores.js` |
| Acceso MongoDB + regla D-01 | `mongo.py` (`CAMPOS_PROHIBIDOS`, `verificar_sin_identidad`, `asegurar_indices`) | `mongo.js` (`CAMPOS_PROHIBIDOS`, `verificarSinIdentidad`, `asegurarIndices`) |
| Notificador interno firmado HMAC | `notificador.py` (`notificar_evento_interno`) | `notificador.js` (`notificarEventoInterno`) |
| Auditoría en PostgreSQL | `_bitacora` / `_registrar_acceso_denegado` sobre `auditoria.bitacora` | `auditoria.js` (`registrarBitacora` no bloqueante) |
| Contratos OpenAPI y Swagger local | `openapi.py` + `estaticos/swagger/*` | `openapi.js` + `estaticos/swagger/*` |

---

## 2. Contratos JSON, XML/XSD y Swagger (OpenAPI 3.0.3)

1. **OpenAPI 3.0.3 y Swagger UI autónomo:**
   - Los 18 servicios en Python construyen dinámicamente su especificación en `GET /openapi.json` y sirven Swagger UI en `GET /docs` mediante `comun/comun/openapi.py`. Los archivos estáticos (`swagger-ui-bundle.js` y `swagger-ui.css`) se sirven localmente desde `estaticos/swagger/` para no depender de CDNs externos.
   - Los 6 servicios en Node.js exponen `/docs` y `/openapi.json` usando `comun-node/src/openapi.js` (que homologa `securitySchemes.bearerAuth`, `security`, `servers`, y las 7 respuestas comunes de error con ejemplos JSON y XML); `catalog-service` y `main-process-service` sincronizan su `openapi.yaml` con `contratos/generar_openapi_node.py`, y los 4 servicios nuevos (`8112`, `8113`, `8116`, `8117`) construyen el contrato desde `src/openapi.js` sincronizando `openapi.json` y `openapi.yaml`.
2. **Esquemas JSON Schema (`contratos/json/`):**
   - El repositorio contiene **106 archivos `.schema.json` (JSON Schema draft 2020-12)** en `contratos/json/` generados a partir de los 24 contratos OpenAPI por `contratos/generar_json.py`.
3. **Esquemas XML Schema (`contratos/xml/`):**
   - Existen **16 archivos `.xsd`** (`comun.xsd`, `sesion.xsd`, `usuarios.xsd`, `catalogos.xsd`, `proceso.xsd`, `documentos.xsd`, `notificaciones.xsd`, `consultas.xsd`, `reportes.xsd`, `algoritmos.xsd`, `cuestionarios.xsd`, `indicadores.xsd`, `apoyo.xsd`, `organizacion.xsd`, `exportacion.xsd`, `integracion.xsd`) bajo el namespace `http://nexum.com.mx/bienestar/v1`.
   - Tanto `xmlizar.py` como `xmlizar.js` comparten exactamente la misma tabla de singularización (`SINGULARES`) y codificación de nulos (`xsi:nil="true"`) y booleanos (`true`/`false`), permitiendo que un cliente estricto en XML como la aplicación de escritorio (`apps/escritorio/cliente.py`) valide con `lxml` respuestas emitidas indistintamente por Python o Node.js.

---

## 3. Autenticación y Ciclo de Vida de Sesión (`auth-service` + `comun` + `comun-node`)

1. **Emisión dual de JWT (`HS256`):**
   - `auth-service` (`apps/microservicios/auth-service/app.py`) autentica en PostgreSQL mediante `crypt(%s, u.contrasena_hash)` (bcrypt) y emite un `token_acceso` de corta duración (`JWT_MINUTOS=15`) con reclamos mínimos (`sub`, `perfil_id`, `perfil`, `unidad_alcance`, `jti`, `tipo="acceso"`, `iat`, `exp`) y un `token_renovacion` (`JWT_DIAS_RENOVACION=7`, `tipo="renovacion"`).
   - **Decisión crítica:** los permisos nunca viajan dentro del JWT; se consultan en `usuarios.perfil_permiso` en cada petición.
   - El portal web (`apps/web/app/seguridad.py`) firma con el mismo `JWT_SECRETO` y usa la cookie `HttpOnly` `bienestar_sesion`, aceptada también por `leer_token` / `leerToken`.
2. **Validación y revocación distribuida en Redis:**
   - En cada petición protegida, `requiere_token` (Python) y `autenticar` (Node) verifican firma y vigencia (`401 TOKEN_EXPIRADO` / `401 TOKEN_INVALIDO` / `401 TOKEN_AUSENTE`) y consultan Redis: si existe `revocado:{jti}` o no existe `sesion:{jti}`, responden `401 SESION_REVOCADA`.
   - `POST /api/v1/auth/logout` escribe `revocado:{jti}` (TTL igual a `DIAS_RENOVACION * 86400`) y elimina `sesion:{jti}`.
   - **Fail-closed en microservicios vs. degradación web:** si Redis cae, los 24 microservicios rechazan con `503 DEPENDENCIA_NO_DISPONIBLE` (no abren ante la duda), mientras que `apps/web/app/seguridad.py` degrada aceptando firma/vigencia de la cookie para no dejar inoperante el portal.
3. **Rotación de Refresh Tokens (`POST /api/v1/auth/renovar`):**
   - Rechaza tokens de acceso (`401 TIPO_DE_TOKEN_INCORRECTO`), valida que `sesion:{jti_viejo}` siga activa, revoca `jti_viejo` en Redis (`revocado:{jti_viejo}` + `delete sesion:{jti_viejo}`) y emite un nuevo par `{token_acceso, token_renovacion}`, evitando la reutilización silenciosa de un refresh token robado.
4. **Bloqueo por intentos fallidos en login:**
   - Registra fallos en Redis (`intentos:{correo_lower}`, ventana `VENTANA_BLOQUEO=900` s). Al llegar a `INTENTOS_MAXIMOS=5`, responde `429 CUENTA_BLOQUEADA` y audita `LOGIN_FALLIDO`. Los mensajes de `401 CREDENCIALES_INVALIDAS` son idénticos exista o no el correo (anti-enumeración).
5. **Recuperación de acceso mediante OTP (`POST /api/v1/auth/recuperar/solicitar` y `/confirmar`):**
   - Blueprints separados (`bp_recuperar_solicitar` con límite 5/60 s; `bp_recuperar_confirmar` con límite 10/60 s).
   - **Anti-enumeración:** `/recuperar/solicitar` responde exactamente `200 {"solicitado": true, "mensaje": "Si el correo esta registrado y activo, recibiras un codigo de recuperacion."}` exista o no la cuenta.
   - **Almacenamiento seguro del OTP:** genera 6 dígitos con `secrets.randbelow(1_000_000)` y guarda en Redis únicamente su **SHA-256** (`recuperacion:{correo_lower}`, `RECUPERACION_TTL=600` s) junto con `recuperacion_intentos:{correo_lower}=0`.
   - **Bloqueo tras 3 intentos fallidos:** `comparación constante` con `hmac.compare_digest`; al 3er fallo (`RECUPERACION_MAX_INTENTOS=3`), elimina `recuperacion:*` de Redis y responde `429 CODIGO_BLOQUEADO`.
   - **Restablecimiento con menor privilegio y revocación masiva:** `/recuperar/confirmar` invoca `SELECT usuarios.fn_restablecer_contrasena(%s, %s)` (`SECURITY DEFINER` de `bienestar_motor` creada en migración 018), elimina contadores de intento y ejecuta `_revocar_sesiones_usuario(usuario_id)` para invalidar todas las sesiones activas previas en Redis. Despacha el código mediante `notificar_evento_interno` (HMAC) y SMTP opcional aislados con `try/except`.

---

## 4. Seguridad Avanzada, Reglas de Privacidad y Tolerancia a Fallos

1. **RBAC por permiso en tiempo real y `Proxy` estricto:**
   - `requiere_permiso(*codigos)` y `autorizar(...codigos)` consultan `usuarios.perfil_permiso JOIN usuarios.permiso` por `perfil_id` en cada petición. Si falta permiso, responden `403 SIN_PERMISO` y registran `ACCESO_DENEGADO` (`RECHAZADO_PERMISO`) en `auditoria.bitacora` sin permitir que un fallo de bitácora oculte el `403`.
   - En `comun-node/src/catalogos-auditoria.js`, `PERFILES`, `PERMISOS` y `ACCIONES` se envuelven en un `Proxy` que lanza error al arrancar si una ruta referencia un código inexistente (previniendo `undefined` silencioso).
2. **Protección Anti-XXE / Billion Laughs:**
   - Python (`comun/comun/xmlizar.py::de_xml`): evalúa `_PATRON_XXE = re.compile(r"<!\s*(DOCTYPE|ENTITY)\b", re.IGNORECASE)` antes de invocar `ET.fromstring`, lanzando `ValueError` que `cuerpo_peticion` traduce en `400 XML_MAL_FORMADO`.
   - Node.js (`comun-node/src/cuerpoXml.js::deXml`): evalúa `PATRON_XXE = /<!\s*(DOCTYPE|ENTITY)\b/i` y valida buena formación con `XMLValidator.validate` antes de parsear, devolviendo `400 XML_INSEGURO` / `400 XML_MAL_FORMADO`.
3. **Regla D-01 (separación estricta de identidad):**
   - `main-process-service` rechaza `400 PRIVACIDAD_D01` si llega `empleado_id` en el cuerpo.
   - `comun/comun/mongo.py` y `comun-node/src/mongo.js` recorren recursivamente objetos y arreglos en `verificar_sin_identidad` / `verificarSinIdentidad` prohibiendo `CAMPOS_PROHIBIDOS` (`empleado_id`, `numero_empleado`, `curp`, `rfc`, `nombre_empleado`, `correo_empleado`) con `422 CAMPO_PROHIBIDO`.
   - Última línea en base de datos: `db/mongo/init.js` define validadores `$jsonSchema` con `additionalProperties: false` en colecciones críticas como `respuestas_encuesta` y `eventos_proceso`.
4. **Umbral $k \ge 5$ y privacidad diferencial:**
   - Las respuestas individuales viven en PostgreSQL (`autoreporte.respuesta_detalle`) sin permisos de `SELECT` ni `INSERT` directo para `bienestar_app` (reforzado en migraciones `001`, `003` y `017`). Toda captura pasa por `autoreporte.fn_registrar_autoreporte` (`SECURITY DEFINER`) y toda publicación agregada pasa por `agregado.fn_calcular_agregado_protegido` / `agregado.fn_ruido_laplace`.
   - `organizational-service` exige `plantilla_declarada >= 5`; `indicators-service` suprime toda métrica con `n_observaciones < 5`; `privacy-service` publica el parámetro `k_umbral_minimo` sin calcular ruido.
5. **Rate limiting por token y ventana en Redis:**
   - `limite_consumo` / `limiteConsumo` mantiene contadores `limite:<recurso>:<jti|ip>` en Redis, calcula el encabezado `Retry-After` a partir del `TTL` real restante, responde `429 LIMITE_EXCEDIDO` y registra `RATE_LIMIT_EXCEDIDO` en `auditoria.bitacora`. Ante caída de Redis, degrada dejando pasar la petición para no negar servicio global.
6. **Validación de archivos, 10 metadatos y URLs firmadas para buckets (`documents-service`):**
   - `apps/microservicios/documents-service/archivos.py` implementa el **adaptador dual** mediante `ALMACEN_MODO` (`local` por defecto sobre `ALMACEN_EVIDENCIAS`, o `gcs` sobre `bucket_gcs()` que acepta tanto `GCS_BUCKET_NAME` como `GCS_BUCKET`, usando `GOOGLE_APPLICATION_CREDENTIALS` para `google.cloud.storage`). En el despliegue GCP (`docker-compose.gcp.yml`), `documents-service` monta `/mnt/evidencias:/var/lib/bienestar/evidencias` (bucket `nexum-610248-evidencias`) y `/opt/nexum/signer.json:/run/gcp/signer.json:ro` con `GCS_BUCKET=nexum-610248-evidencias`.
   - **Validación estricta:** límite de tamaño (`TAMANO_MAXIMO = 8 MB` en `/archivos`, `4 MB` base64 en `/evidencia-apoyo`), lista blanca de extensiones (`pdf`, `png`, `jpg`, `docx`, `xlsx`, `txt`, `csv`), verificación de **magic bytes** (`FIRMAS`) e inmunidad a *path traversal* (`nombre_presentable` + almacenamiento direccionado por hash `sha256[:2]/sha256[2:4]/sha256`). Tanto `POST /api/v1/documentos/archivos` como `POST /api/v1/documentos/evidencia-apoyo` validan `verificar_sin_identidad(cuerpo)` sobre el cuerpo entrante y rechazan archivos falsificados con `422 ARCHIVO_INVALIDO` auditando `ARCHIVO_RECHAZADO`.
   - **Escritura atómica e integridad:** en modo `local` escribe a `.parcial` y aplica `os.replace`; al leer recalcula SHA-256 y rechaza `409 ARCHIVO_ALTERADO` si hubo corrupción en disco/bucket.
   - **10 metadatos de rúbrica sin binario en BD:** los endpoints `POST /api/v1/documentos/archivos` y `POST /api/v1/documentos/evidencia-apoyo` persisten en MongoDB únicamente metadatos (`identificador`, `ruta`, `tipo`, `tamano`, `propietario`, `fecha`, `hash`, `nivel_privacidad`, `estado`, `metadatos`), nunca el contenido binario.
   - **URLs firmadas temporales (compatibilidad dual):**
     - `GET /api/v1/documentos/archivos/<sha256>/url` invoca `archivos.url_firmada(sha256)` para emitir URL firmada `v4` de Cloud Storage (vigencia 600 s) cuando existen `GCS_BUCKET`/`GCS_BUCKET_NAME` y `GOOGLE_APPLICATION_CREDENTIALS`, o responde `409 URL_NO_DISPONIBLE` en ambiente local sin bucket.
     - `GET /api/v1/documentos/<documento_id>/url-firmada` invoca `archivos.generar_url_firmada(...)`, emitiendo URL firmada `v4` de GCS cuando `ALMACEN_MODO=gcs` o cuando están presentes `GCS_BUCKET`/`GCS_BUCKET_NAME` y `signer.json`, o bien URL HMAC-SHA256 (`documento_id:expira`) en modo `local` con TTL acotado (`10..3600` s, defecto `300` s) y auditoría `URL_FIRMADA_GENERADA`. Al consumir `GET /api/v1/documentos/archivos/<documento_id>/descarga-firmada`, rechaza con `403 URL_EXPIRADA` si caducó o `403 FIRMA_INVALIDA` si se alteró.
   - Asimismo, `reports-service/app.py` (`_ping_bucket`) lee indistintamente `GCS_BUCKET_NAME` o `GCS_BUCKET` como dependencia opcional en `/health/ready`.
7. **Comunicación interna firmada HMAC-SHA256, reconexión Redis y sondas de salud resilientes:**
   - `notificar_evento_interno` (Python) y `notificarEventoInterno` (Node.js) firman `"{ts}.{body}"` con `JWT_SECRETO` y envían `X-Servicio-Timestamp`, `X-Servicio-Firma` y `X-Correlacion-Id` hacia `notifications-service` (`/api/v1/notificaciones/evento-interno`, que exige ventana $\le 60$ s y verifica con `hmac.compare_digest`). Si el receptor está caído o expira el timeout (`1.5 s`), devuelven `false`/`False` sin romper el flujo principal.
   - En `comun-node/src/redis.js`, `estrategiaReintentoRedis(intentos)` aplica backoff acotado (`Math.min(Math.max(1, intentos) * 250, 3000)`) sin devolver `null` tras 10 intentos, y `obtenerRedis()` recrea el cliente si `cliente.status === "end"` (junto al listener `"end"`), evitando que los 6 servicios Node queden atascados en `503` permanente después de reiniciar Redis.
   - `/health/live` incluye `version_desplegada`, `instancia` (para detección de bucles de reinicio en `monitoring-service`) y `arrancado_en`. `/health/ready` distingue dependencias esenciales (`503 no_listo` + `falta`) de opcionales (`200 degradado` + `degradado_por`). Ambos entornos configuran `PG_STATEMENT_TIMEOUT_MS=5000`.

### 4.1 Alineación con Despliegue GCP y Base de Datos (`nexum-equipo03`)
- **Infraestructura en Google Cloud (`docker-compose.gcp.yml` e `infra/caddy/Caddyfile`):**
  - Instancia GCE `nexum-equipo03` (`us-central1-a`), dominio público `34.41.26.94.sslip.io` terminado en HTTPS automático por Caddy (Let's Encrypt) con `reverse_proxy 127.0.0.1:8000`.
  - `docker-compose.gcp.yml` cierra todos los puertos públicos de bases de datos y los 24 microservicios (`ports: !reset []`), restringe `web` a `127.0.0.1:8000:8000`, y monta `/mnt/evidencias` y `/opt/nexum/signer.json:/run/gcp/signer.json:ro` con `GCS_BUCKET: nexum-610248-evidencias`.
- **Capacidad de conexiones y orden de arranque en PostgreSQL:**
  - `db/esquema/00_rol_aplicacion.sh` configura `CONNECTION LIMIT 80` en el rol `bienestar_app` (anteriormente 40) para soportar sin `too many connections` los pools simultáneos de los 18 servicios Python (2 workers c/u), los 6 servicios Node y el portal web (4 workers).
  - `docker-compose.yml`, `infra/compose/docker-compose.developer.yml` e `infra/compose/docker-compose.staging.yml` montan las semillas con prefijos `91_semilla.sql`–`94_semilla.sql` para ejecutarse después de todas las migraciones (`03–20`, incluida `018_tercer_parcial_seguridad_y_buckets.sql`) y de `90_permisos.sh`.

---

## 5. Auditoría de Operaciones y Rechazos (`018_tercer_parcial_seguridad_y_buckets.sql`)

La migración `db/migraciones/018_tercer_parcial_seguridad_y_buckets.sql` consolidó dos pilares:

1. **Función `usuarios.fn_restablecer_contrasena(VARCHAR, TEXT)` (`SECURITY DEFINER`):**
   - Propiedad de `bienestar_motor` con `SET search_path = usuarios, public, pg_temp` y ejecución otorgada únicamente a `bienestar_app`.
   - Calcula `public.crypt(..., public.gen_salt('bf'))` dentro de PostgreSQL, valida longitud mínima de 8 caracteres y restringe la actualización a cuentas con `activo = TRUE`.
2. **Catálogo `auditoria.tipo_accion` ampliado (idempotente con `ON CONFLICT DO NOTHING`):**
   - Dado que `auditoria.bitacora` tiene llave foránea hacia `auditoria.tipo_accion`, se añadieron los 6 códigos requeridos para evitar fallos silenciosos por FK:
     - `RECUPERACION_SOLICITADA` (sensible = `TRUE`)
     - `RECUPERACION_CONFIRMADA` (sensible = `TRUE`)
     - `RATE_LIMIT_EXCEDIDO` (sensible = `TRUE`)
     - `URL_FIRMADA_GENERADA` (sensible = `TRUE`)
     - `ARCHIVO_RECHAZADO` (sensible = `TRUE`)
     - `ACCESO_DENEGADO` (sensible = `TRUE`)
3. **Resiliencia en escritura de bitácora:** tanto `_registrar_acceso_denegado` (`seguridad.py`), `_bitacora` (`auth-service`, `documents-service`) y `registrarBitacora` (`auditoria.js`) envuelven el `INSERT INTO auditoria.bitacora` en captura controlada de errores para que un fallo en la persistencia del registro jamás oculte ni convierta en `500` un rechazo `403`, `422` o `429`.

---

## 6. Pruebas Verificadas de Seguridad, Contratos y Tolerancia a Fallos

A continuación se reportan **exclusivamente** las ejecuciones reales verificadas directamente sobre el código actual del repositorio (sin extrapolaciones):

| Suite / Archivo | Comando ejecutado | Resultado verificado | Cobertura principal |
|---|---|---|---|
| `pruebas/test_archivos_evidencia.py` | `python -m pytest -q -o addopts="" --noconftest pruebas/test_archivos_evidencia.py` | **18/18 pasaron** (0.76 s) | Magic bytes, path traversal, deduplicación SHA-256, escritura atómica `.parcial`, detección de corrupción `409 ARCHIVO_ALTERADO`, `url_firmada` sin bucket y ruta `/archivos/<sha256>/url` |
| `pruebas/test_seguridad_y_fallos_t3.py` | `python -m pytest -q -o addopts="" --noconftest pruebas/test_seguridad_y_fallos_t3.py` | **13/13 pasaron** (1.39 s, sin Redis/PG/Mongo ni `mongomock`) | Token expirado 401, sesión revocada 401 y Redis caído 503, flujo OTP completo (anti-enumeración, SHA-256 en Redis, bloqueo 3 fallos -> 429, `fn_restablecer_contrasena`, revocación sesiones), RBAC 403 + bitácora `ACCESO_DENEGADO`, anti-XXE (3 variantes -> 400), dual local + 10 metadatos sin binario + D-01, magic bytes falsificados (`ARCHIVO_RECHAZADO` -> 422), URL firmada (200 / 403 `FIRMA_INVALIDA` / 403 `URL_EXPIRADA` / 409 `ARCHIVO_ALTERADO`), `/health/live` (`version_desplegada`), `/health/ready` (`degradado` 200 vs `no_listo` 503), rate limit 429 + degradación Redis, `notificar_evento_interno` HMAC + caída sin excepción |
| `apps/microservicios/comun/tests/test_fase2.py` | `python -m pytest -q -o addopts="" --noconftest apps/microservicios/comun/tests/test_fase2.py` | **6/6 pasaron** (1.17 s) | `PG_STATEMENT_TIMEOUT_MS`, `version_desplegada`, `notificador` HMAC, `archivos` modo `local` y mock `gcs`, receptor `evento-interno` |
| `pruebas/test_servicios_juan_pablo_y_ricardo.py` | `python -m pytest -q -o addopts="" --noconftest pruebas/test_servicios_juan_pablo_y_ricardo.py` | **7/7 pasaron** (0.69 s) | Sondas `/health/live`, `/health`, `/docs`, `/openapi.json`, `401 TOKEN_AUSENTE`, no reimplementación Laplace, verificación de los 6 servicios en Node |
| `pruebas/test_arranque_de_la_base.py` | `python -m pytest -q -o addopts="" --noconftest pruebas/test_arranque_de_la_base.py` | **14 pasaron, 1 omitida, 3 fallaron** (2.94 s; host sin PostgreSQL vivo) | Todas las validaciones estáticas pasaron (14/14: montaje de esquema, migraciones 001–018, `90_permisos.sh`, semillas `91–94`, orden de `scripts/arranque_base.sh` y acciones/resultados de bitácora; 1 omitida en `docker-compose.base.yml` sin semillas). Las 3 pruebas de BD viva (`gobernanza.fn_verificar_garantias()`) fallaron al no haber contenedor PostgreSQL activo en `datos:5432` en el host. |
| Contratos JSON y XML/XSD | `python contratos/generar_json.py` + `lxml.etree.XMLSchema` + `test_contratos_json.py` (esquemas estáticos) | **106 `.schema.json`** válidos (`Draft202012Validator`, 2/2 pasaron) y **16 `.xsd`** válidos | Generación desde los 24 OpenAPI (151 emisiones -> 106 archivos únicos) y validación XSD |
| Configuración Docker Compose | `docker compose config --quiet` y `docker compose -f docker-compose.yml -f docker-compose.gcp.yml config --quiet` | **Exitosos (exit code 0)** | Sintaxis válida del stack base y de la capa `docker-compose.gcp.yml` |
| `apps/microservicios/comun-node` | `node --test comun-node/tests/*.test.js` | **11/11 pasaron** (759.84 ms) | Validación estricta, `pg-errores`, XML, OpenAPI 3.0.3, `statementTimeoutMs=5000`, `/health/ready` degradado vs 503, `notificarEventoInterno` HMAC, `estrategiaReintentoRedis` infinita y recuperación de `obtenerRedis` tras `status === "end"` |
| Los 6 servicios en Node.js (`catalog`, `main-process`, `survey`, `indicators`, `support`, `organizational`) | `node --test <svc>/tests/*.test.js` | **23/23 pasaron** (`3+5+4+4+3+4`) | Serialización XML compatible con XSD, regla D-01, prevención duplicados encuesta, umbral $k \ge 5$, transiciones de apoyo, plantilla $\ge 5$ y baja lógica |

### Hallazgos verificados y corregidos en revisión cruzada (Fase B)
- **Resuelto en `documents-service/app.py`:** la observación previa sobre `verificar_sin_identidad(cuerpo)` en `POST /api/v1/documentos/archivos` (`subir_archivo()`) y `POST /api/v1/documentos/evidencia-apoyo` (`adjuntar_evidencia_apoyo()`) quedó solventada; ambos endpoints validan `verificar_sin_identidad(cuerpo)` al inicio del manejador antes de procesar el archivo, además de validar `verificar_sin_identidad(doc)` antes de insertar en MongoDB.
- **Corrección menor en `documents-service/contrato.py`:** el filtro `tipo` en `FILTROS` solo listaba 3 tipos históricos; se alineó con los 5 tipos aceptados por `app.py` (`EVIDENCIA_CONSENTIMIENTO`, `AVISO_PRIVACIDAD`, `REPORTE_ORGANIZACIONAL`, `EVIDENCIA_ARCHIVO`, `EVIDENCIA_APOYO`), verificando paridad 11/11 rutas con `openapi.json`.
- **Verificación de saltos de línea LF:** todos los scripts `.sh` bajo `db/` y `scripts/` conservan saltos de línea Unix (`LF`), sin `CRLF`, garantizando ejecución limpia dentro de los contenedores Linux.

---

## 7. Bitácora de Participación e Incidencias Resueltas (Integrante 2)

| Incidencia / Necesidad detectada | Causa raíz verificada en el código | Solución implementada y archivos involucrados |
|---|---|---|
| 1. Necesidad de 6 servicios en Node.js con paridad total respecto a Python | Los clientes (Android JSON y Escritorio XML) consumen indistintamente servicios Python y Node | Homologación en `comun-node/src/` (`autenticacion.js`, `autorizacion.js`, `servicio.js`, `xmlizar.js`, `cuerpoXml.js`, `errores.js`, `mongo.js`, `openapi.js`) y construcción de `catalog-service`, `main-process-service`, `survey-service`, `indicators-service`, `support-service` y `organizational-service`. |
| 2. Errores `403` silenciosos por permisos mal escritos o faltantes en constantes Node | `Object.freeze` devolvía `undefined` al leer una clave inexistente (ocurrido tras migración 004) | Envoltorio con `Proxy` estricto (`conClavesEstrictas`) en `comun-node/src/catalogos-auditoria.js` que falla al arrancar si falta un permiso o acción. |
| 3. Peticiones XML desde la app de escritorio fallaban con `422` en servicios Node | Express solo montaba `express.json()`, dejando `req.body` vacío ante `application/xml` | Middleware `cuerpoXml` en `comun-node/src/cuerpoXml.js` montado antes de `express.json()`, con reglas inversas idénticas a `comun/xmlizar.py::de_xml` y defensa anti-XXE (`PATRON_XXE`). |
| 4. Perfil `ADMINISTRADOR` conservaba permiso para atender solicitudes de apoyo | Asignación heredada permitía a TI leer solicitudes emocionales | Migración `db/migraciones/017_endurecimiento_privacidad_node.sql` revocando `INSERT` directo en `autoreporte.*` y eliminando `APOYO_ATENDER` del perfil `ADMINISTRADOR`. |
| 5. Faltaban acciones de seguridad en `auditoria.tipo_accion` y función de menor privilegio para OTP | `auditoria.bitacora` fallaba por FK al insertar nuevas acciones y `auth-service` no debía actualizar `contrasena_hash` directamente | Migración `db/migraciones/018_tercer_parcial_seguridad_y_buckets.sql` creando `usuarios.fn_restablecer_contrasena` (`SECURITY DEFINER`) y poblando los 6 códigos de auditoría (`ACCESO_DENEGADO`, `RATE_LIMIT_EXCEDIDO`, `RECUPERACION_*`, `URL_FIRMADA_GENERADA`, `ARCHIVO_RECHAZADO`). |
| 6. Verificación autónoma de seguridad y tolerancia a fallos sin infraestructura pesada | Las pruebas de integración completas requieren PG/Redis/Mongo vivos y `mongomock` | Creación de `pruebas/test_seguridad_y_fallos_t3.py` con dobles en memoria limpios verificando **13/13** escenarios críticos sin depender de servicios externos. |
| 7. Servicios Node quedaban en `503` tras reiniciar Redis y faltaba compatibilidad GCP en almacén y BD | `retryStrategy` en `comun-node/src/redis.js` retornaba `null` tras 10 intentos dejando el cliente en `end`; `bienestar_app` tenía límite de 40 conexiones y `GCS_BUCKET` difería de `GCS_BUCKET_NAME` | `estrategiaReintentoRedis` con reconexión continua y recreación en `obtenerRedis()`; `CONNECTION LIMIT 80` en `00_rol_aplicacion.sh`; semillas `91–94`; compatibilidad dual `GCS_BUCKET`/`GCS_BUCKET_NAME` y rutas `/archivos/<sha256>/url` + `/<documento_id>/url-firmada` en `documents-service` y `reports-service`; capa `docker-compose.gcp.yml` e `infra/caddy/Caddyfile`. |
