# Aplicaciones cliente e integración completa

Proyecto 4. Plataforma de Bienestar Laboral y Prevención de Burnout
Integración de Aplicaciones Computacionales · UDEM · Equipo 03 · Tercer parcial

| | |
|---|---|
| Gerardo Quiroga Ramírez | #650313 |
| Rol en este parcial | Integrante 4 — aplicaciones cliente e integración completa |

Pruebas: `pruebas/test_procesos_integrales.py` (8 casos),
`pruebas/test_procesos_desde_el_cliente.py` (10 casos),
`pruebas/test_movil.py`, `pruebas/test_escritorio.py`,
`pruebas/test_degradacion_web.py`, `pruebas/test_web_pantallas_nuevas.py`
Migración: `db/migraciones/019_cuatro_ojos_en_la_aprobacion.sql`

---

## 1. Los tres procesos integrales

Cada proceso atraviesa el sistema completo: una persona con un perfil, una
aplicación cliente, uno o más microservicios, Redis, PostgreSQL o MongoDB,
un archivo en el bucket donde aplique, un registro de auditoría, una
notificación y una visualización del resultado.

### Proceso 1 — Autorreporte de bienestar

| Capa | Qué participa |
|---|---|
| Persona | Colaborador |
| Cliente | Aplicación móvil (JSON) y portal web |
| Microservicios | auth, consent, sync |
| PostgreSQL | `consentimiento`, `sincronizacion.lote`, `sincronizacion.operacion`, `autoreporte.respuesta` |
| Redis | lista de revocación del token |
| MongoDB | la notificación de acuse |
| **Bucket** | **No aplica** — un autorreporte son cinco números, no un archivo |
| Auditoría | `SINCRONIZACION_RECIBIDA` |
| Notificación | acuse al colaborador (`CONFIRMACION_RECIBIDA`) |
| Visualización | su propio estado de consentimiento y participación |

Dos cosas que la prueba exige y que no se ven en la respuesta del endpoint:

**El lote se consulta en PostgreSQL, no en la respuesta.** Es la diferencia
entre comprobar que el sistema dijo que hizo algo y comprobar que lo hizo.
En el parcial anterior `sync-service` contestaba APLICADA con toda
convicción y no guardaba nada: le faltaba el COMMIT. El cliente móvil
borraba su copia local y la respuesta desaparecía.

**La operación guarda huella del contenido.** Es lo que hace idempotente
el reenvío: el cliente móvil reenvía cuando no recibió el acuse, y sin
huella la misma respuesta se guardaría dos veces.

Y la mitad que importa: **un colaborador no puede mandar el lote de otro.**
Sin esa comprobación, el agregado de cualquier unidad se podría mover a
voluntad desde un teléfono.

### Proceso 2 — Del análisis a la intervención aprobada

| Capa | Qué participa |
|---|---|
| Personas | Especialista de bienestar que propone, **otra** especialista que aprueba |
| Cliente | Portal web (`/panel/`, `/panel/recomendaciones`, `/intervenciones/`) |
| Microservicios | auth, queries, algorithms, interventions, notifications |
| PostgreSQL | `agregado.resultado_protegido`, `riesgo.deteccion`, `intervencion.plan` |
| MongoDB | la corrida del motor de algoritmos (`corridas_algoritmo`) |
| Redis | caché del tablero y del análisis, con contadores de acierto y fallo |
| **Bucket** | **No aplica en este paso.** La evidencia de la evaluación sí lleva archivo, y eso es el proceso 3 |
| Auditoría | `ANALISIS_EJECUTADO`, `INTERVENCION_PROPUESTA`, `INTERVENCION_APROBADA` |
| Notificación | al responsable de la unidad (`PLAN_APROBADO`) |
| Visualización | tablero, lista priorizada y el plan con su avance |

**El análisis consume cero épsilon** y la prueba lo comprueba leyendo el
presupuesto de privacidad antes y después. Si el motor recalculara
agregados para tener datos frescos, analizar el riesgo costaría la
capacidad de publicar resultados.

