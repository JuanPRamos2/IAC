# Rendimiento, bases de datos y pruebas de carga

Proyecto 4. Plataforma de Bienestar Laboral y Prevención de Burnout
Integración de Aplicaciones Computacionales · UDEM · Equipo 03 · Tercer parcial

| | |
|---|---|
| Emiliano Pascual Piñales Sánchez | #657657 |
| Rol en este parcial | Integrante 3 — algoritmos, bases de datos y pruebas de rendimiento |

Guiones: `scripts/datos_masivos.py`, `scripts/rendimiento.py`,
`scripts/cuentas_de_carga.sql`, `pruebas/carga/locustfile.py`
Índices: `db/migraciones/018_analisis_complejo_y_rendimiento.sql`
El algoritmo complejo va en su propio documento: `Algoritmo_Complejo_Equipo03.md`

---

## 1. Los datos con los que se midió

Medir sobre los datos de demostración no mide nada: con 16 unidades y
3 800 respuestas todo es rápido, y los problemas que importan aparecen
justamente con volumen. `scripts/datos_masivos.py` genera una
organización completa:

| | |
|---|---|
| Empleados | 26 526 (8% sin consentimiento, como en la realidad) |
| Unidades organizacionales | 136, en árbol de dos niveles |
| Campañas | 12 |
| Respuestas de autorreporte | 206 231 |
| Valores de detalle | 1 031 155 |
| Agregados protegidos | 8 280 (8 232 publicados) |
| Tiempo de generación | 798 s en total; 14.7 s las respuestas |
| Escala de ruido media | 0.0368 |

Dos decisiones del generador que condicionan todo lo demás:

**La plantilla del padre es la suma de los hijos.** Si no, un ataque por
diferencia —restar los hijos conocidos al padre— aísla un residuo por
debajo del umbral k. La invariante se mantiene desde la migración 008 y el
generador la respeta.

**Los agregados se calculan con la función oficial**, no con un INSERT
directo. `agregado.fn_calcular_agregado_protegido` es el único camino que
aplica el recorte al rango, la comprobación de k, el ruido de Laplace y la
contabilidad de épsilon. Un generador que escribiera agregados a mano
produciría datos que el sistema nunca habría publicado, y entonces la
medición sería sobre otra base de datos.

**Por qué la escala de ruido importa tanto.** Con el volumen de la demo,
una unidad de 8 personas recibe ruido con escala 0.5, y el umbral de
detección al 95% queda en 2.118 puntos sobre una escala de 1 a 5: nada es
detectable. Con 60 a 400 personas por unidad la escala baja a 0.01–0.07 y
el umbral a ~0.30. **El volumen no es un adorno de la prueba: es lo que
hace demostrable al algoritmo.**

---

## 2. Índices y optimización de consultas

Siete índices, cada uno con su motivo escrito en la migración. Un índice
sin motivo documentado es uno que nadie se atreve a quitar cuando deja de
servir: ocupa espacio, frena cada escritura, y como nadie sabe por qué
está, ahí se queda.

Tres de los siete son **parciales**, con
`WHERE estado_publicacion = 'PUBLICADO'`. No es adorno: todo lo que leen
el tablero, el motor de reglas y el análisis complejo son resultados
publicados —los suprimidos por el umbral k nunca se consultan, solo se
cuentan— así que dejarlos fuera deja el índice a la mitad y no cambia una
sola respuesta.

### 2.1 Los tres hallazgos, con su causa y su medición

Los tres se encontraron leyendo planes de ejecución, no adivinando por el
tiempo de respuesta. Una consulta puede ser rápida y estar haciendo un
recorrido secuencial porque la tabla cabe en memoria, y eso deja de ser
cierto el día que crece.

**(a) Un índice inerte por una columna al final.** 89 ms → 21 ms.

`agregado.fn_calcular_agregado_protegido` es el camino más caliente del
sistema: 7 920 llamadas para calcular una organización de 110 unidades y
12 campañas. Medía **89 ms por llamada**, y 30 de esos 89 los gastaba una
sola consulta: la que cuenta el tamaño del grupo con consentimiento
vigente.

En el plan, `consentimiento.v_estado_vigente` **ordenaba las 24 476 filas
de la tabla de consentimientos completa en cada llamada** para resolver
los 198 seudónimos que la consulta necesitaba. Y ya existía un índice para
eso, `idx_consent_seud` sobre `(seudonimo_id, fecha_evento DESC)`. No se
usaba, porque el `ORDER BY` de la vista es

```sql
ORDER BY seudonimo_id, fecha_evento DESC, consentimiento_id DESC
```

con una **tercera clave** que el índice no cubre. PostgreSQL no podía
resolver el `DISTINCT ON` con él y caía al ordenamiento completo. Un
desajuste de una columna al final, y el índice queda inerte sin que nada
lo diga: la consulta sigue devolviendo el resultado correcto.

Con `ix_consent_vigente`, que cubre las tres claves en el mismo orden:

| | antes | después |
|---|---|---|
| consulta del tamaño del grupo | 30.5 ms | 11.3 ms |
| **la función completa** | **89 ms** | **21 ms** (4.2x) |

Y de paso `respuesta_detalle` pasa a *Index Only Scan*.

**(b) Una subconsulta correlacionada sin índice.** 458 ms → 4.6 ms.

