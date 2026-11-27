# Guion de capturas y grabaciones

**Equipo 03 · Lo que falta de Emiliano y Gerardo, en orden de ejecución**

Esto existe para que las capturas no se hagan improvisando. Cada punto
dice **con qué cuenta**, **qué pantalla** y **qué tiene que verse** — eso
último es lo que importa, porque una captura donde no se ve el dato clave
hay que repetirla.

---

## Antes de empezar

| | |
|---|---|
| Máquina virtual | encendida, los 24 servicios arriba |
| Laptop | Docker Desktop encendido |
| Emulador | Android Studio abierto, **variante `debug`** |
| Escritorio | `python apps/escritorio/app.py` |

**Dos advertencias que ya costaron tiempo:**

- **No uses `carlos.ramirez` para la prueba de cinco intentos fallidos.**
  Se bloquea 15 minutos y es la cuenta que abre el panel.
- **El emulador va en `debug`.** La variante `release` apunta a dominios
  de producción que no resuelven desde el emulador, y el síntoma es
  idéntico al de un backend caído. INC-003 del registro de incidencias.

---

## EMILIANO — 3 capturas

Todas salen de una sola corrida:

```bash
bash scripts/corrida_en_la_nube.sh
```

El guion deja todo en `informes/nube/` y al final escribe qué capturar.

### E-1 · Salida del generador

| | |
|---|---|
| Archivo | `informes/nube/generador.txt` |
| **Tiene que verse** | el bloque `RESUMEN` (respuestas, valores, agregados, escala de ruido) **y** el bloque `CONSUMO DE RECURSOS` (memoria pico, CPU, filas/s por fase) |

El requisito pide «empleados, respuestas, tiempo». El consumo de recursos
también es requisito y está en el mismo bloque, así que conviene una sola
captura con los dos.

### E-2 · Tabla de Locust

| | |
|---|---|
| Archivo | `informes/nube/microservicios.html` y `informes/nube/portal.html` |
| **Tiene que verse** | peticiones/segundo, mediana, **p95**, **p99** y el conteo de fallas |

Dos capturas, una por archivo. Son mediciones distintas y conviene
decirlo al presentarlas: una mide los microservicios con recursos de la
nube, la otra el camino real de una persona por HTTPS.

### E-3 · El análisis en el portal, DESPUÉS de la carga

| | |
|---|---|
| Entrar como | `mariana.solis@nexum.com.mx` / `demo123` |
| Pantalla | *Análisis* |
| **Tiene que verse** | la lista de unidades priorizadas con sus niveles (PRIORITARIO / ATENCIÓN / INFORMATIVO) |

**Éste es el punto del requisito**: el algoritmo corriendo sobre los datos
masivos recién generados. Con los datos de demostración —unidades de 8
personas— el umbral de detección es de 2.118 puntos sobre una escala de 1
a 5 y **no se detecta nada**. La captura demuestra que con volumen sí hay
hallazgos.

---

## GERARDO — 2 grabaciones + 4 capturas + el APK

### G-1 · Grabación: el emulador

| | |
|---|---|
| Entrar como | `ana.perez@nexum.com.mx` / `demo123` |
| Variante | **`debug`** |
| Recorrido | entrar → portada → encuesta → contestar algunos reactivos → enviar |
| **Tiene que verse** | que es un emulador Android y que la sesión es de `ana.perez` |

Si la encuesta no aparece: **no es un error.** Las campañas se convocan
por unidad; si la unidad de Ana no fue convocada, el portal lo explica y
redirige. Eso también sirve de grabación — es manejo de un caso legítimo,
no una falla.

### G-2 · Grabación: el escritorio en XML

| | |
|---|---|
| Entrar como | `mariana.solis@nexum.com.mx` / `demo123` |
| **Tiene que verse** | una pantalla donde se note que la respuesta vino en **XML** |

