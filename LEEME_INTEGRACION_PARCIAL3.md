# Integración del tercer parcial — parte de Emiliano y Gerardo

**Para quien vaya a integrar esto, humano o asistente.** Léelo completo antes
de mover un archivo. Hay una incompatibilidad de arquitectura que no se
resuelve copiando carpetas, y relajar cualquiera de las reglas de la sección 5
rompe la garantía central del sistema.

---

## 1. Lo primero: esto NO se sobrepone sobre `main`

Son **dos sistemas distintos**, no dos versiones del mismo.

| | `main` de este repositorio | `Parcial3_Emiliano_Gerardo.zip` |
|---|---|---|
| Forma | Monolito Express, una sola app | 24 microservicios |
| Lenguaje | Node (`src/`) | Python y Node, según el servicio |
| Puertos | app 3000, PostgreSQL 5433 | portal 8000, servicios 8101–8124 |
| Clientes | web | web (Flask) + Android (JSON) + escritorio (XML) |
| Pruebas | `node --test tests/*.test.js` (6 archivos) | `pytest pruebas/` (629 casos) |
| Compose | `docker-compose.yml` de una app | `docker-compose.yml` de 24 servicios + `docker-compose.gcp.yml` |

**Un `cp -r` del zip sobre la raíz del repositorio pisa `docker-compose.yml`,
`package.json`, `Dockerfile` y `.env.example`, y deja el monolito sin arrancar
y el tren de microservicios a medias.** No lo hagas.

### Qué hacer en su lugar

Decidan **antes** cuál de las dos cosas es la entrega del tercer parcial:

- **Si la entrega es el sistema de microservicios** → el contenido de
  `Parcial3_Emiliano_Gerardo/codigo/` va a la raíz de una **rama nueva**, y el
  monolito se queda en `main` como está. No se mezclan.
- **Si la entrega es el monolito** → entonces el zip es anexo documental y
  **no se integra como código**. Los documentos de `documentos/` sí sirven,
  porque describen el diseño, no sólo la implementación.
- **Si son dos entregables separados** → el zip se queda tal cual, versionado
  como archivo, que es como está hoy.

Esto lo decide el equipo, no la herramienta. Lo que no se puede es mezclarlos
sin decidir.

### Aviso sobre la rama `cursor/tercer-parcial-juan-pablo-1881`

Esa rama trae **2 servicios y no tiene `apps/`**. No es el árbol sobre el que
está hecho este trabajo. **Si se mezcla con esto sin aclarar cuál es la rama
buena, se pierde una de las dos cosas.** Hay que resolverlo con Juan Pablo
antes de tocar nada.

---

## 2. Qué contiene el zip

```
Parcial3_Emiliano_Gerardo/
  LEEME_PARA_JUAN.md         resumen corto para integrar
  codigo/                    543 archivos — el árbol completo
    apps/web/                portal Flask
    apps/movil/              Android (Kotlin + Compose)
    apps/escritorio/         Tkinter, habla XML
    apps/microservicios/     los 24 servicios + librería común
    db/migraciones/          018, 019, 020 incluidas
    db/semilla/
    pruebas/                 629 casos
    scripts/                 generador, banco de rendimiento, corrida de la VM
    contratos/               XSD y OpenAPI, compartidos por servicios y pruebas
    docker-compose.yml
    docker-compose.gcp.yml
  documentos/                22 documentos en .md, .docx y .pdf
    expediente/
      E1..E5                 parte de Emiliano
      G1..G7                 parte de Gerardo
      Registro_de_Incidencias.md
      Estado_de_Cierre_…md
```

Estado de las pruebas al cerrar: **629 · 627 pasan · 2 se omiten · cero
fallos.** Las dos omitidas son del ambiente (Tkinter ausente del intérprete;
el compose de prueba no monta semilla), no del código.

---

## 3. Lo único que falta, y por qué no se pudo hacer desde fuera

**Una corrida en la máquina virtual.** Un comando, dentro de la VM, en la
carpeta del código:

```bash
pip install locust psycopg2-binary          # si faltan
PG_BASE=bienestar bash scripts/corrida_en_la_nube.sh
```

Tarda **varios minutos**. El cálculo de agregados es el 98 % del tiempo y va
limitado por CPU: es la tubería de privacidad, no el disco. Al terminar deja
todo en `informes/nube/` y escribe en pantalla qué capturar.

No se hizo desde fuera porque **dos de las tres partes son imposibles de hacer
desde internet, y no por descuido sino porque el sistema está bien cerrado**:

- El generador escribe en PostgreSQL y **el puerto de la base no se publica**.
  Es la misma regla que impide exponer la base en producción.
