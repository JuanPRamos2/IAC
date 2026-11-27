# Estado del tercer parcial — Equipo 03, Nexum

Integración de Aplicaciones Computacionales · UDEM  
Fecha: 26 de noviembre de 2026, hora del centro de México  
Repositorio del equipo: https://github.com/JuanPRamos2/IAC  
Rama que ya junta el tercer parcial: `Ricardo`  
Pull request: https://github.com/JuanPRamos2/IAC/pull/6 (contra `Ricardo`, prueba de GitHub en verde, sin mezclar)  
Portal en la nube: https://34.41.26.94.sslip.io

Este documento dice, requisito por requisito, qué ya tenemos, qué está a medias y qué falta. Al final separa lo que ya está en GitHub y solo hay que bajarlo, de lo que todavía hay que ejecutar, demostrar o redactar.

## Dónde está cada pieza hoy

| Lugar | Qué tiene |
|---|---|
| Rama `Ricardo` | Seguridad de Ricardo y los archivos de Google Cloud de Equipo 03. No trae el algoritmo ni Locust de Emiliano y Gerardo. |
| `main` | El paquete de Emiliano y Gerardo comprimido en `Parcial3_Emiliano_Gerardo.zip`. No trae la carpeta `Equipo03_SegundoParcial` ni el despliegue. |
| `Ricardo` | Las tres partes juntas. Parte de `Ricardo` y encima entra el zip. La migración de análisis se renombró a `021_analisis_complejo_y_rendimiento.sql` para no pisar la `018` de Ricardo. |
| Máquina `nexum-equipo03` | Portal HTTPS, 24 servicios, PostgreSQL, MongoDB, Redis, bucket y una URL firmada de prueba (`evidencia-1.txt`). Corre el código anterior a esta rama. |

La integración de código ya se hizo en esa rama. No hay otro merge manual pendiente entre los cuatro. Lo que falta de “bajarlo” es que las laptops y la máquina virtual usen esa rama.

## 1. Despliegue en Google Cloud

| Requisito | Estado | Dónde está |
|---|---|---|
| Google Compute Engine | Tenemos | VM `nexum-equipo03`, zona `us-central1-a`, proyecto `proyecto-prueba-610248`, tipo `e2-standard-4`. |
| Google Cloud Storage | Tenemos | Bucket `gs://nexum-610248-evidencias`, región `us-central1`. Montado en la VM en `/mnt/evidencias` con gcsfuse. |
| Firewall | Tenemos | Regla `nexum-https`: solo TCP 80 y 443 desde internet. 5432, 6379, 27017 y 8000 no responden desde fuera. |
| Direcciones y puertos | Tenemos en la nube; el compose estricto está en Git | IP reservada `nexum-ip` = `34.41.26.94`. `docker-compose.gcp.yml` quita los puertos publicados de las bases y de los 24 servicios y deja el portal solo en `127.0.0.1:8000`. Caddy publica el 443. |
| Variables de entorno | Tenemos en el archivo | El overlay fija `GCS_BUCKET`, `ALMACEN_EVIDENCIAS` y la ruta de la llave. `VERSION_DESPLIEGUE` sigue valiendo `local` mientras no se exporte al levantar. |
| Credenciales protegidas | Tenemos | `signer.json` está en la laptop y en `/opt/nexum/signer.json` de la VM. Está en `.gitignore`. No va en Git. |
| HTTPS | Tenemos | Caddy con Let's Encrypt en `34.41.26.94.sslip.io`. El archivo es `infra/caddy/Caddyfile`. |
| Registro de logs | A medias | Cada servicio escribe en su log de contenedor (`docker compose logs`). No hay un sumidero de Cloud Logging. Para la demo alcanza con mostrar esos logs. |
| Distribución web, microservicios, PostgreSQL, MongoDB, Redis, archivos y monitoreo | Tenemos | Todo vive en la misma VM, en contenedores. El lineamiento permite bases administradas por el equipo. La justificación es una sola máquina compartida, con las bases fuera de internet. |

Incompleto de este bloque: la VM no se levantó con `docker-compose.yml` más `docker-compose.gcp.yml` después de la rama integrada. El firewall ya tapa los puertos, pero el compose de la nube es el que además deja de publicarlos en el host y monta el bucket dentro de `documents-service`.

## 2. Bucket y URLs firmadas