Lo encontró la **prueba de carga**, no una revisión de código:
`/consultas/presupuesto` tenía mediana de 16 ms y p95 de **2 700 ms**. Esa
distancia entre mediana y p95 es la firma de una caché que tapa un
problema — los aciertos van a 16 ms y el fallo paga la consulta real — y
el TTL de ese recurso es de diez segundos a propósito, porque un dato
viejo de presupuesto de privacidad lleva a creer que queda épsilon cuando
ya se agotó.

`agregado.v_estado_presupuesto` cuenta las consultas de cada presupuesto
con una subconsulta correlacionada, y `agregado.consulta_privada` no tenía
índice por `presupuesto_id`: un recorrido secuencial **por cada una de las
1 372 filas** de presupuesto. 1 372 × 0.31 ms = 425 de los 458 ms.

Con el índice, la subconsulta pasa a *Index Only Scan*: **458 ms →
4.6 ms, cien veces**. Y queda claro por qué no lo encontró una revisión
con los datos de demostración: ahí hay 40 filas de presupuesto en lugar de
1 372, y cuarenta recorridos de una tabla de seis filas no se notan. **El
costo de una subconsulta correlacionada crece con las filas de fuera**, que
es justo lo que unos datos de demostración no tienen.

**(c) Una consulta del banco de pruebas que yo había inventado.**

La primera versión de `scripts/rendimiento.py` medía la unión
respuesta-detalle para la **campaña entera**: 42 ms y un recorrido
secuencial del millón de filas de detalle. Conclusión aparente: los
índices no sirven.

Pero ningún endpoint ejecuta esa consulta. La forma real —una unidad y una
campaña, que es lo que hace la función de agregados 1 320 veces— usa los
dos índices en bucle anidado y tarda **0.834 ms**. El recorrido secuencial
era además el plan *correcto* para la forma inventada, porque PostgreSQL
lee casi toda la tabla y un índice no ayuda.

Queda apuntado porque es el error más fácil de cometer midiendo
rendimiento: **medir una consulta que el sistema no hace** y sacar
conclusiones sobre el sistema.

### 2.2 MongoDB: seis índices que faltaban

Las consultas a PostgreSQL se midieron con `EXPLAIN ANALYZE`. Con MongoDB
no se pudo hacer lo mismo: **no está instalado en este ambiente y no se
puede instalar** —las pruebas usan `mongomock`, que no implementa
`explain()`—. Decirlo importa, porque lo que sigue es menos que una
medición: es un **análisis del código**, y encuentra la misma clase de
defecto.

`pruebas/test_indices_mongo.py` lee las 44 consultas a MongoDB de los
cuatro servicios que la usan, extrae su filtro y su campo de orden, y
comprueba contra los índices declarados aplicando las dos reglas de
MongoDB:

- **Prefijo.** Un índice compuesto `(a, b, c)` sirve para un filtro por
  `a`, por `(a, b)` o por `(a, b, c)`. **No** sirve para uno que filtra
  solo por `b`.
- **Orden.** Para que un índice sirva para ordenar por `k`, las claves
  anteriores a `k` en el índice tienen que estar fijadas por una igualdad
  en el filtro.

Encontró **seis consultas sin índice**, de 44:

| Consulta | Qué le pasaba |
|---|---|
| `documentos.find_one({hash_contenido, tipo})` | La consulta de **cada descarga de evidencia**. Ningún índice empezaba por `hash_contenido`: recorrido completo de la colección por descarga |
| `documentos.find({campania_id}).sort(fecha_creacion)` | El índice tenía `campania_id` en **segunda** posición, así que no se podía usar. Recorrido completo **más** orden en memoria |
| `documentos.find({}).sort(fecha_creacion)` | La pantalla de listado, que es la que se abre primero. Ningún índice empezaba por `fecha_creacion` |
| `/notificaciones/mias` sin `solo_sin_leer` | El índice es `(destinatario, leida, fecha_creacion)`; sin fijar `leida` no se puede usar **para ordenar**. Es el endpoint que más llama la aplicación móvil |
| `dispositivos_push.delete_one({token})` | `token` es la segunda columna de su índice. Es la única vía de limpieza de la colección, así que se vuelve lenta justo cuando hay más que limpiar |
| `/algoritmos/corridas` sin `campania_id` | Ordena por `fecha` con el filtro vacío y ningún índice empezaba por ahí |

**Por qué los cuatro casos de `sort` son los que más importan, y no por
lentos:** un ordenamiento sin índice en MongoDB se hace en memoria, tiene
un límite de 32 MB y **falla al pasarlo**. No se degrada: deja de
funcionar, y lo hace justo cuando la colección creció lo suficiente para
que el endpoint importe.

Se agregaron los seis índices, y la colección de documentos pasó de 4 a 7,
la de notificaciones de 4 a 5, los dispositivos de 1 a 2 y las corridas de
4 a 5. Veintiséis índices en total entre los cuatro servicios, todos
creados por `asegurar_indices` y verificados.

### 2.3 Una prueba que grita en falso se acaba desactivando

La primera versión de ese analizador trataba todo filtro armado en una
variable como «podría estar vacío», y produjo **tres falsos positivos**:
el listado de notificaciones y el de reportes siempre llevan una clave
—`destinatario_usuario_id` el uno, `tipo` el otro— porque se asigna en el
literal inicial o con un `setdefault` incondicional.