**La segunda lectura del tablero viene de Redis**, y la prueba lo exige
mirando `desde_cache` en la respuesta. Sin caché, cada apertura del tablero
recalcula.

### Proceso 3 — Reporte con evidencia en el bucket

| Capa | Qué participa |
|---|---|
| Personas | Especialista (genera y adjunta), auditor (descarga y verifica) |
| Cliente | Portal web (`/reportes/`, `/evidencias/`) y aplicación de escritorio (XML) |
| Microservicios | auth, reports, documents |
| PostgreSQL | los agregados que alimentan el reporte, y la bitácora |
| MongoDB | metadatos del reporte y del archivo de evidencia |
| Redis | límite de consumo y caché |
| **Bucket** | **Sí aplica.** El archivo va al almacén de blobs —una carpeta en developer, el punto de montaje de Cloud Storage en producción— y los metadatos a MongoDB |
| Auditoría | `REPORTE_GENERADO`, `EVIDENCIA_CARGADA`, `EVIDENCIA_DESCARGADA` |
| Notificación | aviso de que el reporte está listo |
| Visualización | el reporte, su descarga y la verificación de su sello |

**Los actores salieron de correr la prueba, no de suponerlos.** La primera
versión puso al administrador generando el reporte y subiendo la evidencia.
Las dos cosas dieron 403, y por buenos motivos: el reporte de tablero exige
`AGREGADO_UNIDAD` o `AGREGADO_GLOBAL`, que son del especialista, y adjuntar
evidencia exige `INTERVENCION_SEGUIMIENTO` o `CONSENT_EVIDENCIA_AUDIT`. El
administrador del sistema administra usuarios y parámetros; no lee los
resultados de bienestar de nadie ni toca la evidencia de las
intervenciones.

Conviene decirlo porque la reacción natural ante un 403 en una prueba es
darle el permiso al perfil que falló, y eso **habría roto la garantía para
que la prueba pasara**.

Dos comprobaciones del archivo que convierten el sello en una garantía:

- **El archivo se guarda bajo el SHA-256 de su contenido**, no bajo el
  nombre que manda el cliente. Un nombre como `../../etc/passwd`
  escribiría fuera de la carpeta.
- **Al leerlo se recalcula el sello.** Un archivo cambiado en el almacén
  después de registrarse se niega con 409 `ARCHIVO_ALTERADO`. Sin eso, una
  evidencia alterada se entregaría como legítima, que es justo lo que un
  sello sirve para impedir.

---

## 2. Los cuatro defectos que encontraron estas pruebas

Escribir los procesos de punta a punta encontró cuatro defectos reales.
Los cuatro estaban entre piezas que individualmente funcionaban, que es
dónde viven los defectos de integración.

### 2.1 El especialista podía aprobar su propio plan

`interventions-service` promete, en su propio mensaje de error: «quien
detecta la necesidad no es quien autoriza el cambio». El mecanismo es
correcto —`INTERVENCION_PROPONER` e `INTERVENCION_APROBAR` son permisos
distintos, y aprobar comprueba el segundo y no se conforma con el de
seguimiento— pero la promesa solo se cumple si los dos permisos están en
perfiles distintos, y en la configuración de roles del sistema **los dos
son del perfil ESPECIALISTA**.

El efecto: la misma persona proponía una intervención sobre una unidad y la
autorizaba ella misma, sin que nadie más lo viera. Una intervención cambia
las condiciones de trabajo de un equipo.

**La corrección (migración 019):** quién propuso queda en la **misma
transacción** que el plan, y aprobar comprueba que no sea la misma persona.

No se usó la bitácora, que ya guardaba quién propuso, y el motivo importa:
el registro en bitácora va envuelto en try/except para que un fallo de
auditoría no tumbe la operación principal. Eso es correcto para auditar e
**inaceptable para un control de acceso** — un control que depende de una
escritura best-effort se cae en silencio justo cuando la escritura falla.

