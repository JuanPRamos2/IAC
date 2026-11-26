# Láminas de Presentación — Bloques de Ricardo Arath Sánchez Aguirre (#583928)

**Proyecto:** Bienestar Nexum · Equipo 03 · UDEM  
**Responsable:** Integrante 2 — Seguridad y los 6 Microservicios en Node.js  
**Nota de armado:** Texto conciso listo para pasar a PowerPoint / Google Slides junto con las 6 capturas indicadas en [GUION_ENSAYO_Y_CAPTURAS_RICARDO.md](GUION_ENSAYO_Y_CAPTURAS_RICARDO.md).

---

## Lámina 1 — Seguridad Avanzada en Capas (`auth-service` + Capa Común)

- **Título:** Seguridad de Extremo a Extremo sin Fricción ni Confianza Implícita
- **Puntos clave:**
  - **Tokens JWT (`HS256`) + Estado en Redis:** Acceso de **15 min** y Refresh con rotación de **7 días** (`POST /api/v1/auth/renovar`); en `logout`, cambio de contraseña o expiración se revoca en Redis (`sesion:{jti}` / `revocado:{jti}`).
  - **RBAC en vivo (0 permisos dentro del token):** Cada petición consulta `usuarios.perfil_permiso`; quitar un permiso en Administración surte efecto inmediato.
  - **Protección contra fuerza bruta y OTP:** 5 logins fallidos bloquean **15 min** (`429`); recuperación por código OTP de 6 dígitos guardado como **SHA-256** en Redis, 3 intentos máx. y `fn_restablecer_contrasena` (`SECURITY DEFINER`).
  - **Defensa de entrada y privacidad:** Anti-XXE (`<!DOCTYPE`/`<!ENTITY` bloqueados antes de parsear), Regla **D-01** (`empleado_id` prohibido), validación de *magic bytes* en evidencias y `auditoria.bitacora` inmutable (`bienestar_app` sin `DELETE`).
- **Apoyo visual sugerido:** Diagrama rápido `Cliente -> JWT (15m) -> [Redis sesion/revocado] -> [PostgreSQL perfil_permiso] -> Servicio + auditoria.bitacora` + **Captura 1 (Login correcto)** y **Captura 4 (Swagger `/renovar` y `/logout`)**.

---

## Lámina 2 — Los 6 Microservicios en Node.js y Paridad Total con Python

- **Título:** Arquitectura Políglota Homologada: 6 Microservicios Node.js + `@bienestar/comun`
- **Puntos clave:**
  - **6 servicios especializados (puertos `8103, 8104, 8112, 8113, 8116, 8117`):**
    1. `catalog-service` (`8103`) — Unidades, instrumentos, reactivos, campañas + caché Redis (`300 s`).
    2. `main-process-service` (`8104`) — Captura de respuestas (Regla D-01 + `fn_registrar_autoreporte`) y apoyo.
    3. `survey-service` (`8112`) — Cuestionarios, borradores en MongoDB y prevención de duplicados (`RN-01`).
    4. `indicators-service` (`8113`) — Indicadores protegidos con supresión automática si $n < 5$ ($k \ge 5$).
    5. `support-service` (`8116`) — Solicitudes confidenciales por seudónimo (tiempos y máquina de estados).
    6. `organizational-service` (`8117`) — Árbol jerárquico recursivo y plantilla declarada mínima $\ge 5$.
  - **Capa común `@bienestar/comun` (`comun-node/`):** Misma validación JWT/Redis, mismo `Proxy` estricto de permisos, mismo serializador XML/XSD (`cuerpoXml` + `xmlizar`) y **109 JSON Schemas + OpenAPI 3.0.3 (`/docs`)**.
  - **Resiliencia probada en GCP:** Corrección de `comun-node/src/redis.js` (`estrategiaReintentoRedis`) para que los 6 servicios reconecten solos tras caídas de Redis sin requerir `docker restart`.
- **Apoyo visual sugerido:** Tabla resumida de los 6 puertos + **Captura 6 (Panel Servicios con los 6 Node en verde después de recuperar Redis)**.

---

## Lámina 3 — Evidencia de Pruebas: Token, Permiso, Bloqueo y Dato Inválido

- **Título:** Verificación Real de Seguridad y Contratos ante Fallos y Mal Uso
- **Tabla de resultados en vivo:**
  - **Token revocado (`logout` / rotación):** `401 SESION_REVOCADA` inmediato en Python (`8101`) y Node (`8103`).
  - **Intento sin permiso (`COLABORADOR` → catálogos/admin):** `403 SIN_PERMISO` + fila `ACCESO_DENEGADO` en `auditoria.bitacora` con `correlacion_id`.
  - **Fuerza bruta (5 fallos con correo de prueba):** `401` → al 5.º intento `429 CUENTA_BLOQUEADA` (15 min) sin comprometer `carlos.ramirez`.
  - **Dato mal formado (XXE XML / `empleado_id` D-01 / `.exe` como `.pdf`):** Rechazo `400` / `422` antes de tocar negocio o base de datos.
  - **Cobertura automatizada:** `13/13` en `test_seguridad_y_fallos_t3.py`, `18/18` en `test_archivos_evidencia.py`, `34/34` en pruebas Node (`comun-node` + 6 servicios).
- **Apoyo visual sugerido:** **Captura 2 (Login rechazado)**, **Captura 3 (Bloqueo de 15 minutos)** y **Captura 5 (Fila real de `auditoria.bitacora`)**.
