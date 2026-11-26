# Capítulos del Expediente — Seguridad Avanzada y Diseño de Redis

**Autor:** Ricardo Arath Sánchez Aguirre (#583928) — Integrante 2  
**Proyecto:** Bienestar Nexum · Equipo 03 · UDEM  
**Alcance:** Apartados de **Seguridad Avanzada** y **Diseño de Redis** del expediente final, basados en la implementación verificada en `auth-service`, `comun/`, `comun-node/`, `documents-service`, `apps/web/` y las migraciones `001`–`022`.

---

## 1. Seguridad Avanzada

### 1.1 Ciclo de vida de tokens (JWT de acceso, refresh token, expiración y revocación)
- **JWT de acceso (`HS256`):** emitido por `POST /api/v1/auth/login` en `apps/microservicios/auth-service/app.py` con expiración corta por defecto de **15 minutos** (`JWT_MINUTOS=15`). Incluye únicamente identidad seudonimizada y contexto de alcance (`sub`, `perfil_id`, `perfil`, `unidad_alcance`, `jti`, `tipo="acceso"`, `iat`, `exp`). En el portal web (`apps/web/app/seguridad.py`), el mismo JWT se almacena en la cookie `HttpOnly` `bienestar_sesion`, leída indistintamente por Python (`comun/seguridad.py::leer_token`) y Node.js (`comun-node/src/autenticacion.js::leerToken`).
- **Refresh token con rotación (`POST /api/v1/auth/renovar`):** emitido con vigencia de **7 días** (`JWT_DIAS_RENOVACION=7`, `tipo="renovacion"`). El endpoint rechaza tokens de acceso (`401 TIPO_DE_TOKEN_INCORRECTO`), exige que `sesion:{jti}` siga viva en Redis, **revoca inmediatamente el refresh token consumido** (`revocado:{jti_viejo}` + `delete sesion:{jti_viejo}`) y entrega un nuevo par `{token_acceso, token_renovacion}` impidiendo la reutilización silenciosa de un token interceptado.
- **Revocación inmediata (`POST /api/v1/auth/logout`):** registra `revocado:{jti} = "1"` en Redis con TTL igual a `DIAS_RENOVACION * 86400` y elimina `sesion:{jti}`. En cada petición a cualquiera de los 24 microservicios, `sesion_viva` / `sesionViva` verifican ambos estados y responden `401 SESION_REVOCADA` en menos de 1 ms.

### 1.2 Recuperación de acceso segura mediante OTP (`auth-service` + migración `018`)
- **`POST /api/v1/auth/recuperar/solicitar`** (rate limit dedicado de `5` peticiones/minuto): aplica anti-enumeración devolviendo siempre HTTP `200` (`{"solicitado": true, ...}`), exista o no la cuenta. Si el usuario está activo, genera un código OTP numérico de 6 dígitos con `secrets.randbelow(1_000_000)` y almacena en Redis únicamente su **hash SHA-256** (`recuperacion:{correo}`, TTL `RECUPERACION_TTL=600` s). Despacha el aviso mediante `notificar_evento_interno` (firmado con HMAC-SHA256) y SMTP opcional sin bloquear la respuesta si `notifications-service` no responde.
- **`POST /api/v1/auth/recuperar/confirmar`** (rate limit `10` peticiones/minuto): compara el hash usando `hmac.compare_digest`, bloquea con `429 CODIGO_BLOQUEADO` tras **3 intentos fallidos** (`RECUPERACION_MAX_INTENTOS=3`, eliminando la clave OTP), valida longitud mínima de 8 caracteres y ejecuta `SELECT usuarios.fn_restablecer_contrasena(%s, %s)` (`SECURITY DEFINER` de `bienestar_motor` en `db/migraciones/018_tercer_parcial_seguridad_y_buckets.sql`). Finalmente invoca `_revocar_sesiones_usuario(usuario_id)` para invalidar todas las sesiones previas activas en Redis.

### 1.3 Roles, permisos por recurso y protección de endpoints
- **RBAC consultado en tiempo real:** los permisos **nunca viajan dentro del JWT**. `@requiere_permiso(...)` (`comun/seguridad.py`) y `autorizar(...)` (`comun-node/src/autorizacion.js`) consultan `usuarios.perfil_permiso JOIN usuarios.permiso` en PostgreSQL por cada petición. Si un administrador revoca un permiso o da de baja a un usuario, el rechazo surte efecto en la siguiente petición sin esperar a que expire el JWT.
- **Guardia de arranque en Node.js:** `comun-node/src/catalogos-auditoria.js` envuelve `PERFILES`, `PERMISOS` y `ACCIONES` en un `Proxy` estricto (`conClavesEstrictas`) que falla al iniciar el servicio si alguna ruta referencia un permiso inexistente.
- **Menor privilegio en BD:** todos los servicios se conectan con `bienestar_app` (`CONNECTION LIMIT 80` en `00_rol_aplicacion.sh`), sin `SELECT` sobre `autoreporte.respuesta_detalle` y sin `DELETE` sobre `auditoria.bitacora`. La migración `017_endurecimiento_privacidad_node.sql` retiró además `APOYO_ATENDER` del perfil `ADMINISTRADOR` y la `019_cuatro_ojos_en_la_aprobacion.sql` refuerza segregación de funciones.

### 1.4 Rate limiting, intentos fallidos y bloqueo temporal
- **`limite_consumo` / `limiteConsumo`:** controla ráfagas por recurso y `jti`/IP mediante contadores `limite:<recurso>:<actor>` en Redis (`60 s`), devolviendo `429 LIMITE_EXCEDIDO` con cabecera `Retry-After` exacta del `TTL` restante y registrando `RATE_LIMIT_EXCEDIDO` en `auditoria.bitacora`.
- **Bloqueo de inicio de sesión:** `auth-service` (`INTENTOS_MAXIMOS=5`, `VENTANA_BLOQUEO=900` s) y el portal web (`apps/web/app/seguridad.py`) bloquean al 5.º fallo consecutivo durante **15 minutos** (`429 CUENTA_BLOQUEADA`), registran `LOGIN_FALLIDO` en bitácora y mantienen mensajes genéricos (`401 CREDENCIALES_INVALIDAS`) para evitar enumeración de correos.

### 1.5 Validación de archivos, XML (anti-XXE) y JSON (regla D-01)
- **Archivos privados (`documents-service/archivos.py`):** lista blanca de extensiones (`pdf`, `png`, `jpg`, `docx`, `xlsx`, `txt`, `csv`), límite de tamaño (`8 MB` en `/archivos`, `4 MB` en `/evidencia-apoyo`), verificación obligatoria de **magic bytes** (`FIRMAS`) rechazando archivos disfrazados con `422 ARCHIVO_INVALIDO` + bitácora `ARCHIVO_RECHAZADO`, saneado contra *path traversal*, almacenamiento direccionado por `sha256[:2]/sha256[2:4]/sha256` y recomputación de SHA-256 al descargar (`409 ARCHIVO_ALTERADO`). Las descargas privadas usan URLs firmadas temporales (`/archivos/<sha256>/url` y `/<documento_id>/url-firmada`).
- **XML seguro (Anti-XXE / Billion Laughs):** tanto `comun/comun/xmlizar.py::de_xml` como `comun-node/src/cuerpoXml.js::deXml` bloquean expresiones `<!DOCTYPE` y `<!ENTITY` antes de invocar al parser XML (`400 XML_INSEGURO` / `400 XML_MAL_FORMADO`). Además, la app de escritorio valida sus respuestas contra los **16 archivos `.xsd`** de `contratos/xml/`.
- **JSON y Regla D-01:** `comun/mongo.py::verificar_sin_identidad` y `comun-node/src/mongo.js::verificarSinIdentidad` recorren recursivamente objetos y arreglos rechazando `CAMPOS_PROHIBIDOS` (`empleado_id`, `numero_empleado`, `curp`, `rfc`, `nombre_empleado`, `correo_empleado`) con `422 CAMPO_PROHIBIDO` (`400 PRIVACIDAD_D01` en `main-process-service`), complementado por validadores `$jsonSchema` en `db/mongo/init.js`.

### 1.6 Auditoría inmutable, manejo seguro de errores y secretos
- **`auditoria.bitacora`:** cada operación crítica y cada rechazo (`ACCESO_DENEGADO`, `RATE_LIMIT_EXCEDIDO`, `LOGIN_FALLIDO`, `ARCHIVO_RECHAZADO`, `URL_FIRMADA_GENERADA`, `RECUPERACION_SOLICITADA`, `RECUPERACION_CONFIRMADA`) queda registrado con `correlacion_id` e IP de origen. Un fallo al escribir en bitácora se captura en log para jamás transformar un `403`/`422`/`429` en `500`.
- **Errores seguros y secretos:** todos los microservicios responden con el sobre único `{"error": {"codigo", "mensaje", "correlacion_id"}}` (`ErrorApi`) sin filtrar *stack traces* ni sentencias SQL en `staging`/`production`. La llave de firma de GCS (`signer.json`) está excluida en `.gitignore` y vive únicamente en `/opt/nexum/signer.json` con lectura acotada en el contenedor (`/run/gcp/signer.json:ro`).

---

## 2. Diseño de Redis

### 2.1 Catálogo real de estructuras, claves y TTL
Redis 7 (`cache`) actúa como plano de estado compartido de baja latencia entre los 18 microservicios Python, los 6 microservicios Node.js y el portal web:

| Patrón de clave | Tipo Redis | Servicio(s) que la usan | TTL configurado | Propósito y regla de negocio |
|---|---|---|---|---|
| `sesion:{jti}` | Hash (`usuario_id`, `perfil_id`, `perfil`, `unidad_alcance`) | `auth-service`, `apps/web`, `comun`, `comun-node` | `JWT_DIAS_RENOVACION * 86400` (`7 días`) en API; `JWT_MINUTOS * 60` (`900 s`) en web | Mantiene el estado vivo de cada sesión emitida para verificación en tiempo real. |
| `revocado:{jti}` | String (`"1"`) | `auth-service`, `apps/web`, `comun`, `comun-node` | `7 días` en API; `900 s` en web | Lista negra inmediata tras `logout`, rotación de refresh token o cambio de clave por OTP. |
| `intentos:{correo}` | Counter (`INCR`) | `auth-service`, `apps/web/app/seguridad.py` | `VENTANA_BLOQUEO = 900 s` (15 min) | Cuenta fallos de login consecutivos por correo normalizado; bloquea al alcanzar `5`. |
| `recuperacion:{correo}` | String (SHA-256 hex) | `auth-service` | `RECUPERACION_TTL = 600 s` (10 min) | Almacena el hash del OTP temporal de 6 dígitos sin guardar el código en claro. |
| `recuperacion_intentos:{correo}` | Counter (`INCR`) | `auth-service` | `RECUPERACION_TTL = 600 s` | Cancela y borra el OTP si se supera `RECUPERACION_MAX_INTENTOS = 3`. |
| `limite:{recurso}:{actor}` | Counter (`INCR`) | `comun/servicio.py`, `comun-node/src/servicio.js` | `ventana = 60 s` (dinámico por ruta) | Rate limiting distribuido por token (`jti`) o IP; su `TTL` alimenta `Retry-After`. |
| `cache:catalogo:{clave}` | String (JSON serializado) | `comun-node/src/cache.js` (`catalog-service`) | `CATALOGO_CACHE_TTL_SEG = 300 s` | Caché de catálogos organizacionales y cuestionarios con invalidación por patrón. |
| `consulta:{recurso}:{hash}` | String (JSON serializado) | `queries-service/app.py` | `tablero: 60s`, `tendencia: 120s`, `presupuesto: 10s`, `participacion: 30s`, `catalogo: 300s` | Acelera consultas de agregados protegidos ya publicados; expone cabeceras `X-Cache` y `X-Cache-TTL`. El presupuesto épsilon usa TTL de 10 s a propósito para reflejar agotamiento rápido. |

### 2.2 Política ante fallos y corrección de reconexión automática
1. **Autenticación *fail-closed* en microservicios vs. degradación web:** si Redis deja de responder, `sesion_viva` / `sesionViva` devuelven `503 DEPENDENCIA_NO_DISPONIBLE` en los 24 microservicios (ante la duda sobre revocación, nunca abren un endpoint API). En contraste, el portal web (`apps/web/app/seguridad.py`) degrada aceptando firma y expiración de la cookie `HttpOnly` para no dejar sin pantalla a usuarios legítimos.
2. ***Rate limit* y caché *fail-open*:** si Redis cae, `limite_consumo`, `cache.js` y `queries-service` capturan la excepción y dejan pasar la petición directamente hacia PostgreSQL.
3. **Reconexión infinita en Node.js (`apps/microservicios/comun-node/src/redis.js`):** en las pruebas iniciales de caída de Redis en GCP se detectó que `ioredis` dejaba de reintentar tras 10 intentos (`retryStrategy` devolvía `null`), dejando a `catalog-service` (`8103`) y `main-process-service` (`8104`) en `503` permanente hasta reiniciar sus contenedores. Se corrigió exportando `estrategiaReintentoRedis(intentos)` con backoff acotado (`Math.min(Math.max(1, intentos) * 250, 3000)`) sin límite de corte, fijando `commandTimeout: 2000` para sondas rápidas y recreando la instancia en `obtenerRedis()` si `cliente.status === "end"`.
