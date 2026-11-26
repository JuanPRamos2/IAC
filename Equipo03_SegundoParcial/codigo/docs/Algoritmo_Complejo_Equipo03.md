# Algoritmo complejo: detección de riesgo psicosocial por grupos

Proyecto 4. Plataforma de Bienestar Laboral y Prevención de Burnout
Integración de Aplicaciones Computacionales · UDEM · Equipo 03 · Tercer parcial

| | |
|---|---|
| Emiliano Pascual Piñales Sánchez | #657657 |
| Rol en este parcial | Integrante 3 — algoritmos, bases de datos y pruebas de rendimiento |

Código: `apps/microservicios/analitica/` (paquete `analitica`)
Expuesto en: `GET /api/v1/algoritmos/analisis` (`algorithms-service`, puerto 8109)
Pruebas: `pruebas/test_analitica.py` (31 casos) y `pruebas/test_algoritmos.py`
Validación contra verdad inyectada: `scripts/validar_algoritmo.py`

---

## 1. El problema

La organización tiene 136 unidades y mide cinco dimensiones de bienestar
—carga percibida, recuperación, apoyo, autonomía y claridad— cada
campaña. Son 680 números por campaña y doce campañas de historia. Nadie
puede mirar esa matriz y decidir dónde intervenir.

El algoritmo contesta una pregunta concreta:

> **¿Qué unidades merecen atención, por qué, y qué tan seguros estamos?**

Y la contesta **sin ver a una sola persona**: trabaja únicamente sobre
agregados ya publicados, que pasaron el umbral k (mínimo cinco personas) y
ya llevan aplicado su ruido de privacidad diferencial.

Hay tres razones por las que esto no es un simple umbral, y cada una
salió de intentarlo y medir que no servía:

1. **Comparar contra una constante no funciona.** Un turno nocturno tiene
   peor recuperación que una oficina porque trabaja de noche. Contra un
   umbral fijo sale como anomalía todos los semestres, la lista se llena
   de unidades que nadie puede arreglar, y se deja de leer.

2. **Estar mal y estar empeorando son cosas distintas.** Una unidad en 2.8
   y estable ya tocó fondo. Otra en 3.4 cayendo 0.2 por campaña llegará
   más abajo en un año. El umbral dispara con la primera y no con la
   segunda, y es la segunda donde una intervención todavía sirve.

3. **El ruido de privacidad no es despreciable y no es constante.** Una
   unidad de 8 personas recibe ruido con escala 0.5; una de 400, con
   escala 0.01. La misma diferencia de medio punto es indistinguible del
   azar en la primera y certísima en la segunda. Un umbral fijo trata a
   las dos igual.

---

## 2. Entradas

| Entrada | Tipo | Origen | Restricción |
|---|---|---|---|
| `filas_campania` | lista de diccionarios | `agregado.resultado_protegido` con `estado_publicacion = 'PUBLICADO'` | Cada fila: `unidad_organizacional_id`, `dimension_id`, `valor_protegido` ∈ [1,5], `escala_ruido` > 0, `n_observaciones` ≥ k |
| `series_por_unidad` | `{unidad: {dimensión: [(secuencia, valor, escala)]}}` | la misma tabla, todas las campañas hasta la analizada | `valor` puede ser `None`: son las campañas suprimidas por el umbral k, y se cuentan |
| `semilla` | entero | constante `20260101` | Fija, para que dos corridas sobre los mismos datos den el mismo resultado |

El paquete **no consulta la base de datos**. Recibe filas y devuelve un
informe. Eso no es un detalle de estilo: es lo que permite probar la
matemática sin levantar PostgreSQL ni Flask, y lo que permite auditar que
no gasta épsilon leyendo el código en lugar de confiando. Hay una prueba
que falla si alguien importa `psycopg2` dentro del paquete.

## 3. Salidas

