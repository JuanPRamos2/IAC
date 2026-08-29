# Bienestar Nexum

Monolito web del primer parcial: bienestar laboral y prevención de burnout.
`cloud_models_classifier` queda como el sitio genérico en `web/` más el backend en `src/`.

No hay JOIN entre MongoDB y PostgreSQL. Mongo solo guarda identificadores.
El único pivote identidad real ↔ operativa es `consentimiento.seudonimo`.

## Arranque con contenedores

```bash
cp .env.example .env
docker compose up --build
```

Abre [http://127.0.0.1:3000](http://127.0.0.1:3000).

| Correo | Perfil | Clave |
| --- | --- | --- |
| ana.perez@empresa.com | COLAB | demo123 |
| lucia.hernandez@empresa.com | LIDER_TURNO | demo123 |
| roberto.garcia@empresa.com | AUDITOR | demo123 |
| carlos.ramirez@empresa.com | ADMIN_SISTEMA | demo123 |

Las contraseñas se verifican en PostgreSQL con `pgcrypto` (`crypt` + Blowfish).

## API

| Método | Ruta | Quién |
| --- | --- | --- |
| POST | `/api/auth/login` | público |
| POST | `/api/auth/logout` | sesión |
| GET | `/api/auth/me` | sesión |
| GET | `/api/catalogos/unidades` | autenticado |
| GET | `/api/catalogos/campanias` | autenticado |
| POST | `/api/encuestas/respuestas` | COLAB |
| GET | `/api/agregados/:unidad/:campania` | LIDER / AUDITOR / ADMIN |
| PATCH | `/api/agregados/parametros/k` | ADMIN |
| GET | `/api/auditoria` | AUDITOR / ADMIN |

POST encuesta:

1. Valida `seudonimo_id` y `campania_id` en PostgreSQL.
2. Inserta en MongoDB `respuestas_encuesta` (sin `empleado_id`).
3. Escribe en segundo plano `CREACION_RESPUESTA` en `bitacora_auditoria`.

Si hay menos de **k** respuestas (k=5), el agregado responde `GRUPO_INSUFICIENTE` sin totales ni promedios.

## Redis

| Clave | Tipo | TTL |
| --- | --- | --- |
| `session:{jti}` | Hash | 15 min |
| `revoked:{jti}` | String | resto de vida del JWT |
| `cache:agregado:{unidad}:{campania}` | String JSON | 5 min |
| `contador:login_fallido:{usuario_id}` | String int | 15 min |
| `lock:calculo_agregado:{unidad}` | String | 10 s |

## Estructura

```
src/controladores  src/servicios  src/modelos  src/middlewares  src/rutas  src/config
web/               interfaz del monolito
db/postgres        esquema oficial + enlaces demo
db/mongo           índices
```

## Pruebas

```bash
npm test
```