- El Locust de microservicios entra por `auth-service` y pega a
  `queries-service` y `algorithms-service`; **Caddy sólo publica el portal**
  (`34.41.26.94.sslip.io` → `127.0.0.1:8000`). Abrir los veinticuatro al mundo
  para poder medirlos sería cambiar la postura de seguridad del sistema para
  facilitar una prueba.

La tercera —el portal por HTTPS— sí sale a internet, y es la que mide lo que
vive una persona: DNS, TLS, proxy inverso y portal. Por eso se corre contra la
URL pública aunque se esté en la misma máquina: pasar por `localhost` se
saltaría justo lo que se quiere medir.

### Por qué esta corrida no es opcional

El ruido de Laplace **sólo es demostrable con volumen**. La escala es
`sensibilidad / epsilon`, con `sensibilidad = (hi − lo) / n`:

| n | b | umbral detectable |
|---|---|---|
| 8 (demo) | 0.5 | **2.118 puntos** — nada es detectable |
| 60–400 (masivo) | ≈0.0368 | **≈0.30** |

Con los datos de demostración, el algoritmo no se puede enseñar funcionando.
**El volumen es la precondición para que el algoritmo sea demostrable**, no un
extra.

### Qué hay que devolverle a Emiliano

La carpeta **`informes/nube/` completa**. Las capturas de esa corrida cuentan
para su parte del parcial:

1. La salida del generador (bloques RESUMEN y CONSUMO DE RECURSOS)
2. La tabla de Locust (`microservicios.html` y `portal.html`)
3. La pantalla de **Análisis** del portal **después** de la carga, con las
   unidades priorizadas — el algoritmo corriendo sobre datos masivos, no sobre
   los de demostración

---

## 4. Un pendiente que es de la VM, no del código

**INC-002: el bucket de evidencias no está montado en la VM.**

`documents-service` va a salir **`degradado`** con `almacen: falla` hasta que
se remonte. El servicio sigue contestando —por eso es `degradado` y no
`no_listo`—, pero no puede guardar archivos.

Detalle en `documentos/expediente/Registro_de_Incidencias.md`.

> Si el volumen ya existe con dueño `root`, reconstruir la imagen **no lo
> arregla solo**: Docker fija el dueño al **crear** el volumen. Esto lo
> corrige sin perder nada:
> ```bash
> docker compose run --rm --user root --entrypoint sh documents-service \
>   -c "chown -R servicio:servicio /var/lib/bienestar/evidencias"
> docker compose restart documents-service
> ```

---

## 5. Reglas que NO se pueden relajar al integrar

Si una de estas estorba, el arreglo es cambiar el código que la rompe, no la
regla. Son la garantía central del sistema: que participar no se pueda
rastrear hasta la persona.

- `bienestar_app` **nunca** tiene SELECT sobre `autoreporte.respuesta` ni
  sobre `consentimiento.seudonimo`. El acceso va por funciones
  SECURITY DEFINER o por las vistas permitidas.
- A MongoDB **nunca** llega `empleado_id` ni ningún identificador directo de
  persona. Lo comprueba `verificar_sin_identidad` en el servicio, y el
  validador de la colección como última barrera.
- **El k mínimo es 5, y va ANTES del ruido**, no después.
  `agregado.fn_calcular_agregado_protegido` es el único camino que aplica
  recorte → comprobación de k → ruido de Laplace → contabilidad de epsilon, en
  ese orden. Un agregado calculado por fuera de esa función se salta las tres.
- El invariante de jerarquía existe por el **ataque de diferencia**: restarle a
  un padre los hijos conocidos aísla un residuo bajo k.
- El compose de producción **no publica el puerto de la base**, y `VERSION` es
  obligatoria para desplegar.
- Ningún servicio se conecta a PostgreSQL como superusuario.
- `integration-service` **no** lee el socket de Docker (equivale a root en el
  anfitrión).
- Los `.env` reales, llaves y certificados están en `.gitignore`; sólo se
  versionan los `.ejemplo`. **`signer.json` no se comparte ni se versiona.**
- `scripts/cuentas_de_carga.sql` crea 166 cuentas con contraseña conocida para
  que el Locust pueda autenticarse. **No lo muevas a `db/migraciones/` ni a
  `db/semilla/`**: ahí se aplicaría solo en cualquier despliegue, producción
  incluida. Se corre explícitamente y sólo para medir; el guion de la corrida
  ya lo hace.
- **No uses `carlos.ramirez` para la prueba de cinco intentos fallidos**: se
  bloquea 15 minutos y es la cuenta que abre el panel de servicios.

---

## 6. Tres defectos que se corrigieron, y que vale la pena conocer

Los tres estaban **callados**: ninguna prueba fallaba y la interfaz no se
quejaba. Si al integrar aparece algo parecido, aquí está el patrón.

