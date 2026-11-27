# Guion del ensayo de fallos

**Expediente NEXUM — Equipo 03**

El requisito dice que **los cuatro** tenemos que estar en el ensayo y
poder explicar, para cada fallo, **cinco** cosas:

1. **se detecta**
2. **se registra**
3. **se le dice al usuario**
4. **no se corrompe un dato**
5. **vuelve al levantar el servicio**

Este documento las contesta para las seis situaciones, con dónde está la
evidencia. Lo escribimos Emiliano y Gerardo; Ricardo y Juan Pablo
ejecutan el ensayo en la máquina virtual.

---

## La tabla corta

| Fallo | Se detecta | Se registra | Se le dice al usuario | No se corrompe | Vuelve |
|---|---|---|---|---|---|
| Microservicio detenido | panel: `sin_respuesta` | bitácora del portal | la pantalla lo dice | nada se escribió | al levantarlo |
| Redis | `no_listo` en su sonda | bitácora | el portal explica | la sesión se revalida | inmediato |
| MongoDB | sonda: esencial u opcional | bitácora | 503 `ALMACEN_NO_DISPONIBLE` | PostgreSQL no se tocó | inmediato |
| PostgreSQL | `no_listo`, 503 | log del servicio | **503 `BASE_NO_DISPONIBLE`** | **rollback** | **1 petición falla** |
| Bucket | `degradado`, 200 | bitácora | error del almacén | metadato sin blob → se evita | inmediato |
| Tiempo máximo | el plazo | **bitácora, `RECHAZADO`** | 503 `TIEMPO_EXCEDIDO` | **no se escribe nada** | n/a |

---

## 1. Microservicio detenido

**Se detecta.** El panel lo marca `sin_respuesta`, que **no es lo mismo
que `no_listo`**: un 503 con cuerpo es un servicio vivo que dice qué le
falta; uno que no contesta está caído. Se arreglan en lugares distintos.

**Se registra.** El portal anota el fallo de llamada en su bitácora con el
identificador de correlación.

**Se le dice al usuario.** La pantalla dice qué no está disponible. No se
queda cargando ni da una traza.

**No se corrompe un dato.** No llegó a escribirse nada: la petición no
salió del portal.

**Vuelve al levantar el servicio.** Sí, en la siguiente sonda. El panel
tiene caché de 5 s, así que con `?sin_cache=1` se ve de inmediato.

> Demostración: apagar un servicio, recargar `/admin/servicios`,
> levantarlo, recargar.

---

## 2. Redis caído

**Se detecta.** Redis es **esencial** en los 24: la sonda da `no_listo`.

**Se registra.** En la bitácora, y el panel lo muestra en la columna de
dependencias.

**Se le dice al usuario.** El portal explica que la sesión no se puede
validar.

**No se corrompe un dato.** Redis guarda sesión y caché, no datos de
negocio. **La caché acelera, no es la fuente de verdad**: lo que se pierde
es velocidad.

**Vuelve.** Inmediato. Y hay un detalle que conviene señalar en el
ensayo: **`monitoring-service` sigue funcionando con Redis caído**, porque
es el que tiene que avisar de que Redis se cayó. Su historial sale
**nulo y dicho**, no en cero — un cero se lee como «estuvo caído todo el
rato» y manda a buscar un incidente que no existe.

> Evidencia: `pruebas/test_monitoreo.py::test_el_historial_sobrevive_sin_redis`

---

## 3. MongoDB caído

**Se detecta.** Depende del servicio, y la diferencia es el punto:

- En `documents-service`, `notifications-service` y `reports-service` es
  **esencial** → `no_listo`, 503.
- En `algorithms-service` es **opcional** → `degradado`, **200**. El motor
  evalúa leyendo agregados de PostgreSQL y sólo usa MongoDB para el
  historial de corridas. Declararlo esencial sacaría de servicio una pieza
  que funciona.

**Se registra.** Bitácora, y la sonda guarda **desde cuándo** está caída
(`caida_desde_hace_s`).

**Se le dice al usuario.** `ALMACEN_NO_DISPONIBLE` con **503, no 500**. La
diferencia es útil: 503 dice «reintenta, falta una dependencia»; 500 dice
«el código está roto» y manda a revisar el lugar equivocado.

**No se corrompe un dato.** PostgreSQL no se tocó.

**Vuelve.** En la siguiente sonda, y **de inmediato**: el recuerdo del
fallo se borra al primer éxito en vez de esperar a que caduque. Sin eso,
un servicio recuperado seguiría anunciándose degradado quince segundos.

> Evidencia: `pruebas/test_sonda_de_salud.py::test_la_recuperacion_de_una_opcional_se_detecta_de_inmediato`

