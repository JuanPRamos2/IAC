# Láminas — Emiliano Pascual Piñales Sánchez (#657657)

**Tramo:** datos, algoritmo, pruebas de carga, resultados. Cuatro láminas.

Formato: lo que va **en** la lámina es poco y grande; lo que va abajo es lo
que se dice de viva voz. Una lámina llena de texto se lee y no se escucha.

---

## Lámina 1 — Los datos

### En la lámina

**EL VOLUMEN NO ES ADORNO**

| | demostración | masivos |
|---|---|---|
| Personas por unidad | 8 | 60–400 |
| Escala del ruido | 0.5 | 0.037 |
| **Umbral de detección** | **2.118 pts** | **0.30 pts** |

> Sobre una escala de 1 a 5

**206 231 respuestas · 1 031 155 valores · 26 526 personas**

### Lo que se dice

«El sistema publica datos con ruido de Laplace para proteger a las
personas. La escala del ruido baja cuando el grupo crece — es
`sensibilidad / epsilon`, y la sensibilidad es el rango dividido entre el
número de personas.

Con los datos de demostración, grupos de 8 personas, el umbral de
detección queda en 2.118 puntos sobre una escala de 1 a 5. Ninguna señal
real de bienestar laboral se mueve dos puntos. O sea: **con esos datos, un
detector perfecto y uno roto producen la misma salida — ninguna alerta.**

Por eso los datos masivos no son relleno del parcial. Son la condición
para que el algoritmo tenga algo que encontrar.»

**Si preguntan:** el generador llama a la función oficial de agregados
7 920 veces en vez de insertar directo. Es mucho más lento y produce
valores que sí pasaron por la tubería de privacidad.

---

## Lámina 2 — El algoritmo

### En la lámina

**CINCO ETAPAS**

perfiles → **agrupamiento** → desplazamiento → anomalías → tendencia →
prioridad

**k-medias++ · silueta · Theil-Sen · Mann-Kendall**

**Épsilon consumido: 0.0**

### Lo que se dice

«Lee sólo agregados ya publicados, así que **no gasta presupuesto de
privacidad y no ve a ninguna persona**. Eso está medido: cero.

El agrupamiento usa k-medias con siembra k-means++ y elige *k* por
silueta. La tendencia usa Theil-Sen, que es la mediana de las pendientes
entre todos los pares, en vez de mínimos cuadrados — porque el ruido de
Laplace tiene colas pesadas y un solo valor atípico tuerce una regresión
por mínimos cuadrados. Theil-Sen aguanta que el 29 % de los puntos estén
mal.

Y la etapa de desplazamiento existe por un defecto que encontramos
validando: **k-medias agrupó las cinco unidades deterioradas en el mismo
grupo** — para eso sirve — y dentro de su grupo las cinco parecían
normales. El motor las reportaba INFORMATIVO. El agrupamiento escondía
exactamente lo que había que encontrar. Ahora cada grupo se compara
también contra la mediana de la organización.»

**Si preguntan por qué sin numpy:** son veinte veces el tamaño de la
imagen para media docena de funciones, y así cada línea de la matemática
está escrita donde se puede leer.

---

## Lámina 3 — Las pruebas de carga

### En la lámina

**TRES CORRIDAS A LA BASURA ANTES DE LA BUENA**

34.6 % · 37.9 % · 42.0 % de error
→ medían el **limitador**, no el sistema

**La buena:**

| | |
|---|---|
| p95 | **40 ms** |
| Errores | **0.02 %** |
| Mediana de 7 a 140 usuarios | **plana en 14 ms** |

### Lo que se dice

«Esto va primero porque es el error más común al medir carga. Las tres
primeras corridas daban cuarenta por ciento de error, y ninguna hablaba
del sistema: todos los usuarios virtuales salían de la misma IP, o
compartían el mismo token, o usaban cuentas sin seudónimo.

Y un cuarto caso: la clase del colaborador llamaba endpoints que exigen un
permiso que un colaborador no tiene **y no debe tener**. Eso fabricaba un
52 % de errores. La tentación era darle el permiso para que la prueba
pasara — eso habría roto la separación de funciones del sistema para
arreglar un guion. Movimos las tareas al perfil correcto.

La lección: una corrida con 40 % de errores casi nunca significa que el
sistema falle. Casi siempre significa que el guion mide otra cosa.

Con 166 cuentas de carga, cada una con su perfil: p95 de 40 ms y la
mediana plana de 7 a 140 usuarios. Escalado lineal con latencia constante
es la definición de que no hay contención.»

---

## Lámina 4 — Resultados

### En la lámina

**LO QUE SE MIDIÓ, ANTES Y DESPUÉS**

| | antes | después |
|---|---|---|
| Camino caliente | 89 ms | **17.6 ms** |
| `/consultas/presupuesto` | 458 ms | **4.6 ms** |
| Panel de monitoreo | 1 635 ms | **2.8 ms** |

**Techo: 197 pet/s · cero errores 5xx**

**Agregados: 99 % de CPU → limitado por cómputo, no por disco**

### Lo que se dice

«Las tres mejoras tienen causa, no son afinación a ciegas.

La primera: había un índice que existía y no servía, porque el `ORDER BY`
de una vista tenía una **tercera** clave que el índice no cubría. La
consulta devolvía lo correcto, así que nada lo delataba — ordenaba 24 476
filas en cada llamada.

La segunda: una subconsulta correlacionada sin índice, que se ejecutaba
una vez por cada una de 1 372 filas de presupuesto. Invisible con datos de
demostración, donde hay 40 filas: el costo de una subconsulta correlacionada
crece con las filas de **fuera**.

Y el consumo de recursos dio la conclusión que el reloj solo no da: el
cálculo de agregados tiene el backend de PostgreSQL al **99 % de CPU**. No
espera disco. Ni un disco más rápido ni otro índice lo mejoran — la
palanca es el paralelismo, porque las llamadas son independientes entre
unidades.»

**Si preguntan por la honestidad de la medición:** se midió en un solo
contenedor con todo compartiendo CPU, así que los números de throughput
son un piso. Y encontramos tres errores de medición propios, que están
documentados — entre ellos que el banco medía una unidad al azar y dos
corridas daban 15.85 ms y 226.41 ms del mismo camino.