```
{
  "unidades_analizadas": 110,
  "unidades_sin_perfil_completo": [...],     # excluidas, y por qué
  "dimensiones": ["DIM-APOYO", ...],
  "agrupamiento": {
     "grupos": 4, "silueta": 0.8099,
     "umbrales_materiales": {...},
     "mediana_de_la_organizacion": {...},
     "centroides": [...],
     "grupos_desplazados_hacia_peor": [1, 3]
  },
  "priorizadas": [                            # ordenado: nivel, luego puntaje
     {"unidad_organizacional_id": ..., "nivel": "PRIORITARIO",
      "puntaje": 0.407, "dimensiones_anomalas": [...],
      "dimensiones_empeorando": [...], "grupo_desplazado_en": [...],
      "desglose": {...}, "motivos": [...]}
  ],
  "hallazgos_de_segmento": [...],             # grupos desplazados, aparte
  "tendencias": {...},
  "epsilon_consumido": 0.0,
  "tiempo_ms": 69.21
}
```

Tres cosas de la salida que son decisiones y no formato:

- **`epsilon_consumido` es siempre 0.0** y hay una prueba de comportamiento
  y otra de código fuente que lo garantizan.
- **`unidades_sin_perfil_completo` se reporta en lugar de omitirse.** Una
  unidad a la que le suprimieron una dimensión queda fuera del
  agrupamiento. Rellenar el hueco con la media del grupo la describiría
  con un número que nadie midió; omitirla en silencio haría creer que ahí
  no hay riesgo, cuando lo que hay es falta de datos publicables.
- **Cada unidad priorizada trae su `desglose`.** Un ranking sin desglose no
  se puede discutir, y este se discute en un comité que puede —y debe— no
  estar de acuerdo.

---

## 4. Variables y constantes

| Nombre | Valor | De dónde sale |
|---|---|---|
| `SEMILLA` | 20260101 | Constante. Hace repetible el agrupamiento |
| `MAXIMO_ITERACIONES` | 100 | k-medias converge mucho antes; es un tope de seguridad |
| `TOLERANCIA` | 1e-6 | Corte de convergencia |
| candidatos de k | 2…6 | Se elige por silueta, no a mano |
| `FRACCION_DESVIACION` | 0.5 | Media desviación estándar: el «efecto medio» de Cohen |
| `PISO_MATERIAL` | 0.25 puntos | Piso del umbral material, para organizaciones muy homogéneas |
| `MINIMO_PARA_SEGMENTO` | 3 unidades | Por debajo, un grupo no es un segmento |
| `MINIMO_PUNTOS` (tendencia) | 3 campañas | Con dos puntos cualquier par define una recta perfecta |
| `FACTOR_CONTRA_CENTROIDE` | √2 | Comparar un valor con ruido contra un centroide |
| `FACTOR_DOS_MUESTRAS` | 2.0 | Comparar dos valores con ruido entre sí |
| `PESOS` | anomalía 0.30, tendencia 0.30, contexto 0.20, persistencia 0.12, confianza 0.08 | Suman 1.0. Solo ordenan; el **nivel** sale de reglas |

El umbral material **no es una constante inventada**: es media desviación
estándar de lo que varían las unidades de la propia organización entre sí.
Un umbral fijo sería arbitrario —0.3 puntos es mucho en una organización
homogénea y poco en una dispar— y lo que importa es si esta área se sale
de la variación normal de *su* organización.

---

## 5. Restricciones

1. **Cero épsilon adicional.** Solo lee resultados publicados. Si llamara
   a `agregado.fn_calcular_agregado_protegido` para tener datos frescos,
   cada corrida gastaría presupuesto de privacidad, y al agotarlo la
   campaña se quedaría sin poder publicar: analizar el riesgo costaría la
   capacidad de medirlo.
2. **Nunca accede a datos de persona.** No toca `autoreporte.respuesta` ni
   `consentimiento.seudonimo`, y el rol de aplicación no tiene SELECT
   sobre ellas.
3. **Determinista.** Misma entrada, misma salida. La semilla va en la
   clave de caché para que un cambio de semilla caduque los informes
   guardados en lugar de servirlos como si fueran del algoritmo actual.
4. **Sin numpy ni scipy.** Son veinte veces el tamaño de la imagen para
   media docena de funciones, y aquí cada línea de la matemática —el
   mecanismo de Laplace, la pendiente de Theil-Sen, la corrección de
   empates de Mann-Kendall— está escrita y comentada donde se puede leer
   y defender.
5. **No afirma causas.** Detecta que una unidad está lejos de sus pares o
   que viene cayendo; por qué, lo averigua una persona hablando con el
   área.

---

