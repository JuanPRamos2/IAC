# Reflexión individual — Emiliano Pascual Piñales Sánchez (#657657)

> **Borrador.** El requisito dice que cada quien escribe y sube la suya,
> y tiene razón: esto es sobre lo que *tú* aprendiste. Lo que sigue es el
> material real de lo que hiciste, ordenado, para que lo reescribas en tu
> voz. Donde dice **[tuyo]** falta algo que sólo tú puedes poner.

---

## Lo que me tocó

Algoritmos, bases de datos y pruebas de rendimiento. En concreto: el
algoritmo complejo de detección de riesgo psicosocial, la generación del
conjunto masivo de datos, la optimización de PostgreSQL y MongoDB, la
caché con Redis y las pruebas de carga con Locust.

---

## Lo que de verdad aprendí

### 1. Mirar la salida de un algoritmo no es evaluarlo

Es lo más importante que me llevo del parcial.

El motor de análisis producía informes que se veían razonables. Unidades
marcadas, niveles asignados, tendencias detectadas. Leyéndolos, uno asiente
y sigue adelante.

Cuando hice que el generador **inyectara señal a propósito** —elegir al
azar un 5 % de unidades, deteriorarlas, y anotar cuáles **antes** de correr
el detector— aparecieron **cuatro defectos** que la lectura casual no había
visto en ninguna de las veces anteriores:

- k-medias agrupaba las unidades deterioradas en el mismo grupo, y dentro
  de su grupo parecían normales. **El agrupamiento escondía exactamente lo
  que había que encontrar.**
- Con ruido bajo, todo pasaba la prueba de significancia: 36 dimensiones
  marcadas con desviación mediana de 0.12 puntos sobre una escala de 1 a 5.
- El nivel salía de un promedio ponderado que diluía señales fuertes y
  aisladas.
- «Empeorar» se confundía con «bajar»: en carga percibida subir es
  empeorar, así que una mejora contaba como deterioro.

Ninguno de los cuatro era un error que se viera leyendo código. Los cuatro
se vieron comparando contra una verdad que yo mismo había escrito antes.

La lección general: **si no tengo con qué comparar, no estoy midiendo.**

### 2. Un número que no se puede reproducir no es una medición

Mi banco de pruebas elegía a qué unidad medirle con `ORDER BY random()`.
Dos corridas seguidas contra la misma base, sin cambiar nada, dieron
**15.85 ms y 226.41 ms** del mismo camino. Catorce veces de diferencia.

Y lo que más me marcó: **casi puse el 15.85 ms en el documento como "el"
número.** No estaba equivocado por descuido en los datos; estaba
equivocado en el método, y el método no se ve al leer el resultado.

Lo mismo con la medición de CPU, que reportaba «0.00 ms» —que se lee como
«no consume CPU»— cuando lo que pasaba era que no llegaba a la resolución
del reloj del kernel; y con el conteo de filas, que leía estimaciones que
decían 0 y 5 para tablas con un millón y con ocho mil filas.

Tres errores, y los tres estaban en **mi instrumento**, no en el sistema
medido. Ahora entiendo por qué un informe de rendimiento tiene que decir
cómo se midió y no sólo qué salió.

### 3. La diferencia entre tener un control y que el control sirva

Puse un límite de tiempo por petición para que una petición lenta no
terminara con gunicorn matando al obrero. El límite existía, se veía bien,
y pasaba sus pruebas.

Estaba puesto **sólo en la parte barata** —armar las series, que es
recorrer un diccionario—. El trabajo caro está en el motor: la silueta es
O(u²) y Theil-Sen O(c²) por serie. O sea: **el corte no habría disparado
nunca donde de verdad se gasta el tiempo.**

Lo encontré porque fui a comprobar una afirmación que yo mismo había
escrito en el documento. Esa es la parte que quiero recordar: no lo
encontré programando, lo encontré **verificando lo que ya había dado por
bueno**.

### 4. El volumen cambia qué problemas existen

Con los datos de demostración —unidades de 8 personas— la escala del ruido
es 0.5 y el umbral de detección queda en 2.118 puntos sobre una escala de
1 a 5. Ninguna señal real se mueve dos puntos: **con esos datos, un
detector perfecto y uno roto producen la misma salida.**

Y en la base: un índice que existía y no servía, porque el `ORDER BY` de
una vista tenía una tercera clave que el índice no cubría. La consulta
devolvía lo correcto, así que nada lo delataba — ordenaba 24 476 filas en
cada llamada. Con 40 filas de demostración, invisible.

Aprendí que «funciona en mi máquina con datos de prueba» y «funciona» son
afirmaciones distintas, y que la segunda cuesta trabajo construirla.

### 5. Una prueba que grita en falso se acaba desactivando

Mi analizador de índices de MongoDB dio tres falsos positivos la primera
vez. Mi primer impulso fue bajarle la sensibilidad.

Lo que entendí al corregirlo bien: una prueba que avisa de problemas que
no existen **se desactiva**, y entonces deja de encontrar los que sí. El
costo de un falso positivo no es el minuto que se pierde revisándolo; es
que mata la confianza en la herramienta entera.

### 6. Tres corridas de carga a la basura

34.6 %, 37.9 % y 42.0 % de errores. Las tres medían el limitador de
peticiones, no el sistema: todos los usuarios virtuales salían de la misma
IP, o compartían token, o usaban cuentas sin seudónimo.

Y una cuarta donde el colaborador llamaba endpoints que exigen un permiso
que un colaborador **no debe tener**. La salida fácil era darle el permiso
para que la prueba pasara. Eso habría roto la separación de funciones del
sistema para arreglar un guion de pruebas.

**[tuyo]** — aquí puedes decir qué sentiste al tirar tres corridas, o si
te costó resistir la tentación de "arreglar" el permiso.

---

## Lo que haría distinto

**[tuyo]** — algunas ideas por si te sirven de arranque:

- Escribir la validación contra verdad inyectada **antes** del algoritmo,
  no después. Habría ahorrado tres de los cuatro defectos.
- Fijar el objetivo de las mediciones desde el principio, en vez de
  descubrir a la quinta corrida que `random()` las hacía incomparables.
- No dar nada por terminado leyendo mi propio resumen de los requisitos.
  Las dos veces que lo hice, había hueco.

---

## Lo que queda pendiente de mi parte

Correr el generador y Locust en la máquina virtual contra
`https://34.41.26.94.sslip.io`, guardar la salida y el CSV, y mostrar el
análisis en el portal después de esa carga. Las mediciones que tengo se
hicieron en un solo contenedor con todo compartiendo CPU, así que los
números de throughput son un **piso**, y eso está dicho en el documento en
lugar de presentarse como si fueran de la nube.

---

## Qué puedo explicar de cualquier parte del sistema

**[tuyo]** — el requisito dice que cada quien debe poder contestar tres
preguntas de cualquier capa, no sólo de la suya. Vale la pena que leas
antes de la entrega:

- `Guion_del_Ensayo_de_Fallos.md` — las seis situaciones y las cinco cosas
  que hay que poder explicar de cada una.
- `G1_Mapa_de_los_24_Microservicios.md` — qué hace cada servicio y de
  quién es.
- `G2_Monitoreo.md` y `G5_Diseno_del_Bucket_Servicio.md` — lo de Gerardo,
  que es lo más probable que te pregunten fuera de tu tramo.
