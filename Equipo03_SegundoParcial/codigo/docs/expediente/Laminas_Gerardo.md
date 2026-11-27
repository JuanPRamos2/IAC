# Láminas — Gerardo Quiroga Ramírez (#650313)

**Tramo pedido:** web, móvil, escritorio, usuarios y perfiles. **Cuatro
láminas**, una por tema.

Al final hay una quinta **opcional** sobre las seis situaciones de fallo:
no estaba en la lista de láminas, pero el monitoreo es de este tramo y el
ensayo de fallos la va a necesitar. Usarla o no según el tiempo.

Formato: lo que va **en** la lámina es poco y grande; lo que va abajo es
lo que se dice de viva voz. Una lámina llena de texto se lee y no se
escucha.

---

## Lámina 1 — Web

### En la lámina

**EL PORTAL NO ES UNO DE LOS 24**

Con los 24 microservicios apagados, el portal
**abre, deja entrar y explica qué no está disponible**

**Panel de servicios:**
estado · última verificación · tiempo · errores · historial · degradados ·
dependencias caídas

### Lo que se dice

«La arquitectura obligatoria exige que el sistema web opere de manera
independiente del módulo de microservicios. El panel de servicios es la
pantalla que lo demuestra: sondea a los 24 y sigue funcionando cuando
ninguno contesta.

Hay cuatro estados, no dos, porque se arreglan en lugares distintos.
*Caído* no contesta: se reinicia. *No listo* contesta 503 y dice qué le
falta —una dependencia esencial—: se revisa esa dependencia, no el
servicio. *Degradado* contesta 200 a propósito, porque atiende con una
dependencia opcional caída.

Aquí encontramos un defecto que vale la pena contar: el panel leía el
estado del **código HTTP** en lugar del cuerpo. Con eso mostraba lo
contrario de lo que pasaba — un servicio degradado, que devuelve 200,
salía como "Disponible"; uno no_listo, que devuelve 503, salía como
"Degradado". **Toda la distinción que el microservicio se toma el trabajo
de calcular se perdía en la última línea, justo donde alguien la iba a
leer.**»

> **Demostración en vivo:** abrir `/admin/servicios`, apagar un servicio,
> recargar, volver a levantarlo.

---

## Lámina 2 — Móvil

### En la lámina

**ANDROID · KOTLIN · JSON**

`ana.perez@nexum.com.mx`

**Variante `debug`** ← no `release`

El endpoint que más llama: `/notificaciones/mias`

### Lo que se dice

«La aplicación móvil consume **JSON** y habla directo con los
microservicios, no con el portal. Por eso la validación de evidencias tuvo
que mudarse del portal al servicio: mientras vivía en una pantalla, para
la app móvil la carga de evidencia sencillamente no existía.

Dos cosas que encontramos desde el lado móvil:

El endpoint que más llama es `/notificaciones/mias`, y **no tenía índice
que sirviera para ordenar**. El índice es `(destinatario, leída,
fecha_creación)` y sin fijar `leída` no sirve para el orden. Y eso no es
"va lento": un ordenamiento sin índice en MongoDB se hace en memoria, tiene
un límite de 32 MB y **falla** al pasarlo. Deja de funcionar justo cuando
la bandeja creció.

Y la variante. La `release` apunta a los dominios de producción, que desde
el emulador no resuelven. El síntoma —"no conecta"— es idéntico al de un
backend caído y lleva a revisar el servidor, que está bien. Está en el
registro de incidencias como INC-003.»

> **Demostración:** emulador con `ana.perez` recorriendo la encuesta,
> **variante `debug`**.

---

## Lámina 3 — Escritorio

### En la lámina

**PYTHON · TKINTER · XML**

`mariana.solis@nexum.com.mx`

**Cada respuesta se valida contra su XSD antes de usarse**

16 esquemas · un solo espacio de nombres

### Lo que se dice

«Que el escritorio hable XML y el móvil JSON no es capricho del enunciado:
es lo que obliga a que el contrato mande sobre la implementación. Si los
dos hablaran JSON, el servicio podría devolver lo que le saliera y el
cliente adaptarse.

Y encontró un defecto: los servicios leían el cuerpo con `get_json()`. El
efecto era que una aplicación que mandara XML recibía un 422 por "campos
obligatorios" **aunque los hubiera mandado todos**. Como el escritorio
consume XML exclusivamente, **no podía hacer ninguna operación de
escritura**.

