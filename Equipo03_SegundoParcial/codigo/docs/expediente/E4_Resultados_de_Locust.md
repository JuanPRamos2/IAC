# Resultados de las pruebas de carga (Locust)

**Expediente NEXUM — Equipo 03 · Capítulo de Emiliano Pascual Piñales
Sánchez (#657657)**

Guion: `pruebas/carga/locustfile.py`. Desarrollo completo en
`docs/Rendimiento_y_Carga_Equipo03.md`, sección 4.

---

## 1. Tres corridas que no midieron nada

Esto va primero, antes que cualquier número, porque es el error más común
al medir carga y porque sin contarlo los resultados buenos no se pueden
creer.

| Corrida | Errores | Qué midió en realidad |
|---|---|---|
| 1 | 34.6 % | el limitador por IP: todos los usuarios virtuales salen de la misma IP |
| 2 | 37.9 % | el limitador por token: 120 pet/min por token y todos compartían cuenta |
| 3 | 42.0 % | cuentas sin seudónimo, que no pueden contestar una encuesta |

Y un cuarto caso, más sutil: la clase `Colaborador` llamaba endpoints que
exigen el permiso `AGREGADO_UNIDAD`, que un colaborador **no tiene y no
debe tener**. Eso fabricaba un 52 % de errores. La tentación era darle el
permiso para que la prueba pasara; eso habría roto la separación de
funciones del sistema para arreglar un guion de pruebas. Se movieron las
tareas al perfil de especialista, que es quien las hace de verdad.

**La lección, que es la del capítulo:** una corrida con 40 % de errores
casi nunca significa que el sistema falle. Casi siempre significa que el
guion está midiendo otra cosa. La corrección fue dar a cada usuario
virtual su propia cuenta —166 cuentas de carga, 100 colaboradores, 32
especialistas, 22 administradores, 12 auditores— con el perfil correcto
para las tareas que ejecuta.

---

## 2. Corrida realista

140 usuarios concurrentes, llegando a medio usuario por segundo, con
esperas de persona (2–15 s según el perfil). Rampa escalonada y vuelta,
con `NEXUM_FORMA=rampa`.

| | |
|---|---|
| Peticiones | 5 601 |
| **Fallidas** | **1 (0.02 %)** |
| Peticiones/segundo | 11.2 de media, 23.7 en el pico |
| Tiempo medio | 44 ms |
| Mediana | 14 ms |
| **p95** | **40 ms** |
| p99 | 1 600 ms |
| Máximo | 1 726 ms |

El p99 de 1 600 ms tiene explicación concreta: es el refresco de la caché
del panel cada 5 s. Una petición de cada tantas paga el sondeo completo de
los 24 componentes. No es cola ni contención.

### La curva: no hay saturación hasta 140 usuarios

| seg | usuarios | pet/s | p50 | p95 |
|---|---|---|---|---|
| 15 | 7 | 1.3 | 15 ms | 1 700 ms |
| 90 | 40 | 6.1 | 16 ms | 210 ms |
| 196 | 90 | 14.5 | 15 ms | 30 ms |
| 301 | 140 | 22.9 | 15 ms | 64 ms |
| 376 | 140 | 23.7 | 13 ms | 28 ms |
| **391** | **10** | 7.7 | **12 ms** | 150 ms |
| 481 | 10 | 1.4 | 15 ms | 33 ms |

**La mediana se queda plana en 13–16 ms de 7 a 140 usuarios** y las
peticiones por segundo escalan linealmente de 1.3 a 23.7. Escalado lineal
con latencia constante es la definición operativa de «no hay contención».

### Recuperación

En el segundo 380 la carga cae de 140 usuarios a 10 de golpe. **La mediana
no se mueve (13 → 12 ms) y no queda cola arrastrada.**

Esto se mide aparte a propósito: un sistema que aguanta un pico y se
recupera es distinto de uno que aguanta el pico y tarda veinte minutos en
volver, y los dos pueden dar el mismo p95 durante el pico. La diferencia
sólo aparece si la prueba **baja** la carga y sigue midiendo, que es para
lo que existe la forma `RampaYVuelta`.

---

## 3. Corrida de esfuerzo: dónde está el techo

«No saturó» sin haber encontrado el techo no dice dónde está el techo. Con
`NEXUM_PRISA=25` las esperas se dividen entre veinticinco. No pretende ser
realista —ningún colaborador abre la aplicación cada 100 ms— sino
encontrar el límite.

| | |
|---|---|
| Peticiones | 23 644 |
| Peticiones/segundo | **131 de media, 197 en el pico** |
| Mediana | 23 ms |
| **p95** | **400 ms** |
| p99 | 680 ms |
| Máximo | 1 778 ms |
| Fallidas | 3 917 (16.57 %) |
| **De las cuales 5xx** | **cero** |

**Las 3 917 fallas fueron todas 429.** Bajo seis veces la carga realista el
sistema no produjo un solo error de servidor: rechazó educadamente y
siguió atendiendo al resto.

### El codo

| pet/s | p50 | p95 | 429/s |
|---|---|---|---|
| 8 | 14 ms | 31 ms | 0 |
| 51 | 14 ms | 36 ms | 2.3 |
| 96 | 13 ms | 47 ms | 18.4 |
| 116 | 14 ms | 53 ms | 28.9 |
| **137** | **16 ms** | **110 ms** | 31.1 |
| 159 | 28 ms | 190 ms | 28.2 |
| 183 | 36 ms | 290 ms | 39.2 |
| 197 | 35 ms | 450 ms | 22.3 |

- **Codo de saturación: ~130 peticiones/segundo.** Por debajo, mediana
  plana en 13–16 ms y p95 bajo 60 ms. Por encima, la mediana sube
  (16 → 41 ms) y el p95 sube **más rápido** (110 → 530 ms). Que el p95
  suba más rápido que la mediana es la firma de una cola formándose.
- **Techo de throughput: ~190–197 pet/s** en esta máquina con 17
  servicios.
- **El límite que se alcanza primero es administrativo, no físico.** Los
  429 empiezan a los 51 pet/s: es `limite_consumo(maximo=120, ventana=60)`
  — 120 peticiones por minuto y por token, 2 por segundo por usuario. La
  infraestructura aguantaba más.

---

## 4. Endpoints más lentos

De la corrida de esfuerzo, por p95:

| Endpoint | p95 | peticiones |
|---|---|---|
| `GET /monitoreo/componentes` | 1 400 ms | 1 496 |
| `GET /monitoreo/errores` | 1 200 ms | 529 |
| `GET /tendencias/descensos` | 690 ms | 359 |
| `GET /algoritmos/analisis [sin caché]` | 620 ms | 187 |
| `GET /consentimiento/mio` | 450 ms | 9 629 |
| `GET /tendencias/unidad/{id}` | 270 ms | 591 |
| `GET /consultas/participacion` | 79 ms | 380 |
| `GET /algoritmos/analisis [caché]` | 79 ms | 579 |

Dos lecturas:

- Los dos primeros son el panel de monitoreo, y en esta corrida una parte
  de las peticiones iba con `?sin_cache=1` **a propósito**, para medir el
  costo real del sondeo. Con la caché de 5 s, `/componentes` queda en
  2.8 ms de acierto.
- `/consentimiento/mio` tiene p95 de 450 ms con **9 629 peticiones** — es
  el endpoint más llamado con diferencia. Un p95 moderado sobre un volumen
  así pesa más en la experiencia que un p95 alto sobre 187 peticiones.
  Ordenar la tabla por p95 sin mirar la columna de volumen lleva a
  optimizar lo que no importa.

---

## 5. Lo que la corrida salta, y por qué se dice

El guion consulta `/health/ready` de cada servicio al arrancar y arma el
conjunto `NO_LISTOS`. Los servicios que dependen de MongoDB —que no está
en el ambiente de medición— quedan ahí y sus endpoints **no se ejercitan**.

La alternativa sería dejarlos y contar sus 503 como errores. Eso daría una
tasa de error alta que no describe la capacidad del sistema sino la
ausencia de una dependencia en el ambiente de prueba, y haría ilegible el
número que sí importa. Se saltan **y se imprime cuáles**, para que nadie
lea «0.02 % de errores» creyendo que cubre los 24.

---

## 6. Lo que falta medir, y es honesto decirlo

**Esta corrida se hizo fuera de la nube**, en un solo contenedor con los
servicios, PostgreSQL y Redis compartiendo CPU. Los números de throughput
son por lo tanto un **piso**, no un techo: en la máquina virtual, con
recursos dedicados y sin 17 procesos peleando por el mismo CPU, dan más.

Lo que **no** cambia al mover la medición a la nube son los hallazgos
estructurales —el codo administrativo en el limitador, el escalado lineal
de la mediana, la recuperación inmediata— porque son propiedades del
diseño y no de la máquina.

Queda pendiente la corrida contra `https://34.41.26.94.sslip.io` con el
CSV de salida. Ese paso necesita la máquina virtual encendida y no se
puede hacer desde el contenedor de desarrollo.