Dejarlos habría sido peor que no tener la prueba: una prueba que avisa de
problemas que no existen se desactiva, y entonces deja de encontrar los
que sí. Así que el analizador resuelve lo que se puede resolver —las
claves del literal de la asignación y las de los `setdefault`, que son
incondicionales— y **no** cuenta las que se agregan dentro de un `if`, que
son justamente las que pueden faltar.

De los tres avisos quedó uno, y era real.

### 2.4 Un error de medición propio: la unidad al azar

La versión anterior de esta sección traía una tabla de una sola columna de
tiempos. Estaba mal, y lo que la delató fueron dos corridas seguidas del
mismo guión contra la misma base, sin que nada cambiara entre ellas:

| Medición | corrida A | corrida B |
|---|---|---|
| tamaño del grupo con consentimiento | 7.45 ms | 110.96 ms |
| `fn_calcular_agregado_protegido` | 15.85 ms | 226.41 ms |

Catorce veces de diferencia. La causa no estaba en la base: el guión
elegía a quién medirle con `ORDER BY random() LIMIT 1`, y las unidades van
de 48 a 2 528 respuestas. Cada corrida medía otra cosa.

Lo que esto costaba no es la precisión, es la utilidad: **un banco de
pruebas cuyo objetivo cambia en cada corrida no sirve para comparar**, que
es para lo único que sirve un banco de pruebas. Y casi puse el 15.85 ms en
este documento como «el» tiempo del camino caliente.

La corrección está en `unidades_representativas()`: se eligen **tres**
unidades por volumen —la más chica, la mediana y la más grande—, de forma
determinista y por orden de respuestas con desempate por identificador.
Las tres se miden y las tres se reportan. El número útil no es un promedio
sino el **rango**: la unidad grande decide si el sistema aguanta y la
mediana es lo que vive la mayoría.

(El guión sí escribe: cada llamada al camino caliente publica agregados,
así que el par «más grande» puede desplazarse un poco entre corridas. La
regla de selección es determinista; los datos no están congelados.)

### 2.5 Tiempos finales de consulta, por volumen

Medianas de 7 repeticiones, descartando la primera —paga el arranque del
plan y la lectura de disco, y mezclarla inventa una cola que no describe
el uso real—. Las tres unidades: 48, 870 y 2 528 respuestas.

| Consulta | chica (48) | mediana (870) | grande (2 528) | plan |
|---|---|---|---|---|
| tablero de una unidad | 0.10 ms | 0.10 ms | 0.09 ms | índice |
| serie completa de una unidad | 0.17 ms | 0.19 ms | 0.20 ms | índice |
| matriz de toda una campaña | 0.12 ms | 0.49 ms | 0.51 ms | índice |
| recuento de respuestas por unidad | 0.12 ms | 0.92 ms | 0.92 ms | índice |
| unión de una unidad y campaña | 0.20 ms | 0.41 ms | 0.67 ms | índice |
| tamaño del grupo con consentimiento | 12.74 ms | 7.43 ms | 8.15 ms | índice |
| **`fn_calcular_agregado_protegido`** | — | — | **17.6 ms** (min 17.2, max 21.4) | — |

**Lo que la tabla de una sola columna escondía y ésta muestra:**

1. **Cinco de las seis consultas son planas o casi planas en el volumen
   de la unidad.** Multiplicar por 53 las respuestas de la unidad cambia
   el tablero en nada y la unión en 3.4×. Eso es la firma de un índice que
   de verdad acota: el trabajo depende de las filas que se devuelven, no
   de las que existen.

2. **`tamaño del grupo con consentimiento` es más lenta en la unidad
   CHICA.** 12.74 ms contra 8.15 ms, al revés del volumen. No es ruido: el
   costo de esa consulta no está en la unidad sino en recorrer el estado
   de consentimiento vigente —20 602 bloques de caché, el 100 % en
   memoria— y la unidad chica pertenece a otra campaña con otra
   distribución. La conclusión práctica es que esa consulta **no se
   optimiza acotando la unidad**, que es lo que la tabla de una columna
   habría sugerido.

### 2.6 Tamaños

| Tabla | total | índices | filas |
|---|---|---|---|
| `autoreporte.respuesta_detalle` | 112 MB | 69 MB | 1 031 155 |
| `autoreporte.respuesta` | 34 MB | 16 MB | 206 231 |
| `agregado.resultado_protegido` | 2.3 MB | 944 kB | 8 284 |
| `agregado.consulta_privada` | 1.0 MB | 200 kB | 8 236 |

Los índices de `respuesta_detalle` pesan 69 MB sobre 112 MB de datos. Es
mucho y está justificado: sin ellos, cada una de las 7 920 llamadas a la
función de agregados recorre el millón de filas.

---

### 2.7 Consumo de recursos

El requisito pide medir, con datos masivos, el consumo de recursos además
del tiempo. Lo obvio sería leer la memoria del proceso que corre el guión;
mediría lo que no importa, porque ese proceso manda una cadena de SQL y
espera. El trabajo —leer un millón de filas, agruparlas, ordenarlas— lo
hace el proceso **servidor** de PostgreSQL. Así que se mide el backend que
atiende la conexión: `pg_backend_pid()` dice cuál es, y `/proc/<pid>/stat`
y `/proc/<pid>/status` dan su CPU y su memoria.

#### Por consulta

