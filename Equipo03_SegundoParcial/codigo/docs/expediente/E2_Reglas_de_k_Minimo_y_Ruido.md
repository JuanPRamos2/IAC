# Las reglas de *k* mínimo 5 y el ruido

**Expediente NEXUM — Equipo 03 · Capítulo de Emiliano Pascual Piñales
Sánchez (#657657)**

---

## 1. El problema que estas dos reglas resuelven

El sistema publica cómo está el bienestar de cada unidad. Nadie debe poder
deducir cómo contestó una persona concreta.

Esas dos frases parecen compatibles y no lo son. Un promedio de un grupo
chico delata; un promedio de un grupo grande consultado muchas veces
también. Las dos reglas atacan ataques distintos, y hace falta cumplir las
dos: **cualquiera de ellas sola deja abierto el ataque de la otra.**

| Regla | Qué ataque corta |
|---|---|
| *k* mínimo 5 | el grupo es tan chico que el promedio *es* la persona |
| Ruido de Laplace | el grupo es grande, pero la diferencia entre dos consultas aísla a una persona |

---

## 2. *k* mínimo = 5

### La regla

Ningún agregado se publica si el grupo tiene menos de **5** personas con
consentimiento vigente. Si no llega, la fila se guarda con
`estado_publicacion = 'SUPRIMIDO'`.

### Por qué se guarda la supresión en lugar de no escribir nada

Si un grupo bajo *k* simplemente no produjera fila, el tablero mostraría
un hueco — y un hueco es indistinguible de «la campaña todavía no cierra»
o «esa unidad no fue convocada». Quien opera no sabría si falta un dato o
si está protegido.

Guardar `SUPRIMIDO` convierte el silencio en una afirmación: *aquí hay un
grupo, y no se publica porque es chico*. Eso se puede explicar a quien
pregunte, y se puede auditar.

### Por qué 5 y no 3

Con *k* = 3, basta que dos personas del grupo comparen sus respuestas
entre ellas para despejar la tercera. Con 5 hacen falta cuatro cómplices,
y en ese punto el ataque deja de ser práctico dentro de un equipo de
trabajo. No es un número mágico; es el punto donde el esfuerzo del ataque
supera al valor de lo que obtiene.

### El ataque que *k* solo no detiene

Supongamos una dirección de 40 personas con tres equipos de 20, 15 y 5.
Los tres pasan *k*. Y sin embargo:

```
promedio(dirección) × 40  −  promedio(equipo A) × 20  −  promedio(equipo B) × 15
= suma del equipo C (5 personas)
```

Nada de eso viola *k*. Todas las consultas son legítimas. Y si el equipo C
tuviera 3 personas en lugar de 5, el residuo sería un grupo sub-*k*
obtenido **sin consultarlo nunca**.

De ahí el control de inferencia en `queries-service`, y de ahí que la
invariante de la jerarquía —el padre nunca declara menos plantilla que la
suma de sus hijas— tenga un disparador que la impide. Con el padre
declarando de menos, el residuo calculado sale negativo, la condición
nunca se cumple, y el control queda presente y **sin efecto**.

---

## 3. El ruido de Laplace

### La fórmula

```
escala (b) = sensibilidad / epsilon
sensibilidad = (hi − lo) / n
valor_publicado = valor_real + Laplace(0, b)
```

- `hi − lo` es el rango de la escala de respuesta (1 a 5 → 4).
- `n` es el número de personas del grupo.
- `epsilon` es el presupuesto de privacidad que se gasta en esa consulta.

### Qué significa la sensibilidad

Es *cuánto puede mover el resultado una sola persona*. En un promedio de
`n` personas sobre una escala de rango 4, una persona que cambie su
respuesta de 1 a 5 mueve el promedio en `4/n`. El ruido tiene que ser
proporcional a eso: si fuera menor, la diferencia entre «con esa persona»
y «sin esa persona» seguiría siendo visible.

### La consecuencia que define todo el proyecto

La escala del ruido **baja cuando el grupo crece**. Y eso es exactamente
lo que hace que el algoritmo sea demostrable o no:

| | demostración | datos masivos |
|---|---|---|
| Personas por unidad | 8 | 60 a 400 |
| Escala del ruido *b* | 0.5 | 0.0368 |
| Umbral de detección al 95 % | **2.118 puntos** | **≈ 0.30 puntos** |

Sobre una escala de 1 a 5, un umbral de 2.118 puntos significa que **nada
es detectable**: ninguna señal real de bienestar laboral se mueve dos
puntos. Con los datos de demostración, un detector perfecto y uno roto
producen la misma salida — ninguna alerta.

Por eso los datos masivos no son un adorno del parcial. **Son la condición
para que el algoritmo tenga algo que encontrar**, y por eso el generador
inyecta la señal y la anota: para poder medir si la encontró.

### Por qué Laplace y no una gaussiana

Laplace es la distribución que da privacidad diferencial *pura* (ε, 0)
para una consulta de sensibilidad acotada. Una gaussiana da (ε, δ), es
decir, deja una probabilidad δ de que la garantía no se cumpla. Para
publicar datos de bienestar laboral de personas identificables dentro de
su propia empresa, una garantía con letra chica no es lo que se quiere.

Tiene un costo, y el capítulo de algoritmos lo paga: **Laplace tiene colas
pesadas.** Un valor atípico es mucho más probable que con una gaussiana, y
por eso la tendencia se ajusta con Theil-Sen —mediana de pendientes, 29 %
de punto de ruptura— en vez de mínimos cuadrados, que un solo atípico
tuerce.

---

## 4. El recorte, que va antes

Antes de promediar, cada respuesta se acota al rango válido. Sin esto, un
valor fuera de rango —por un error de captura o a propósito— mueve el
promedio más de lo que la sensibilidad asume, y el ruido calculado deja de
ser suficiente para la garantía.

**El orden es parte de la garantía:** recortar después de promediar no
acota la influencia de nadie, porque el promedio ya la absorbió.

---

## 5. La contabilidad del épsilon

El ruido no protege si se puede pedir mil veces. Promediar mil lecturas
ruidosas del mismo valor real cancela el ruido y deja el valor.

Dos defensas, y hacen falta las dos:

1. **El agregado se materializa.** La fila se calcula una vez y se guarda
   con su ruido. Leerla cien veces devuelve cien veces el mismo número,
   no cien muestras independientes. Esto es lo que vuelve inútil el ataque
   por repetición desde la lectura.
2. **El presupuesto.** Cada *cálculo* anota su épsilon en
   `agregado.consulta_privada` contra un `presupuesto_privacidad` por
   unidad y ventana. Agotado el presupuesto, la función deja de contestar.

El presupuesto es lo que convierte «le ponemos ruido» en privacidad
diferencial de verdad: sin él, recalcular es gratis y el ruido se cancela.

---

## 6. Dónde vive cada regla, y por qué ahí

Todo esto está en **una sola función de base de datos**:

```
agregado.fn_calcular_agregado_protegido(campania, unidad, dimension, actor)
```

No hay otro camino que produzca una fila de `resultado_protegido`.

El motivo de concentrarlo ahí y no en el servicio: si la regla viviera en
el código de un microservicio, cualquier otro servicio —o un script, o una
consulta manual— podría escribir en la tabla sin pasar por ella. Siendo la
única puerta, la propiedad se sostiene aunque alguien escriba código
nuevo sin saber de estas reglas.

Lo mismo con el acceso: el rol de aplicación `bienestar_app` **no tiene
SELECT** sobre `autoreporte.respuesta` ni sobre
`consentimiento.seudonimo`. Llega a los datos sólo por funciones
`SECURITY DEFINER` y por vistas permitidas. Es decir: aunque el código de
un servicio quisiera leer respuestas individuales, la base no se lo
permite.

---

## 7. Lo que estas reglas le cuestan al sistema

Se documenta porque un capítulo que sólo dice lo que se ganó no sirve para
decidir.

| Costo | Magnitud |
|---|---|
| Unidades que no se pueden reportar | las de menos de 5 personas con consentimiento |
| Incertidumbre del valor publicado | ±0.30 puntos con datos masivos; ±2.1 con grupos de 8 |
| Consultas que se rechazan | las que agotan el presupuesto de su ventana |
| Tiempo del cálculo | 17.6 ms por agregado, limitado por CPU |
| Lo que el algoritmo **no** puede hacer | seguir a una persona en el tiempo, comparar dos personas, explicar un caso individual |

Esa última línea no es una limitación técnica que se pueda levantar más
adelante. Es el punto del diseño.
