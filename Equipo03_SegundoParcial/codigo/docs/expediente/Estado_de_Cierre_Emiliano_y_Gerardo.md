# Estado de cierre — Emiliano y Gerardo

**Equipo 03 · Verificado punto por punto contra el documento de
instrucciones, no contra un resumen.**

---

## Resumen en una línea

**Todo lo que es código, pruebas y documentos está hecho y verificado.**
Lo que falta son **siete** cosas que necesitan la máquina virtual, Android
Studio o una grabación de pantalla, más las dos reflexiones, que cada
quien sube.

**629 pruebas · 627 pasan · 2 se omiten · cero fallos.**

Las dos omisiones son del ambiente, no del sistema: no hay Tkinter en este
intérprete y un archivo de compose no monta semilla.

---

## Emiliano Pascual Piñales Sánchez (#657657)

| Punto de la instrucción | Estado |
|---|---|
| Algoritmo complejo documentado (problema, entradas, salidas, variables, restricciones, complejidad, pseudocódigo, pruebas, métricas, limitaciones, tiempo) | ✅ |
| Conjunto grande de datos (inserción, consulta, índices, caché, **CPU, memoria**, con y sin Redis) | ✅ |
| Índices y consultas en PostgreSQL | ✅ 3 hallazgos medidos, migración 018 |
| Índices y consultas en MongoDB | ✅ 6 índices; por análisis estático, y se dice |
| Caché Redis con y sin comparación | ✅ 6.7× |
| Locust: usuarios, RPS, media, p95, p99, errores, saturación, recuperación, endpoints lentos | ✅ |
| **Explicar el corte de 20 segundos** | ✅ implementado, probado y escrito |
| Capítulos (5) | ✅ E1 a E5 |
| Láminas: datos, algoritmo, carga, resultados | ✅ 4 láminas |
| Media página de bitácora | ✅ |
| **Correr el generador en la VM y guardar la salida** | ⏳ **un comando: `bash scripts/corrida_en_la_nube.sh`** |
| **Correr Locust y guardar el CSV** | ⏳ **mismo comando** |
| **Mostrar el análisis en el portal tras esa carga** | ⏳ **mismo comando lo explica al terminar** |
| **Capturas: generador, tabla de Locust, análisis** | ⏳ **guion en `Guion_de_Capturas_y_Grabaciones.md`** |
| **Reflexión individual** | 📝 borrador listo, la sube él |

---

## Gerardo Quiroga Ramírez (#650313)

| Punto de la instrucción | Estado |
|---|---|
| Sistema web completo | ✅ |
| Aplicación móvil integrada (JSON) | ✅ protocolo verificado |
| Aplicación de escritorio integrada (XML) | ✅ |
| Bucket de Google Cloud Storage | ✅ |
| URLs firmadas para archivos privados | ✅ y comprueba que el objeto exista antes de firmar |
| Health checks (proceso, PostgreSQL, MongoDB, Redis, **bucket, tiempo, versión**) | ✅ los siete |
| Panel de monitoreo (estado, última verificación, tiempo, errores, **historial**, degradados, dependencias caídas) | ✅ los siete |
| Tres procesos de punta a punta | ✅ verificados capa por capa |
| Pruebas de fallos: servicio, Redis, MongoDB, PostgreSQL, archivos, **tiempo máximo** | ✅ las seis |
| Capítulos (7) | ✅ G1 a G7 |
| Láminas: web, móvil, escritorio, usuarios y perfiles | ✅ 4 láminas, una por tema |
| Registro de incidencias con las tres | ✅ abierto, con formato para los demás |
| Media página de bitácora | ✅ |
| Escritorio: instrucciones para abrirlo | ✅ en G6 y G7 |
| **Emulador con `ana.perez`, variante `debug`** | ⏳ **guion G-1** |
| **Grabar escritorio (Mariana, pantalla XML)** | ⏳ **guion G-2** |
| **Grabar portal (no solo login) y bandeja** | ⏳ **guion G-3** |
| **Capturas: emulador, escritorio, Swagger URL firmada, evidencias** | ⏳ **guiones G-4 a G-6** |
| **APK de Android** | ⏳ **guion G-7, con los comandos exactos** |
| **Reflexión individual** | 📝 borrador listo, la sube él |

---

## Por qué los pendientes no se pueden hacer desde aquí

No es una suposición: se probó.

| Qué se intentó | Resultado |
|---|---|
| Llegar a `https://34.41.26.94.sslip.io` | **Rechazado** por el proxy de salida (código 000) |
| `gradle wrapper` en el proyecto móvil | **403** de `plugins.gradle.org`, `repo.maven.apache.org` y `dl.google.com` |
| `gradle wrapper` en proyecto vacío | **403** de `services.gradle.org` |

El contenedor sólo alcanza registros de paquetes y GitHub. Y no hay SDK de
Android ni forma de instalarlo.

**Nota para el APK:** el proyecto móvil **no trae el wrapper de Gradle** —
sólo `gradle/wrapper/gradle-wrapper.properties`, que apunta a Gradle 8.7.
Faltan `gradlew`, `gradlew.bat` y `gradle-wrapper.jar`. Android Studio los
genera solo al abrir el proyecto; desde consola hay que correr una vez,
con red:

