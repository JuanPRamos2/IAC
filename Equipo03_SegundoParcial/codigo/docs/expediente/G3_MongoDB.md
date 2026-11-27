# Diseño de MongoDB

**Expediente NEXUM — Equipo 03 · Capítulo de Gerardo Quiroga Ramírez
(#650313)**

---

## 1. Qué va en MongoDB y qué no

El reparto no es de gusto. PostgreSQL guarda lo que tiene **integridad
referencial y reglas**: personas, unidades, consentimientos, agregados
protegidos, bitácora. MongoDB guarda lo que es **un documento con forma
variable** y que nadie va a unir con un JOIN.

| Colección | Servicio | Qué guarda |
|---|---|---|
| `documentos` | `documents-service` | metadatos de evidencias, avisos versionados y reportes |
| `notificaciones` | `notifications-service` | la bandeja de cada persona |
| `preferencias_notificacion` | `notifications-service` | qué quiere recibir cada quien |
| `dispositivos_push` | `notifications-service` | tokens de dispositivos |
| `cola_push` | `notifications-service` | envíos pendientes |
| `corridas_algoritmo` | `algorithms-service` | historial de corridas del motor |
| `reportes` | `reports-service` | reportes generados y su sello |

**El archivo NO va en MongoDB.** Un PDF de 8 MB guardado como documento
vuelve lenta cualquier consulta de la colección. El blob va al almacén —
una carpeta en developer, el punto de montaje del bucket en production — y
a MongoDB sólo sus metadatos.

### La regla que MongoDB nunca rompe

**Ninguna colección recibe `empleado_id` ni ningún identificador directo
de persona.** Hay una verificación (`verificar_sin_identidad`) que lo
impide.

El motivo: MongoDB no tiene el mismo control de acceso por columna que
PostgreSQL, donde el rol de aplicación ni siquiera tiene `SELECT` sobre
`autoreporte.respuesta` ni sobre `consentimiento.seudonimo`. Si un
identificador de persona llegara a una colección, toda esa protección se
podría sortear leyendo MongoDB. Lo que viaja es el seudónimo, y sólo donde
hace falta.

---

## 2. Las dos reglas de índices que hay que entender

MongoDB no usa los índices como uno supone, y los seis defectos de la
sección siguiente salen todos de estas dos reglas.

### Regla del prefijo

Un índice compuesto `(a, b, c)` sirve para filtros sobre `a`, sobre
`(a, b)` y sobre `(a, b, c)`. **No sirve para un filtro sobre `b` solo.**

Un índice no es un conjunto de columnas: es un **orden**. Buscar por `b`
sin fijar `a` es como buscar un apellido en un directorio ordenado por
nombre.

### Regla del orden

Para ordenar por `k` usando un índice, todas las claves que preceden a `k`
en el índice tienen que estar fijadas **por igualdad** en el filtro.

Y aquí está lo que vuelve esto grave: **un ordenamiento sin índice no se
degrada, falla.** MongoDB lo hace en memoria con un límite de 32 MB y
**deja de funcionar** al pasarlo. No se pone lento: devuelve un error,
justo cuando la colección creció lo suficiente para que ese endpoint
importe.

---

## 3. Seis consultas que no tenían índice detrás

| Consulta | Qué le pasaba |
|---|---|
| `documentos.find_one({hash_contenido, tipo})` | La consulta de **cada descarga de evidencia**. Ningún índice empezaba por `hash_contenido` |
| `documentos.find({campania_id}).sort(fecha_creacion)` | `campania_id` era la **segunda** columna de `ix_unidad_campania` |
| `documentos.find({}).sort(fecha_creacion)` | La pantalla de listado, la primera que se abre. Ningún índice empezaba por `fecha_creacion` |
| `/notificaciones/mias` sin `solo_sin_leer` | El índice es `(destinatario, leida, fecha_creacion)`; sin fijar `leida` no sirve **para ordenar**. Es el endpoint que más llama la app móvil |
| `dispositivos_push.delete_one({token})` | `token` es la segunda columna. Es la única vía de limpieza de la colección |
| `/algoritmos/corridas` sin `campania_id` | Ordena por `fecha` con filtro vacío |

**Cuatro de las seis eran ordenamientos sin índice**, o sea del caso que
falla en lugar de degradarse.

Índices agregados: `ix_hash_tipo`, `ix_campania_fecha` y `ix_fecha` en
`documentos`; `ix_destinatario_fecha` e `ix_token` en notificaciones;
`ix_fecha` en `corridas_algoritmo`.

---

## 4. Cómo se encontraron, y por qué eso es menos que medirlo

**MongoDB no está instalado en el ambiente de medición y no se puede
instalar desde él.** Las pruebas usan `mongomock`, que no implementa
`explain()`. Así que no hay plan de ejecución que leer.

En su lugar, `pruebas/test_indices_mongo.py` (10 casos) hace un **análisis
estático**: lee las 44 consultas del código, extrae el filtro y el campo
de orden de cada una, y las comprueba contra los índices declarados
aplicando las dos reglas de arriba.

Esto es **menos que una medición** y se dice así en lugar de presentarlo
como equivalente. Un `explain()` real diría cuántos documentos examinó;
este análisis sólo dice si existe un índice capaz de servir la consulta.

### Una prueba que gritaba en falso

La primera versión del analizador dio **tres falsos positivos**, porque
trataba todo filtro armado en una variable como «podría estar vacío»:

```python
filtro = {"campania_id": campania}      # siempre lleva esta clave
if unidad:
    filtro["unidad_organizacional_id"] = unidad
```

El analizador veía `coleccion.find(filtro)` y no sabía qué traía `filtro`.

Eso importa más de lo que parece: **una prueba que avisa de problemas que
no existen se desactiva, y entonces deja de encontrar los que sí.** La
corrección resuelve las claves que el filtro lleva **siempre** —el literal
de la asignación y los `setdefault`— y no cuenta las que se agregan dentro
de un `if`.

---

## 5. Lo que queda pendiente

Medir con `explain()` contra un MongoDB real, en la máquina virtual, y
comparar `totalDocsExamined` contra `nReturned` antes y después de los
seis índices. Eso convertiría el análisis estático en una medición. No se
puede hacer desde el contenedor de desarrollo.