| Consulta | reloj | CPU | CPU/reloj | bloques en memoria | derrames a disco |
|---|---|---|---|---|---|
| tablero de una unidad | 0.09 ms | 0.066 ms | 73 % | 6 | ninguno |
| serie completa de una unidad | 0.20 ms | 0.179 ms | 90 % | 184 | ninguno |
| matriz de toda una campaña | 0.51 ms | 0.371 ms | 73 % | 19 | ninguno |
| recuento de respuestas por unidad | 0.92 ms | 0.985 ms | ~100 % | 38 | ninguno |
| unión de una unidad y campaña | 0.67 ms | 0.649 ms | 97 % | 3 831 | ninguno |
| tamaño del grupo con consentimiento | 8.15 ms | 8.214 ms | ~100 % | 20 602 | ninguno |

**Tres cosas que sólo se ven aquí:**

1. **CPU ≈ reloj en todas.** Significa que ninguna consulta espera disco:
   los 100 % de aciertos de caché lo confirman desde el otro lado. La
   consecuencia práctica es que **estas consultas no se mejoran con disco
   más rápido ni con más índices** —ya no leen de disco—; se mejoran
   haciendo menos trabajo. Con sólo el reloj esto es indistinguible de una
   consulta que espera E/S, y se arreglan en lugares opuestos.

2. **Cero derrames a `work_mem`.** El plan dice cuánta memoria usó cada
   ordenación y cada tabla hash y si tuvo que derramar a disco. El pico
   medido es de 49 kB contra 4 MB de `work_mem`: hay margen de ochenta
   veces. Importa porque un derrame es la diferencia entre 5 ms y 500 ms y
   **aparece de golpe** cuando los datos crecen un poco más. Con datos de
   demostración no ocurriría nunca; con un millón de filas es lo que había
   que comprobar.

3. **Memoria del backend: 27 MB, pico 27 MB.** Plana en las seis
   consultas. El número que dimensiona no es ése sino ése multiplicado por
   la concurrencia: en el pico de carga medido (440 usuarios), el límite
   del pool —`PG_POOL_MAX=5` por servicio— es lo que mantiene este número
   acotado.

#### De la generación masiva, por fase

La medición separada por fase corrigió una conclusión equivocada. El guión
reportaba una sola cifra, «filas por segundo» sobre el tiempo total:

```
    filas por segundo:        2 168  (respuestas + valores)
```

Eso hacía creer que la carga es lenta. No lo es, y las dos fases hacen
cosas opuestas:

```
==> CONSUMO DE RECURSOS
    generador, memoria pico:  28.1 MB
    backend, memoria pico:    51.3 MB  (shared_buffers 128MB, maintenance_work_mem 64MB)
    backend, cpu:             61.27 s de 61.7 s de reloj (99%)
    insercion (COPY):         99 998 filas/s en 0.97 s
    calculo de agregados:     888 en 60.5 s (68.1 ms cada uno, limitado por CPU)
```

- La **inserción** entra a 100 000 filas por segundo con `COPY`. La cifra
  conjunta la describía 46 veces peor de lo que es.
- El **cálculo de agregados** es el 98 % del tiempo, y el backend está al
  **99 % de CPU**. Es decir: la tubería de privacidad diferencial —recorte,
  umbral *k*, ruido de Laplace, contabilidad de épsilon— está **limitada
  por cómputo, no por disco**. Ni un disco más rápido ni un índice más la
  mejoran; la palanca es el paralelismo, porque las llamadas son
  independientes entre unidades.
- El **generador** se mantiene en 28 MB: arma los lotes y los entrega con
  `COPY` en vez de acumular un millón de tuplas en memoria. Esa diferencia
  no se ve en el reloj —el tiempo total es el mismo— hasta el momento en
  que el proceso se cae en un contenedor con poca memoria.

#### Del servidor

| | |
|---|---|
| `shared_buffers` | 128 MB |
| `work_mem` | 4 MB |
| memoria por backend | mediana 32.0 MB, máximo 32.0 MB |
| pico del guión cliente | 38.8 MB |

La memoria compartida y la privada se reportan aparte porque se
dimensionan distinto: la compartida es una decisión de configuración que
se paga una vez, y la privada se multiplica por la concurrencia. Sumar los
RSS de los backends da una **cota superior** y no la memoria real, porque
cada RSS incluye la parte de `shared_buffers` que ese backend ya tocó; el
informe lo dice en lugar de presentar el total como si fuera memoria
distinta.

#### Un error de medición que esta sección introdujo y luego corrigió

Al añadir el conteo exacto de filas, la función de tamaños quedó corriendo
**al principio**. Contar `respuesta_detalle` lee 112 MB por unos
`shared_buffers` de 128 MB: desalojaba justo las páginas que las consultas
siguientes iban a usar, y todas se medían con la caché de PostgreSQL fría.
El informe describía un estado que no es el de operación. Ahora los
tamaños se miden al final, y está comentado en el guión para que nadie lo
mueva.

Y de paso: ese conteo empezó leyendo `n_live_tup` de
`pg_stat_user_tables`, que devolvía **0** hasta que autovacuum pasara, y
cayó a `reltuples`, que devolvía **5** para una tabla con 8 299 filas
porque era lo que dejó el último `ANALYZE`. Una columna de volumen
equivocada invalida el informe entero: el volumen es la variable
independiente de todo lo demás. Se cuentan.

---

## 3. Caché: con y sin Redis

### 3.1 El análisis complejo, que es el caso que importa