```
cd apps/movil
gradle wrapper --gradle-version 8.7
./gradlew assembleDebug        # el APK queda en app/build/outputs/apk/debug/
```

Conviene saberlo antes del día de la entrega, para que no sea una
sorpresa.

---

## Lo que se dejó listo para que lo pendiente sea rápido

| | |
|---|---|
| `scripts/corrida_en_la_nube.sh` | **Un comando** en la VM: generador + Locust contra los microservicios + Locust contra el portal por HTTPS. Deja todo en `informes/nube/` y al terminar escribe qué capturar |
| `pruebas/carga/locustfile_portal.py` | Perfil nuevo para medir el camino real de una persona: DNS, TLS, Caddy y portal |
| `Guion_de_Capturas_y_Grabaciones.md` | Cada captura con **su cuenta, su pantalla y qué tiene que verse** |
| `documentos/expediente/word_y_pdf/` | Los 21 capítulos también en Word y PDF, que es el formato del resto del expediente |

### Un hallazgo sobre la corrida en la nube

**Caddy sólo publica el portal:**

```
34.41.26.94.sslip.io  ->  127.0.0.1:8000
```

Los microservicios **no están expuestos**, y eso es correcto: es la misma
decisión por la que el puerto de la base no se publica. Abrirlos al mundo
para poder medirlos cambiaría la postura de seguridad del sistema para
facilitar una prueba.

Consecuencia práctica: un Locust **desde internet** contra esa URL mide el
portal, no los microservicios. Por eso hay dos corridas y las dos hacen
falta — y el guion las hace en el orden correcto sin que haya que
pensarlo:

| Corrida | Dónde | Qué mide |
|---|---|---|
| `locustfile.py` | **en la VM** | los microservicios con recursos de la nube |
| `locustfile_portal.py` | desde donde sea | el camino real del usuario, con TLS y proxy |

---

## Los 19 defectos encontrados

Ninguno era visible con los datos de demostración.

**Del algoritmo (4).** k-medias agrupaba las unidades deterioradas y
dentro de su grupo parecían normales; con ruido bajo todo salía
significativo; el nivel salía de un promedio que diluía señales fuertes; y
«empeorar» se confundía con «bajar».

**De PostgreSQL (3).** Un índice inerte por una tercera clave en el
`ORDER BY` de una vista; una subconsulta correlacionada sin índice que
recorría una tabla 1 372 veces; y el panel reteniendo un obrero 1.4 s.

**De MongoDB (6).** Seis consultas de 44 sin índice; cuatro eran
ordenamientos, que es el caso que **falla** en lugar de degradarse.

**De integración (4).** El especialista aprobaba su propio plan; un 500
con error de Python filtrado; la ruta del blob calculada dos veces; la
invariante de la jerarquía sin impedirse.

**De observabilidad y límites (6).** Sin estado del bucket en las sondas;
sin historial en el panel; sin tiempo máximo por petición; un `skip` que
escondía un servicio roto; el corte de tiempo puesto sólo en la parte
barata; y una conexión muerta a PostgreSQL reportada como 500.

**Errores de medición propios (3).** El banco medía una unidad al azar; la
medición de CPU no llegaba a la resolución del reloj; y el conteo de filas
leía estimaciones falsas.

---

## Lo que falta y NO es nuestro

| | De quién |
|---|---|
| Despliegue en GCP: bucket, cuenta de servicio, máquinas, montaje tras reinicio | Juan Pablo |
| Ensayo de fallos en la máquina virtual | Ricardo y Juan Pablo |
| Juntar video y presentación | Juan Pablo |
| Juntar las cuatro medias páginas de bitácora | Ricardo |
| Capítulos de seguridad, contratos JSON, Swagger, Redis | Ricardo |
| Portada, resumen, problema, objetivos, alcance | Juan Pablo |

**Y una advertencia de repositorio:** la rama
`cursor/tercer-parcial-juan-pablo-1881` tiene 2 servicios y ninguna carpeta
`apps/`. No es el árbol de los 24 microservicios sobre el que está todo lo
nuestro. Hay que aclarar con Juan cuál es el bueno antes de integrar.

---

## Lo que los cuatro tienen que hacer, y nadie puede hacer por otro

- Leer el sistema completo, no sólo la parte propia. Empezar por
  `Guion_del_Ensayo_de_Fallos.md` y `G1_Mapa_de_los_24_Microservicios.md`.
- Escribir y subir la reflexión individual.
- Revisar el expediente, el video y la presentación completos, también los
  capítulos de otros.
- Estar en el ensayo de fallos y poder explicar las cinco cosas.
- El día de la entrega, poder entrar al portal de la nube y al de la
  laptop.

**Dos advertencias para ese día:** no usar `carlos.ramirez` para la prueba
de cinco intentos fallidos (se bloquea 15 minutos y es la cuenta del
panel), y compilar el móvil con la variante **`debug`**, no `release`.