## 6. Las cinco etapas, y la matemática de cada una

### 6.1 Perfiles — `construir_perfiles`

Matriz unidad × dimensión. Una unidad entra solo si tiene valor publicado
en **todas** las dimensiones; las demás se listan aparte.

### 6.2 Agrupamiento — `agrupamiento.py`

**k-medias con siembra k-means++**, y k elegido por **silueta** entre 2 y 6.

La silueta de un punto es `(b − a) / max(a, b)`, con `a` = distancia media
a su grupo y `b` = distancia media al grupo más cercano. Importa porque
k-medias devuelve grupos **siempre**, incluso cuando no hay ninguno: sin
la silueta, el algoritmo partiría una organización homogénea en tres
grupos arbitrarios y después mediría desviaciones contra centroides que no
significan nada.

Siembra k-means++ y no al azar porque con siembra aleatoria el resultado
depende de la suerte y dos corridas sobre los mismos datos pueden dar
grupos distintos. Un informe que cambia sin que cambien los datos no se
puede usar para decidir nada.

### 6.3 Anomalías — `detectar_anomalias`

Cada unidad se compara con el centroide de su grupo, y la desviación tiene
que pasar **dos pruebas, no una**:

**Prueba 1 — ¿puede el ruido explicarlo?** El sistema guarda la escala de
Laplace que aplicó, así que la pregunta tiene respuesta exacta. La cola de
Laplace es `P(|X| > t) = exp(−t/b)`, y el umbral al 95% de confianza es

```
umbral = factor · b · (− ln(1 − 0.95)) = factor · b · 2.996
```

con `factor = √2` al comparar un valor ruidoso contra un centroide.

**Prueba 2 — ¿es materialmente grande?** `|desviación| ≥ max(0.25,
0.5 · σ_entre_unidades)`.

Esta segunda prueba se agregó después de medir, y es la corrección más
importante del algoritmo. Con los datos masivos la escala de ruido baja a
0.04, y entonces una diferencia de 0.12 puntos es estadísticamente
certísima. El detector marcaba **36 dimensiones con desviación mediana de
0.12 puntos**: treinta y seis hallazgos ciertos e inservibles. Sobre una
escala de 1 a 5, 0.12 puntos no es nada sobre lo que un comité pueda
actuar, y la lista perdía su único propósito, que es decir por dónde
empezar.

**La unidad que queda sola o en pareja se compara contra el grupo vecino.**
k-medias aísla a la unidad anómala en su propio grupo —para eso sirve— y
entonces su centroide es ella misma, su desviación es cero, y la anomalía
se esconde a sí misma. Se comprobó: una unidad con recuperación 1.9 y
apoyo 2.0 contra pares en 3.5 salía INFORMATIVO y sin un solo hallazgo.

### 6.4 Desplazamiento de grupos — `desplazamiento_de_grupos`

Aquí está el defecto más grave que encontró la validación, y su
corrección.

Comparar cada unidad con su grupo de pares resuelve el problema del turno
nocturno y tiene un punto ciego que lo anula: **el grupo puede ser él
mismo la anomalía.** Medido con 110 unidades y cinco deterioradas a
propósito, k-medias puso a las cinco en el **mismo grupo** —porque para
eso sirve, agrupa lo parecido— con un centroide de recuperación 1.86
contra 3.97 del grupo sano. Dos puntos de diferencia en una escala de 1 a
5, y dentro de su grupo las cinco parecían normales. El motor las reportó
INFORMATIVO. Eran las cinco unidades que había que encontrar.

Así que cada grupo se mide además contra la **mediana** de la organización
—mediana y no media: si un puñado de unidades está muy mal, arrastran la
media y el punto de referencia se contamina justamente con lo que se
quiere detectar.

**Lo que esta etapa NO puede decir.** Que un grupo esté desplazado no
significa que esté en problemas. Un turno nocturno descansa peor porque
trabaja de noche: desplazamiento legítimo y estructural. Un grupo de áreas
en crisis también está desplazado. **Desde los datos las dos cosas son
idénticas** y ningún estadístico las separa. Por eso el desplazamiento se
reporta **aparte** del desvío intra-grupo, como `hallazgos_de_segmento`,
con la pregunta que una persona tiene que contestar:

> ¿Las 6 unidades de este grupo comparten una condición de trabajo que
> explique estar por debajo en apoyo, carga y recuperación?

Y por eso el hallazgo es del **segmento** y no de cada unidad. Marcar a
sus seis unidades como PRIORITARIO cada una diría que hacen falta seis
intervenciones de equipo, cuando lo que hace falta es una revisión del
segmento.

### 6.5 Tendencia — `tendencia.py`

**Pendiente por Theil-Sen**: la mediana de las pendientes entre todos los
pares de puntos. Se usa en lugar de mínimos cuadrados porque el ruido de
privacidad es de Laplace, de **colas pesadas**, y un solo valor extremo
arrastra una recta de mínimos cuadrados. Theil-Sen aguanta que hasta un
29% de los puntos sean atípicos.

**Significancia por Mann-Kendall**, no paramétrica —no supone normalidad,
y aquí no la hay— con corrección de continuidad y corrección de empates:

```
S = Σ_{i<j} signo(y_j − y_i)
Var(S) = [n(n−1)(2n+5) − Σ_t t(t−1)(2t+5)] / 18
z = (S ∓ 1) / √Var(S)
p = erfc(|z| / √2)
```

Tres detalles que cambian el resultado:

- **Los puntos suprimidos se descartan del cálculo y se cuentan.** Si una
  unidad no publicó en la campaña 3, las campañas 2 y 4 no son
  consecutivas: el salto entre ellas no es un paso, son dos.
- **La pendiente va contra la secuencia real de campaña**, no contra la
  posición en la lista. Esa distinción convierte «bajó 0.4 entre dos
  lecturas» en «bajó 0.2 por campaña».
- **«Empeorar» no es «bajar».** En carga percibida, subir es empeorar y
  bajar es mejorar. La primera versión contaba `A_LA_BAJA` en todas las
  dimensiones y además sumaba aparte las cargas al alza: una unidad cuya
  carga estaba bajando —una mejora clara— se contaba como si estuviera
  empeorando, y una que de verdad empeoraba en carga se contaba dos veces.

Y la misma compuerta material que en las anomalías: el **recorrido
acumulado** tiene que superar el umbral material, no solo el ruido. Con
110 unidades por 5 dimensiones hay 550 series, y a p < 0.05 el azar solo
produce unas 27 detecciones. El filtro de ruido no las frena porque con
datos masivos la escala de Laplace baja a 0.04 y cualquier deriva real la
supera.

### 6.6 Priorización — `priorizar`

El **puntaje** combina cinco componentes ponderados y sirve para
**ordenar**. El **nivel** sale de reglas sobre los hallazgos:

```
PRIORITARIO  si  anómalas ≥ 2  o  empeorando ≥ 3  o  (anómalas ≥ 1 y empeorando ≥ 2)
ATENCION     si  anómalas ≥ 1  o  empeorando ≥ 2  o  (grupo desplazado y empeorando ≥ 1)
INFORMATIVO  en los demás casos
```

Usar el puntaje para el nivel estaba mal, y se midió por qué: al ser un
promedio ponderado, diluye una señal fuerte y aislada. Una unidad con
tres de cinco dimensiones deteriorándose de forma sostenida —p ≈ 0.000,
casi un punto de caída en doce campañas— y sin nada más que señalar salía
con 0.316, por debajo del corte de ATENCION. Es exactamente la unidad
donde una intervención todavía sirve. Subir los pesos no lo arregla:
desplaza el problema a otra combinación. Lo que estaba mal era usar un
promedio para una decisión que es una **disyunción**.

Y un nivel por reglas se puede explicar en una frase —«ATENCION porque
tres dimensiones vienen cayendo por encima del ruido»— mientras «ATENCION
porque 0.407 > 0.35» no explica nada y no se puede discutir en un comité.

---

## 7. Pseudocódigo