Medido sobre HTTP contra los datos masivos, con `?sin_cache=1` para forzar
el recálculo:

| | mediana |
|---|---|
| Sin caché (calcula) | **115 ms** |
| Con caché (Redis) | **9.3 ms** |
| **Mejora** | **12.4x**, ahorra ~106 ms por petición |

De los 115 ms, 64 son el algoritmo y el resto es cargar los datos de
PostgreSQL. El informe se cachea diez minutos: depende solo de agregados
**publicados**, y publicar es una operación deliberada que nadie hace cada
minuto.

**El endpoint acepta `?sin_cache=1` y eso existe para poder medir.** Una
medición de rendimiento tomada contra una caché caliente no mide el
algoritmo, mide Redis. La prueba de carga ejerce los dos caminos con
nombres distintos (`[cache]` y `[sin cache]`) para que la comparación salga
del mismo informe y bajo la misma carga.

**Y la caché guarda el informe GLOBAL; el recorte por alcance se aplica
después de leerla.** Al revés —cachear lo ya recortado— la clave tendría
que incluir el alcance de quien pregunta, y un fallo al construir esa clave
serviría a un líder de unidad el informe completo de la organización.

La semilla del agrupamiento va en la clave: si alguien la cambia, los
informes guardados caducan solos en lugar de servirse como si fueran del
algoritmo de hoy.

### 3.2 La metodología, porque es fácil falsearla

Comparar «con y sin caché» exige **borrar la clave entre corridas**. Si no,
la segunda medición siempre gana y la conclusión está escrita de antemano.
`scripts/rendimiento.py` borra la clave antes de cada medición «sin caché»
y lo dice en la salida.

### 3.3 El panel de monitoreo: 1 635 ms → 2.8 ms

Este no era una optimización buscada, salió de la prueba de carga.

`/monitoreo/componentes` sondea a los 24 componentes en paralelo, y tarda
lo que tarda el más lento en contestar su propia sonda: **1.4 s medidos**.
Mientras eso ocurre, la petición **ocupa un obrero de gunicorn**, y el
servicio corre con `--workers 2`.

El efecto, medido directamente:

| | |
|---|---|
| `GET /monitoreo/errores` solo | **5 ms** |
| `GET /monitoreo/errores` con 4 peticiones de panel en vuelo | **2 549 ms** |

Quinientas veces peor, y la consulta de `errores` es de 1.1 ms: todo lo
demás era cola. **Un panel de monitoreo que se vuelve inservible cuando
hay carga es un panel que falla exactamente cuando hace falta.**

Y había un segundo problema independiente: sin caché, cada apertura del
panel sondea a los 24 componentes. Con varios administradores mirando el
tablero eso son cientos de sondas por minuto contra el sistema que se está
vigilando. **El monitoreo se convierte en carga.**

La corrección es una caché de 5 s **en Redis y no en memoria del proceso**,
porque los obreros son procesos distintos y en memoria cada uno tendría la
suya. Resultado: **1 635 ms → 2.8 ms** en acierto. Y la respuesta dice
siempre `sondeo_edad_segundos`: un tablero que muestra información vieja
sin decirlo es peor que uno lento, porque quien opera decide creyendo que
ve el ahora.

### 3.4 La sonda de salud: 1 286 ms → 53 ms

El mismo tipo de problema, un nivel más abajo.

`algorithms-service` declara MongoDB **opcional**: evalúa leyendo
PostgreSQL y solo usa MongoDB para el historial de corridas. Con MongoDB
caído atiende perfectamente, y por eso la sonda responde «degradado» con
200 en lugar de sacarlo de rotación.

Eso estaba bien y seguía roto por otro lado: el cliente de MongoDB espera
1.2 s antes de rendirse, y la sonda lo esperaba **en cada llamada**. Medido:
**1 286 ms**. Un orquestador que sondea con un segundo de paciencia declara
muerto a un servicio que está atendiendo bien, y justamente por preguntar
si algo que no necesita está disponible. **El efecto anula el sentido de
haber declarado la dependencia opcional.**

Tres correcciones, en `comun/servicio.py`:

1. **Presupuesto propio** para las comprobaciones opcionales (300 ms): si
   no contestan en ese plazo se dan por caídas sin esperarlas más.
2. **Recuerdo del fallo** (15 s): un fallo *es* una espera agotada, así que
   recordarlo evita pagarla otra vez.
3. **Reintento con presupuesto corto** (50 ms) cuando hay un fallo
   recordado. Sin esto había que elegir entre pagar la espera completa cada
   vez o no detectar la recuperación hasta que caducara el recuerdo —y una
   prueba lo encontró: una dependencia que volvía seguía anunciándose caída
   quince segundos. Con un fallo recordado la pregunta es más fácil: no
   «¿funciona?» sino «¿ya volvió?», y eso se contesta rápido o no se
   contesta.

Y una asimetría deliberada: **una dependencia esencial no se recuerda nunca
y no tiene presupuesto.** Su resultado decide si mandar tráfico, y ahí vale
más la respuesta correcta que la rápida: un «listo» viejo sobre una
esencial manda tráfico a un servicio roto, y una esencial que vuelve tiene
que detectarse en la siguiente sonda.

Resultado: la sonda pasa de **1 286 ms a 53 ms estables**, y sigue
reportando `degradado` con la causa real de MongoDB y desde cuándo. Lo fija
`pruebas/test_sonda_de_salud.py`, 17 casos.