**Y la corrección creaba un bloqueo, que es parte del mismo hallazgo.** El
sistema traía **un solo especialista**. Con el control activado, esa
persona solo podría aprobar planes que no propuso —es decir, ninguno— y
ningún plan se aprobaría jamás. Un control que deja inservible la
configuración por omisión no está terminado, así que la migración trae
también una segunda cuenta con el permiso de aprobar.

No se le dio el permiso al administrador a propósito: quien opera la
plataforma no decide sobre las condiciones de trabajo de un equipo. Dos
especialistas deja la autorización en el área que entiende lo que
autoriza, y deja de ser una sola persona.

### 2.2 Un 500 con un error de Python filtrado

`documents-service` hacía `(cuerpo.get("intervencion_id") or "").strip()`,
que supone que el campo llega como texto. En PostgreSQL la columna es un
bigint, así que un cliente que mandaba el **tipo correcto** —el número que
devuelve el propio servicio al crear el plan— provocaba
`'int' object has no attribute 'strip'` y recibía **500 ERROR_INTERNO** con
el texto de la excepción dentro.

Dos cosas mal a la vez: el tipo correcto fallaba, y fallaba con un 500 que
le dice al cliente «el servidor está roto, reintenta» cuando lo que había
era una petición que el servidor no supo leer. Y filtrar el mensaje de una
excepción interna le cuenta al cliente cómo está escrito el servicio.

Ahora acepta número y texto numérico —la aplicación de escritorio habla
XML y en XML todo llega como texto— y rechaza lo demás con 422.

### 2.3 La ruta del blob se calculaba dos veces

`url_firmada` armaba el nombre del objeto en Cloud Storage por su cuenta y
`ruta_de` la ruta en disco por otra. Hoy coincidían, y coincidían **por
casualidad**: nada lo comprobaba.

Lo que costaba el día que alguien cambiara una: en developer todo seguiría
funcionando, porque la descarga va por el servicio. En la máquina de
Google, donde el almacén es el punto de montaje del bucket, las direcciones
firmadas apuntarían a objetos que no existen y las descargas darían 404 sin
que nada en el código pareciera roto. **Un fallo que solo aparece en el
ambiente donde no se puede depurar.**

Ahora `ruta_relativa` es la única función que decide dónde vive un archivo,
y una prueba comprueba que la ruta en disco y el nombre del objeto
coinciden.

### 2.4 Firmar una dirección para un objeto que no está

Firmar es una operación local: la biblioteca arma la dirección con la llave
y no pregunta nada a Google. Así que una dirección firmada para un objeto
ausente se entregaba igual, con cara de válida, y el cliente se encontraba
un 404 de Cloud Storage —un XML, no el error del sistema— sin ninguna
pista.

Ahora se comprueba que el objeto exista antes de firmar. Cuesta una llamada
y convierte ese 404 silencioso en un error del sistema que dice qué pasó.

---

## 3. Las aplicaciones cliente

### 3.1 Aplicación móvil — JSON

Kotlin con Compose. Pide `Accept: application/json` y manda
`application/json; charset=utf-8`. Consume auth, catálogos, proceso
principal, documentos y notificaciones.

Lo que las pruebas (`test_movil.py`) exigen y conviene saber que se exige:

- **El token no se guarda en preferencias normales**, sino en el almacén
  cifrado del dispositivo.
- **Los permisos se consultan por petición** y no viajan en el token: es
  lo que permite revocar un permiso sin esperar a que caduquen los tokens
  emitidos.
- **El tráfico en claro está prohibido** salvo en la variante de
  desarrollo.
- **La cámara no pide un permiso que no necesita.**
- **Todas las rutas que el Kotlin invoca existen en los servicios**, y los
  códigos de error que la aplicación maneja son los que los servicios
  emiten. Una aplicación que maneja códigos inventados muestra un mensaje
  genérico justo cuando hace falta el específico.
- **La evidencia no deja que el cliente elija el seudónimo.** El servicio
  lo toma del token.

