# Resultados de rendimiento

**Expediente NEXUM — Equipo 03 · Capítulo de Emiliano Pascual Piñales
Sánchez (#657657)**

Banco de pruebas: `scripts/rendimiento.py`. Generador:
`scripts/datos_masivos.py`. Desarrollo completo en
`docs/Rendimiento_y_Carga_Equipo03.md`.

---

## 1. El conjunto de datos

| | |
|---|---|
| Empleados | 26 526 |
| Seudónimos | 26 526 |
| Unidades organizacionales | 136 |
| Campañas | 17 |
| Respuestas | 206 231 |
| Valores de detalle | 1 031 155 |
| Agregados protegidos | 8 314 |
| Tamaño de la base | ~155 MB |

Dos decisiones del generador que no se ven en las cifras:

- **La plantilla del padre es la suma de las hijas.** Si no, el ataque por
  diferencia aísla un residuo sub-*k*.
- **Los agregados se calculan con la función oficial**, 7 920 llamadas, no
  con INSERT directo. Insertarlos a mano sería mucho más rápido y
  produciría valores que nunca pasaron por la tubería de privacidad.

---

## 2. Las tres mejoras medidas

| | antes | después |
|---|---|---|
| `fn_calcular_agregado_protegido` (7 920 llamadas) | **89 ms** | **17.6 ms** |
| `/consultas/presupuesto` | **458 ms** | **4.6 ms** (100×) |
| Panel de monitoreo | **1 635 ms** | **2.8 ms** |
| Sonda de salud con dependencia opcional caída | **1 286 ms** | **53 ms** |

Sobre el camino caliente: a 89 ms, recalcular la organización completa
tomaba 705 s. A 17.6 ms toma 139 s.

Las causas están en el capítulo *Modelo de agregados e índices*. En una
línea cada una: un índice inerte porque el `ORDER BY` de una vista tenía
una tercera clave que el índice no cubría; una subconsulta correlacionada
sin índice que recorría una tabla 1 372 veces; y el panel de monitoreo
reteniendo un obrero de gunicorn 1.4 s, lo que llevaba
`/monitoreo/errores` de 5 ms a 2 549 ms con cuatro paneles en vuelo.

---

## 3. Tiempos de consulta, por volumen

| Consulta | chica (48) | mediana (870) | grande (2 528) | plan |
|---|---|---|---|---|
| tablero de una unidad | 0.10 ms | 0.10 ms | 0.09 ms | índice |
| serie completa de una unidad | 0.17 ms | 0.19 ms | 0.20 ms | índice |
| matriz de toda una campaña | 0.12 ms | 0.49 ms | 0.51 ms | índice |
| recuento de respuestas por unidad | 0.12 ms | 0.92 ms | 0.92 ms | índice |
| unión de una unidad y campaña | 0.20 ms | 0.41 ms | 0.67 ms | índice |
| tamaño del grupo con consentimiento | 12.74 ms | 7.43 ms | 8.15 ms | índice |

Metodología: mediana de 7 repeticiones, **descartando la primera** — paga
el arranque del plan y la lectura de disco, y mezclarla inventa una cola
que no describe el uso real.

El uso de índice **se lee del plan de ejecución**, no se deduce del
tiempo. Una consulta puede ser rápida y estar haciendo un recorrido
secuencial porque la tabla cabe en memoria, y eso deja de ser cierto el
día que crece.

---

## 4. Caché: con y sin Redis

| | |
|---|---|
| Sin caché | 0.726 ms |
| Con caché | 0.109 ms |
| Mejora | **6.7×** |

Y en el caso que de verdad importa, el análisis complejo:

| | |
|---|---|
| `/algoritmos/analisis` sin caché | 620 ms (p95 bajo esfuerzo) |
| `/algoritmos/analisis` con caché | 79 ms (p95 bajo esfuerzo) |

**Metodología, porque es fácil falsearla:** la clave se borra **antes de
cada** medición «sin caché». Si no, la segunda corrida siempre gana y la
comparación no prueba nada — está escrita de antemano.

Dos detalles del diseño de la caché que vale la pena anotar:

- **La clave incluye la semilla del algoritmo.** Si no, cambiar la semilla
  serviría resultados viejos calculados con otra.
- **La caché guarda el informe GLOBAL y el recorte por alcance se aplica
  al leer.** Al revés haría falta el alcance del solicitante en la clave,
  y un fallo al construirla le serviría a un líder de unidad el informe de
  toda la organización.

---

## 5. Consumo de recursos

Se mide el **proceso servidor de PostgreSQL**, no el guion. El guion manda
una cadena de SQL y espera; el trabajo lo hace el servidor. Medir el
cliente daría números bonitos y constantes mientras el servidor se queda
sin memoria. `pg_backend_pid()` dice qué proceso es, y `/proc/<pid>/stat`
y `/proc/<pid>/status` dan su CPU y su memoria.

### Por consulta

| Consulta | reloj | CPU | CPU/reloj | bloques en memoria | derrames |
|---|---|---|---|---|---|
| tablero de una unidad | 0.09 ms | 0.066 ms | 73 % | 6 | ninguno |
| serie completa de una unidad | 0.20 ms | 0.179 ms | 90 % | 184 | ninguno |
| matriz de toda una campaña | 0.51 ms | 0.371 ms | 73 % | 19 | ninguno |
| recuento de respuestas por unidad | 0.92 ms | 0.985 ms | ~100 % | 38 | ninguno |
| unión de una unidad y campaña | 0.67 ms | 0.649 ms | 97 % | 3 831 | ninguno |
| tamaño del grupo con consentimiento | 8.15 ms | 8.214 ms | ~100 % | 20 602 | ninguno |

**Tres cosas que sólo se ven aquí:**

1. **CPU ≈ reloj en todas.** Ninguna consulta espera disco, y los 100 % de
   aciertos de caché lo confirman desde el otro lado. La consecuencia
   práctica: **estas consultas no se mejoran con disco más rápido ni con
   más índices** —ya no leen de disco—; se mejoran haciendo menos trabajo.
   Con sólo el reloj, esto es indistinguible de una consulta que espera
   E/S, y se arreglan en lugares opuestos.
2. **Cero derrames a `work_mem`.** El pico medido es de 49 kB contra 4 MB
   disponibles: margen de ochenta veces. Importa porque un derrame es la
   diferencia entre 5 ms y 500 ms y **aparece de golpe** cuando los datos
   crecen un poco más. Con datos de demostración no ocurriría nunca.
3. **Memoria del backend: 27 MB, pico 27 MB**, plana en las seis
   consultas. El número que dimensiona no es ése sino ése multiplicado por
   la concurrencia; `PG_POOL_MAX=5` por servicio es lo que lo mantiene
   acotado.

### De la generación masiva, por fase

```
    generador, memoria pico:  28.1 MB
    backend, memoria pico:    51.3 MB  (shared_buffers 128MB, maintenance_work_mem 64MB)
    backend, cpu:             61.27 s de 61.7 s de reloj (99%)
    insercion (COPY):         99 998 filas/s en 0.97 s
    calculo de agregados:     888 en 60.5 s (68.1 ms cada uno, limitado por CPU)
```

- La **inserción** entra a 100 000 filas/s con `COPY`.
- El **cálculo de agregados** es el 98 % del tiempo, con el backend al
  **99 % de CPU**. La tubería de privacidad diferencial está **limitada
  por cómputo, no por disco**. Ni un disco más rápido ni un índice la
  mejoran; la palanca es el paralelismo, porque las llamadas son
  independientes entre unidades.
- El **generador** se mantiene en 28 MB: arma los lotes y los entrega con
  `COPY` en vez de acumular un millón de tuplas en memoria. Esa diferencia
  no se ve en el reloj hasta el momento en que el proceso se cae en un
  contenedor con poca memoria.

**El reporte por fase corrigió una conclusión equivocada.** La versión
anterior daba una sola cifra sobre el tiempo total —«2 168 filas por
segundo»— que hacía creer que la carga es lenta. Describía la inserción
46 veces peor de lo que es, y escondía que lo caro es el cálculo.

### Del servidor

| | |
|---|---|
| `shared_buffers` | 128 MB |
| `work_mem` | 4 MB |
| memoria por backend | mediana 32.0 MB, máximo 32.0 MB |

La memoria compartida y la privada se reportan aparte porque se dimensionan
distinto: la compartida se paga una vez, la privada se multiplica por la
concurrencia. Sumar los RSS de los backends da una **cota superior**, no la
memoria real, porque cada RSS incluye la parte de `shared_buffers` que ese
backend ya tocó.

---

## 6. Tres errores de medición propios

Un informe equivocado es un defecto. Estos se encontraron y se corrigieron:

1. **El banco medía una unidad al azar.** Dos corridas contra la misma
   base, sin cambiar nada, dieron **15.85 ms y 226.41 ms** del mismo
   camino caliente, y 7.45 ms contra 110.96 ms de la misma consulta. La
   causa era `ORDER BY random() LIMIT 1`, y las unidades van de 48 a 2 528
   respuestas. Un banco cuyo objetivo cambia en cada corrida no sirve para
   comparar, que es para lo único que sirve un banco. Ahora se miden tres
   unidades deterministas y se reportan las tres.

2. **La medición de CPU no superaba la resolución del reloj.** Un tic del
   kernel son 10 ms; con siete repeticiones de una consulta de 0.13 ms el
   contador no se movía y salía «0.00 ms», que se lee como «no consume
   CPU». Y una consulta que cruzaba el límite de un tic reportó 2.86 ms de
   CPU para 0.34 ms de reloj, que es imposible. Ahora se repite hasta
   acumular 20 tics, y si no se alcanza la resolución **se dice** en lugar
   de reportar un número.

3. **El conteo de filas leía estimaciones.** `n_live_tup` decía **0** para
   una tabla de 112 MB (autovacuum no había pasado) y `reltuples` decía
   **5** para una de 8 299 filas (era lo que dejó el último `ANALYZE`). El
   volumen es la variable independiente de todo lo demás. Se cuentan. Y
   contarlas al principio enfriaba la caché de PostgreSQL —112 MB por unos
   `shared_buffers` de 128 MB—, así que se cuentan al final.

---

## 7. Honestidad sobre el ambiente

Las mediciones se hicieron en **un solo contenedor** con los servicios,
PostgreSQL y Redis compartiendo CPU. Los números de throughput son un
**piso**.

**MongoDB no está disponible** en ese contenedor y no se puede instalar
desde él. Las pruebas usan `mongomock`, que no implementa `explain()`. Por
eso los seis índices de MongoDB se verificaron **analizando las 44
consultas del código** contra los índices declarados, aplicando las reglas
de prefijo y de orden —`pruebas/test_indices_mongo.py`, 10 casos—, y no
midiendo. Eso es menos que una medición y se dice así en lugar de
presentarlo como equivalente.

Lo que **no** cambia con el despliegue son los hallazgos de consultas y de
índices, porque salen del plan de ejecución y no del reloj.