### 3.5 El bucket, y lo que una clave ausente no puede significar

Las sondas comprobaban PostgreSQL, MongoDB y Redis. Faltaba el **almacén
de archivos**, y faltaba justo en `documents-service`, que es el que lo
tiene. La consecuencia no es cosmética:

> Con el almacén caído, la sonda contesta «listo» y 200 —PostgreSQL
> responde, MongoDB responde, Redis responde—. El servicio acepta una
> carga, valida el archivo, calcula su hash, escribe los metadatos en
> MongoDB… y falla al escribir el blob, con el registro ya creado.

Queda **un documento registrado cuyo archivo no existe**: el registro dice
que la evidencia está, la descarga da 404, y la bitácora muestra una carga
exitosa. Que la sonda lo vea antes no evita el fallo, pero lo pone donde
se mira.

Se declara **opcional**, no esencial, y la razón es que un 503 sería peor:
con el almacén caído el servicio todavía sirve el listado de documentos,
la búsqueda por hash y la consulta de quién subió qué —la mayoría del
tráfico—. Un 503 apagaría esas pantallas por una falla que sólo afecta a
la carga y la descarga. Así que `degradado`, 200 y
`degradado_por: ["almacen"]`.

**Qué se comprueba, y por qué `isdir` no basta.** En producción el almacén
es el punto de montaje del bucket, y **un montaje muerto deja el
directorio visible** mientras cualquier operación real sobre él devuelve
EIO. `statvfs` es una llamada al sistema de archivos de verdad: con el
montaje caído lanza. Y se comprueba que se pueda **escribir**, no sólo
leer: un bucket montado de sólo lectura —porque la cuenta de servicio
perdió el permiso, la falla de permisos más común en GCS— pasa cualquier
comprobación de lectura y falla en cada carga. Si hay `GCS_BUCKET`
configurado, se pregunta además a Cloud Storage, a lo más una vez cada 30 s
porque la sonda la contestan el orquestador y el panel varias veces por
minuto.

**Y la sonda ahora dice lo que *no* comprueba.** Un panel que recibe
`dependencias: {postgresql, redis}` de `users-service` no puede distinguir
«este servicio no usa MongoDB» de «la comprobación de MongoDB no se
ejecutó»: las dos se ven igual, la clave no está, y las consecuencias son
opuestas —la primera es normal, la segunda es un hueco de
observabilidad—. Con `no_aplican`, el silencio deja de ser ambiguo: una
dependencia que no esté ni en `dependencias` ni en `no_aplican` es un
error de declaración y se nota. El conjunto completo lo decide una lista
en `comun`, así que agregar una dependencia al sistema la hace aparecer de
inmediato en las sondas de los veinte servicios.

### 3.6 Historial de disponibilidad en el panel

El panel contestaba «¿cómo está el sistema?». No contestaba «¿cómo ha
estado?», y son preguntas distintas que se usan para cosas distintas:

1. **Un servicio que se cae y se levanta no dejaba rastro.** Con sondeos
   cada cinco segundos, una caída de cuarenta segundos es invisible salvo
   que alguien esté mirando la pantalla en ese momento. Un componente que
   hace eso veinte veces al día está caído para uno de cada veinte
   usuarios, al azar, y nadie lo puede reproducir.
2. **«Está listo» no decía si acaba de recuperarse.** Un verde después de
   un incidente se leía igual que un verde que nunca falló, y cerrar el
   incidente era una decisión a ciegas.

Ahora `/monitoreo/componentes` trae `historial_disponibilidad` por
componente: ventana de 60 minutos en cubetas de un minuto, porcentaje de
disponibilidad, muestras, minutos con falla, último estado y desde cuándo.
`/monitoreo/componentes/<nombre>?ventana_minutos=10` acota la ventana,
porque durante un incidente diez minutos dicen más que una hora.

**Cuatro decisiones que deciden si el número significa algo:**

| Decisión | Por qué |
|---|---|
| `degradado` cuenta como **disponible** | Devuelve 200 a propósito: el servicio atiende. Contarlo como caída daría un número que no describe lo que vivió ningún usuario. Se cuenta aparte, porque degradado mucho tiempo también es un problema |
| `desconocido` **no cuenta** ni a favor ni en contra | Significa que no supimos interpretar la respuesta, o sea que el fallo puede ser nuestro. Meterlo en el numerador o en el denominador sería culpar al componente de un fallo del monitoreo. Se reporta aparte |
| Se reportan las **muestras** junto al porcentaje | Un 100 % sobre tres muestras no es un 100 % sobre setecientas, y un panel que no distingue las dos miente sin decir ninguna falsedad |
| Sólo cuentan los **sondeos reales**, no las lecturas de caché | El sondeo se reutiliza hasta 5 s. Si cada apertura del panel sumara una muestra, diez administradores mirando el tablero multiplicarían por diez el denominador sin sondear una vez más |

Un minuto con alguna muestra no disponible se marca como minuto con falla,
sin promediar: promediarlo esconde una caída de diez segundos dentro de un
minuto que sale al 83 %.

El historial vive en Redis —los obreros de gunicorn son procesos distintos
y en memoria cada uno tendría el suyo— y se cuenta con `HINCRBY`, que es
atómico: leer-sumar-escribir pierde muestras con dos obreros sondeando a
la vez, sin que nada falle. Y es **de mejor esfuerzo**: este servicio es el
que avisa de que Redis se cayó, así que con Redis abajo el panel sigue
funcionando y el historial sale **nulo y dicho**, no en cero —un cero se
lee como «estuvo caído todo el rato» y manda a buscar un incidente que no
existe.

