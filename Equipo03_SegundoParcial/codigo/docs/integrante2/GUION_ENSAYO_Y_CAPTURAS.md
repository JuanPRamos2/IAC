# Guion de Ensayo de Fallos, Seguridad y Checklist de Capturas — Integrante 2 ()

**Ambientes:**
- **Nube (VM `nexum-equipo03`):** https://34.41.26.94.sslip.io
- **Laptop (Docker local):** http://localhost:8000 (`PG_PUERTO_HOST=5433` si Postgres local ocupa `5432`)

> **REGLA DE ORO DEL ENSAYO DE BLOQUEO:**
> **NUNCA** hagas los 5 intentos fallidos de login contra `carlos.ramirez@nexum.com.mx` (ni contra `ana.perez`, `lucia.hernandez`, `mariana.solis` o `roberto.garcia`). Bloquearías tu propia cuenta demo durante 15 minutos en plena demostración. Usa **siempre** el correo de prueba `prueba.bloqueo@nexum.com.mx` (igual dispara `intentos:{correo}` y bloquea con `429` al 5.º intento sin afectar ninguna cuenta real).

---

## 1. Qué explicar en cada fallo (los 5 puntos obligatorios del equipo)

En cada escena de falla del ensayo, recuerda verbalizar estos **5 puntos**:
1. **Se detecta:** la sonda `/health/ready` (o el guardia de seguridad/validación) detecta el problema (`503`, `401`, `403`, `422` o `400`) y el panel **Servicios** marca `DEGRADADO` o `CAIDO`.
2. **Se registra:** queda evidencia en logs con `X-Correlacion-Id` y en PostgreSQL (`auditoria.bitacora` / `auditoria.sonda_disponibilidad`).
3. **Se le dice al usuario:** la respuesta sigue el sobre seguro `ErrorApi` (`codigo`, `mensaje`, `correlacion_id`) sin exponer trazas ni detalles internos.
4. **No se corrompe un dato:** operaciones bloqueadas o canceladas (ej. corte de 20 s, XXE, D-01, archivo alterado) no escriben resultados parciales en PostgreSQL ni MongoDB.
5. **Vuelve al levantar el servicio:** al restaurar el contenedor o Redis, las sondas y los 6 servicios Node regresan a `200 DISPONIBLE` sin requerir reinicio manual.

---

## 2. Script Automatizado de Apoyo para Ensayo de Seguridad

Desde `Equipo03_SegundoParcial/codigo/`:
```bash
# Contra tu Docker local (puertos 8101..8117 abiertos):
python scripts/ensayo_seguridad.py

# Si estás dentro de la VM por SSH (donde 8101..8117 viven en 127.0.0.1 / red Docker):
python3 scripts/ensayo_seguridad.py --web-url https://34.41.26.94.sslip.io
```
*(Si corres desde tu laptop sin entrar por SSH a la VM, recuerda que el firewall `nexum-https` cierra `8101..8124` al exterior; las pruebas HTTP directas a `8101..8117` o Swagger `/docs` se ejecutan ya sea en tu Docker local o dentro de la VM tras `ssh`, mientras que los ensayos del portal web y el panel **Servicios** se prueban directo en `https://34.41.26.94.sslip.io`).*

---

## 3. Escenas del Ensayo Paso a Paso (VM GCP y Laptop)

### Escena A — Login correcto, Login rechazado y Bloqueo de 15 minutos (Capturas 1, 2 y 3)
1. En https://34.41.26.94.sslip.io/entrar inicia sesión como `carlos.ramirez@nexum.com.mx` / `demo123`.
   - **Toma CAPTURA 1 (Login correcto dentro del portal).**
   - Cierra sesión (`Salir`) o abre una ventana privada para la siguiente prueba.
2. En una ventana privada ve a `/entrar`, escribe `prueba.bloqueo@nexum.com.mx` con contraseña incorrecta `malaclave1` e intenta entrar.
   - El portal responde mensaje genérico de credenciales inválidas (anti-enumeración).
   - **Toma CAPTURA 2 (Login rechazado).**
3. Repite el envío incorrecto con `prueba.bloqueo@nexum.com.mx` hasta completar **5 intentos**.
   - Al 5.º/6.º intento aparece el bloqueo de 15 minutos (`Demasiados intentos fallidos...` / `429 CUENTA_BLOQUEADA`).
   - **Toma CAPTURA 3 (Bloqueo de 15 minutos).**

