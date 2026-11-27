# Registro de incidencias

**Expediente NEXUM — Equipo 03**

Abierto por Gerardo Quiroga Ramírez (#650313) con las tres primeras. Los
demás integrantes agregan las suyas al final, con el mismo formato.

**Cómo se llena.** Una incidencia es algo que *pasó* y costó tiempo, no
una tarea pendiente. Cada una lleva qué se vio, qué lo causaba, qué se
hizo, y —la columna que de verdad sirve— **cómo evitar que vuelva**. Una
incidencia sin esa última línea se repite.

---

## INC-001 · Base vieja en la laptop sin permisos

| | |
|---|---|
| **Abierta por** | Gerardo Quiroga (#650313) |
| **Fecha** | noviembre 2026 |
| **Severidad** | Media |
| **Estado** | Cerrada |

**Qué se vio.** El portal levantaba, la sonda de salud contestaba, y al
entrar a cualquier pantalla con datos salía un error de permiso denegado
sobre una tabla.

**Qué lo causaba.** La base de la laptop venía de un parcial anterior.
Tenía las tablas de entonces, pero no los `GRANT` que las migraciones
nuevas otorgan al rol `bienestar_app`. Como el esquema existía, las
migraciones nuevas no reconstruían nada.

**Por qué costó encontrarlo.** La sonda de salud decía «listo». Hace un
`SELECT 1`, que es exactamente la consulta que el rol sí podía ejecutar.
«Levanta bien» y «funciona» no eran lo mismo, y la sonda decía lo primero.

**Qué se hizo.** Recrear la base desde cero con
`scripts/arranque_base.sh`, que aplica esquema, **todas** las migraciones
y los permisos de menor privilegio en el orden correcto.

**Cómo evitar que vuelva.**
- `arranque_base.sh` recorre las migraciones con un **glob ordenado**, no
  con una lista a mano. La lista a mano fue la causa de un problema
  parecido: corría sólo la migración 001.
- Hay una prueba (`pruebas/test_arranque_de_la_base.py`) que verifica la
  cadena de arranque completa.
- Ante cualquier error de permisos en la laptop: **recrear, no parchear**.
  Una base a medio migrar produce fallos que no corresponden a ningún
  defecto del código.

---

## INC-002 · La llave del bucket, ilegible para el contenedor

| | |
|---|---|
| **Abierta por** | Gerardo Quiroga (#650313) |
| **Fecha** | noviembre 2026 |
| **Severidad** | Alta |
| **Estado** | Cerrada |

**Qué se vio.** `documents-service` arrancaba y contestaba. Al pedir la
dirección firmada de un documento, fallaba. En developer no pasaba.

**Qué lo causaba.** `signer.json` estaba en la máquina, pero el usuario
del contenedor no podía leerlo: dueño y permisos del archivo montado.

**Por qué era peligroso, más allá del error.** La firma de una URL es una
operación **local** — la biblioteca arma la dirección con la llave y no le
pregunta nada a Google. Un fallo al leer la llave podía degradar en
silencio: devolver `None` y caer a la descarga por el servicio, que
funciona… y deja de usar el bucket sin que nadie se entere. El sistema
«funcionaba» mientras la entrega por bucket estaba rota.

**Qué se hizo.**
- Corregir dueño y permisos de `/opt/nexum/signer.json`.
- Que el servicio **compruebe que el objeto exista antes de firmar**. Una
  dirección firmada para un objeto que no está se entrega igual, con cara
  de válida, y el cliente recibe un 404 de Cloud Storage —un XML, no el
  error del sistema— sin pista de por qué. Ahora da
  `ARCHIVO_NO_ESTA_EN_EL_BUCKET` (409) con explicación.
- Que la sonda de salud **comprobara el bucket**, como dependencia
  opcional. Antes no lo hacía: con el almacén caído el servicio decía
  «listo», aceptaba una carga, escribía los metadatos en MongoDB y fallaba
  al escribir el blob, dejando **un documento registrado cuyo archivo no
  existe**.

**Cómo evitar que vuelva.**
- La sonda reporta el estado del bucket y el panel lo muestra.
- `signer.json` **no se versiona**. Sólo plantillas `.ejemplo`.
- Comprobar antes de cualquier demostración: subir una evidencia y abrir
  su URL firmada.

---

## INC-003 · La variante `release` del celular apuntando a dominios que no existen

| | |
|---|---|
| **Abierta por** | Gerardo Quiroga (#650313) |
| **Fecha** | noviembre 2026 |
| **Severidad** | Media |
| **Estado** | Cerrada — queda como advertencia permanente |

**Qué se vio.** La aplicación en el emulador no pasaba del login: error de
red. El backend estaba arriba y el portal funcionaba.

**Qué lo causaba.** Se compiló la variante **`release`**, que apunta por
`buildConfigField` a los dominios de producción. Esos dominios no resuelven
desde el emulador.

**Por qué confunde.** El síntoma —«no conecta»— es idéntico al de un
backend caído, y lleva a revisar el servidor, que está bien. Nada en la
pantalla dice qué variante se compiló.

**Qué se hizo.** Compilar con la variante **`debug`**, que apunta a la
laptop.

**Cómo evitar que vuelva.**
- **Para cualquier demostración en emulador: variante `debug`.** Está en
  el manual técnico y en el guion de la demostración.
- Que las dos variantes existan es correcto y no se va a cambiar: es lo
  que permite que la misma aplicación apunte a la nube sin tocar código.
  Lo que hay que recordar es cuál se está compilando.
- Antes de grabar el video: confirmar en Android Studio que el selector
  de variante diga `debug`.

---

## Formato para las que faltan

```
## INC-00X · Título corto de lo que pasó

| | |
|---|---|
| **Abierta por** | Nombre (#matrícula) |
| **Fecha** | |
| **Severidad** | Alta / Media / Baja |
| **Estado** | Abierta / Cerrada |

**Qué se vio.**
**Qué lo causaba.**
**Qué se hizo.**
**Cómo evitar que vuelva.**
```

Pendientes de abrir por los demás: el ensayo de fallos en la máquina
virtual (Ricardo y Juan Pablo), el montaje del bucket tras reinicio (Juan
Pablo) y lo que salga de las pruebas en la nube.
