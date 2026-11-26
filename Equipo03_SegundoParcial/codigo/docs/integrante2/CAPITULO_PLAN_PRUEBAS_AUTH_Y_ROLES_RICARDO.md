# Capítulo del Expediente — Plan de Pruebas de Autenticación y Roles

**Autor:** Ricardo Arath Sánchez Aguirre (#583928) — Integrante 2  
**Proyecto:** Bienestar Nexum · Equipo 03 · UDEM  
**Alcance:** Plan de pruebas funcionales, de seguridad, control de acceso basado en roles (RBAC) y tolerancia a fallos sobre autenticación, sesión y microservicios Node.js/Python.

---

## 1. Matriz de Perfiles, Cuentas de Prueba y Fronteras de Acceso

| Perfil | Cuenta de demostración (`demo123`) | Alcance clave | Operaciones permitidas destacadas | Restricciones críticas verificadas |
|---|---|---|---|---|
| `COLABORADOR` | `ana.perez@nexum.com.mx` | Propio (`seudonimo`) | Login, encuestas (`/cuestionarios`, `/encuestas/respuestas`), solicitudes de apoyo propias (`APOYO_SOLICITAR`), evidencias de apoyo | Rechazado (`403`) en catálogos administrativos, listado global de usuarios/apoyo, tableros agregados y bitácora |
| `LIDER_UNIDAD` | `lucia.hernandez@nexum.com.mx` | Unidad `UO-CC-TURNO-B` | Tableros e indicadores protegidos de su unidad (`AGREGADO_UNIDAD`) con umbral $k \ge 5$ | Rechazado (`403` / `ALCANCE_FUERA_DE_AMBITO`) si consulta unidades fuera de su jerarquía |
| `ESPECIALISTA` | `mariana.solis@nexum.com.mx` | Organizacional | Atención de solicitudes de apoyo (`APOYO_ATENDER`), intervenciones, carga/firma de evidencias (`documents-service`), análisis y escritorio XML | No administra usuarios ni parámetros globales del sistema |
| `AUDITOR` | `roberto.garcia@nexum.com.mx` | Global de lectura | Consulta de `auditoria.bitacora`, verificación de garantías de gobernanza, evidencias de consentimiento y monitoreo | Sin modificación de catálogos ni borrado en bitácora (`bienestar_app` tiene prohibido `DELETE`) |
| `ADMINISTRADOR` | `carlos.ramirez@nexum.com.mx` | Administración TI | CRUD de unidades/instrumentos/campañas (`catalog-service`, `organizational-service`), usuarios, parámetros y panel **Servicios** | **Sin permiso `APOYO_ATENDER`** (migración `017`): TI no puede leer solicitudes confidenciales de apoyo |

> **Regla operativa de ensayo en vivo:** Para las pruebas de bloqueo de 5 intentos fallidos (`PA-03`) se utiliza **exclusivamente** una cuenta de prueba dedicada (ej. `prueba.bloqueo.ricardo@nexum.com.mx`), **nunca** `carlos.ramirez@nexum.com.mx`, para no bloquear el acceso administrativo durante la demostración.

---

## 2. Casos de Prueba de Autenticación, Autorización y Seguridad

| ID | Caso de prueba | Entrada / Estímulo | Resultado esperado (HTTP y efectos) | Verificación automática / manual |
|---|---|---|---|---|
| **PA-01** | Emisión dual JWT (`login`) | `POST /api/v1/auth/login` con `ana.perez@nexum.com.mx` / `demo123` | `200`, entrega `token_acceso` (15 min) + `token_renovacion` (7 días), crea `sesion:{jti}` en Redis, sin permisos dentro del JWT | `test_auth_y_usuarios.py`, `smoke_docker_t3.py` |
| **PA-02** | Login inválido anti-enumeración | Credenciales erróneas para correo existente y para correo inexistente | Ambos responden idéntico `401 CREDENCIALES_INVALIDAS` e incrementan `intentos:{correo}` (TTL 900 s) | `test_auth_y_usuarios.py`, `ensayo_seguridad_ricardo.py` |
| **PA-03** | Bloqueo temporal tras 5 intentos fallidos | 5 peticiones `POST /login` fallidas con `prueba.bloqueo.ricardo@nexum.com.mx` | Del 1.º al 4.º: `401`; al 5.º/6.º: `429 CUENTA_BLOQUEADA` durante 15 min y registro `LOGIN_FALLIDO` en `auditoria.bitacora` | `test_seguridad_y_fallos_t3.py`, `ensayo_seguridad_ricardo.py` |
| **PA-04** | Rotación de refresh token | `POST /api/v1/auth/renovar` con `token_renovacion` válido; luego reintentar con el mismo refresh | Primer llamado `200` con nuevo par de tokens; segundo intento con el refresh viejo responde `401 SESION_REVOCADA` | `test_auth_y_usuarios.py`, `ensayo_seguridad_ricardo.py` |
| **PA-05** | Revocación distribuida Python → Node | `POST /api/v1/auth/logout` en `:8101`; luego `GET /api/v1/catalogos/unidades` en `:8103` con el mismo JWT | Ambos servicios (Python y Node) rechazan inmediatamente con `401 SESION_REVOCADA` al consultar Redis | `smoke_docker_t3.py`, `ensayo_seguridad_ricardo.py` |
| **PA-06** | Flujo OTP completo + bloqueo a 3 fallos | `POST /recuperar/solicitar` → 3 códigos malos en `/confirmar` → OTP correcto desde `notifications-service` | Solicitud siempre `200` (anti-enumeración); 3 fallos → `429 CODIGO_BLOQUEADO`; éxito ejecuta `fn_restablecer_contrasena`, revoca sesiones previas y registra `RECUPERACION_CONFIRMADA` | `test_seguridad_y_fallos_t3.py`, `smoke_docker_t3.py` |
| **PA-07** | Rechazo RBAC `403` y auditoría | Colaborador (`ana.perez`) intenta `POST /api/v1/catalogos/unidades` en `:8103` | `403 SIN_PERMISO` con `correlacion_id` y fila `ACCESO_DENEGADO` (`RECHAZADO_PERMISO`) en `auditoria.bitacora` | `test_seguridad_y_fallos_t3.py`, `smoke_docker_t3.py` |
| **PA-08** | Segregación de privacidad (`ADMINISTRADOR`) | `carlos.ramirez` intenta listar/atender solicitudes en `support-service` (`:8116`) | Rechazado con `403 SIN_PERMISO` conforme a migración `017` | Matriz RBAC y `test_seguridad_y_fallos_t3.py` |
| **PA-09** | Defensa Anti-XXE en Python y Node | Payload XML con `<!DOCTYPE` / `<!ENTITY` hacia `:8101` y `:8117` | Rechazo antes del parser con `400 XML_INSEGURO` / `400 XML_MAL_FORMADO` | `test_seguridad_y_fallos_t3.py`, `smoke_docker_t3.py` |
| **PA-10** | Defensa Regla D-01 y umbral $k \ge 5$ | Enviar `"empleado_id"` a `:8104` / `:8112` / `:8105`; crear unidad con `plantilla_declarada: 3` en `:8117` | Rechazado (`400 PRIVACIDAD_D01` / `422 CAMPO_PROHIBIDO`); unidad `< 5` rechazada en `organizational-service` | `main-process.test.js`, `survey.test.js`, `organizational.test.js` |
| **PA-11** | Rate limiting por token/ventana | Exceder cuota en endpoint protegido con Redis arriba y con Redis caído | Con Redis activo: `429 LIMITE_EXCEDIDO` + `Retry-After` + `RATE_LIMIT_EXCEDIDO`. Con Redis caído: degrada dejando pasar | `test_seguridad_y_fallos_t3.py` |
| **PA-12** | Archivos falsificados y URL firmada | Subir `.exe` renombrado a `.pdf` (`MZ`); luego PDF válido y alterar firma / expirar TTL | Archivo falso: `422 ARCHIVO_INVALIDO` + `ARCHIVO_RECHAZADO`; URL firmada: `200` válida, `403 FIRMA_INVALIDA`, `403 URL_EXPIRADA` | `test_seguridad_y_fallos_t3.py`, `test_archivos_evidencia.py` |
| **PA-13** | Caída y autorecuperación de Redis (>12 s) | Detener `cache` por 13 s, consultar `:8103`/`:8104`, volver a iniciar `cache` | Durante corte: `503` fail-closed en API y degradación controlada en portal web. Al subir `cache`: los 6 Node vuelven solos a `200` sin `docker restart` | `comun-node.test.js`, ensayo en Docker (`RECOVERED_8103=200 RECOVERED_8104=200`) |
| **PA-14** | Garantías de BD en arranque | Ejecutar `gobernanza.fn_verificar_garantias()` sobre esquema real (`bienestar_app`, `CONNECTION LIMIT 80`) | Todas las garantías en `TRUE` (`test_arranque_de_la_base.py`: `17 passed, 1 skipped` contra Docker Postgres) | `pruebas/test_arranque_de_la_base.py` |
| **PA-15** | Timeout SQL y corte de petición (20 s) | Consulta bloqueada > 5 s (`PG_STATEMENT_TIMEOUT_MS=5000`) o bucle largo (`exigir_tiempo`) | SQL aborta a los 5 s; análisis largo aborta a los 20 s con `503 TIEMPO_EXCEDIDO` sin escrituras parciales | `test_fase2.py`, `comun-node.test.js`, `test_analitica.py` |

---

## 3. Criterios de Aceptación y Evidencia Ejecutada
- Ninguna prueba de seguridad modifica o debilita validaciones en producción.
- **Suites automatizadas locales verificadas sobre la rama integrada:**
  - `pruebas/test_seguridad_y_fallos_t3.py`: **13/13** casos autónomos aprobados.
  - `apps/microservicios/comun/tests/test_fase2.py`: **6/6** casos aprobados.
  - `pruebas/test_archivos_evidencia.py`: **18/18** casos aprobados.
  - `apps/microservicios/comun-node/tests/*.test.js`: **11/11** casos aprobados (incluye `estrategiaReintentoRedis`).
  - Los 6 microservicios en Node.js (`catalog`, `main-process`, `survey`, `indicators`, `support`, `organizational`): **23/23** pruebas unitarias aprobadas.
