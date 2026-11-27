# Entrega del segundo parcial — Equipo 03

Proyecto 4. Plataforma de Bienestar Laboral y Prevención de Burnout
Integración de Aplicaciones Computacionales · UDEM

| | |
|---|---|
| Emiliano Pascual Piñales Sánchez | #657657 |
| Gerardo Quiroga Ramírez | #650313 |
| Ricardo Arath Sánchez Aguirre | #583928 |
| Juan Pablo Ramos Salazar | #610248 |

---

## Qué hay en este paquete

```
documentos/                      en .docx y en .pdf
  Reporte_Tecnico_Integrado       EL DOCUMENTO GENERAL: todo el proyecto
  Manual_Tecnico_y_Demostracion   manual de operación y guión de la demo
  Modulo_Microservicios_Completo  el segundo parcial en detalle
  Seguridad_JWT_y_Servicios       seguridad y servicios del Integrante 1
  Contratos_JSON_XML_y_Swagger    contratos del Integrante 3
  Monorepo_y_Ambientes            monorepo y los tres ambientes
  Arquitectura_de_Hardware        dimensionamiento con mediciones reales

codigo/                          el monorepo completo
  apps/web/                      sistema web (M01–M12)
  apps/microservicios/           los nueve microservicios
  apps/escritorio/               aplicación de escritorio (Tkinter), solo XML
  apps/movil/                    aplicación Android (Kotlin), solo JSON
  contratos/                     10 XSD y 58 esquemas JSON
  db/                            esquema, migraciones, semilla, init de MongoDB
  infra/compose/                 los cuatro archivos de compose
  pruebas/                       211 pruebas
  .github/workflows/             dos flujos de integración continua

entrega_original_integrante2/    la entrega de Ricardo tal como llegó,
                                 para poder confrontarla con lo integrado
```

`node_modules/` no va en el paquete: se reinstala con `npm install` y son
unos 40 MB de copias. `package-lock.json` sí va, que es lo que hace esa
reinstalación reproducible.

Aparte de este ZIP hay otro, **`Equipo03_repositorio_git.zip`**, con el
mismo código pero como repositorio git —con su historial y sus mensajes de
confirmación— y un `COMO_SUBIR_A_GIT.md` con los comandos exactos para
agregar el remoto y hacer push.

---

## Los nueve microservicios

Siete en Python (Flask) y dos en Node (Express), porque los escribieron
integrantes distintos. Un cliente no puede notar la diferencia: los nueve
firman el JWT con el mismo secreto, leen la misma sesión en Redis,
autorizan contra `usuarios.perfil_permiso` en cada petición, devuelven el
mismo sobre de error y serializan XML con las mismas reglas.

| Servicio | Responsable | Lenguaje | Puerto |
|---|---|---|---|
| `auth-service` | Integrante 1 | Python | 8101 |
| `users-service` | Integrante 1 | Python | 8102 |
| `catalog-service` | Integrante 2 | Node | 8103 |
| `main-process-service` | Integrante 2 | Node | 8104 |
| `documents-service` | Integrante 3 | Python | 8105 |
| `notifications-service` | Integrante 3 | Python | 8106 |
| `queries-service` | — | Python | 8107 |
| `reports-service` | — | Python | 8108 |
| `algorithms-service` | — | Python | 8109 |

---

## Las dos aplicaciones cliente

Dos aplicaciones que atienden **procesos distintos**, hablan **formatos
distintos** y comparten el mismo backend.

| | Escritorio | Móvil |
|---|---|---|
| Proceso | atender solicitudes y leer el tablero | responder la encuesta y pedir apoyo |
| Quién | especialista de bienestar | colaborador |
| Formato | **XML exclusivamente** | **JSON exclusivamente** |
| Tecnología | Python + Tkinter | Kotlin + Jetpack Compose |
| Servicios | 6 | 5 |

```bash
cd codigo
./scripts/arrancar_microservicios.sh      # sin Docker, los nueve servicios
python3 apps/escritorio/app.py            # necesita python3-tk en Linux
```

La móvil se abre en Android Studio desde `codigo/apps/movil/`.

---

## Cómo levantarlo

Un comando, sin variables que recordar:

```bash
cd codigo
docker compose up -d --build
docker compose ps
```

El `docker-compose.yml` de la raíz trae los valores de developer a la
vista. Carga el esquema, las seis migraciones, los cuatro archivos de
datos sintéticos, y declara los índices y validadores de MongoDB.

La primera vez tarda: son doce imágenes y la base poblada con 19,385
valores de reactivo. El `healthcheck` tiene 180 s de margen para eso, así
que si un servicio aparece como «starting» un rato es lo normal.