---

## 4. Pruebas de carga con Locust

### 4.1 Lo que midió cada corrida, y los tres intentos que no midieron nada

Las tres primeras corridas dieron tasas de error del 34.6%, 37.9% y 42.0%.
**Ninguna de las tres hablaba del sistema**, y vale la pena contarlas porque
el error es el más común al medir carga: medir la prueba en lugar del
sistema medido.

| Corrida | errores | qué estaba midiendo en realidad |
|---|---|---|
| 1 | 34.6% | el límite de 30 inicios de sesión por minuto **y por IP**: los 150 usuarios virtuales salen de 127.0.0.1 y lo comparten. 65 rechazos con 429 y 899 peticiones con 401 después, de los usuarios que se quedaron sin token |
| 2 | 37.9% | el límite de 120 peticiones por minuto **y por token**, al compartir un token por perfil entre cien colaboradores |
| 3 | 42.0% | `403 SIN_SEUDONIMO`: las cuentas de carga no estaban ligadas a un empleado, así que no tenían seudónimo. El servicio contestaba correctamente a una pregunta que no podía tener respuesta |

Y hubo un cuarto error, anterior: el colaborador pedía
`/consultas/tablero/unidad/{id}` y `/consultas/participacion`, que exigen
`AGREGADO_UNIDAD`. Un colaborador no tiene ese permiso —y no debe tenerlo,
son cifras agregadas de su área, no suyas— así que devolvían 403. Con peso
10 de 16, eran el 52% de las peticiones. **El informe habría dicho «52% de
errores bajo carga» cuando lo que había era el sistema de autorización
funcionando correctamente contra una prueba mal escrita.**

Las correcciones, todas en la dirección de parecerse a producción:

- **Una cuenta por usuario virtual** (`scripts/cuentas_de_carga.sql`, 166
  cuentas en la proporción de los pesos de la prueba), cada una ligada a un
  empleado con seudónimo. En producción 150 usuarios son 150 cuentas.
- **Un ritmo de llegada creíble**: medio nacimiento por segundo, que son 30
  por minuto, justo el límite. Treinta inicios de sesión **por segundo** no
  es un patrón real; ni el cambio de turno de una planta produce eso.
- **Cada tarea en el perfil que la puede ejecutar.**
- **Los servicios no listos se saltan** y se imprime cuáles: sus 503
  entrarían en la tasa de error y mezclarían un problema del ambiente con
  uno de capacidad, que son las dos cosas que una prueba de carga existe
  para distinguir.
- **Un usuario sin token se detiene** en lugar de pasar la corrida
  generando 401.

### 4.2 Corrida realista: rampa escalonada y vuelta

140 usuarios concurrentes, llegando a medio usuario por segundo, con
esperas de persona (2–15 s según el perfil). 17 servicios arriba, 7 no
listos por falta de MongoDB en el ambiente de medición.

| | |
|---|---|
| Peticiones | 5 601 |
| **Fallidas** | **1 (0.02%)** |
| Peticiones/segundo | 11.2 de media, 23.7 en el pico |
| Tiempo medio | 44 ms |
| Mediana | 14 ms |
| **p95** | **40 ms** |
| p99 | 1 600 ms |
| Máximo | 1 726 ms |
| p95 < 800 ms | **CUMPLE** |
| errores < 1% | **CUMPLE** |

El p99 de 1 600 ms es el refresco de la caché del panel cada 5 s: una
petición de cada tantas paga el sondeo completo.

**La curva: no hay saturación hasta 140 usuarios.**

| seg | usuarios | pet/s | p50 | p95 |
|---|---|---|---|---|
| 15 | 7 | 1.3 | 15 ms | 1 700 ms |
| 90 | 40 | 6.1 | 16 ms | 210 ms |
| 196 | 90 | 14.5 | 15 ms | 30 ms |
| 301 | 140 | 22.9 | 15 ms | 64 ms |
| 376 | 140 | 23.7 | 13 ms | 28 ms |
| **391** | **10** | 7.7 | **12 ms** | 150 ms |
| 481 | 10 | 1.4 | 15 ms | 33 ms |

**La mediana se queda plana en 13–16 ms de 7 a 140 usuarios** y las
peticiones por segundo escalan linealmente de 1.3 a 23.7. Escalado lineal
con latencia constante significa que no hay contención.

**Recuperación: inmediata.** En el segundo 380 la carga cae de 140 usuarios
a 10 de golpe. La mediana no se mueve (13 → 12 ms) y no hay cola
arrastrada. Un sistema que aguanta un pico y se recupera es distinto de uno
que aguanta el pico y tarda veinte minutos en volver, aunque los dos den el
mismo p95 en el pico.

### 4.3 Corrida de esfuerzo: dónde está el techo

«No saturó» sin haber encontrado el techo no dice dónde está el techo. Con
`NEXUM_PRISA=25` las esperas se dividen entre veinticinco y los mismos
usuarios generan veinticinco veces más peticiones. No pretende ser realista
—ningún colaborador abre la aplicación cada 100 ms— sino encontrar el
límite.

