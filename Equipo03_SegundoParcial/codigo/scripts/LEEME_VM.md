# Corrida en la máquina virtual — paquete mínimo

Seis archivos. **No reemplaza el despliegue**: son los guiones de medición
actualizados y el SQL de las cuentas de carga. Nada de esto toca los
microservicios que están corriendo.

```
scripts/corrida_en_la_nube.sh     el comando único
scripts/datos_masivos.py          generador, ahora con consumo de recursos
scripts/cuentas_de_carga.sql      las 166 cuentas que el Locust necesita
scripts/rendimiento.py            banco de consultas, por si quieres medir la base
pruebas/carga/locustfile.py       Locust de microservicios
pruebas/carga/locustfile_portal.py  Locust del portal por HTTPS
```

---

## 1. Subirlo a la VM

Desde tu laptop, en la carpeta donde descomprimiste esto:

```bash
gcloud compute scp --recurse nexum_corrida \
    NOMBRE_DE_LA_VM:~/ --zone ZONA
```

Si usan ssh normal en vez de gcloud:

```bash
scp -r nexum_corrida USUARIO@34.41.26.94:~/
```

> `NOMBRE_DE_LA_VM` y `ZONA` los sabe Juan. Si no, `gcloud compute instances list`
> te los dice.

## 2. Entrar a la VM

```bash
gcloud compute ssh NOMBRE_DE_LA_VM --zone ZONA
# o
ssh USUARIO@34.41.26.94
```

## 3. Poner los archivos donde está el código

Primero encuentra la carpeta del proyecto:

```bash
ls ~; ls /opt; ls /srv 2>/dev/null
# busca la que tenga apps/ db/ scripts/
```

Llámala `$PROYECTO` y copia encima:

```bash
PROYECTO=~/nexum          # <-- ajusta a la real
cp -r ~/nexum_corrida/scripts/*        "$PROYECTO/scripts/"
cp -r ~/nexum_corrida/pruebas/carga/*  "$PROYECTO/pruebas/carga/"
chmod +x "$PROYECTO/scripts/corrida_en_la_nube.sh"
```

> Si el sistema corre en contenedores, igual se copia en el **host**: los
> guiones hablan con PostgreSQL y con los puertos por red, no viven dentro
> de un contenedor.

## 4. Lo que hace falta instalado

```bash
pip install locust psycopg2-binary
```

## 5. Correrlo

```bash
cd "$PROYECTO"
PG_BASE=bienestar bash scripts/corrida_en_la_nube.sh
```

Si la base se llama distinto, cambia `PG_BASE`. Para saberlo:

```bash
psql -l
```

Tarda **varios minutos** — el cálculo de agregados es el 98 % del tiempo y
va limitado por CPU. Al terminar deja todo en `informes/nube/` y escribe
en pantalla qué capturar.

## 6. Bajar los resultados

```bash
# desde tu laptop
gcloud compute scp --recurse NOMBRE_DE_LA_VM:~/nexum/informes/nube ./ --zone ZONA
```

---

## Si algo falla

| Síntoma | Qué pasa |
|---|---|
| `FALTA: locust` | el paso 4 |
| `psql: FATAL: ... authentication failed` | el usuario de la terminal no es el de la base. Prueba `sudo -u postgres bash scripts/corrida_en_la_nube.sh` o exporta `PGUSER`/`PGPASSWORD` |
| `no contesta .../salud` | Caddy o el portal están abajo. Las partes 1 y 2 corren igual; la 3 no |
| Locust con muchísimos errores | casi seguro son las cuentas de carga. El guion las crea solo; si el `psql` del paso 0 falló, lo dice y se detiene |
| `relation "usuarios.usuario" does not exist` | `PG_BASE` apunta a la base equivocada |

**No uses `carlos.ramirez` para la prueba de cinco intentos fallidos** del
ensayo: se bloquea 15 minutos y es la cuenta que abre el panel.

---

## Por qué son dos corridas de Locust

Caddy publica **sólo el portal**:

```
34.41.26.94.sslip.io  ->  127.0.0.1:8000
```

Los microservicios no están expuestos a internet, y está bien que así sea
— es la misma regla por la que el puerto de la base no se publica. Así
que:

| Corrida | Dónde corre | Qué mide |
|---|---|---|
| `locustfile.py` | **dentro de la VM** | los microservicios con recursos de la nube |
| `locustfile_portal.py` | sale a internet | el camino real de una persona: DNS, TLS, Caddy, portal |

Las dos hacen falta y el guion las hace en orden.
