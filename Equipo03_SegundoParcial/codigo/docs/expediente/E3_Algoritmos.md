# Algoritmos

**Expediente NEXUM — Equipo 03 · Capítulo de Emiliano Pascual Piñales
Sánchez (#657657)**

Desarrollo completo en `docs/Algoritmo_Complejo_Equipo03.md`. Este
capítulo es el del expediente: qué hace, cómo, qué tan bien, y qué no
hace.

---

## 1. El problema

**Dado** el historial de agregados protegidos de todas las unidades de una
organización a lo largo de varias campañas, **encontrar** los grupos que
necesitan intervención, **sin ver a ninguna persona** y **sin gastar
presupuesto de privacidad**.

Las tres partes son restricciones duras:

- *Sin ver a ninguna persona*: el algoritmo lee `resultado_protegido`, que
  ya tiene el ruido aplicado. No toca `autoreporte.respuesta`, y el rol de
  aplicación tampoco podría.
- *Sin gastar épsilon*: lee filas ya publicadas, no calcula agregados
  nuevos. **Épsilon consumido = 0.0**, medido.
- *Encontrar los grupos que necesitan intervención*: no basta con listar
  los peores promedios. Una unidad siempre tuvo 3.2 y otra bajó de 4.1 a
  3.4; la segunda es la que necesita atención y la primera sale peor en
  cualquier orden por promedio.

### Entradas

| | |
|---|---|
| `filas_campania` | agregados publicados de la campaña, por unidad y dimensión |
| `series_por_unidad` | la serie histórica de cada unidad: (secuencia, valor, escala de ruido) |
| `semilla` | 20260101, fija, para que dos corridas den lo mismo |

### Salida

Un informe con: perfiles por unidad, grupos (con centroides y silueta),
hallazgos de segmento, anomalías, tendencias, y una lista priorizada con
nivel `PRIORITARIO` / `ATENCION` / `INFORMATIVO`.

### Restricciones

- Sin numpy ni scipy. Son veinte veces el tamaño de la imagen para media
  docena de funciones, y así cada línea de la matemática está escrita
  donde se puede leer y defender en un examen.
- Determinista: misma entrada, misma salida.
- Debe tolerar unidades con huecos (campañas en las que no fueron
  convocadas) y valores suprimidos por *k*.

---

## 2. Las cinco etapas

### 2.1 Perfiles

Una fila por unidad con su valor por dimensión en la campaña actual.

### 2.2 Agrupamiento — k-medias con siembra k-means++

*k* se elige por **silueta**, probando *k* ∈ 2..6 y quedándose con el que
mejor separa. k-means++ en lugar de siembra aleatoria porque la aleatoria
converge a óptimos locales distintos en cada corrida, y eso rompe el
determinismo que el examen necesita.

### 2.3 Desplazamiento de grupos — `desplazamiento_de_grupos`

Cada grupo se compara con la **mediana de la organización**, no con su
media.

**Esta etapa existe por un defecto que encontró la validación**, y es el
hallazgo más importante del algoritmo: k-medias agrupó las cinco unidades
deterioradas en el mismo grupo —para eso sirve— con un centroide dos
puntos por debajo del grupo sano. Y dentro de su grupo, las cinco parecían
perfectamente normales. El motor las reportó `INFORMATIVO`.

Dicho de otro modo: **el agrupamiento escondía exactamente lo que había
que encontrar.** La corrección es medir cada grupo contra la organización
y reportar eso como hallazgo aparte.

La mediana y no la media: la media está contaminada por lo que se está
buscando.

### 2.4 Anomalías — dos pruebas, no una

Una dimensión se marca anómala sólo si pasa **las dos**:

```python
"anomala": significativa and material and hacia_peor
```

- **Significativa**: la desviación supera el ruido esperado.
- **Material**: supera un umbral derivado de los datos — media desviación
  estándar de lo que varían las unidades de la propia organización, con
  piso de 0.25.
- **Hacia peor**: en la dirección que empeora *para esa dimensión*.

La segunda condición también salió de un defecto: con datos masivos el
ruido baja a 0.04 y **todo** pasa la prueba de significancia. El motor
marcaba 36 dimensiones con desviación mediana de 0.12 puntos sobre una
escala de 1 a 5. Estadísticamente significativo; prácticamente nada.

### 2.5 Tendencia — Theil-Sen y Mann-Kendall

- **Theil-Sen**: mediana de las pendientes entre todos los pares de
  puntos. 29 % de punto de ruptura, contra 0 % de mínimos cuadrados. Hace
  falta porque el ruido de Laplace tiene **colas pesadas**: un atípico es
  mucho más probable que con una gaussiana, y tuerce una regresión por
  mínimos cuadrados.
- **Mann-Kendall**: prueba no paramétrica de tendencia monótona, con
  corrección de continuidad y de empates vía `math.erfc`.

La dirección se interpreta **por dimensión**: en carga percibida, subir es
empeorar. El código contaba `A_LA_BAJA` en todas las dimensiones *y*
sumaba aparte las cargas al alza — así que una mejora en carga contaba
como deterioro, y un deterioro real contaba dos veces.

### 2.6 Priorización

El nivel sale de **reglas**, no de un promedio ponderado:

```python
if len(anomalas) >= 2 or empeorando >= 3 or (anomalas and empeorando >= 2):
    nivel = "PRIORITARIO"
elif anomalas or empeorando >= 2 or (desplazadas and empeorando >= 1):
    nivel = "ATENCION"
else:
    nivel = "INFORMATIVO"
```

Antes el nivel salía de un promedio ponderado de cinco factores, y eso
**diluye una señal fuerte y aislada**: tres dimensiones en deterioro
sostenido con p ≈ 0.000 daban 0.316, por debajo del corte de 0.35. Con
reglas, el nivel además se puede explicar en una frase, que es lo que un
especialista necesita para actuar.

El puntaje sigue existiendo, pero sólo **ordena** dentro de cada nivel.

---

## 3. Complejidad

| Etapa | Complejidad |
|---|---|
| Perfiles | O(u · d) |
| k-medias (por *k*, por iteración) | O(u · d · k) |
| Silueta | O(u² · d) |
| Theil-Sen por serie | O(c²) |
| Mann-Kendall por serie | O(c²) |
| **Total dominante** | **O(u² · d + u · d · c²)** |

con *u* unidades, *d* dimensiones, *c* campañas. La silueta es cuadrática
en unidades y es el término que manda con *u* grande; con 110 unidades y 6
dimensiones el total medido es **69 ms**.

---

## 4. Métricas, contra verdad inyectada

No se mide mirando la salida y opinando. El generador elige al azar un 5 %
de unidades y las deteriora, otro 5 % y las hace decaer, y lo anota en
`public.verdad_inyectada` **antes** de correr el detector.

| | |
|---|---|
| Hallazgos de segmento | precisión 100 %, exhaustividad 100 % (10/10) |
| Deterioro sostenido | precisión 83.3 %, exhaustividad 100 %, F1 90.9 % |
| Ranking top 5 / top 10 | 5 de 5 / 9 de 10 |
| Épsilon consumido | **0.0** |
| Tiempo | 69 ms sobre 110 unidades |

**Los cuatro defectos de las secciones anteriores salieron de aquí.** Sin
verdad inyectada, la salida del motor se veía razonable en los cuatro
casos.

Validación: `scripts/validar_algoritmo.py`. Pruebas: 31 casos en
`pruebas/test_analitica.py`, 7 más en `pruebas/test_algoritmos.py`.

---

## 5. El corte de 20 segundos

El análisis es Python puro: agrupa, calcula siluetas y ajusta tendencias
sobre 110 unidades y 12 campañas. `statement_timeout` de PostgreSQL **no
lo puede cancelar**, porque no es una consulta.

Sin un límite propio, el único tope sería el de gunicorn, que mata al
obrero: el cliente recibe una conexión cortada sin código ni
identificador, y se cae además lo que ese obrero tenía en vuelo.

El bucle por unidad consulta su plazo con `exigir_tiempo()`. Al agotarse:

```
HTTP 503  TIEMPO_EXCEDIDO
Retry-After: 10
"La peticion excedio el tiempo maximo de 20 s mientras calculaba las
 series por unidad, y se detuvo. Se detuvo a proposito y no se perdio
 nada: no se escribio ningun resultado parcial."
```

**Lo que hay que poder explicar en la demostración:** el análisis se
detiene y **no guarda un resultado a medias**. El corte ocurre *entre*
unidades, no en medio de una, y el informe sólo se escribe al final. Un
informe parcial sería peor que ninguno — un especialista lo leería como si
estuviera completo y concluiría que las unidades que faltan están bien.

Es **cooperativo** y no una alarma: `signal.alarm` sólo llega al hilo
principal y el servicio corre con `--threads 2`, así que cortaría una
petición al azar, no la lenta. Y matar un hilo a la fuerza en Python lo
deja a medias, posiblemente con una transacción abierta.

---

## 6. Limitaciones

1. **Sobre datos ruidosos.** Lee agregados con ruido de Laplace. Con
   grupos chicos (escala 0.5) el umbral de detección es 2.118 puntos y
   **nada es detectable**. El algoritmo necesita volumen para servir — y
   esa es una propiedad del diseño de privacidad, no un defecto que se
   pueda corregir.
2. **No explica causas.** Dice qué unidad y qué dimensión, no por qué.
3. **No sigue personas.** Por construcción.
4. **Una unidad nueva no tiene tendencia.** Con menos de 3 campañas sólo
   hay anomalía y desplazamiento.
5. **El agrupamiento depende de la composición.** Si toda la organización
   se deteriora a la vez, no hay grupo sano contra el cual destacar; la
   etapa de desplazamiento mitiga esto midiendo contra la mediana, pero la
   mediana también se mueve.
6. **La precisión del deterioro es 83.3 %**: uno de cada seis avisos de
   deterioro es un falso positivo. Para una herramienta que dispara una
   conversación con un equipo, es un costo aceptable; para una que
   disparara una acción automática, no lo sería.