### 3.2 Aplicación de escritorio — XML

Tkinter, y **solo XML**: todas las peticiones piden
`Accept: application/xml` y **todas las respuestas se validan contra su
XSD** antes de mostrarse. No hay una vía en JSON «por si acaso», porque
tenerla haría que la validación dejara de ejercitarse.

Lo que las pruebas (`test_escritorio.py`) exigen:

- **Una respuesta que no cumple el XSD no se muestra.** Si el servicio
  cambia un contrato, la aplicación lo dice en lugar de dibujar datos que
  no entiende.
- **`nil` y vacío no son lo mismo**, ni lo es un elemento ausente. Un
  agregado suprimido llega con `xsi:nil` y significa «lo consulté y no se
  puede publicar»; una cadena vacía significa otra cosa.
- **Sin conexión dice qué hacer**, y no muestra una traza.
- **Un sobre de error se convierte en un error del cliente** con su
  código, no en una excepción.
- **Un 404 con documento normal tampoco se muestra**: un cuerpo que no
  valida no se dibuja ni cuando el código HTTP es un error.
- **El XML crudo queda disponible para diagnóstico**: cuando un contrato
  falla, lo primero que hace falta es ver qué llegó exactamente.

### 3.3 Portal web

Es el cliente de los tres procesos completos. `test_procesos_desde_el_cliente.py`
comprueba, para cada proceso:

- que **tiene sus pantallas** —un proceso que solo funciona por API no
  existe para la organización—,
- que **el perfil correcto llega** a ellas,
- que **el perfil equivocado no llega** y recibe algo que explica por qué,
- que **sin sesión no se abre ninguna** (el error que más se cuela al
  agregar una pantalla: olvidar el decorador),
- y que una campaña inexistente **no da 500**. Un 500 manda a alguien a
  revisar bitácoras por una dirección mal escrita.

Y `test_degradacion_web.py` comprueba lo que peor se comporta en cualquier
portal: **que una pantalla con un microservicio caído lo diga**. Una tabla
vacía porque el servicio está caído es indistinguible de una tabla vacía
porque no hay datos, y las dos llevan a conclusiones opuestas.

Una prueba que vale la pena destacar por lo que encontró: la pantalla de
encuesta. La primera versión daba por hecho que la colaboradora podía
responder la campaña abierta más reciente. No podía —ya la había
respondido— y el portal hizo lo correcto: redirigir con «Esa campaña no
está disponible para ti: puede estar cerrada, ya respondida, o tu
consentimiento no está vigente». **La prueba estaba mal y el sistema
bien**, y la versión corregida vale más, porque comprueba las dos ramas y
cuál se recorre lo decide el estado de los datos.

---

## 4. Conexión a los microservicios en GCP

Los dos clientes ya apuntan a donde haga falta **por configuración, sin
tocar código**:

**Aplicación de escritorio** — una variable de ambiente por servicio, con
el local por omisión:

```
AUTH_SERVICE_URL, USERS_SERVICE_URL, CATALOG_SERVICE_URL,
MAIN_PROCESS_SERVICE_URL, DOCUMENTS_SERVICE_URL, QUERIES_SERVICE_URL,
REPORTS_SERVICE_URL, ALGORITHMS_SERVICE_URL
```

**Aplicación móvil** — `buildConfigField` en `app/build.gradle.kts`, con
dos variantes: `debug` apunta a `10.0.2.2` (como el emulador de Android ve
el `127.0.0.1` de la máquina) y `release` a los dominios de producción.

**Google Cloud Storage** — `documents-service` lee `GCS_BUCKET` y
`GOOGLE_APPLICATION_CREDENTIALS`. Con las dos presentes entrega
direcciones firmadas que caducan a los diez minutos; sin ellas, la
descarga va por el propio servicio. El objeto en el bucket es el mismo
camino relativo que la ruta en disco (`ab/cd/abcd…`), así que un montaje
del bucket en `ALMACEN_EVIDENCIAS` hace que escribir el archivo cree el
objeto.