| Requisito | Estado | Dónde está |
|---|---|---|
| Archivos en Cloud Storage, no en la base | Tenemos en código y en la VM | Las evidencias van por hash `ab/cd/<sha256>`. La base guarda identificador, ruta, tipo, tamaño, propietario, fecha, hash y metadatos. |
| URL firmada para archivos privados | Tenemos en código; probada a mano | `documents-service` firma por 10 minutos en `GET /api/v1/documentos/archivos/<sha256>/url`. Sin bucket responde 409 y el cliente usa la descarga directa. En la VM se firmó `evidencia-1.txt` con `gcloud storage sign-url`. |
| La aplicación sube y firma | Incompleto | Falta levantar el compose de GCP para que `documents-service` vea `/mnt/evidencias` y la llave, y repetir la prueba subiendo desde el portal. |

`reports-service` también sondea el bucket como dependencia opcional. El resto de los servicios no tiene bucket y no lo reportan. Eso se defiende así: el lineamiento pide el estado del bucket en el servicio que guarda archivos.

## 3. Health checks y monitoreo

Cada microservicio, por la librería común, expone:

| Dato | Estado |
|---|---|
| Proceso vivo, con identificador de instancia y hora de arranque | Tenemos, en `/health/live` |
| PostgreSQL, MongoDB y Redis | Tenemos, en `/health/ready`. Hay tres estados: `listo` (200), `degradado` (200, falla una dependencia opcional) y `no_listo` (503, falla una esencial). |
| Bucket | Tenemos en `documents-service` y, como sonda opcional, en `reports-service` |
| Tiempo de respuesta de cada dependencia | Tenemos, campo `ms` |
| Versión desplegada | Tenemos en `/health` y `/health/live`. El panel web lee `/health/ready`, que no repite la versión. |

El panel central es **Administración → Servicios** (`/portal/` del administrador, ruta `/servicios`).

| Lo que pide el panel | Estado |
|---|---|
| Estado actual | Tenemos: DISPONIBLE, DEGRADADO o CAIDO |
| Tiempo de respuesta del sondeo | Tenemos |
| Dependencias caídas | Tenemos, en el detalle de cada fila |
| Servicios degradados | Tenemos |
| Última verificación | Tenemos. La pantalla Servicios muestra la hora del centro de México de esa apertura. |
| Número de errores | Tenemos en la misma pantalla, leído de `auditoria.bitacora` en 24 horas, y también en `GET /api/v1/monitoreo/errores`. |
| Historial de disponibilidad | Tenemos en código. Cada apertura guarda una muestra en `auditoria.sonda_disponibilidad` (migración 022) y la pantalla resume 24 horas. En la VM aparece después de aplicar esa migración. |

Fallos que hay que poder mostrar:

| Escena | Estado |
|---|---|
| Se detiene un microservicio | El panel lo marca CAIDO. El portal sigue. Hay prueba `test_degradacion_web.py`. |
| Redis no responde | Probado en la VM. Varios servicios pasan a degradado. `catalog-service` y `main-process-service` pueden quedarse degradados después de que Redis vuelve, porque su cliente de Node deja de reintentar. Se recuperan reiniciando esos dos contenedores. La rama de Ricardo trae la reconexión; la VM todavía no corre esa rama. |
| MongoDB no responde | En código, Mongo es opcional para documentos, notificaciones y algoritmos: siguen en `degradado` y atienden. Hay `test_sonda_de_salud.py`. Falta hacerlo en vivo en la VM. |
| PostgreSQL no responde | La sonda esencial responde 503 `no_listo`. Falta la pasada en vivo. |
| El servicio de archivos no está | `documents-service` queda degradado por `almacen` y la carga falla con el error del almacén. Metadatos siguen consultables. |
| Una petición excede el tiempo | `exigir_tiempo` corta a los 20 s con 503 `TIEMPO_EXCEDIDO` y no escribe un resultado a medias. Está en la rama integrada, dentro de `comun`. La VM actual no lo tiene hasta que se actualice. |

## 4. Algoritmo complejo

Tenemos el algoritmo y su documento. No está corriendo en la VM.

Código: `apps/microservicios/analitica/`  
Ruta: `GET /api/v1/algoritmos/analisis` en `algorithms-service`  
Documento: `docs/Algoritmo_Complejo_Equipo03.md`  
Pruebas: `pruebas/test_analitica.py`, `pruebas/test_algoritmos.py`, `scripts/validar_algoritmo.py`