Después:

- Portal: <http://localhost:8000>
- Swagger de cada servicio: <http://localhost:8101/docs> … `:8109`

Usuarios de demostración, todos con contraseña `demo123`:

| Correo | Perfil |
|---|---|
| `ana.perez@nexum.com.mx` | Colaborador |
| `lucia.hernandez@nexum.com.mx` | Líder (alcance: UO-CC-TURNO-B) |
| `mariana.solis@nexum.com.mx` | Especialista |
| `roberto.garcia@nexum.com.mx` | Auditor |
| `carlos.ramirez@nexum.com.mx` | Administrador |

Para staging o production se usan los cuatro archivos de
`infra/compose/`, que es donde viven las guardas: production no publica el
puerto de la base y exige `VERSION`.

### Si no se puede usar Docker

La base corre contra un PostgreSQL ya instalado:

```bash
cd codigo
createdb bienestar_dev
./scripts/arranque_base.sh bienestar_dev --con-semilla
```

El guión aplica el esquema, **todas** las migraciones, los permisos y las
semillas, en ese orden. Antes nombraba las migraciones una por una y solo
corría la primera: la base levantaba, respondía su sonda de salud y fallaba
al primer uso real. Ahora recorre la carpeta, y hay una prueba que falla si
alguien vuelve a escribir una lista a mano.

---

## Cómo probarlo

```bash
cd codigo
pip install ./apps/microservicios/comun
pip install -r apps/microservicios/comun/requirements.txt
pip install pytest mongomock jsonschema lxml pyyaml
npm --prefix apps/microservicios/comun-node install
npm --prefix apps/microservicios/catalog-service install
npm --prefix apps/microservicios/main-process-service install

PG_HOST=127.0.0.1 PG_BASE=bienestar_dev PG_USUARIO=bienestar_app \
PG_CLAVE=<la clave> REDIS_HOST=127.0.0.1 APP_AMBIENTE=developer \
python3 -m pytest pruebas/ -q
```

211 pruebas. La suite es repetible: corre dos veces seguidas con el mismo
resultado, porque limpia su estado en Redis.

Las pruebas de los dos servicios en Node **los levantan de verdad**, en un
puerto libre, y les hablan por HTTP con un token emitido por
`auth-service`. Eso es lo que prueba —y no un mock— que un token firmado en
Python se valida en Node y que un `logout` revoca en los dos.

---

## El guión de la demostración, en catorce pasos

El detalle está en `documentos/Manual_Tecnico_y_Demostracion_Equipo03.pdf`.
Este es el índice.

| # | Qué se hace | Qué demuestra |
|---|---|---|
| 1 | `./scripts/arrancar_microservicios.sh estado` | Los nueve componentes arriba, cada uno con su estado |
| 2 | Entrar al portal como `ana.perez` | El menú lo decide el perfil, no el código |
| 3 | Responder la encuesta en el emulador | App móvil, solo JSON, proceso del colaborador |
| 4 | Cerrar la app a media encuesta y reabrirla | Almacenamiento local cifrado |
| 5 | Pedir apoyo con una foto | Cámara, y los metadatos EXIF que se quitan |
| 6 | Abrir la app de escritorio como `mariana.solis` | App de escritorio, solo XML |
| 7 | Tablero de `UO-CC-TURNO-B` | 24 filas publicadas |
| 8 | Tablero de `UO-CC-TURNO-A` | 24 filas, 24 suprimidas: se muestran, no se esconden |
| 9 | Entrar como `carlos.ramirez` e intentar ver agregados | **403 SIN_PERMISO**: el administrador opera, no interpreta |
| 10 | Pestaña Riesgo del escritorio | 37 detecciones, cada una con su explicación |
| 11 | `epsilon_consumido` de una corrida | Cero: evaluar el riesgo no gasta privacidad |
| 12 | Generar un reporte y verificar su sello | Integridad de lo que sale del sistema |
| 13 | Apagar `main-process-service` y recargar | **503 ALMACEN_NO_DISPONIBLE**, no «no cargó» |
| 14 | `python3 -m pytest pruebas/ -q` | 211 pruebas en verde |

Los pasos 8, 9 y 13 son los que más conviene ensayar, y los tres consisten
en **mostrar algo que el sistema se niega a hacer**. Es a propósito: la
mitad de las garantías de este proyecto son negativas, y una garantía
negativa no se demuestra enseñando una pantalla que funciona.

Los pasos 3, 5 y 12 necesitan MongoDB arriba. Sin él responden 503 con el
código `ALMACEN_NO_DISPONIBLE`, que es el comportamiento correcto y, de
hecho, lo mismo que demuestra el paso 13.