### Escena B — Swagger de Renovar y Revocar Token + Rechazo Inmediato (Captura 4)
1. En tu laptop (`http://localhost:8101/docs`) o con túnel SSH hacia el puerto `8101` de la VM:
   - Ejecuta `POST /api/v1/auth/login` (obtienes `token_acceso` y `token_renovacion`).
   - Despliega `POST /api/v1/auth/renovar`, pega `token_renovacion` en el body y pulsa **Execute** → `200` con par rotado.
   - Despliega `POST /api/v1/auth/logout`, autoriza arriba en **Authorize** con el `token_acceso` nuevo y pulsa **Execute** → `200 {"revocado": true}`.
   - Prueba volver a usar ese mismo `token_acceso` en `GET /api/v1/auth/validar` o `GET http://localhost:8103/api/v1/catalogos/unidades` → `401 SESION_REVOCADA`.
   - **Toma CAPTURA 4 (Swagger UI mostrando `/api/v1/auth/renovar` y `/api/v1/auth/logout` con respuesta `200`).**

### Escena C — Entrar sin permiso (`403`) + Dato mal formado (`400`/`422`) + Bitácora (Captura 5)
1. Ejecuta `python scripts/ensayo_seguridad.py` (envía colaborador sin permiso a `catalog-service` -> `403`, payload XML XXE -> `400`, y payload D-01 con `empleado_id` -> `400`/`422`).
2. Consulta en PostgreSQL una fila reciente de `auditoria.bitacora`:
   ```sql
   SELECT bitacora_id, fecha_evento, actor_perfil, accion, tipo_recurso,
          recurso_id, resultado, correlacion_id
     FROM auditoria.bitacora
    WHERE accion IN ('ACCESO_DENEGADO', 'LOGIN_FALLIDO', 'RATE_LIMIT_EXCEDIDO')
    ORDER BY fecha_evento DESC
    LIMIT 5;
   ```
   *(En la VM puedes correr: `docker compose exec -T datos psql -U postgres -d bienestar -c "SELECT bitacora_id, fecha_evento, actor_perfil, accion, resultado, correlacion_id FROM auditoria.bitacora ORDER BY fecha_evento DESC LIMIT 5;"`).*
   - **Toma CAPTURA 5 (Fila de `auditoria.bitacora` mostrando `ACCESO_DENEGADO` / `LOGIN_FALLIDO` y su `correlacion_id`).**

### Escena D — Detener un microservicio y Detener Redis → Recuperar los 6 Node en verde (Captura 6)
1. **Detener un microservicio** (ej. `catalog-service` o `notifications-service`):
   ```bash
   docker compose stop catalog-service
   ```
   - Abre el panel **Servicios** en https://34.41.26.94.sslip.io/administracion/servicios (con `carlos.ramirez@nexum.com.mx`): verás `catalog-service` en **`CAIDO`** mientras el portal web sigue funcionando sin caerse.
   - Levanta de nuevo: `docker compose start catalog-service` y recarga **Servicios** → vuelve a `DISPONIBLE`.
2. **Detener Redis (`cache`) y recuperar los 6 Node automáticamente:**
   ```bash
   docker compose stop cache
   sleep 15
   ```
   - Recarga **Servicios**: verás la caída detectada en dependencias de Redis (`CAIDO` / `503` en servicios que dependen de Redis para sesión).
   - Vuelve a levantar Redis (**sin reiniciar los contenedores Node**):
     ```bash
     docker compose start cache
     sleep 5
     ```
   - Recarga el panel **Servicios**: confirma que los **6 microservicios Node.js** (`catalog-service`, `main-process-service`, `survey-service`, `indicators-service`, `support-service`, `organizational-service`) regresan solos a **`DISPONIBLE` (verde)** gracias a `estrategiaReintentoRedis`.
   - **Toma CAPTURA 6 (Panel Servicios mostrando los 6 servicios Node en verde después de levantar Redis).**

---

## 4. Checklist Final de las 6 Capturas de Integrante 2

| # | Captura requerida | Dónde se toma | Estado |
|---:|---|---|---|
| 1 | Login correcto | Portal https://34.41.26.94.sslip.io (sesión de `carlos.ramirez`) | [ ] |
| 2 | Login rechazado | Pantalla `/entrar` con `prueba.bloqueo@nexum.com.mx` | [ ] |
| 3 | Bloqueo de 15 minutos | Pantalla `/entrar` al 5.º intento fallido con el correo de prueba | [ ] |
| 4 | Swagger de renovar y revocar | `http://localhost:8101/docs` (endpoints `/renovar` y `/logout`) | [ ] |
| 5 | Una fila de `auditoria.bitacora` | Consola `psql` sobre contenedor `datos` (o pantalla Auditoría en portal) | [ ] |
| 6 | Los 6 servicios Node en verde tras Redis | Panel **Servicios** luego de `stop cache` -> `start cache` | [ ] |
