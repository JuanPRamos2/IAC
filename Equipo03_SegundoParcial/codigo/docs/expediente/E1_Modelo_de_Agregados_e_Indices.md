# Modelo de agregados e índices

**Expediente NEXUM — Equipo 03 · Capítulo de Emiliano Pascual Piñales
Sánchez (#657657)**

---

## 1. Por qué existe una tabla de agregados

La pregunta que el sistema tiene que contestar es «¿cómo está el bienestar
de esta unidad?». La respuesta obvia sería calcularla cuando alguien la
pide: promediar las respuestas de esa unidad y devolverla.

Eso está mal por dos razones distintas, y la segunda es la que importa.

**La razón de rendimiento** es que promediar en cada consulta recorre el
detalle completo. Con 1 031 155 valores eso no escala, y el tablero es la
pantalla que más se abre.

**La razón de privacidad** es la que decide el diseño: *un promedio
calculado al vuelo no deja rastro*. Si cada consulta recalcula, no hay
dónde anotar cuánto épsilon se gastó, ni cuántas veces se preguntó por el
mismo grupo, ni con qué recorte. Y sin ese rastro, el ataque por
repetición funciona: preguntar cien veces por la misma unidad y promediar
las cien respuestas cancela el ruido de Laplace y deja el valor real.

Así que el agregado **se materializa**: se calcula una vez, se guarda con
el ruido que se le puso y el épsilon que costó, y toda consulta posterior
lee esa fila. El ruido es el mismo porque la fila es la misma, y promediar
cien lecturas de la misma fila devuelve exactamente esa fila.

---

## 2. Las tablas

### `agregado.resultado_protegido`

Una fila por (unidad, campaña, dimensión). La dimensión nula es el índice
global de bienestar.

| Columna | Qué guarda | Por qué está |
|---|---|---|
| `unidad_organizacional_id` | la unidad | parte de la clave |
| `campania_id` | la campaña | parte de la clave |
| `dimension_id` | la dimensión, o NULL para el global | parte de la clave |
| `valor_protegido` | el valor **con ruido ya aplicado** | es el único valor que sale del sistema |
| `escala_ruido` | el parámetro *b* de Laplace que se usó | sin esto, quien lee no sabe cuánta incertidumbre tiene el número |
| `n_respuestas` | cuántas personas contestaron | para la comprobación de *k* |
| `estado_publicacion` | `PUBLICADO` o `SUPRIMIDO` | un grupo bajo *k* se suprime, y la supresión se guarda |
| `epsilon_consumido` | lo que costó calcularlo | alimenta el presupuesto |

**El valor crudo no se guarda.** No hay columna `valor_real`. Esa es una
decisión de diseño y no un olvido: una columna con el valor sin ruido
convertiría toda la protección en una medida de acceso —«no consultes esa
columna»— en lugar de una propiedad de los datos. Si alguien con acceso a
la base la leyera, el ruido no habría servido de nada. Como no existe, no
hay nada que leer.

### `agregado.consulta_privada` y `agregado.presupuesto_privacidad`

El libro de contabilidad del épsilon. Cada cálculo anota una fila en
`consulta_privada` contra un `presupuesto_privacidad`, que es por (unidad,
ventana de tiempo). Cuando el presupuesto se agota, la función deja de
contestar.

Esto es lo que convierte «le ponemos ruido» en privacidad diferencial de
verdad: el ruido por sí solo no protege si se puede pedir mil veces.

### `public.verdad_inyectada`

Tabla de **pruebas**, no de producción. El generador de datos masivos
elige al azar un 5 % de unidades y las deteriora, otro 5 % y las hace
decaer, y lo anota aquí **antes** de correr el detector. Sirve para medir
si el algoritmo encuentra lo que hay, en lugar de mirar su salida y
opinar. Sin ella, las métricas del capítulo de algoritmos no existirían.

---

## 3. La única puerta: `fn_calcular_agregado_protegido`

```
agregado.fn_calcular_agregado_protegido(campania, unidad, dimension, actor)
```

Es la **única** forma de producir una fila de `resultado_protegido`. No
hay INSERT directo en ningún camino del código, y el generador de datos
masivos tampoco lo hace: llama a esta función 7 920 veces aunque sea más
lento, porque insertar a mano produciría valores que nunca pasaron por la
tubería de privacidad — exactamente lo que el proyecto entero existe para
evitar.

La función hace, en este orden:

1. **Recorte (*clipping*).** Acota cada respuesta al rango válido. Sin
   esto, un solo valor extremo mueve el promedio lo suficiente para
   delatar a quien lo puso.
2. **Comprobación de *k*.** Si el grupo tiene menos de 5 personas con
   consentimiento vigente, no se calcula: se guarda `SUPRIMIDO`. La
   supresión **se guarda** en lugar de no escribir nada, porque un hueco
   silencioso es indistinguible de un dato que aún no llegó.
3. **Ruido de Laplace.** `escala = sensibilidad / epsilon`, con
   `sensibilidad = (hi - lo) / n`.
4. **Contabilidad del épsilon.** Anota la consulta contra el presupuesto.

El orden importa: recortar *después* de promediar no acota la influencia
de un valor extremo, y comprobar *k* después de calcular ya dejó el
cálculo hecho en memoria.

---

## 4. Los índices, con su motivo y su medición

Un índice sin motivo escrito es un índice que nadie se atreve a quitar
después, aunque ya no sirva: ocupa espacio, frena cada escritura, y como
nadie sabe por qué está, ahí se queda. Los siete de la migración **018**
llevan su motivo en el propio archivo.

| Índice | Sobre | Para qué consulta |
|---|---|---|
| `ix_respuesta_campania_unidad` | `respuesta (campania_id, unidad_organizacional_id)` | el camino caliente: las respuestas de una unidad en una campaña |
| `ix_detalle_respuesta_reactivo` | `respuesta_detalle (respuesta_id, reactivo_id)` | el desglose por reactivo |
| `ix_agregado_unidad_campania_dim` | `resultado_protegido (unidad, campania, dimension)` | el tablero de una unidad |
| `ix_agregado_campania_publicado` | `resultado_protegido (campania_id, estado_publicacion)` | la matriz de toda una campaña |
| `ix_bitacora_fecha_accion` | `bitacora (fecha_hora DESC, accion)` | el panel de errores de 24 horas |
| `ix_consent_vigente` | `consentimiento (seudonimo_id, fecha_evento DESC, consentimiento_id DESC)` | la vista de consentimiento vigente |
| `ix_consulta_privada_presupuesto` | `consulta_privada (presupuesto_id)` | la suma del épsilon gastado |

### Los dos que cambiaron un número grande

**`ix_consent_vigente` — 30.5 ms → 11.3 ms, y el camino caliente de 89 ms
a 21 ms.**

Ya existía un índice `idx_consent_seud` sobre
`(seudonimo_id, fecha_evento DESC)`. Parecía correcto. No servía, y el
motivo es una sola columna: el `ORDER BY` de
`consentimiento.v_estado_vigente` tiene una **tercera** clave,
`consentimiento_id DESC`, para desempatar dos eventos con la misma marca
de tiempo. PostgreSQL no puede usar un índice de dos columnas para
resolver un orden de tres, así que ordenaba las 24 476 filas de
consentimientos **en cada llamada** para resolver 198 seudónimos.

Lo que lo hacía invisible: la consulta devolvía lo correcto. Nada falla,
nada avisa, y con los datos de demostración —donde hay decenas de filas—
tampoco se nota en el reloj.

**`ix_consulta_privada_presupuesto` — 458 ms → 4.6 ms.**

`agregado.consulta_privada` no tenía índice por `presupuesto_id`, y la
suma del épsilon gastado es una subconsulta correlacionada: se ejecuta una
vez **por cada fila de presupuesto**. Con 1 372 presupuestos, eso son 1 372
recorridos secuenciales de la tabla de consultas.

Por qué no se veía con datos de demostración: ahí hay 40 filas de
presupuesto en lugar de 1 372. El costo de una subconsulta correlacionada
crece con las filas de **fuera**, no con las de dentro, así que el
problema no es que la tabla creciera — es que creció la otra.

---

## 5. Tiempos finales, por volumen

Tres unidades elegidas de forma determinista por número de respuestas: la
más chica, la mediana y la más grande.

| Consulta | chica (48) | mediana (870) | grande (2 528) | plan |
|---|---|---|---|---|
| tablero de una unidad | 0.10 ms | 0.10 ms | 0.09 ms | índice |
| serie completa de una unidad | 0.17 ms | 0.19 ms | 0.20 ms | índice |
| matriz de toda una campaña | 0.12 ms | 0.49 ms | 0.51 ms | índice |
| recuento de respuestas por unidad | 0.12 ms | 0.92 ms | 0.92 ms | índice |
| unión de una unidad y campaña | 0.20 ms | 0.41 ms | 0.67 ms | índice |
| tamaño del grupo con consentimiento | 12.74 ms | 7.43 ms | 8.15 ms | índice |
| `fn_calcular_agregado_protegido` | — | — | 17.6 ms | — |

**Cinco de las seis son planas o casi planas en el volumen de la unidad.**
Multiplicar por 53 las respuestas cambia el tablero en nada y la unión en
3.4×. Esa es la firma de un índice que acota de verdad: el trabajo depende
de las filas que se devuelven, no de las que existen.

**La sexta va al revés**, y es el dato más útil de la tabla: `tamaño del
grupo con consentimiento` es **más lenta en la unidad chica** (12.74 ms
contra 8.15 ms). No es ruido — el costo de esa consulta no está en la
unidad sino en recorrer el estado de consentimiento vigente, 20 602
bloques, el 100 % en memoria. La consecuencia práctica: **esa consulta no
se optimiza acotando la unidad.** Una tabla de una sola columna de tiempos
habría sugerido justo lo contrario.

---

## 6. Tamaños

| Tabla | total | índices | filas |
|---|---|---|---|
| `autoreporte.respuesta_detalle` | 112 MB | 69 MB | 1 031 155 |
| `autoreporte.respuesta` | 34 MB | 16 MB | 206 231 |
| `agregado.resultado_protegido` | 2.3 MB | 944 kB | 8 314 |
| `agregado.consulta_privada` | 1.1 MB | 312 kB | 8 246 |
| `agregado.presupuesto_privacidad` | 936 kB | 136 kB | 1 372 |

Los índices de `respuesta_detalle` pesan 69 MB sobre 112 MB de datos. Es
mucho y está justificado: sin ellos, cada una de las 7 920 llamadas a la
función de agregados recorre el millón de filas.

Las filas **se cuentan, no se estiman.** El informe empezó leyendo
`n_live_tup` de `pg_stat_user_tables`, que devolvía **0** hasta que
autovacuum pasara, y cayó a `reltuples`, que devolvía **5** para una tabla
con 8 299 filas porque era lo que dejó el último `ANALYZE`. Una columna de
volumen equivocada invalida el informe entero: el volumen es la variable
independiente de todo lo demás.

---

## 7. La invariante de la jerarquía

`plantilla_declarada` de una unidad padre **no puede ser menor** que la
suma de sus hijas. No es prolijidad de catálogo: el control de inferencia
calcula «plantilla del padre menos las hijas ya consultadas» para decidir
si una consulta permitiría aislar un grupo por debajo de *k*. Con el padre
declarando menos, ese residuo sale negativo, la condición nunca se cumple,
y el control queda **presente y sin efecto** — que es la peor de las tres
posibilidades, porque aparenta proteger.

La migración 008 lo arregló una vez y creó la función que lo **detecta**.
Nada lo **impedía**, y lo descubrió una prueba de inferencia fallando sin
que nadie tocara la jerarquía: unidades creadas por otras pruebas habían
empujado al padre por encima de su declaración.

La migración **020** instala un disparador de restricción
`DEFERRABLE INITIALLY IMMEDIATE`: estricto por omisión, diferible para una
carga masiva que arma el árbol por partes. **Diferir no es desactivar** —
la comprobación ocurre igual, al `COMMIT`, sobre el árbol ya completo. La
carga de la semilla usa esa vía y verificada desde cero da 0 violaciones.