### 6.1 El almacén de evidencias no se podía escribir

`documents-service` corre como usuario `servicio`, no como root. Cuando Docker
monta un volumen con nombre sobre una ruta que **no existe en la imagen**, la
crea propiedad de root con 0755: el proceso no podía escribir en su propio
almacén.

El síntoma era mudo hasta que existió la sonda del bucket: el servicio
contestaba «listo», aceptaba una carga, calculaba el hash, escribía los
metadatos en MongoDB y fallaba al escribir el archivo — **dejando un documento
registrado cuyo archivo no existe**.

Arreglo: el punto de montaje se crea en el Dockerfile **y con dueño**, antes de
`USER servicio`, para que Docker copie esos permisos al inicializar el volumen.
→ `apps/microservicios/documents-service/Dockerfile`

### 6.2 Una evidencia se cargaba y no se podía volver a encontrar

Dos desajustes de contrato entre el portal y `documents-service`:

| | el portal pedía | el servicio usa |
|---|---|---|
| tipo | `REPORTE_ORGANIZACIONAL` | `EVIDENCIA_ARCHIVO` |
| clave de la lista | `elementos` | `documentos` |

**Ninguno de los dos levanta un error.** `.get("elementos", [])` sobre un sobre
que trae `documentos` devuelve `[]` sin quejarse, y filtrar por un tipo que no
existe devuelve cero resultados, que es una respuesta válida. La pantalla decía
«No hay evidencias registradas todavía» justo después de cargar una con éxito:
**afirmaba que el trabajo no existe**.

Tampoco lo veían las pruebas que había, porque bajaban el archivo **por su
sello** y esa ruta no pasa por el listado.

Arreglo: `apps/web/app/rutas/evidencias.py`, más
`pruebas/test_la_evidencia_se_vuelve_a_encontrar.py`, que recorre el camino
completo —cargar, listar, encontrar— y que **lee del código del portal** el
tipo y la clave en lugar de repetirlos, para que cambiar uno de los dos lados
rompa la prueba en vez de vaciar la pantalla.

### 6.3 La encuesta nunca se pudo enviar desde el teléfono

La app mandaba `respuestas` como arreglo de `{reactivo_id, valor}`. El servicio
espera `valores` como objeto `{reactivo_id: valor}` y contestaba
`PARAMETRO_INVALIDO`. Entraba, cargaba los reactivos, dejaba contestar las
cinco preguntas y fallaba en el último paso.

**Mandó el servicio, no la aplicación**, porque la forma del cuerpo es parte
del contrato publicado y el portal y `main-process-service` ya la usan así
(`Object.keys(d.valores)`). Ninguna prueba del lado móvil lo habría encontrado:
el JSON que armaba era válido.

Junto con ese salieron otros tres de Android, todos compilando y corriendo la
app de verdad: faltaba `@mipmap/ic_launcher`, `ErrorApi(mensaje = …)` donde el
parámetro es `message`, y `CardDefaults.buttonColors()` donde va
`ButtonDefaults`. **Los tres impedían compilar.**

---

## 7. Tres 403 de administrador que se dejaron a propósito

El administrador **no** puede generar reportes de bienestar, tocar evidencia de
intervención ni aprobar intervenciones.

Si al integrar aparecen como pruebas en rojo, **no se arreglan dando
permisos**: eso rompería la separación de funciones, que es un requisito del
proyecto. Lo que se corrigió fueron los actores de cada proceso. Un
administrador que puede aprobar la intervención que él mismo propuso no es un
administrador, es un agujero.

---

## 8. Dónde está el razonamiento

Cada documento del expediente dice **por qué** está hecho así, no sólo qué
hace. Si algo no cuadra al integrarlo, ahí está el argumento para discutirlo en
vez de adivinar:

- `E2_Reglas_de_k_Minimo_y_Ruido.md` — por qué k va antes del ruido, y el
  ataque de diferencia
- `E3_Algoritmos.md` — k-means++ y silueta, Theil-Sen y Mann-Kendall, y por qué
  Theil-Sen (29 % de punto de ruptura) frente a una regresión por mínimos
  cuadrados, dado que Laplace tiene colas pesadas
- `G2_Monitoreo.md` — los tres estados de la sonda, los siete elementos, y por
  qué el panel lee el estado del **cuerpo** y no del código HTTP
- `G5_Diseno_del_Bucket_Servicio.md` — por qué la sonda del bucket hace una
  llamada real al sistema de archivos y no un `isdir`
- `E5_Resultados_de_Rendimiento.md` — por qué las mediciones son deterministas
  y no sobre una unidad al azar (dos corridas de la misma base dieron 15.85 ms
  y 226.41 ms para la misma consulta)
