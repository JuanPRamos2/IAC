# Entrega de Emiliano (Integrante 3) y Gerardo (Integrante 4)

Juan: esto es lo que nos tocaba a nosotros dos, listo para integrar. Abajo
está qué cambió, qué ya está comprobado, y **la única cosa que falta y que
sólo se puede hacer en la máquina virtual**.

---

## 1. Lo que falta, y por qué no lo pudimos hacer nosotros

**Una sola cosa: la corrida de datos masivos y de carga en la VM.**

No es que se nos haya olvidado. Son dos cosas que, por diseño, no se
pueden hacer desde fuera de la máquina:

- El generador escribe en PostgreSQL, y **el puerto de la base no se
  publica**. Es la misma regla que impide exponer la base en producción.
- El Locust de microservicios entra por `auth-service` y pega a
  `queries-service` y `algorithms-service`, y **Caddy sólo publica el
  portal** (`34.41.26.94.sslip.io` → `127.0.0.1:8000`). Abrir los
  veinticuatro al mundo para poder medirlos sería cambiar la postura de
  seguridad del sistema para facilitar una prueba.

Está todo en un solo comando. Dentro de la VM, en la carpeta del código:

```bash
pip install locust psycopg2-binary          # si no están
PG_BASE=bienestar bash scripts/corrida_en_la_nube.sh
```

Tarda **varios minutos** (el cálculo de agregados es el 98 % del tiempo y
va limitado por CPU: es la tubería de privacidad, no el disco). Al
terminar deja todo en `informes/nube/` y escribe en pantalla qué capturar.

Detalle completo en `scripts/LEEME_VM.md`, incluido qué hacer si psql
pide usuario o si falta Locust.

> **No uses `carlos.ramirez` para la prueba de cinco intentos fallidos**:
> se bloquea 15 minutos y es la cuenta que abre el panel de servicios.

---

## 2. Un pendiente que es tuyo, no nuestro

**INC-002: el bucket de evidencias no está montado en la VM.**

En la laptop lo dejamos funcionando y la sonda lo reporta `ok`. En la VM,
`documents-service` va a salir **`degradado`** con `almacen: falla` hasta
que se remonte el bucket. El servicio sigue contestando —por eso es
`degradado` y no `no_listo`—, pero no puede guardar archivos.

Está anotado en `docs/expediente/Registro_de_Incidencias.md`.

---

## 3. Tres defectos que encontramos ejecutando, no leyendo

Los tres estaban callados: ninguna prueba fallaba y la pantalla no se
quejaba. Vale la pena que los conozcas porque dos son de piezas que tocan
tu parte.

### 3.1 El almacén de evidencias no se podía escribir

`documents-service` corre como usuario `servicio`, no como root. Cuando
Docker monta un volumen con nombre sobre una ruta que **no existe en la
imagen**, la crea propiedad de root con 0755: el proceso no podía escribir
en su propio almacén.

El síntoma era mudo hasta que la sonda del bucket existió: el servicio
contestaba «listo», aceptaba una carga, calculaba el hash, escribía los
metadatos en MongoDB y fallaba al escribir el archivo — dejando un
documento registrado cuyo archivo no existe.

**Arreglo:** el punto de montaje se crea en el Dockerfile y con dueño,
antes de `USER servicio`, para que Docker copie esos permisos al
inicializar el volumen.
→ `apps/microservicios/documents-service/Dockerfile`

> Si la VM ya tiene el volumen creado con dueño root, reconstruir la
> imagen no lo arregla solo: Docker fija el dueño al **crear** el
> volumen. Un `docker compose run --rm --user root --entrypoint sh
> documents-service -c "chown -R servicio:servicio /var/lib/bienestar/evidencias"`
> lo corrige sin perder nada.

### 3.2 Una evidencia se cargaba y no se podía volver a encontrar

Dos desajustes entre el portal y `documents-service`:

| | el portal pedía | el servicio usa |
|---|---|---|
| tipo | `REPORTE_ORGANIZACIONAL` | `EVIDENCIA_ARCHIVO` |
| clave de la lista | `elementos` | `documentos` |

Ninguno de los dos levanta un error. `.get("elementos", [])` sobre un
sobre que trae `documentos` devuelve `[]` sin quejarse, y filtrar por un
tipo que no existe devuelve cero resultados, que es una respuesta
perfectamente válida. La pantalla decía **«No hay evidencias registradas
todavía»** justo después de cargar una con éxito: afirmaba que el trabajo
no existe.

Tampoco se veía en las pruebas que ya había, porque bajaban el archivo
**por su sello** y esa ruta no pasa por el listado.

**Arreglo:** `apps/web/app/rutas/evidencias.py`, y pruebas nuevas en
`pruebas/test_la_evidencia_se_vuelve_a_encontrar.py` que recorren el
camino completo —cargar, listar, encontrar— y que **leen del código del
portal** el tipo y la clave en lugar de repetirlos, para que cambiar uno
de los dos lados rompa la prueba en vez de vaciar la pantalla.

### 3.3 Cuatro defectos de la aplicación móvil

Salieron compilándola y corriéndola de verdad contra los servicios:

1. Faltaba `@mipmap/ic_launcher` — no compilaba (icono adaptativo, minSdk 26).
2. `ErrorApi(mensaje = …)` donde el parámetro es `message` — no compilaba.
3. `CardDefaults.buttonColors()` donde va `ButtonDefaults` — no compilaba.
4. **La encuesta nunca se pudo enviar desde el teléfono.** Mandaba
   `respuestas` como arreglo de `{reactivo_id, valor}`; el servicio espera
   `valores` como objeto `{reactivo_id: valor}` y contestaba
   `PARAMETRO_INVALIDO`. Entraba, cargaba los reactivos, dejaba contestar
   las cinco y fallaba en el último paso.

El cuarto es el que importa para el contrato: **mandó el servicio, no la
aplicación**, porque la forma del cuerpo es parte del contrato publicado y
el portal y `main-process-service` ya la usan así (`Object.keys(d.valores)`).
Ninguna prueba del lado móvil lo habría encontrado, porque el JSON que
armaba era válido.

---

## 4. Lo que hay que saber antes de integrar

### La rama no coincide con este árbol

`cursor/tercer-parcial-juan-pablo-1881` trae **2 servicios y no tiene
`apps/`**. Este trabajo está sobre el árbol completo de 24 servicios con
`apps/web`, `apps/movil` y `apps/escritorio`. **Hay que aclarar cuál es la
rama buena antes de mezclar**, o se pierde una de las dos cosas.

### Archivos que NO van a migraciones ni a semilla

`scripts/cuentas_de_carga.sql` crea 166 cuentas con contraseña conocida
para que el Locust pueda autenticarse. **No lo muevas a `db/migraciones/`
ni a `db/semilla/`**: ahí se aplicaría solo en cualquier despliegue,
producción incluida. Se corre explícitamente y sólo para medir — el guion
de la corrida ya lo hace.

### Reglas que no se pueden relajar al integrar

- `bienestar_app` **nunca** debe tener SELECT sobre `autoreporte.respuesta`
  ni `consentimiento.seudonimo`. El acceso va por funciones SECURITY
  DEFINER o por las vistas permitidas.
- A MongoDB **nunca** llega `empleado_id` ni ningún identificador directo
  de persona (`verificar_sin_identidad`, y el validador de la colección
  como última barrera).
- El compose de producción **no publica el puerto de la base**, y `VERSION`
  es obligatoria para desplegar.
- Ningún servicio se conecta a PostgreSQL como superusuario.
- `integration-service` **no** lee el socket de Docker (equivale a root en
  el anfitrión).
- Los `.env` reales, llaves y certificados están en `.gitignore`; sólo se
  versionan los `.ejemplo`. `signer.json` no se comparte ni se versiona.

---

## 5. Estado

- Suite completa: ver `docs/expediente/Estado_de_Cierre_Emiliano_y_Gerardo.md`
  para la cifra exacta y qué cubre cada archivo.
- Migraciones 018, 019 y 020 comprobadas desde cero con datos de semilla:
  7 índices, acción de auditoría, columna, 2 aprobadores, disparador, y
  **0 violaciones del invariante de jerarquía**.
- Hay una prueba que falla si un documento del expediente declara un
  número de pruebas o de casos que ya no es cierto. Se cachó a sí misma
  una vez (618 → 625), por eso existe.

### Tres 403 de administrador que dejamos a propósito

El administrador **no** puede generar reportes de bienestar, tocar
evidencia de intervención ni aprobar intervenciones. Darle esos permisos
para que las pruebas pasaran habría roto la separación de funciones; lo
que se corrigió fueron los actores de cada proceso, no los permisos.

---

## 6. Dónde está cada cosa

```
docs/expediente/
  E1..E5                  lo de Emiliano  (agregados, k mínimo y ruido,
                          algoritmos, Locust, rendimiento)
  G1..G7                  lo de Gerardo   (mapa de los 24 servicios,
                          monitoreo, MongoDB, contratos XML del
                          escritorio, bucket, manual técnico, manual
                          de usuario)
  Bitacora_…              qué se hizo y cuándo
  Registro_de_Incidencias qué se rompió y cómo se cerró (INC-002 es
                          el que sigue abierto, y es de la VM)
  Guion_del_Ensayo_de_Fallos      cómo se tiran los servicios a propósito
  Guion_de_Capturas_y_Grabaciones qué capturar y en qué orden
  Laminas_Emiliano / Laminas_Gerardo   para la presentación
  Reflexion_Emiliano / Reflexion_Gerardo
  Estado_de_Cierre_…      el resumen de todo

scripts/
  corrida_en_la_nube.sh   el comando único de la VM
  LEEME_VM.md             cómo subirlo y correrlo, y qué hacer si falla
  datos_masivos.py        el generador
  rendimiento.py          el banco de consultas
  cuentas_de_carga.sql    las 166 cuentas (NO va a migraciones)

pruebas/carga/
  locustfile.py           microservicios, se corre DENTRO de la VM
  locustfile_portal.py    portal por HTTPS, sale a internet
```

Cada documento dice **por qué** está hecho así, no sólo qué hace. Si algo
no cuadra al integrarlo, ahí está el razonamiento para discutirlo.