La mejor para esto es el **tablero de una unidad**: trae filas con sus
supresiones, y cada respuesta se validó contra su XSD antes de mostrarse.
Si la aplicación muestra el XML crudo en algún panel de depuración, mejor
aún — es lo que distingue este cliente del móvil.

### G-3 · Grabación: el portal (no el login) y la bandeja

| | |
|---|---|
| Entrar como | `mariana.solis` o `lucia.hernandez` |
| Pantallas | una de trabajo real **y** `/notificaciones/` |
| **Tiene que verse** | que no es sólo la pantalla de entrar |

El requisito es explícito en que no sea sólo el login. Buenas opciones: el
tablero de la unidad, o *Intervenciones*.

**En la bandeja, señalar al narrar:** las notificaciones **no llevan
cifras ni nombres de personas**. Eso es deliberado — una notificación que
dijera «tu unidad bajó a 2.8» filtraría el dato por un canal que no pasa
por el control de inferencia.

### G-4 · Captura: Swagger de la URL firmada

| | |
|---|---|
| Dónde | `documents-service` → `/docs` |
| Endpoint | el de la dirección firmada |
| **Tiene que verse** | el endpoint y su respuesta, incluido el **vencimiento** |

Vale la pena capturar también el error `ARCHIVO_NO_ESTA_EN_EL_BUCKET`
(409) si está documentado ahí: es la comprobación de que el objeto exista
**antes** de firmar, que evita entregar una dirección con cara de válida
hacia un objeto que no está.

### G-5 · Captura: evidencias con el archivo cargado

| | |
|---|---|
| Entrar como | `mariana.solis@nexum.com.mx` |
| Pantalla | *Intervenciones* → *Evidencias* |
| **Tiene que verse** | el archivo ya cargado, con su nombre y su sello |

Y después: **abrir la URL firmada** y capturar que el archivo baja sin
pedir contraseña. Eso es lo que pide el requisito del bucket.

### G-6 · Captura: el panel de servicios

| | |
|---|---|
| Entrar como | `carlos.ramirez@nexum.com.mx` / `demo123` |
| Pantalla | *Administración* → *Servicios* |
| **Tiene que verse** | estado, última verificación, tiempo, **disponibilidad de 60 min con sus muestras**, versión desplegada y el **«no aplica»** de cada servicio |

Es la captura que demuestra de un golpe los siete elementos del panel que
pide el requisito.

### G-7 · El APK

```bash
cd apps/movil
gradle wrapper --gradle-version 8.7     # una sola vez: el proyecto no trae el wrapper
./gradlew assembleDebug
# queda en app/build/outputs/apk/debug/app-debug.apk
```

El proyecto trae `gradle/wrapper/gradle-wrapper.properties` pero **no**
`gradlew`, `gradlew.bat` ni `gradle-wrapper.jar`. Android Studio los
genera al abrir el proyecto; desde consola hay que correr el primer
comando una vez, con red.

---

## Orden sugerido para una sola sesión

1. **Emiliano** arranca `corrida_en_la_nube.sh` — tarda varios minutos y
   corre solo.
2. Mientras tanto, **Gerardo** hace G-1 (emulador) y G-2 (escritorio).
3. Cuando termine la corrida, **Emiliano** hace E-1, E-2 y E-3.
4. **Gerardo** cierra con G-3 a G-6, que son del portal ya con datos
   masivos cargados — se ven mucho mejor.
5. El APK (G-7) puede quedar para el final; no depende de nada.

---

## Al terminar

Las capturas y grabaciones van al expediente y al video. Y conviene
revisar, antes de dar por cerrado:

- [ ] Que en cada captura se vea **la cuenta con la que se entró**.
- [ ] Que las de Locust muestren **p95 y p99**, no sólo el promedio.
- [ ] Que la del análisis sea **después** de la carga masiva.
- [ ] Que la del panel muestre el **historial**, que es lo que faltaba.