Resuelve qué unidades merecen atención sin leer a una persona. Trabaja sobre agregados ya publicados (k mínimo 5 y ruido de Laplace). Combina agrupamiento, comparación contra el grupo de pares y tendencia (Theil-Sen y Mann-Kendall).

El documento cubre problema, entradas, salidas, variables, restricciones, complejidad, pseudocódigo, casos de prueba, métricas, limitaciones y tiempo de ejecución.

Esto está solo en la rama integrada. `Ricardo` y la VM no lo tienen. `main` lo tiene dentro del zip, separado del resto de la aplicación.

## 5. Grandes volúmenes y rendimiento

Tenemos el generador, las mediciones y el informe. No están cargados en la base de la VM.

| Dato generado | Cifra, según `docs/Rendimiento_y_Carga_Equipo03.md` |
|---|---|
| Empleados | 26 526 |
| Unidades | 136 |
| Campañas | 12 |
| Respuestas | 206 231 |
| Valores de detalle | 1 031 155 |
| Agregados protegidos | 8 280 |
| Tiempo de generación | 798 s |

Guiones en la rama: `scripts/datos_masivos.py`, `scripts/rendimiento.py`, `scripts/cuentas_de_carga.sql`, migración `021_analisis_complejo_y_rendimiento.sql` (índices).

El informe mide tiempo de inserción, planes de consulta, índices, caché, tiempo de procesamiento, comportamiento con y sin Redis, y el antes y después de las consultas lentas. Ejemplos que ya están escritos: el agregado protegido de 89 ms a 21 ms, la vista de presupuesto de 458 ms a 4.6 ms, el p95 de la corrida realista de 1 500 ms a 40 ms.

Esas cifras salieron de un solo contenedor, sin MongoDB. Siete servicios no se midieron por eso. El propio informe lo dice. Volver a correrlas en la VM, con los 24 servicios y Mongo, es evidencia nueva. El guion ya está en Git.

## 6. Locust

Tenemos el escenario y el informe. No hay una corrida contra la nube ni un CSV guardado en el repositorio.

Archivo: `pruebas/carga/locustfile.py`  
Cuatro perfiles: colaborador (móvil), especialista (escritorio), administrador (web) y proceso automático.

El informe trae usuarios concurrentes, peticiones por segundo, mediana, p95, errores y los endpoints más lentos. En la corrida de esfuerzo, `/monitoreo/componentes` quedó en 1 400 ms de p95 y `/algoritmos/analisis` sin caché en 620 ms. En la corrida realista el p95 general quedó en 40 ms y los errores en 0.02 %.

Para apuntar a la VM:

```bash
locust -f pruebas/carga/locustfile.py --host https://34.41.26.94.sslip.io \
  --headless -u 200 -r 20 -t 5m --csv=resultados/carga
```

Eso no se resuelve con otro commit. El archivo ya está. Falta ejecutarlo y conservar el CSV.

## 7. Seguridad

| Requisito | Estado |
|---|---|
| JWT de acceso | Tenemos. 15 minutos. Cookie `bienestar_sesion` en el web. |
| Token de renovación | Tenemos. Campo `token_renovacion`, ruta `POST /api/v1/auth/renovar`. Lo usan el escritorio y el móvil. |
| Revocación | Tenemos. Redis guarda `sesion:<jti>` y `revocado:<jti>`. Renovar invalida el token anterior. |
| Expiración | Tenemos. |
| Roles y permisos por recurso | Tenemos. El permiso se lee de la base, no del token. Matriz viva en Administración. |
| Rate limiting | Tenemos. `limite_consumo` (120 por minuto en general; el login es más estricto). |
| Protección de endpoints | Tenemos. `requiere_permiso` / `requiere_token`. |
| Validación de archivos | Tenemos. `documents-service` función `validar`. |
| Validación XML y JSON | Tenemos. El escritorio habla XML; los esquemas JSON están en `contratos/json` (incluye los de análisis). Swagger en cada servicio. |
| Intentos fallidos | Tenemos. Cinco intentos bloquean 15 minutos. La recuperación por OTP corta a los 3 intentos. |
| Auditoría | Tenemos. `auditoria.bitacora`. |
| Secretos | Tenemos. `signer.json` fuera de Git. Contraseña de demostración `demo123` solo en datos de semilla. |
| Errores sin filtrar internos | Tenemos. `ErrorApi` con código y mensaje. El 500 del portal no devuelve el traceback al navegador; el traceback queda en el log. |

