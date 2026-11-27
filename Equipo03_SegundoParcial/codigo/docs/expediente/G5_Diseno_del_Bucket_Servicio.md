# Diseño del bucket — el servicio que guarda y firma

**Expediente NEXUM — Equipo 03 · Capítulo de Gerardo Quiroga Ramírez
(#650313)**

> La otra mitad de este capítulo —la máquina, la cuenta de servicio, el
> montaje y los permisos de GCP— es de Juan Pablo. Aquí va el lado del
> servicio: qué valida, dónde guarda, cómo firma y qué pasa cuando el
> bucket no está.

Código: `apps/microservicios/documents-service/archivos.py` y `app.py`.
Bucket: `nexum-610248-evidencias`.

---

## 1. Por qué esta lógica vive en el servicio y no en el portal

Esta validación existía y funcionaba, pero vivía en el portal web
(`apps/web/app/rutas/evidencias.py`). El efecto era que
`documents-service` —el servicio cuya responsabilidad declarada es «carga,
almacenamiento, consulta y administración segura de documentos; validación
de formatos y tamaños»— **sólo guardaba metadatos**, y la parte difícil la
hacía otro componente.

Dos consecuencias concretas, no estéticas:

1. **Sólo el portal podía subir evidencia.** La aplicación de escritorio y
   la móvil hablan con los microservicios, no con el portal. Para ellas la
   carga de evidencia sencillamente no existía.
2. **La validación no era una propiedad del sistema, sino de una
   pantalla.** Cualquier cliente que llamara `POST /api/v1/documentos`
   directamente registraba un documento **sin pasar por la comprobación de
   firma ni por el límite de tamaño**.

Ahora la validación está en el servicio y el portal es un cliente más.

---

## 2. Qué se valida, y por qué así

### El tamaño, antes de leer el archivo

`EVIDENCIA_TAMANO_MAXIMO` = 8 MB. Un acta, una minuta o la foto de una
sesión caben de sobra; un video no, y no es lo que una evidencia de
intervención debe ser.

Se revisa **antes** de leer el archivo completo en memoria. Al revés, un
archivo de 2 GB se cargaría entero para después rechazarlo, y bastarían
unas pocas peticiones así para tumbar el servicio.

### El tipo, por el contenido y no por la extensión

| Formato | Firma real |
|---|---|
| pdf | `%PDF-` |
| png | `\x89PNG\r\n\x1a\n` |
| jpg | `\xff\xd8\xff` |
| docx / xlsx | `PK\x03\x04` (son ZIP) |
| txt / csv | sin firma: se valida que sea decodificable |

**Un ejecutable renombrado a `.pdf` pasa cualquier validación de
extensión; no pasa la de firma.**

### El nombre que manda el cliente NO se usa como ruta

Un nombre como `../../etc/passwd` escribiría fuera de la carpeta. El
archivo se guarda bajo el **SHA-256 de su contenido** y el nombre original
queda sólo como metadato que se muestra.

---

## 3. El hash es la identidad

```
ruta_relativa(sha256) = sha256[:2] / sha256[2:4] / sha256
```

Dos niveles de subcarpeta porque un directorio plano con decenas de miles
de archivos se vuelve lento de listar en casi cualquier sistema de
archivos.

Tres propiedades que salen de usar el hash como nombre:

1. **Subir dos veces el mismo archivo no lo duplica**: se reconoce y se
   reutiliza.
2. **Se puede comprobar después** que lo que alguien descargó es lo que se
   subió. Al leer, se recalcula el hash y si no coincide **no se entrega**:
   una evidencia que cambió después de registrarse ya no respalda nada.
3. **La escritura es atómica**: a un archivo temporal y después un
   `rename`. Escribir directo sobre la ruta final dejaría, si el proceso
   muere a la mitad, un archivo con el nombre correcto y el contenido
   truncado — exactamente el caso que el hash ya no podría detectar,
   porque nadie lo volvería a calcular.

### Un defecto: la ruta se calculaba dos veces

La ruta del blob estaba escrita **dos veces**: una en `ruta_de`, para el
disco, y otra dentro de `url_firmada`, para armar el nombre del objeto en
Cloud Storage. Las dos coincidían, y coincidían **por casualidad**: nada
lo comprobaba.

Lo que eso costaba el día que alguien cambiara una: en developer todo
seguiría funcionando, porque la descarga va por el servicio y usa
`ruta_de`. En la máquina de Google, donde el almacén es el punto de
montaje del bucket, **las direcciones firmadas apuntarían a objetos que no
existen y las descargas darían 404 sin que nada en el código pareciera
roto.** Un fallo que sólo aparece en el ambiente donde no se puede
depurar.

Ahora `ruta_relativa` es la **única** función que decide dónde vive un
archivo, y existe para serlo.

---

## 4. Las URLs firmadas

En developer el archivo se descarga por el propio servicio. En la máquina
de Google, `GCS_BUCKET` y la llave de la cuenta de servicio permiten
entregar el archivo **sin abrirlo al mundo**: la dirección deja de servir
cuando vence (10 minutos por omisión).

```python
blob.generate_signed_url(version="v4",
                         expiration=timedelta(minutes=minutos),
                         method="GET")
```

### Se comprueba que el objeto exista antes de firmar

Firmar es una operación **local**: la biblioteca arma la dirección con la
llave y no le pregunta nada a Google. Así que una dirección firmada para
un objeto que no está se entrega igual, con cara de válida, y el cliente
se encuentra un **404 de Cloud Storage — un XML, no el error del
sistema**— sin ninguna pista de por qué.

Cuesta una llamada y convierte ese 404 silencioso en un error del sistema
que dice qué pasó:

```
HTTP 409  ARCHIVO_NO_ESTA_EN_EL_BUCKET
"El documento esta registrado pero su archivo no esta en Cloud Storage.
 No se entrega una direccion firmada que daria un 404 de Google sin
 explicacion."
```

### La llave no se comparte

`signer.json` no está en el repositorio ni en la entrega. Vive en la
laptop y en `/opt/nexum/signer.json` de la máquina virtual. Lo que sí se
versiona son las plantillas `.ejemplo`.

---

## 5. El bucket en la sonda de salud

Las sondas comprobaban PostgreSQL, MongoDB y Redis. Faltaba el almacén, y
faltaba justo en el servicio que lo tiene.

**Lo que eso permitía:** con el almacén caído, la sonda contesta «listo» y
200 —PostgreSQL responde, MongoDB responde, Redis responde—. El servicio
acepta una carga, valida el archivo, calcula su hash, escribe los
metadatos en MongoDB… y falla al escribir el blob, **con el registro ya
creado**.

Queda un documento registrado cuyo archivo no existe: el registro dice que
la evidencia está, la descarga da 404, y la bitácora muestra una carga
exitosa. Es el peor de los dos fallos posibles.

### Por qué es opcional y no esencial

Sacar el servicio de rotación con un 503 sería **peor**. Con el almacén
caído el servicio todavía sirve toda la consulta de metadatos: listar
documentos de una campaña, buscar por hash, ver quién subió qué y cuándo.
Eso es la mayoría del tráfico. Un 503 apagaría esas pantallas por una
falla que sólo afecta a la carga y la descarga.

Así que: `degradado`, 200 y `degradado_por: ["almacen"]`. Quien opera lo
ve; quien consulta metadatos sigue trabajando; quien intenta subir recibe
el error del almacén, que es la verdad.

### Qué se comprueba, y por qué `isdir` no basta

En producción el almacén es el **punto de montaje del bucket**, y un
montaje muerto deja el directorio *visible* mientras cualquier operación
real sobre él devuelve EIO. `statvfs` es una llamada al sistema de
archivos de verdad: con el montaje caído lanza.

Y se comprueba que se pueda **escribir**, no sólo leer. Un bucket montado
de sólo lectura —porque la cuenta de servicio perdió el permiso, que es la
falla de permisos más común en GCS— pasa cualquier comprobación de lectura
y falla en cada carga.

Si hay `GCS_BUCKET` configurado, se pregunta además a Cloud Storage, **a
lo más una vez cada 30 s**: la sonda la contestan el orquestador y el
panel varias veces por minuto, y sin ese techo la comprobación de salud
costaría más que el trabajo.

---

## 6. El proceso completo, de punta a punta

El proceso 3 del expediente —*reporte con evidencia en el bucket*— pasa
por aquí:

1. El especialista genera un reporte desde el portal.
2. `reports-service` lo produce y lo registra en MongoDB.
3. El especialista adjunta la evidencia; `documents-service` **valida
   firma y tamaño**, calcula el hash, guarda el blob y registra los
   metadatos.
4. Se escribe la acción en `auditoria.bitacora`.
5. Se emite una notificación **sin cifras ni personas**.
6. El auditor abre el documento: `documents-service` comprueba que el
   objeto exista, firma la dirección y la entrega.
7. El auditor descarga el archivo **sin contraseña** y la dirección vence
   a los 10 minutos.

Verificado capa por capa en `pruebas/test_procesos_integrales.py` y
`pruebas/test_procesos_desde_el_cliente.py`.

Y una cosa que **no** se arregló al escribir estas pruebas: el
administrador recibe 403 al tocar evidencia de intervención. Darle el
permiso para que la prueba pasara habría roto la separación de funciones;
se corrigió el actor del proceso, no el permiso.