```
ENTRADA: filas de la campaña (unidad, dimensión, valor, escala, n)
         series históricas por unidad y dimensión
         semilla

1. PERFILES
   para cada unidad:
       si tiene valor publicado en TODAS las dimensiones:
           perfil[unidad] ← vector de valores
       si no:
           incompletas[unidad] ← dimensiones que faltan     # se reportan

2. UMBRAL MATERIAL
   para cada dimensión d:
       σ ← desviación estándar de perfil[*][d]
       umbral_material[d] ← max(PISO_MATERIAL, 0.5 · σ)

3. AGRUPAMIENTO
   mejor ← nulo
   para k en 2..6:
       centroides ← siembra k-means++(puntos, k, semilla)
       repetir hasta convergencia o 100 iteraciones:
           asignar cada punto al centroide más cercano
           recalcular cada centroide como media de sus puntos
       s ← silueta(asignación)
       si s > mejor.s: mejor ← (k, asignación, centroides, s)

4. DESPLAZAMIENTO DE GRUPOS
   mediana_org[d] ← mediana de perfil[*][d]                 # mediana, no media
   para cada grupo g:
       para cada dimensión d:
           desplazamiento ← centroide[g][d] − mediana_org[d]
           material ← |desplazamiento| ≥ umbral_material[d]
           hacia_peor ← (d es invertida) ? desplazamiento>0 : desplazamiento<0
       si g tiene ≥ 3 unidades y alguna dimensión material y hacia peor:
           emitir hallazgo_de_segmento(g)                   # APARTE

5. ANOMALÍAS
   para cada unidad u:
       grupo ← asignación[u]
       si |grupo| ≤ 2:  referencia ← centroide del grupo MÁS CERCANO distinto
       si no:           referencia ← centroide del propio grupo
       para cada dimensión d:
           desviación ← valor[u][d] − referencia[d]
           b ← escala de ruido de valor[u][d]
           p ← exp(−|desviación| / (√2 · b))
           significativa ← p < 0.05
           material      ← |desviación| ≥ umbral_material[d]
           hacia_peor    ← (d es invertida) ? desviación>0 : desviación<0
           anómala[u][d] ← significativa Y material Y hacia_peor

6. TENDENCIAS
   para cada unidad u, dimensión d:
       puntos ← series[u][d]
       publicados ← puntos con valor ≠ nulo
       suprimidos ← |puntos| − |publicados|                 # se cuentan
       si |publicados| < 3: dirección ← INDETERMINADA; continuar
       pendiente ← mediana de (y_j−y_i)/(x_j−x_i) sobre todos los pares  # Theil-Sen
       S, z, p ← Mann-Kendall(publicados) con corrección de empates
       recorrido ← |pendiente| · (max x − min x)
       supera_ruido ← recorrido > 2 · escala_combinada
       empeorando[u][d] ← p<0.05 Y supera_ruido Y
                          recorrido ≥ umbral_material[d] Y hacia peor

7. PRIORIZACIÓN
   para cada unidad u:
       puntaje ← 0.30·magnitud + 0.30·tendencia + 0.20·contexto
                 + 0.12·persistencia + 0.08·confianza
       nivel   ← reglas sobre (|anómalas|, |empeorando|, grupo desplazado)
   ordenar por (nivel, −puntaje, id)

SALIDA: priorizadas, hallazgos_de_segmento, agrupamiento, tendencias,
        unidades_sin_perfil_completo, epsilon_consumido = 0.0
```

---

## 8. Complejidad

Con **n** unidades, **d** dimensiones (5), **m** campañas (12), **k**
grupos, **i** iteraciones de k-medias.

| Etapa | Complejidad | Nota |
|---|---|---|
| Perfiles | O(n · d) | Un recorrido de las filas |
| Umbrales materiales | O(n · d) | Una desviación estándar por dimensión |
| Siembra k-means++ | O(n · k · d) | Por cada k candidato |
| Iteraciones k-medias | O(n · k · i · d) | Por cada k candidato |
| Silueta | **O(n² · d)** | Distancia de cada punto a todos los demás |
| Desplazamiento de grupos | O(k · d) | Centroides contra mediana |
| Anomalías | O(n · d) | |
| Tendencias | O(n · d · m²) | Theil-Sen son todos los pares: m(m−1)/2 |
| Priorización | O(n log n) | El ordenamiento |

**El término dominante es la silueta, O(n² · d)**, y conviene decirlo
porque es el que limita el crecimiento: con n en cientos son
milisegundos, pero con n = 10 000 unidades serían ~10⁸ operaciones por
cada k candidato. Si la organización creciera a ese tamaño, la silueta se
calcularía sobre una muestra en lugar de sobre todos los puntos, que es
la solución estándar y cambia el intervalo de confianza del valor, no el
k elegido.