---

## 4. PostgreSQL caído — el más importante de explicar

**Se detecta.** Esencial en los 24 → `no_listo`, 503, con
`falta: ["postgresql"]`.

**Se registra.** En el log del servicio. (La bitácora vive en PostgreSQL,
así que con PostgreSQL caído **no hay dónde anotarlo** — eso hay que
decirlo, no esconderlo. Es la razón de que el log del proceso exista
aparte.)

**Se le dice al usuario.** 503 diciendo qué dependencia falta.

**No se corrompe un dato.** Ésta es la que hay que saber explicar bien.
`cursor()` hace **rollback ante cualquier excepción**, así que una
operación que revienta a la mitad no deja media fila escrita.

Por qué importa más que los otros casos: **media operación escrita no
falla al leerse.** Un plan de intervención sin su primera acción, o una
bitácora con la acción y sin su resultado, se leen como datos válidos y
nadie los vuelve a mirar. Un error se ve; media escritura, no.

> Evidencia: `pruebas/test_integracion.py::test_un_fallo_a_media_escritura_no_deja_la_fila_a_medias`
> y `::test_sin_commit_tampoco_queda_nada`

**Vuelve al levantar el servicio — con un matiz medido.** El pool guarda
hasta 5 conexiones, y al reiniciar PostgreSQL quedan **muertas**. Medido:

```
pool caliente con 5 conexiones
PostgreSQL reiniciado. Peticiones despues:
  1: FALLA          <- la conexion muerta del pool
  2: OK
  3: OK  4: OK  5: OK  6: OK

Fallaron 1 peticiones antes de recuperarse.
```

**La primera petición después del reinicio falla**, el pool descarta la
conexión muerta y la siguiente funciona. No hay que reiniciar el servicio.
Bajo concurrencia pueden fallar hasta tantas peticiones como conexiones
muertas se toquen.

**Y esa primera petición ahora contesta bien.** Antes salía como **500
«Error interno del servicio»**, que dice *el código está roto* y manda a
revisar el lugar equivocado, cuando lo que pasó es que la base se reinició
y el sistema ya se está recuperando solo. Ahora:

```
HTTP 503  BASE_NO_DISPONIBLE
Retry-After: 2
"La conexion con la base de datos se perdio, probablemente porque la base
 se reinicio. El servicio esta arriba y la conexion se restablece sola:
 reintenta la operacion. Nada quedo escrito a medias, porque la
 transaccion se deshizo completa."
```

**Cómo se encontró, que vale para el ensayo:** al reiniciar PostgreSQL
para medir cuánto tarda el sistema en recuperarse, tres pruebas de los
clientes fallaron con 500. No era un defecto nuevo del código — era el
reinicio, que es exactamente lo que se estaba midiendo. Pero dejó ver que
el síntoma estaba mal clasificado. Es el mismo razonamiento que con
MongoDB: el servicio está arriba y lo que falló es su dependencia.

Y se distingue por la **clase** de la excepción, no por el texto: un error
de sintaxis en una consulta —que sí es un bug— sigue siendo 500, porque si
todo lo de psycopg2 fuera 503, nadie buscaría nunca ese bug.

> Evidencia: `pruebas/test_sonda_de_salud.py::test_una_conexion_muerta_a_postgresql_es_503_y_no_500`
> y `::test_un_error_de_verdad_sigue_siendo_500`

Decirlo así en el ensayo es mejor que decir «se recupera solo»: se
recupera solo **y cuesta una petición**, y quien lo vea fallar una vez no
va a pensar que está roto.

> Reproducible con `scripts/` + el guion de la medición; el resultado está
> arriba tal como salió.

---

## 5. El servicio de archivos / el bucket caído

**Se detecta.** `documents-service` lo comprueba en su sonda como
dependencia **opcional** → `degradado`, 200, `degradado_por: ["almacen"]`.

Y no basta `isdir`: en producción el almacén es el **punto de montaje del
bucket**, y un montaje muerto deja el directorio *visible* mientras toda
operación real devuelve EIO. Por eso se usa `statvfs`, y se comprueba que
se pueda **escribir** — un bucket montado de sólo lectura pasa cualquier
comprobación de lectura y falla en cada carga.

**Se registra.** Bitácora, y el panel lo muestra.

**Se le dice al usuario.** Quien sube recibe el error del almacén. Quien
consulta metadatos **sigue trabajando**: listar documentos, buscar por
hash y ver quién subió qué siguen funcionando, que es la mayoría del
tráfico. Por eso es opcional: un 503 apagaría esas pantallas por una falla
que sólo afecta a carga y descarga.