| | |
|---|---|
| Peticiones | 23 644 |
| Peticiones/segundo | **131 de media, 197 en el pico** |
| Mediana | 23 ms |
| **p95** | **400 ms** |
| p99 | 680 ms |
| Máximo | 1 778 ms |
| Fallidas | 3 917 (16.57%) |
| **De las cuales 5xx** | **cero** |

**Las 3 917 fallas fueron todas 429.** Bajo seis veces la carga realista el
sistema no produjo un solo error de servidor: rechazó educadamente.

**La curva, y el codo:**

| pet/s | p50 | p95 | 429/s |
|---|---|---|---|
| 8 | 14 ms | 31 ms | 0 |
| 51 | 14 ms | 36 ms | 2.3 |
| 96 | 13 ms | 47 ms | 18.4 |
| 116 | 14 ms | 53 ms | 28.9 |
| **137** | **16 ms** | **110 ms** | 31.1 |
| 159 | 28 ms | 190 ms | 28.2 |
| 183 | 36 ms | 290 ms | 39.2 |
| 182 | 41 ms | 530 ms | 28.1 |
| 197 | 35 ms | 450 ms | 22.3 |

- **Codo de saturación: ~130 peticiones/segundo.** Por debajo, la mediana
  está plana en 13–16 ms y el p95 bajo 60 ms. Por encima, la mediana sube
  (16 → 41 ms) y el p95 sube más rápido (110 → 530 ms).
- **Techo de throughput: ~190–197 peticiones/segundo** en esta máquina con
  17 servicios.
- **El límite que se alcanza primero es administrativo, no físico.** Los
  429 empiezan a los 51 pet/s y crecen: es `limite_consumo(maximo=120,
  ventana=60)`, 120 peticiones por minuto y por token, es decir 2 por
  segundo por usuario. La infraestructura aguantaba más.

### 4.4 Endpoints más lentos

De la corrida de esfuerzo, por p95:

| Endpoint | p95 | peticiones |
|---|---|---|
| `GET /monitoreo/componentes` | 1 400 ms | 1 496 |
| `GET /monitoreo/errores` | 1 200 ms | 529 |
| `GET /tendencias/descensos` | 690 ms | 359 |
| `GET /algoritmos/analisis [sin cache]` | 620 ms | 187 |
| `GET /consentimiento/mio` | 450 ms | 9 629 |
| `GET /tendencias/unidad/{id}` | 270 ms | 591 |
| `GET /consultas/participacion` | 79 ms | 380 |
| `GET /algoritmos/analisis [cache]` | 79 ms | 579 |

Los dos primeros son el panel de monitoreo, y en esta corrida de esfuerzo
una parte de las peticiones iba con `?sin_cache=1` a propósito. En la
corrida realista, con la caché de 5 s, `/componentes` queda en 2.8 ms de
acierto.

---

## 5. Honestidad sobre el ambiente de medición

**MongoDB no está disponible en este contenedor** y no se puede instalar
desde él. Consecuencias, dichas sin maquillar:

- 7 de los 24 servicios quedan `no_listo`: documents, notifications,
  reports, main-process, survey, indicators y support. Sus endpoints **no
  se midieron**, y la prueba de carga los salta e imprime cuáles.
- `algorithms-service` queda `degradado` y **sí se mide**: atiende
  perfectamente sin MongoDB, que es el caso interesante y para lo que
  existen los tres estados de la sonda.
- `/monitoreo/componentes` tarda 1.4 s en un sondeo nuevo porque espera a
  esos 7. Con MongoDB arriba sería ~50 ms, que es la peor latencia medida
  entre los componentes que sí atienden.

Las mediciones se hicieron en **un solo contenedor** con los 17 servicios,
PostgreSQL y Redis compartiendo CPU. Los números de throughput son por
tanto un **piso**: en GCP, con los servicios en contenedores separados, el
techo es más alto. Lo que no cambia con el despliegue son los hallazgos de
consultas y de índices, porque son del plan de ejecución.

---

## 6. Resumen de las mejoras medidas

| Qué | Antes | Después | Factor |
|---|---|---|---|
| `fn_calcular_agregado_protegido` (camino más caliente) | 89 ms | 21 ms | **4.2x** |
| `v_estado_presupuesto` (`/consultas/presupuesto`) | 458 ms | 4.6 ms | **100x** |
| Vista de consentimiento (consulta del tamaño de grupo) | 30.5 ms | 11.3 ms | 2.7x |
| Análisis complejo con caché | 115 ms | 9.3 ms | **12.4x** |
| Panel de monitoreo con caché | 1 635 ms | 2.8 ms | **580x** |
| Sonda de listo con dependencia opcional caída | 1 286 ms | 53 ms | **24x** |
| p95 de la corrida realista | 1 500 ms | 40 ms | **37x** |
| Errores de la corrida realista | 42.0% | 0.02% | — |
| Consultas a MongoDB sin índice | 6 de 44 | **0 de 44** | — |

De las nueve líneas, **tres salieron de la prueba de carga y no de leer
código**: la subconsulta correlacionada, la inanición de obreros del panel
y la lentitud de la sonda. Las tres eran invisibles con los datos de
demostración y en reposo, y las tres habrían aparecido en producción.

Y las seis de MongoDB salieron de leer el código **porque no se podía
medir**: sin MongoDB en el ambiente no hay `explain()`, así que se
analizaron las 44 consultas contra los índices declarados. Cuatro de las
seis eran ordenamientos sin índice, que es el caso que no se degrada sino
que falla.