Las tendencias son O(m²) por el Theil-Sen, no O(m log m): con m = 12 son
66 pares por serie y no vale la pena optimizarlo; con m = 200 campañas
(cien años de historia semestral) habría que cambiar a una mediana
aproximada.

---

## 9. Casos de prueba

`pruebas/test_analitica.py` — **31 casos**, sin base de datos ni Flask.
Los agrupo por lo que cada bloque protege:

**Que dispare con señal real (3 casos)**
- Detecta una unidad con recuperación 1.9 y apoyo 2.0 contra pares en 3.5.
- Una unidad aislada se compara contra el grupo vecino, no contra sí misma.
- En carga percibida, alto es malo y bajo no.

**Que NO dispare con ruido (4 casos)**
- No marca nada en una organización homogénea.
- El umbral crece con el ruido.
- Una diferencia pequeña con mucho ruido no es anomalía.
- La misma diferencia con poco ruido sí lo es.

**Que significativo no sea lo mismo que importante (2 casos)**
- Una diferencia de 0.12 puntos con ruido 0.01 —doce veces la escala, así
  que cierta— no es un hallazgo. Y la misma organización con 0.9 puntos de
  diferencia sí dispara, para que la prueba no pase por no detectar nunca
  nada.
- El umbral material reacciona a la dispersión de la organización y tiene
  piso.

**Que el grupo pueda ser la anomalía (2 casos)**
- Seis unidades juntas y muy por debajo producen un hallazgo de segmento
  que las cubre a las seis y no arrastra unidades sanas; y cada una trae
  el contexto consigo en la lista priorizada.
- El hallazgo de segmento **no afirma** que el segmento esté mal: deja una
  pregunta y advierte que los datos no distinguen un segmento que *es* así
  de uno que *está* mal.

**Que el nivel y la dirección sean correctos (3 casos)**
- El nivel sale de los hallazgos y no del promedio: tres dimensiones en
  deterioro sostenido dan PRIORITARIO aunque el puntaje quede en 0.316.
- En carga percibida, bajar es mejorar (y subir, empeorar).
- Una tendencia real pero minúscula —0.11 puntos en doce campañas— no
  cuenta como deterioro.

**Que no gaste épsilon (2 casos)**
- El informe declara 0.0.
- El paquete no puede gastar aunque quisiera: la prueba falla si aparece
  `fn_calcular_agregado`, `psycopg2` o un `SELECT` dentro del paquete.

**Matemática, una por una (15 casos)**
- Theil-Sen aguanta un valor atípico que rompe mínimos cuadrados.
- Mann-Kendall distingue tendencia de azar.
- Una serie de dos puntos da INDETERMINADA.
- Los puntos suprimidos se cuentan y no se rellenan.
- El agrupamiento es repetible con la misma semilla.
- Separa dos poblaciones claramente distintas (oficina y turno nocturno).
- La silueta prefiere grupos separados.
- La cola de Laplace es la fórmula conocida.
- Sin ruido declarado no se inventa un umbral.
- Una confianza imposible (0, 1, negativa) se rechaza.
- Un valor nulo no se toma como cero.
- Una unidad sin todas las dimensiones queda fuera y se reporta.

Y en `pruebas/test_algoritmos.py`, siete casos más sobre el endpoint: que
no gasta épsilon (comportamiento y código), que recorta al alcance del
líder, que usa caché y la puede saltar, que una campaña sin agregados
publicados no se lee como campaña sin riesgo, y que la corrida queda en
bitácora.

---

## 10. Métricas medidas

Las métricas se obtienen contra **verdad inyectada**: el generador de
datos masivos elige al azar un 5% de las unidades y les baja el
bienestar, y otro 5% y se lo hace decaer campaña a campaña, y escribe
cuáles en `public.verdad_inyectada` **antes** de que el detector corra.
Es la única forma de medir un detector: ajustarlo hasta que sus salidas
parezcan razonables no prueba nada.

**Datos**: 26 526 empleados, 136 unidades, 12 campañas, 206 231
respuestas, 1 031 155 valores de detalle. Escala de ruido media 0.0368.

