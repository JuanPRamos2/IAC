# Reflexión individual — Gerardo Quiroga Ramírez (#650313)

> **Borrador.** El requisito dice que cada quien escribe y sube la suya,
> y tiene razón: esto es sobre lo que *tú* aprendiste. Lo que sigue es el
> material real de lo que hiciste, ordenado, para que lo reescribas en tu
> voz. Donde dice **[tuyo]** falta algo que sólo tú puedes poner.

---

## Lo que me tocó

Aplicaciones cliente e integración completa: el sistema web, la aplicación
móvil (JSON), la de escritorio (XML), los procesos de punta a punta, el
bucket de Cloud Storage, el monitoreo y el manejo de errores, permisos y
fallos de conexión.

---

## Lo que de verdad aprendí

### 1. Dónde vive una regla decide si es una regla del sistema

La validación de evidencias —formato, tamaño, firma del archivo—
funcionaba. Estaba en el portal web.

Eso tenía dos consecuencias que no se veían usando el portal:

- **Sólo el portal podía subir evidencia.** El escritorio y el móvil
  hablan con los microservicios, no con el portal. Para ellos la carga de
  evidencia sencillamente no existía.
- **La validación era propiedad de una pantalla, no del sistema.**
  Cualquier cliente que llamara `POST /api/v1/documentos` directamente
  registraba un documento sin pasar por ninguna comprobación.

Moverla al servicio no cambió ni una línea de lo que valida. Cambió
**quién no puede evitarla**, y eso resultó ser lo importante.

### 2. Un error mal clasificado manda a buscar al lugar equivocado

Es el patrón que más se repitió en mi parte, y en todas partes era lo
mismo: el sistema sabía qué pasaba y lo contaba mal.

- `documents-service` devolvía **500 con un error de Python filtrado**
  —`'int' object has no attribute 'strip'`— a un cliente que mandaba el
  tipo correcto.
- El panel leía el estado del **código HTTP** en lugar del cuerpo, y por
  eso mostraba **lo contrario** de lo que pasaba: un servicio `degradado`
  (200) salía como "Disponible" y uno `no_listo` (503) salía como
  "Degradado". Llamaba sano al que tenía la falla.
- Una conexión muerta a PostgreSQL tras un reinicio salía como **500
  "error interno"**, que dice *el código está roto*, cuando la base sólo
  se había reiniciado y el pool se recupera solo en una petición.

Las tres veces el sistema tenía la información correcta y la perdía al
presentarla. Lo que me llevo: **la última línea, la que alguien va a leer,
es parte del sistema.**

### 3. Lo que una sonda no comprueba, no existe

Las sondas de salud revisaban PostgreSQL, MongoDB y Redis. No el bucket —
y el bucket es de mi servicio.

Con el almacén caído, la sonda contestaba «listo». El servicio aceptaba
una carga, validaba el archivo, calculaba su hash, escribía los metadatos
en MongoDB… y fallaba al escribir el blob, **con el registro ya creado**.

Quedaba un documento registrado cuyo archivo no existe: el registro dice
que la evidencia está, la descarga da 404, y la bitácora muestra una carga
exitosa. **De los dos fallos posibles, es el peor** — porque no se ve.

Y aprendí que `isdir` no basta: en producción el almacén es el punto de
montaje del bucket, y un montaje muerto deja el directorio *visible*
mientras toda operación real devuelve EIO.

### 4. Un silencio ambiguo es un hueco

Esto lo encontré pensando en cómo se lee el panel desde afuera. Un panel
que recibe `dependencias: {postgresql, redis}` de un servicio no puede
distinguir «este servicio no usa MongoDB» de «la comprobación de MongoDB
no se ejecutó». Las dos se ven igual —la clave no está— y las
consecuencias son opuestas.

Agregar `no_aplican` suena a detalle cosmético. No lo es: convierte la
ausencia en una afirmación, y entonces una dependencia que falte en los
dos lados **es un error de declaración y se nota**.

