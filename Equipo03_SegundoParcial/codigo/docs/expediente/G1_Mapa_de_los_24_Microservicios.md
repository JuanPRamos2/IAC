# Mapa de los 24 microservicios

**Expediente NEXUM — Equipo 03 · Capítulo de Gerardo Quiroga Ramírez
(#650313)**

---

## 1. La tabla

Dieciocho en Python (Flask) y seis en Node (Express), porque los
escribieron integrantes distintos. Un cliente no puede notarlo, y la
sección 3 explica por qué.

| # | Servicio | Resp. | Leng. | Qué hace | PG | Mongo | Redis | Bucket |
|---|---|---|---|---|---|---|---|---|
| 1 | `auth-service` | Juan Pablo | Python | Sesión, JWT, renovación, revocación | ✓ | | ✓ | |
| 2 | `users-service` | Juan Pablo | Python | Usuarios, perfiles, permisos | ✓ | | ✓ | |
| 3 | `catalog-service` | Ricardo | Node | Catálogos: dimensiones, reactivos, instrumentos | ✓ | | ✓ | |
| 4 | `main-process-service` | Ricardo | Node | Orquestación del proceso principal | ✓ | | ✓ | |
| 5 | `documents-service` | **Gerardo** | Python | Evidencias, avisos versionados, reportes; **valida, guarda y firma** | ✓ | ✓ | ✓ | **✓** |
| 6 | `notifications-service` | **Gerardo** | Python | Bandeja, avisos, dispositivos push | ✓ | ✓ | ✓ | |
| 7 | `queries-service` | Emiliano | Python | Consultas agregadas con control de inferencia | ✓ | | ✓ | |
| 8 | `reports-service` | Emiliano | Python | Reportes de bienestar | ✓ | ✓ | ✓ | |
| 9 | `algorithms-service` | Emiliano | Python | Reglas, evaluación y **análisis complejo** | ✓ | opc. | ✓ | |
| 10 | `consent-service` | Juan Pablo | Python | Consentimiento, seudónimos, estado vigente | ✓ | | ✓ | |
| 11 | `privacy-service` | Juan Pablo | Python | Presupuesto de épsilon, supresión | ✓ | | ✓ | |
| 12 | `survey-service` | Ricardo | Node | Encuestas y autorreporte | ✓ | | ✓ | |
| 13 | `indicators-service` | Ricardo | Node | Indicadores | ✓ | | ✓ | |
| 14 | `trends-service` | Emiliano | Python | Series y descensos | ✓ | | ✓ | |
| 15 | `interventions-service` | Emiliano | Python | Planes de intervención, **cuatro ojos** | ✓ | | ✓ | |
| 16 | `support-service` | Ricardo | Node | Solicitudes de apoyo | ✓ | | ✓ | |
| 17 | `organizational-service` | Ricardo | Node | Estructura organizacional | ✓ | | ✓ | |
| 18 | `audit-service` | Juan Pablo | Python | Bitácora | ✓ | | ✓ | |
| 19 | `data-governance-service` | Juan Pablo | Python | Gobierno del dato, retención | ✓ | | ✓ | |
| 20 | `sync-service` | **Gerardo** | Python | Sincronización de lotes de clientes | ✓ | | ✓ | |
| 21 | `export-service` | Emiliano | Python | Exportaciones | ✓ | | ✓ | |
| 22 | `configuration-service` | **Gerardo** | Python | Parámetros del sistema | ✓ | | ✓ | |
| 23 | `monitoring-service` | **Gerardo** | Python | Estado, latencia, errores, **historial** | ✓ | | ✓ | |
| 24 | `integration-service` | **Gerardo** | Python | Integración entre servicios | ✓ | | ✓ | |

Más una biblioteca por lenguaje, que no son servicios: `comun` (Python),
`comun-node` (Node) y `analitica` (el motor del análisis complejo).

**Seis son de Gerardo**: documentos, notificaciones, sincronización,
configuración, monitoreo e integración.

---

## 2. Qué significa cada columna de dependencia

No es decoración: define qué pasa cuando esa dependencia se cae.

- **PG** — PostgreSQL. Dependencia **esencial** en los 24. Caída →
  `no_listo`, HTTP 503, el orquestador deja de mandarle tráfico.
- **Mongo** — sólo 4 servicios. En `algorithms-service` es **opcional**:
  el motor evalúa leyendo agregados de PostgreSQL y sólo usa MongoDB para
  guardar el historial de corridas. Con MongoDB caído atiende
  perfectamente, así que declararlo esencial lo sacaría de servicio
  estando sano.
- **Redis** — esencial en todos: ahí vive la sesión.
- **Bucket** — sólo `documents-service`. Declarado **opcional**: con el
  almacén caído el servicio sigue sirviendo todo el listado y la búsqueda
  de metadatos, que es la mayoría del tráfico.

Y una cosa que la tabla dice y la sonda también: **las casillas vacías son
una afirmación, no un silencio.** Cada sonda devuelve `no_aplican` con las
dependencias que ese servicio no usa. Sin eso, un panel no puede
distinguir «este servicio no tiene bucket» de «la comprobación del bucket
no se ejecutó», que se ven igual —la clave no está— y son cosas opuestas.

---

## 3. Lo que hace que 24 servicios sean un sistema y no 24 programas

Los seis de Node y los dieciocho de Python los escribieron cuatro personas
distintas. Que un cliente no lo note es la propiedad que de verdad
importa, y se sostiene en cinco acuerdos:

1. **El mismo JWT.** Los 24 firman y validan con el mismo secreto. Un
   token emitido por `auth-service` sirve en los otros 23.
2. **Los permisos NO viajan en el token.** Se consultan al servicio. Si
   viajaran, revocar un permiso no tendría efecto hasta que el token
   expirara.
3. **La misma sesión en Redis.** Cerrar sesión en un servicio la revoca en
   todos, incluidos los de Node — hay una prueba que lo fija
   (`test_cerrar_sesion_en_python_revoca_en_node`).
4. **El mismo sobre de error.** `{error: {codigo, mensaje, detalles,
   correlacion_id}}`, en JSON o en XML según `Accept` o `Content-Type`.
   Un cliente escribe un solo manejador de errores.
5. **Las mismas reglas de XML.** Mismo espacio de nombres, mismo
   serializador. La aplicación de escritorio consume XML exclusivamente y
   habla con servicios de los dos lenguajes sin saber cuál es cuál.

Las tres sondas son iguales en los 24: `/health/live` (el proceso),
`/health/ready` (proceso, PostgreSQL, MongoDB, Redis, bucket, tiempo y
versión) y `/docs` (el contrato en Swagger).

---

## 4. Por qué el portal no es uno de los 24

El sistema web **no** está en esta lista, y es a propósito. La
arquitectura obligatoria exige que el portal opere de manera independiente
del módulo de microservicios: con los 24 apagados, el portal sigue
abriendo, deja entrar y explica qué no está disponible, en lugar de dar
una pantalla en blanco o un error de servidor.

La pantalla `/admin/servicios` es la que lo demuestra: sondea a los 24 y
sigue funcionando cuando ninguno contesta.

---

## 5. Un acceso que `integration-service` no tiene

`integration-service` **no lee el socket de Docker**, y hay una prueba que
lo impide (`test_no_se_lee_el_socket_de_docker`).

El motivo: montar `/var/run/docker.sock` en un contenedor es equivalente a
darle root en el anfitrión — con ese socket se puede arrancar otro
contenedor con el disco del anfitrión montado. Sería la forma fácil de
listar contenedores para el panel, y es exactamente por eso que está
prohibido y vigilado por una prueba en lugar de por una convención.