| Métrica | Valor |
|---|---|
| Unidades analizadas | 110 (las 26 restantes sin perfil completo o sin convocar) |
| Grupos encontrados | 4, silueta 0.8099 |
| **Hallazgos de segmento — precisión** | **100%** (10 de 10 unidades señaladas son inyectadas) |
| **Hallazgos de segmento — exhaustividad** | **100%** (las 5 anómalas, cubiertas) |
| Deterioro, Mann-Kendall solo | precisión 26.3%, exhaustividad 100% |
| **Deterioro, con compuerta material** | **precisión 83.3%, exhaustividad 100%, F1 90.9%** |
| Ranking, top 5 | 5 de 5 inyectadas |
| Ranking, top 10 | 9 de 10 inyectadas |
| Épsilon consumido | 0.0 |
| Tiempo de ejecución | 69 ms |

La línea que más dice es la del deterioro: la compuerta material lleva la
precisión de **26.3% a 83.3% sin perder una sola detección**. Un detector
con 100% de exhaustividad y 26% de precisión no sirve para decidir nada,
porque de cada cuatro áreas que señala, tres están bien.

Las dos métricas se reportan juntas a propósito. Una sola es fácil de
falsear: un detector que señala a todas tiene exhaustividad perfecta y
precisión inútil; uno que señala solo a la peor tiene precisión perfecta y
deja pasar al resto. Y el costo de los dos errores no es igual: un falso
positivo gasta el tiempo de un especialista en un área que está bien; un
falso negativo deja sin atender a un equipo que lo necesita.

---

## 11. Limitaciones

1. **No distingue un segmento que *es* así de uno que *está* mal.** Es la
   limitación de fondo y no tiene solución estadística. Un turno nocturno
   descansa peor porque trabaja de noche; un segmento en crisis también
   está desplazado. El algoritmo mide, nombra la pregunta y la deja a una
   persona.

2. **No dice causas.** Detecta distancia y dirección. Por qué, lo averigua
   alguien hablando con el área.

3. **Las unidades pequeñas son invisibles.** Por debajo de k = 5 personas
   no hay publicación, y sin publicación no hay análisis. Es el precio de
   la garantía de privacidad y está bien pagado, pero significa que el
   algoritmo **no puede ver** a los equipos más chicos, que pueden ser los
   más vulnerables. Se reporta como `unidades_sin_perfil_completo` en
   lugar de omitirse.

4. **El umbral material es un juicio, no un teorema.** Media desviación
   estándar viene de la convención de Cohen y es defendible, no inevitable.
   Con otro valor el detector sería más o menos sensible, y conviene que el
   número esté en un solo lugar y documentado en lugar de repartido por el
   código.

5. **k ≤ 6.** Si la organización tuviera más de seis perfiles de trabajo
   realmente distintos, el agrupamiento los mezclaría. La silueta avisa
   —bajaría— pero el techo está puesto a mano.

6. **La silueta es O(n²).** Con n en cientos son milisegundos; a partir de
   unos miles habría que calcularla sobre una muestra.

7. **Doce campañas son poca historia para una tendencia.** Theil-Sen con
   doce puntos es razonable y Mann-Kendall da p fiable, pero una unidad con
   tres campañas publicadas y nueve suprimidas sale INDETERMINADA, y eso es
   lo correcto aunque no sea lo útil.

---

## 12. Tiempo de ejecución medido

| Escenario | n unidades | Tiempo |
|---|---|---|
| Datos de demostración | 13 | 4.65 ms |
| Datos masivos | 110 | 69 ms |
| Lectura desde caché Redis | 110 | < 1 ms |

El informe se cachea diez minutos. El TTL es largo a propósito: el
análisis depende solo de agregados **publicados**, y publicar es una
operación deliberada que nadie hace cada minuto. No es como el presupuesto
de épsilon, donde un dato viejo lleva a creer que queda presupuesto cuando
ya se agotó; aquí un informe de hace diez minutos describe los mismos
datos publicados.

El endpoint acepta `?sin_cache=1`, y eso **existe para poder medir**: una
medición de rendimiento tomada contra una caché caliente no mide el
algoritmo, mide Redis. La prueba de carga ejerce los dos caminos con
nombres distintos (`[cache]` y `[sin cache]`) para que la comparación salga
del mismo informe y bajo la misma carga.