### 5. Un control que depende de una escritura best-effort no es un control

El especialista podía aprobar su propio plan. El código prometía «quien
detecta la necesidad no es quien autoriza el cambio» y la configuración de
roles daba proponer y aprobar al mismo perfil.

Lo que me hizo pensar fue **dónde** guardar quién propuso. Lo natural era
leerlo de la bitácora, que ya lo registraba. Pero esa escritura va
envuelta en try/except para que un fallo de bitácora no tumbe la
operación — así que un control de acceso apoyado ahí **se desactiva
silenciosamente** el día que la bitácora falle. Va en la misma transacción
que el plan.

Y una consecuencia que no había previsto: el sistema traía **un solo
especialista**, así que el control recién puesto habría bloqueado *todas*
las aprobaciones. Un control correcto que deja el sistema inoperable no
está terminado.

**[tuyo]** — si te acuerdas de cómo llegaste a eso, vale la pena contarlo.

### 6. Una prueba que falla no siempre significa que el sistema esté mal

Escribí una prueba donde la colaboradora contestaba la campaña abierta.
Falló. El portal la redirigía con una explicación.

La prueba estaba mal y el sistema bien: las campañas se convocan por
unidad, y la unidad de esa persona no estaba convocada.

Lo mismo con tres 403 del administrador: no genera reportes, no toca
evidencia, no aprueba intervenciones. La salida fácil era darle los
permisos. **Eso habría roto la separación de funciones para que pasara una
prueba.** Corregí el actor del proceso, no el permiso.

### 7. Un `skip` puede esconder una rotura

Las pruebas de los clientes omitían el caso cuando el login fallaba por
cualquier motivo. Un cambio mío en la cadena de conexión dejó
`auth-service` contestando error interno, y **quince casos pasaron a
"omitido"**: la corrida salió **en verde, con cero fallos, y el sistema
estaba roto**.

Un `skip` sólo tiene sentido cuando el ambiente no está. Si el servicio
escucha y contesta un error, eso es justo lo que la prueba existe para
encontrar.

---

## Lo que haría distinto

**[tuyo]** — algunas ideas por si te sirven de arranque:

- Preguntar desde el principio «¿qué dependencias tiene este servicio?» y
  ponerlas todas en la sonda, en vez de agregarlas cuando algo falla.
- Revisar cómo se *presenta* cada error, no sólo que se maneje. Tres de
  mis defectos fueron de presentación, no de lógica.
- Desconfiar de una corrida en verde que tiene más omitidos de lo normal.

---

## Lo que queda pendiente de mi parte

- Emulador con `ana.perez` recorriendo la encuesta, **variante `debug`**.
- Grabar el escritorio con Mariana en una pantalla donde se vea el XML.
- Grabar una pantalla del portal que no sea el login, y la bandeja.
- Capturas: emulador, escritorio con sesión, Swagger de la URL firmada,
  evidencias con el archivo cargado.
- El APK. **Nota técnica:** el proyecto móvil no trae el wrapper de Gradle
  (`gradlew`, `gradlew.bat` ni `gradle-wrapper.jar`), sólo
  `gradle-wrapper.properties` apuntando a Gradle 8.7. Android Studio lo
  genera solo al abrir el proyecto; desde consola hay que correr
  `gradle wrapper --gradle-version 8.7` una vez, con red.

---

## Qué puedo explicar de cualquier parte del sistema

**[tuyo]** — el requisito dice que cada quien debe poder contestar tres
preguntas de cualquier capa. Vale la pena que leas antes de la entrega:

- `Guion_del_Ensayo_de_Fallos.md` — las seis situaciones y las cinco cosas
  de cada una. Buena parte es tuya.
- `E2_Reglas_de_k_Minimo_y_Ruido.md` — por qué *k* = 5 y por qué el ruido;
  es lo que explica todo el diseño de privacidad.
- `E3_Algoritmos.md` — lo de Emiliano, que es lo más probable que te
  pregunten fuera de tu tramo.
