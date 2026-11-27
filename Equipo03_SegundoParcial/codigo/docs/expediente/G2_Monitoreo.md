# Monitoreo

**Expediente NEXUM — Equipo 03 · Capítulo de Gerardo Quiroga Ramírez
(#650313)**

Servicio: `apps/microservicios/monitoring-service`. Pantalla:
`/admin/servicios`. Pruebas: `pruebas/test_monitoreo.py` (33 casos),
`pruebas/test_sonda_de_salud.py` (21 casos).

---

## 1. Lo que cada microservicio reporta de sí mismo

Las sondas ya existían y estaban bien; lo que no existía era quien las
leyera todas. Las tres:

| Sonda | Contesta |
|---|---|
| `/health/live` | el proceso responde |
| `/health/ready` | proceso, PostgreSQL, MongoDB, Redis, bucket, tiempo y versión |
| `/docs` | el contrato en Swagger |

Un `/health/ready` completo:

```json
{
  "servicio": "documents-service",
  "estado": "degradado",
  "dependencias": {
    "postgresql": {"ok": true,  "esencial": true,  "ms": 0.4},
    "mongodb":    {"ok": true,  "esencial": true,  "ms": 1.1},
    "redis":      {"ok": true,  "esencial": true,  "ms": 0.7},
    "almacen":    {"ok": false, "esencial": false, "ms": 0.6,
                   "error": "el almacen /var/lib/bienestar/evidencias no existe",
                   "caida_desde_hace_s": 42.3}
  },
  "no_aplican": [],
  "degradado_por": ["almacen"],
  "proceso": {"instancia": "632b2422a1b4",
              "arrancado_en": "2026-11-26T23:54:34Z",
              "segundos_arriba": 1840.2},
  "version": {"api": "v1", "despliegue": "tercer-parcial-gcp",
              "ambiente": "production"},
  "tiempo_ms": 2.8,
  "verificado_en": "2026-11-27T00:25:14Z"
}
```

### Los tres estados, y por qué no son dos

```
listo      todo responde                         -> 200
degradado  falla sólo una dependencia OPCIONAL   -> 200
no_listo   falla una dependencia ESENCIAL        -> 503
```

`degradado` con **200 es deliberado**. El caso real que lo motivó:
`algorithms-service` lee los agregados de PostgreSQL y sólo usa MongoDB
para guardar el historial de corridas. Con MongoDB caído el motor evalúa
perfectamente y responde `/reglas`, `/evaluar`, `/cobertura` y
`/analisis`. Antes se declaraba `no_listo`, y un orquestador deja de
mandar tráfico a un servicio no listo: **una pieza que funcionaba se
sacaba de servicio**.

Devolver 503 ahí escondería un servicio sano; devolver 200 sin decir nada
escondería la falla. De ahí `degradado_por`.

### Por qué `proceso` trae identidad de instancia

Sin ella, **un contenedor que se reinicia en bucle pasa todas las
sondas**: cada petición llega a un proceso recién arrancado que contesta
«vivo» con toda honestidad, y el reinicio —que es el problema— no se ve en
ningún lado. `instancia` es un identificador nuevo por proceso, así que
`monitoring-service` compara el de ahora con el que vio antes y cuenta
reinicios. Se usa el identificador y no sólo la hora porque un contenedor
sin reloj sincronizado puede reportar horas que no avanzan.

### Por qué `tiempo_ms` no es la suma de sus partes

A propósito. Las dependencias opcionales corren con presupuesto en un hilo
aparte y **se abandonan a los 300 ms** aunque sigan colgadas. El total es
lo que mide el orquestador con su propia paciencia, así que es el número
que decide si saca al servicio de rotación.

### `no_aplican`

Un panel que recibe `dependencias: {postgresql, redis}` de `users-service`
no puede distinguir «este servicio no usa MongoDB» de «la comprobación de
MongoDB no se ejecutó». Las dos se ven igual —la clave no está— y las
consecuencias son opuestas: la primera es normal, la segunda es un hueco
de observabilidad.

Con `no_aplican` el silencio deja de ser ambiguo: **una dependencia que no
esté ni en `dependencias` ni en `no_aplican` es un error de declaración y
se nota.** El conjunto completo lo decide una lista en `comun`, así que
agregar una dependencia al sistema la hace aparecer de inmediato en las
sondas de los veinticuatro.

---

## 2. La sonda rápida: 1 286 ms → 53 ms

Declarar MongoDB opcional estaba bien y seguía estando roto por otro lado.
Medido: la sonda de `algorithms-service` con MongoDB abajo tardaba
**1 286 ms**, porque el cliente de MongoDB espera 1.2 s antes de rendirse
y la sonda lo esperaba en cada llamada.

El efecto **anula el sentido de haber declarado la dependencia
opcional**: un orquestador que sondea con un segundo de paciencia declara
muerto a un servicio que está atendiendo bien, y justamente por preguntar
si algo que no necesita está disponible.

Tres correcciones:

1. **Presupuesto propio** para las opcionales (300 ms). Si no contestan en
   ese plazo se dan por caídas sin esperarlas más.
2. **Recuerdo del fallo** (15 s). Un fallo *es* una espera agotada, así
   que recordarlo evita pagarla otra vez.
3. **Reintento con presupuesto corto** (50 ms) cuando hay fallo recordado.
   Sin esto había que elegir entre pagar la espera completa cada vez o no
   detectar la recuperación hasta que caducara el recuerdo — y una prueba
   lo encontró: una dependencia que volvía seguía anunciándose caída
   quince segundos. Con un fallo recordado la pregunta es más fácil: no
   «¿funciona?» sino «¿ya volvió?», y eso se contesta rápido o no se
   contesta.

Y una asimetría deliberada: **una dependencia esencial no se recuerda
nunca y no tiene presupuesto.** Su resultado decide si mandar tráfico, y
ahí vale más la respuesta correcta que la rápida.

El hilo que termina tarde apunta la causa **real** para la siguiente
sonda, así que el error que se reporta no es «no contestó en 50 ms» sino
«documentos:27017 no responde», que dice qué arreglar.

---

## 3. El panel central

`GET /api/v1/monitoreo/componentes` — pide token, porque un panel de
monitoreo suele ser lo primero que se abre sin autenticación «porque sólo
son métricas», y aquí eso sería una fuga: saber que una unidad tiene datos
publicados ya dice algo de esa unidad.

Los siete elementos que el requisito pide:

| Elemento | Dónde |
|---|---|
| Estado | `estado` por componente + `veredicto` global |
| Última verificación | `verificado_en` + `sondeo_edad_segundos` |
| Tiempo | `latencia_ms` (medido desde aquí) y `tiempo_ms` (el que el servicio dice) |
| Errores | `/monitoreo/errores`, de la bitácora |
| Historial | `historial_disponibilidad` |
| Degradados | `degradado_por` + `por_estado` |
| Dependencias caídas | `falta` + el detalle de cada dependencia |

### El veredicto global

```
sin_respuesta o no_listo  -> con_fallas
degradado                 -> degradado
desconocido               -> incierto
todo listo                -> operativo
```

Se calcula aquí para que no lo calcule cada pantalla a su manera. Un
`degradado` no es urgente y un `sin_respuesta` sí: juntarlos en un
semáforo de dos colores haría que se atendieran igual.

### Cuatro estados, no dos

`sin_respuesta` no es lo mismo que `no_listo`. Un 503 **con cuerpo** es un
servicio vivo que dice qué le falta; uno que no contesta está caído. Se
arreglan en lugares distintos, y mezclarlos manda a buscar el problema al
lugar equivocado. Por eso el estado se lee del **cuerpo** y no del código
HTTP: la sonda devuelve 200 tanto para `listo` como para `degradado`.

### El sondeo: paralelo y con caché

En serie, veinticuatro sondas de 2.5 s son un minuto, y con las esperas en
serie el peor caso depende de **cuántos** componentes estén caídos — justo
cuando hay que abrir el panel rápido. Va en paralelo.

Y con **caché de 5 s en Redis**, por dos motivos medidos:

```
GET /monitoreo/errores  solo .....................     5 ms
GET /monitoreo/errores  con 4 /componentes en vuelo  2 549 ms
```

Quinientas veces peor. El sondeo tarda 1.4 s y **ocupa un obrero de
gunicorn** mientras espera, y el servicio corre con `--workers 2`: el
endpoint lento mataba a los rápidos del mismo proceso. Un panel de
monitoreo que se vuelve inservible bajo carga falla exactamente cuando
hace falta.

El segundo motivo: sin caché, cada apertura del panel sondea a los 24. Con
varios administradores mirando, eso son cientos de sondas por minuto
contra el sistema vigilado — **el monitoreo se convierte en carga**.

La caché va en Redis y no en memoria del proceso porque los obreros son
procesos distintos: en memoria, cada uno tendría la suya. Y la respuesta
dice **siempre** la edad del dato: un tablero que muestra información
vieja sin decirlo es peor que uno lento, porque quien opera decide
creyendo que ve el ahora. Con `?sin_cache=1` se fuerza un sondeo nuevo.

---

## 4. El historial de disponibilidad

El panel contestaba «¿cómo está el sistema?». No contestaba «¿cómo ha
estado?», y son preguntas distintas:

1. **Un servicio que se cae y se levanta no dejaba rastro.** Con sondeos
   cada cinco segundos, una caída de cuarenta segundos es invisible salvo
   que alguien esté mirando en ese momento. Un componente que lo hace
   veinte veces al día está caído para uno de cada veinte usuarios, al
   azar, y nadie lo puede reproducir.
2. **«Está listo» no decía si acaba de recuperarse.** Un verde después de
   un incidente se leía igual que un verde que nunca falló.

Ventana de 60 minutos en cubetas de un minuto. Cuatro decisiones hacen que
el número signifique algo:

| Decisión | Por qué |
|---|---|
| `degradado` cuenta como **disponible** | Devuelve 200 a propósito: el servicio atiende. Contarlo como caída daría un número que no describe lo que vivió ningún usuario. Se cuenta aparte, porque degradado mucho tiempo también es un problema |
| `desconocido` **no cuenta** ni a favor ni en contra | Significa que no supimos interpretar la respuesta, o sea que el fallo puede ser nuestro. Meterlo en el numerador o el denominador sería culpar al componente de un fallo del monitoreo |
| Se reportan las **muestras** junto al porcentaje | Un 100 % sobre tres muestras no es un 100 % sobre setecientas, y un panel que no distingue las dos miente sin decir ninguna falsedad |
| Sólo cuentan los **sondeos reales**, no las lecturas de caché | Si cada apertura del panel sumara una muestra, diez administradores mirando multiplicarían por diez el denominador sin sondear una vez más |

Un minuto con alguna muestra no disponible se marca como **minuto con
falla**, sin promediar: promediarlo esconde una caída de diez segundos
dentro de un minuto que sale al 83 %.

Se cuenta con `HINCRBY`, que es atómico: leer-sumar-escribir pierde
muestras con dos obreros sondeando a la vez, sin que nada falle. Y es **de
mejor esfuerzo**: este servicio es el que avisa de que Redis se cayó, así
que con Redis abajo el panel sigue funcionando y el historial sale **nulo
y dicho**, no en cero — un cero se lee como «estuvo caído todo el rato» y
manda a buscar un incidente que no existe.

---

## 5. Los errores salen de la bitácora

`/monitoreo/errores` agrupa por acción y resultado desde
`auditoria.bitacora`, no desde un contador en memoria.

El motivo: un contador se reinicia con el proceso, y entonces el panel
dice **cero errores justo después de un incidente**, que es cuando más
importa el número. La bitácora es durable y es la misma fuente que se
audita.

---

## 6. Un defecto que este capítulo encontró

El panel web leía el estado del **código HTTP** en lugar del cuerpo:

```python
estado = "DISPONIBLE" if r.status_code == 200 else "DEGRADADO"
```

Con eso la tabla mostraba **lo contrario** de lo que pasaba, porque los
dos estados interesantes no se distinguen por el código:

| Estado real | HTTP | La tabla decía |
|---|---|---|
| `degradado` (opcional caída, atiende) | 200 | **Disponible** |
| `no_listo` (esencial caída, no atiende) | 503 | **Degradado** |

Es decir: llamaba sano al que tenía una falla y medio-sano al que de
verdad no podía atender. **Toda la distinción que el microservicio se toma
el trabajo de calcular se perdía en la última línea, justo donde alguien
la iba a leer.**

Corregido: el estado se lee del cuerpo, los cuatro estados se muestran por
separado, y la pantalla trae además última verificación, historial,
versión, degradados, dependencias caídas y el conteo de errores de 24
horas.

Y una cosa que se conservó: el portal **mide el estado él mismo** y sólo
pide a `monitoring-service` el historial y los errores. Así esta pantalla
sigue sirviendo con `monitoring-service` caído — entonces el estado de
cada servicio es de ahora y las columnas de historial salen vacías **y
dichas**, con un aviso, en lugar de salir en blanco como si no hubiera
nada que reportar.