Evidencia de código: `pruebas/test_seguridad_y_fallos_t3.py` y `pruebas/test_auth_y_usuarios.py`, en la rama. El PDF `documentos/Seguridad_JWT_y_Servicios_Equipo03.pdf` es del segundo parcial y sigue sirviendo de contexto.

## 8. Integración completa

Hay tres procesos de punta a punta, descritos en `docs/Clientes_e_Integracion_Equipo03.md` y probados en `pruebas/test_procesos_integrales.py`.

| Proceso | Usuario y cliente | Servicios | Datos | Bucket | Auditoría y aviso |
|---|---|---|---|---|---|
| Autorreporte | Colaborador, móvil | Encuesta y privacidad | PostgreSQL. Redis en la sesión. | No aplica: son cinco números | Sí |
| Análisis de la organización | Especialista, escritorio | Algoritmos | PostgreSQL para agregados. MongoDB para el historial de la corrida. | No aplica en el cálculo | Sí |
| Reporte con evidencia | Especialista o líder, web | Reportes y documentos | PostgreSQL y el archivo | Sí. El archivo va al almacén por hash. | Sí, y el resultado se ve en el portal |

El web, el móvil (Kotlin) y el escritorio (Python, solo XML) están en `apps/`. No hay APK ni instalador de escritorio en el repositorio. Para el tercer parcial el lineamiento pide las aplicaciones integradas. El código integrado está. El binario instalable es de la entrega final.

Esos tres flujos están en la rama integrada. En la VM de hoy el análisis complejo todavía no existe, porque la VM no tiene esta rama.

## 9. Los 17 entregables del tercer parcial

| # | Entregable | Veredicto |
|---|---|---|
| 1 | Plataforma en GCP | Tenemos. Falta que esa máquina corra la rama junta. |
| 2 | Sistema web | Tenemos. |
| 3 | Microservicios desplegados | Tenemos los 24 en la VM, con el código anterior. |
| 4 | Aplicación móvil integrada | Código en la rama. Falta el APK para la entrega final. |
| 5 | Aplicación de escritorio integrada | Código en la rama. Falta el instalador para la entrega final. |
| 6 | Buckets | Tenemos. |
| 7 | URLs firmadas | Código y una firma manual. Falta la firma desde el portal ya desplegado. |
| 8 | Health checks | Tenemos. |
| 9 | Panel de monitoreo | Tenemos estado, latencia, versión, errores de 24 horas e historial. El historial en la VM exige la migración 022. |
| 10 | Algoritmo complejo | Tenemos en la rama, con documento. No está en la VM. |
| 11 | Datos de alto volumen | Generador e informe en la rama. La base de la VM sigue con la semilla de demostración. |
| 12 | Pruebas Locust | Escenario e informe en la rama. Falta la corrida contra la URL pública y el CSV. |
| 13 | Resultados de rendimiento | Tenemos el informe. Medido sin Mongo y fuera de la VM. |
| 14 | Pruebas de fallos | Redis se probó en vivo. El resto está en pruebas automáticas. Falta repetir Mongo, PostgreSQL, archivos y tiempo máximo en la VM ya actualizada. |
| 15 | Evidencia de seguridad | Tenemos pruebas y el flujo de tokens. |
| 16 | Documentación del tercero | Tenemos los tres markdown (algoritmo, clientes, rendimiento) más este estado. Siguen repartidos. El expediente único de 32 apartados es de la entrega final. |
| 17 | Demostración en la nube | El portal está vivo. La demo todavía no enseña algoritmo, Locust ni una evidencia subida por la aplicación. |

## 10. Qué se cerró en código en esta pasada

- El panel distingue disponible, degradado, sin dependencia (503) y caído.
- `/health/ready` incluye `version_desplegada`. En la nube el compose la fija en `tercer-parcial-gcp`.
- `documents-service` en GCP queda en modo `gcs`: sube al bucket `nexum-610248-evidencias` y firma por 10 minutos.
- Migración `022_historial_disponibilidad.sql`, montada como `24_mig_022.sql` en un volumen nuevo.
- `scripts/desplegar_gcp.sh` levanta el compose de la nube y aplica 019 a 022 sobre la base que ya existe.
- `scripts/aplicar_migraciones_en_caliente.sh` hace solo esa parte de la base.
- `infra/gcp/nexum-bucket.service` vuelve a montar el bucket si la VM se reinicia. Hay que instalarlo una vez.