Lo que más distingue a este cliente: **valida cada respuesta contra su
esquema antes de usarla**. Si no cumple, no la muestra. La alternativa
—confiar y leer los campos que uno espera— falla de la peor manera: un
campo que cambió de nombre produce un `None` silencioso que se pinta como
un dato vacío en la pantalla. El usuario ve una tabla con huecos y no hay
nada en ningún log.

Y al cerrar sesión **borra las credenciales locales aunque la red esté
caída**. Si dependiera de que el servicio conteste, alguien sin red se
quedaría con el token guardado en su máquina creyendo que salió.»

> **Demostración:** el escritorio con Mariana adentro, en una pantalla
> donde se vea el XML.

---

## Lámina 4 — Usuarios y perfiles

### En la lámina

**CINCO PERFILES, Y LO QUE CADA UNO *NO* PUEDE HACER**

| Perfil | No puede |
|---|---|
| Colaborador | ver resultados de su unidad |
| Líder | ver detalle individual |
| Especialista | **aprobar su propio plan** |
| Auditor | cambiar nada |
| Administrador | ver datos de bienestar |

**Los permisos NO viajan en el token**

### Lo que se dice

«La columna que importa es la de la derecha. Un perfil se define por lo
que **no** puede hacer tanto como por lo que puede.

El colaborador no ve el agregado de su propia unidad: si un equipo tiene 6
personas, ver el promedio del equipo le diría casi exactamente qué
contestaron sus 5 compañeros.

El administrador no ve datos de bienestar — tres 403 que dejamos tal cual:
no genera reportes, no toca evidencia y no aprueba intervenciones. Al
escribir las pruebas, la salida fácil era darle los permisos para que
pasaran. **Eso habría roto la separación de funciones para arreglar una
prueba.** Corregimos el actor del proceso, no el permiso.

Y el especialista no aprueba su propio plan. Eso **no estaba**: el código
prometía "quien detecta la necesidad no es quien autoriza el cambio" y la
configuración de roles daba proponer y aprobar al mismo perfil. Lo
corregimos en la migración 019, con el autor guardado en la misma
transacción que el plan — no en la bitácora, porque un control de acceso
no puede depender de una escritura envuelta en try/except. Y como el
sistema traía un solo especialista, el control habría bloqueado todas las
aprobaciones: la migración crea una segunda cuenta.

Los permisos se consultan al servicio, no viajan en el JWT. Si viajaran,
revocar un permiso no tendría efecto hasta que el token expirara.»

---

## Lámina 5 (opcional) — Las seis situaciones de fallo

> No estaba en la lista de láminas pedidas. Se incluye porque el monitoreo
> es de este tramo y el ensayo de fallos la va a necesitar. El desarrollo
> completo está en `Guion_del_Ensayo_de_Fallos.md`.

### En la lámina

**QUÉ CONTESTA EL SISTEMA CUANDO ALGO SE CAE**

| Falla | Respuesta |
|---|---|
| Microservicio detenido | la pantalla lo dice, no se queda cargando |
| Redis | sigue atendiendo; el historial sale **nulo y dicho**, no en cero |
| MongoDB | **503**, no 500: el servicio funciona, su dependencia no |
| PostgreSQL | **503 `BASE_NO_DISPONIBLE`**; falla **una** petición y se recupera |
| **Bucket** | `degradado` con 200: sigue sirviendo metadatos |
| **Tiempo máximo** | **503 `TIEMPO_EXCEDIDO`** con mensaje y correlación |

### Lo que se dice

«Las dos últimas son las que faltaban.

El bucket no se comprobaba, y faltaba justo en el servicio que lo tiene.
Con el almacén caído la sonda decía "listo": el servicio aceptaba una
carga, calculaba el hash, escribía los metadatos en MongoDB… y fallaba al
escribir el blob, **con el registro ya creado**. Quedaba un documento
registrado cuyo archivo no existe — el registro dice que la evidencia
está, la descarga da 404, y la bitácora muestra una carga exitosa.

Y el tiempo máximo: antes el único tope era el de gunicorn, que **mata al
obrero**. El cliente recibe una conexión cortada sin código ni
identificador, la consulta **sigue viva** en PostgreSQL, y se cae además
lo que ese obrero tenía en vuelo.»

> **Demostración en vivo:** apagar Redis y recargar el panel — sigue
> funcionando y el historial sale nulo, dicho, no en cero.