### Lo que falta y no depende de esta parte

**El despliegue en GCP no existe todavía.** Es del Integrante 1, y en el
código que se integró no está. Lo que esta parte podía hacer está hecho:
los clientes no tienen ninguna dirección fija, el servicio de documentos
firma direcciones de Cloud Storage cuando se le dan el bucket y la llave, y
`docker-compose.gcp.yml` ya quita los puertos publicados para que la base
de datos no quede expuesta.

Lo que no se puede hacer desde aquí es crear el bucket, la cuenta de
servicio y las máquinas. Sin eso, las direcciones firmadas no se pueden
probar contra Cloud Storage de verdad: lo que está probado es que el
servicio las pide bien, que comprueba que el objeto exista antes de
firmarlas, y que cuando no hay bucket cae a la descarga directa en lugar
de fallar.

---

## 5. Manejo de errores, permisos y fallos de conexión

Resumido, porque está repartido por los archivos de prueba:

| Qué | Dónde se comprueba |
|---|---|
| Un microservicio caído: la pantalla lo dice | `test_degradacion_web.py` |
| Sin conexión: la aplicación de escritorio dice qué hacer | `test_escritorio.py` |
| Una respuesta que no cumple su contrato no se muestra | `test_escritorio.py` |
| Los códigos de error que maneja el móvil son los que emiten los servicios | `test_movil.py` |
| Sin sesión no se abre ninguna pantalla de proceso | `test_procesos_desde_el_cliente.py` |
| El perfil equivocado no entra, y se le dice por qué | `test_procesos_desde_el_cliente.py` |
| Una campaña inexistente no da 500 | `test_procesos_desde_el_cliente.py` |
| Un identificador mal formado es 400 y no 500 | `test_exportacion.py` |
| Un archivo mal formado es 422 y no 500 | `test_exportacion.py` |
| Un colaborador no carga evidencias | `test_web_pantallas_nuevas.py` |
| Cuando el servicio de notificaciones no responde, la bandeja lo dice | `test_web_pantallas_nuevas.py` |
| Nadie se quita a sí mismo la administración | `test_web_pantallas_nuevas.py` |
| Nadie aprueba su propia propuesta | `test_intervenciones.py` |

### 5.1 Las seis situaciones de fallo

| Situación | Qué contesta el sistema | Dónde se comprueba |
|---|---|---|
| El microservicio está detenido | `sin_respuesta` en el panel; la pantalla del cliente lo dice y no se queda cargando | `test_monitoreo.py`, `test_degradacion_web.py` |
| Redis caído | El servicio sigue atendiendo: la caché acelera, no es la fuente de verdad. El panel de monitoreo funciona —es el que avisa— y su historial sale **nulo y dicho**, no en cero | `test_monitoreo.py` |
| MongoDB caído | `ALMACEN_NO_DISPONIBLE` con **503**, no 500: el servicio funciona y su dependencia no. Donde MongoDB es opcional, la sonda dice `degradado` con 200 y el servicio no sale de rotación | `test_sonda_de_salud.py`, `test_documentos_y_notificaciones.py` |
| PostgreSQL caído | `no_listo` con 503 en la sonda, con `falta: ["postgresql"]`. Es dependencia esencial: no se le manda tráfico | `test_sonda_de_salud.py` |
| El almacén de archivos (bucket) caído | `degradado` con 200 y `degradado_por: ["almacen"]`. La consulta de metadatos sigue sirviendo; la carga y la descarga dan el error del almacén | `test_sonda_de_salud.py` |
| **Una petición excede el tiempo máximo** | **503 `TIEMPO_EXCEDIDO`** con mensaje, `Retry-After` e identificador de correlación | `test_sonda_de_salud.py` |

### 5.2 La petición que excede el tiempo máximo

Las cinco primeras situaciones ya estaban demostradas. Ésta no, y el único
tope que existía era el de gunicorn, que ante una petición que no termina
**mata al obrero**. Eso tiene tres consecuencias y las tres son malas:

1. **El cliente no recibe un error, recibe una conexión cortada.** Sin
   código, sin mensaje y sin identificador de correlación. La aplicación
   móvil o la de escritorio ven «la conexión se cerró» y no pueden
   distinguirlo de un corte de red ni decir nada útil a quien las usa.
2. **La consulta sigue corriendo.** Matar al obrero no cancela nada en
   PostgreSQL: el servidor sigue ejecutando una consulta cuyo resultado ya
   no tiene a quién entregarle. Y el reintento arranca otra igual: tres
   reintentos son tres consultas vivas haciendo el mismo trabajo inútil.
3. **Se cae lo que ese obrero tenía en vuelo.** Con `-w 2 --threads 2`,
   matar un obrero tira hasta dos peticiones sanas que compartían proceso
   con la lenta.

Ahora hay **tres límites, en este orden**, y el orden es la decisión:

| Límite | Valor | Quién lo aplica | Qué recibe el cliente |
|---|---|---|---|
| `statement_timeout` | 15 s | PostgreSQL, por consulta | 503 `TIEMPO_EXCEDIDO`, con la conexión del pool intacta |
| Plazo de la petición | 20 s | el servicio, en bucles largos | 503 `TIEMPO_EXCEDIDO` diciendo en qué se gastaba el tiempo |
| `--timeout` de gunicorn | 30 s | gunicorn, matando al obrero | nada: conexión cortada |

El de gunicorn queda **por encima** a propósito. Si actuara primero, los
dos límites buenos no se verían nunca.

**Por qué hacen falta los dos primeros y no basta uno.**
`statement_timeout` cubre la mayoría de los casos, porque la mayoría del
tiempo de una petición es base de datos, y es el mejor de los tres: lo
aplica PostgreSQL, cancela **su** consulta, y la conexión queda usable. No
cubre:

- El motor de análisis, que agrupa y ajusta tendencias en **Python puro**.
  Con 110 unidades y 12 campañas son miles de operaciones, y ninguna es
  una consulta que PostgreSQL pueda cancelar.
- Un endpoint que hace cien consultas de 200 ms: no excede ningún
  `statement_timeout` y tarda veinte segundos.

De ahí el plazo por petición, que los bucles largos consultan con
`exigir_tiempo()`. Está en el bucle por unidad de `/algoritmos/analisis`.

**Por qué es cooperativo y no una alarma.** Lo natural sería
`signal.alarm` o un hilo que interrumpa. Las dos cosas están mal aquí: las
señales sólo llegan al hilo principal y el servicio corre con `-k gthread
--threads 2`, así que la alarma cortaría una petición **al azar**, no la
lenta. Y matar un hilo a la fuerza en Python lo deja a medias,
posiblemente con una transacción abierta y una conexión del pool
inutilizable. Cooperativo significa que el bucle decide dónde es seguro
rendirse: entre iteraciones, con la transacción limpia.

**Por qué 503 y no 504.** El 504 dice que una puerta de enlace no obtuvo
respuesta de otro servidor, y aquí no hay puerta de enlace ni otro
servidor: es *este* servicio el que decidió no seguir esperando a su base.
Eso es exactamente 503 con `Retry-After`.

Y se reconoce por la **clase** de la excepción (`QueryCanceled`), no por
su texto: «canceling statement due to statement timeout» está en inglés y
cambia entre versiones de PostgreSQL.

### 5.3 Un error propio al implementarlo

El `statement_timeout` se puso en la cadena de conexión como
`options=-c statement_timeout=15000`, sin comillas. El formato clave=valor
de libpq separa opciones por espacios y el valor de `options` contiene
uno, así que libpq leyó `statement_timeout=15000` como una opción de
conexión aparte y falló con `invalid connection option`. El pool no se
podía crear y **293 pruebas pasaron a error de golpe**. La corrección son
las comillas simples, y está comentada en el código para que nadie las
quite por limpieza.