**No se corrompe un dato.** Éste es el motivo de que el bucket esté en la
sonda. Sin la comprobación, el servicio decía «listo», aceptaba una carga,
calculaba el hash, **escribía los metadatos en MongoDB** y fallaba al
escribir el blob: quedaba **un documento registrado cuyo archivo no
existe**. El registro dice que la evidencia está, la descarga da 404, y la
bitácora muestra una carga exitosa.

Además: la escritura del blob es a un temporal y después un `rename`, que
es atómico. Escribir directo dejaría, si el proceso muere a la mitad, un
archivo con el nombre correcto y el contenido truncado — justo el caso que
el hash ya no detectaría, porque nadie lo volvería a calcular.

> Evidencia: `pruebas/test_archivos_evidencia.py::test_una_escritura_a_medias_no_deja_un_archivo_valido_a_medias`

**Vuelve.** Inmediato al remontar. La consulta al bucket de Cloud Storage
se cachea 30 s, así que puede tardar eso en reflejarse.

---

## 6. Una petición que excede el tiempo máximo

**Se detecta.** Tres límites escalonados, y el orden es la decisión:

| Límite | Valor | Quién | Qué recibe el cliente |
|---|---|---|---|
| `statement_timeout` | 15 s | PostgreSQL | 503, conexión del pool intacta |
| Plazo de la petición | 20 s | el servicio | 503 diciendo en qué se gastaba |
| `--timeout` gunicorn | 30 s | gunicorn | **nada: conexión cortada** |

El de gunicorn va **por encima** a propósito: si actuara primero, los dos
buenos no se verían nunca.

**Se registra.** En la bitácora como `ANALISIS_EJECUTADO` / `RECHAZADO`.
Esto **faltaba**: la petición devolvía un 503 correcto y no quedaba rastro
en ningún lado, así que quien revisara la bitácora después de que alguien
se quejara de que «el análisis no carga» no encontraba nada y el problema
parecía no haber ocurrido.

> Evidencia: `pruebas/test_algoritmos.py::test_un_corte_por_tiempo_queda_en_la_bitacora`

**Se le dice al usuario.** 503 `TIEMPO_EXCEDIDO` con `Retry-After`,
identificador de correlación y un mensaje que dice qué hacer. Verificado
contra un servidor real con gunicorn, no sólo con el cliente de pruebas.

**No se corrompe un dato — la frase que hay que poder decir.**

> **El análisis se detiene y no guarda un resultado a medias.**

El corte ocurre **entre unidades**, no en medio de una, y las escrituras
—la caché y la bitácora de éxito— están **después** de que el motor
termina. Un informe parcial sería **peor que ninguno**: un especialista lo
leería como si estuviera completo y concluiría que las unidades que faltan
están bien.

> Evidencia: `pruebas/test_algoritmos.py::test_un_corte_por_tiempo_no_deja_un_informe_a_medias`

Y es **cooperativo**, no una alarma: `signal.alarm` sólo llega al hilo
principal y el servicio corre con `--threads 2`, así que cortaría una
petición **al azar**, no la lenta. Matar un hilo a la fuerza en Python lo
deja a medias, posiblemente con una transacción abierta y una conexión del
pool inutilizable — es decir, provocaría exactamente lo que se quiere
evitar.

**Vuelve.** No aplica: no se cayó nada. La siguiente petición corre
normal.

---

## Un error propio que vale la pena contar en el ensayo

El plazo estuvo primero **sólo en la preparación de datos**, que es la
parte barata —recorrer un diccionario—. El trabajo caro está en el motor:
la silueta es O(u²) y Theil-Sen O(c²) por serie.

O sea: **el corte no habría disparado nunca donde de verdad se gasta el
tiempo.** Una petición pesada seguía terminando en manos de gunicorn, que
mata al obrero. El límite existía, se veía bien, y no servía.

Ahora el motor pregunta por el plazo entre etapas y dentro del bucle por
unidad, y hay una prueba que lo fija
(`test_el_motor_pregunta_por_el_plazo_en_sus_etapas_caras`).

Es un buen ejemplo de la diferencia entre *tener* un control y que el
control *esté donde sirve* — y es el tipo de pregunta que puede caer.

---

## Dos advertencias para el día del ensayo

1. **No usar `carlos.ramirez` para la prueba de cinco intentos
   fallidos.** Se bloquea 15 minutos y es la cuenta que abre el panel.
   Usar otro correo.
2. **El emulador va con la variante `debug`.** La `release` apunta a los
   dominios de producción y desde el emulador no resuelven: el síntoma es
   idéntico al de un backend caído y lleva a revisar el servidor, que está
   bien. Está en el registro de incidencias como INC-003.