La reconexión de Redis de los servicios Node ya estaba en `comun-node`. Entra cuando la VM reconstruye esas imágenes. No había que reescribirla.

## 11. Qué falta y ya está en GitHub

Nada de esta lista hay que volver a programarlo ni que volver a juntarlo a mano. Está en `Ricardo`.

- Paquete `analitica` y el `algorithms-service` que lo expone.
- `exigir_tiempo` en la librería común.
- Migraciones `019_cuatro_ojos_en_la_aprobacion.sql`, `020_la_jerarquia_se_impide_romper.sql` y `021_analisis_complejo_y_rendimiento.sql`.
- `docker-compose.gcp.yml`, `infra/caddy/Caddyfile` y `infra/gcp/nexum-bucket.service`.
- Migración `022_historial_disponibilidad.sql` y el panel con historial y errores.
- `scripts/desplegar_gcp.sh` y `scripts/aplicar_migraciones_en_caliente.sh`.
- Locust, `datos_masivos.py`, `rendimiento.py`, `validar_algoritmo.py` y `cuentas_de_carga.sql`.
- Contratos JSON de análisis, tendencia y unidad priorizada.
- Pruebas de analítica, procesos integrales, sonda de salud e índices.
- `docs/Algoritmo_Complejo_Equipo03.md`, `docs/Clientes_e_Integracion_Equipo03.md`, `docs/Rendimiento_y_Carga_Equipo03.md`.
- Seguridad, renovación, revocación y migración `018_tercer_parcial_seguridad_y_buckets.sql` (ya venían de `Ricardo` y siguen en esta rama).

En la laptop, dentro de la carpeta del repositorio IAC:

```bat
git fetch origin
git checkout Ricardo
git pull
```

En la VM, el usuario `DELL` y la carpeta del código (`Equipo03_SegundoParcial/codigo`):

```bash
git fetch origin
git checkout Ricardo
git pull
bash scripts/desplegar_gcp.sh
```

Ese guion reconstruye las imágenes y aplica 019, 020, 021 y 022 sobre la base que ya existe. PostgreSQL no las corre solo: `docker-entrypoint-initdb.d` únicamente actúa cuando el volumen está vacío. Borrar el volumen también borra la semilla. El bucket no se borra con eso.

`signer.json` no se baja de GitHub. Ya está en la VM. No hay que subirlo.

## 12. Qué no se resuelve bajando la rama

Estas piezas no están esperando en otro branch. O se ejecutan, o se demuestran, o son de la entrega final.

1. Correr `bash scripts/desplegar_gcp.sh` en la VM. Eso reconstruye las imágenes, incluida `algorithms-service`, y aplica 019, 020, 021 y 022.
2. Subir una evidencia desde el portal y abrir la URL firmada que devuelve la aplicación.
3. Cargar el volumen con `scripts/datos_masivos.py` si la demo del algoritmo debe verse con 206 mil respuestas. Con la semilla de demostración el algoritmo corre, pero el informe dice que el ruido tapa la señal.
4. Correr Locust contra https://34.41.26.94.sslip.io y guardar el CSV.
5. Ensayar en la VM: un microservicio detenido, Redis, MongoDB, PostgreSQL, el almacén de archivos y una petición que pasa de 20 segundos. Mostrar el panel y el log, reiniciar y comprobar que no se escribió un resultado a medias.
6. Instalar una vez el servicio `infra/gcp/nexum-bucket.service` si quieres que el bucket se monte solo al reiniciar la VM. `VERSION_DESPLIEGUE` ya queda en `tercer-parcial-gcp` por el compose.
7. APK, instalador de escritorio, video, presentación, expediente único y la reflexión individual. Son de la entrega final. La reflexión la escribes y la entregas tú. Quien no la entregue queda en cero en esa parte, aunque el repositorio esté completo.

## 13. Lectura corta

El tercer parcial, como código de los cuatro integrantes, ya está junto en `Ricardo`. La nube ya tiene el portal, el firewall, el certificado y el bucket, con el código anterior. Lo que sigue es bajar esa rama en la laptop y en la VM, y en la VM correr `scripts/desplegar_gcp.sh`. Locust contra la URL pública, la carga masiva y la pasada de fallos en vivo son ejecuciones. El video, la presentación y la reflexión individual no forman parte de ese pull.
