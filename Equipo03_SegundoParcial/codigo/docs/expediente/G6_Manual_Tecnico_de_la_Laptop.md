# Manual técnico — levantar el sistema en la laptop

**Expediente NEXUM — Equipo 03 · Capítulo de Gerardo Quiroga Ramírez
(#650313)**

> El manual de instalación de la máquina virtual es de Juan Pablo. Éste es
> el de la laptop: lo que hay que hacer para que el sistema corra en una
> máquina de desarrollo, y qué revisar cuando no arranca.

---

## 1. Lo que hace falta

| | |
|---|---|
| Docker Desktop | encendido |
| Python | 3.11 o más |
| Node | 20 o más, si se corren los seis servicios de Node fuera de Docker |
| Puertos libres | 8000 (portal), 8101–8124 (microservicios) |
| Espacio | ~2 GB con imágenes y datos de demostración |

---

## 2. Camino normal: Docker

```bash
cd codigo
cp .env.ejemplo .env          # y editar lo que haga falta
docker compose up -d --build
```

Levanta los 24 microservicios, el portal, PostgreSQL, MongoDB y Redis. La
base se crea y se migra sola en el arranque del contenedor de PostgreSQL.

Comprobar:

```
http://localhost:8000              el portal
http://localhost:8000/admin/servicios   el panel de estado
```

El panel debe mostrar los 24 en **Disponible**. Si alguno sale
**Degradado** o **No listo**, la columna *Dependencias* dice cuál le
falta — no hay que adivinar.

### Dos cosas del compose que importan

- **El puerto de la base NO se publica en producción.** En developer sí,
  para poder conectarse con un cliente; el archivo de producción no lo
  expone y hay una prueba que lo impide.
- **`VERSION` es obligatoria para desplegar en producción.** Sin ella, el
  panel no puede contestar «¿ya está la nueva arriba?» después de un
  despliegue.

---

## 3. Sin Docker, para la demostración

Más rápido de arrancar y más fácil de ver fallar, que es lo que se pide en
el ensayo de fallos.

```bash
# PostgreSQL y Redis locales
service postgresql start
redis-server --daemonize yes

# La base, desde cero
bash scripts/arranque_base.sh bienestar_dev --con-semilla

# Los microservicios
bash scripts/arrancar_microservicios.sh

# El portal
bash scripts/arrancar_web.sh
```

`arranque_base.sh` recorre las migraciones con un **glob ordenado**, no
con una lista escrita a mano. La lista a mano fue un error real: el guion
corría sólo la migración 001, y una base recién creada levantaba,
respondía su sonda de salud, y fallaba al primer uso con un error de tabla
inexistente. Lo que lo hacía difícil es que «levanta bien» y «funciona» no
eran lo mismo, y la sonda decía lo primero.

---

## 4. Las pruebas

```bash
python3 -m pytest pruebas/ -q
```

629 pruebas. Las que tocan los clientes necesitan los microservicios
arriba; si no escuchan, se **omiten y lo dicen**.

**No correr dos suites a la vez contra la misma base.** Comparten
`bienestar_limpio` y se pisan: produce fallos inventados que no
corresponden a ningún defecto.

Variables que usan las pruebas:

```
PG_HOST=127.0.0.1  PG_BASE=bienestar_limpio
PG_USUARIO=bienestar_app  PG_CLAVE=desarrollo_local
```

---

## 5. Cuentas de demostración

Contraseña `demo123` en todas.

| Correo | Perfil | Para qué |
|---|---|---|
| `ana.perez@nexum.com.mx` | Colaborador | la encuesta, el celular |
| `lucia.hernandez@nexum.com.mx` | Líder | el tablero de su unidad |
| `mariana.solis@nexum.com.mx` | Especialista | escritorio, evidencias, intervenciones |
| `roberto.garcia@nexum.com.mx` | Auditor | bitácora, descarga de evidencia |
| `carlos.ramirez@nexum.com.mx` | Administrador | usuarios, perfiles, panel de servicios |

Dos advertencias para el ensayo de fallos:

- **No usar `carlos.ramirez` para la prueba de cinco intentos fallidos.**
  Se bloquea 15 minutos y es la cuenta que abre el panel. Usar otro
  correo.
- `teresa.villalobos@nexum.com.mx` es el **segundo especialista**, y existe
  porque el control de cuatro ojos lo exige: con un solo especialista,
  nadie podría aprobar ninguna intervención.

---

## 6. Cuando no arranca

| Síntoma | Causa casi siempre | Qué hacer |
|---|---|---|
| El portal abre y todo sale **Caído** | los microservicios no están arriba | `arrancar_microservicios.sh`; el portal funcionando sin ellos es lo esperado |
| Un servicio en **No listo** | le falta una dependencia esencial | mirar la columna *Dependencias*: dice cuál |
| Un servicio en **Degradado** | una dependencia **opcional** caída | atiende igual; `degradado_por` dice cuál |
| `documents-service` degradado por `almacen` | la carpeta del almacén no existe o no se puede escribir | `mkdir -p` y permisos de escritura |
| Todo falla con `invalid dsn` | alguien tocó la cadena de conexión | `options` lleva comillas simples porque su valor tiene un espacio |
| `Operation not permitted` al borrar | normal | no es un fallo del sistema |
| `relation ... does not exist` | la base se creó sin migrar | `arranque_base.sh` de nuevo |
| El panel dice cero errores y hubo un incidente | se está leyendo un contador en memoria | los errores salen de `auditoria.bitacora`; si el panel no los trae, `monitoring-service` está caído y lo avisa |

---

## 7. La aplicación de escritorio

```bash
cd codigo
python apps/escritorio/app.py
```

Requiere Tkinter. Apunta a donde haga falta por variables de ambiente, una
por servicio:

```
AUTH_SERVICE_URL=https://34.41.26.94.sslip.io/auth
```

Entrar con `mariana.solis@nexum.com.mx` / `demo123`.

---

## 8. La aplicación móvil

```
Android Studio → abrir  apps/movil
variante: debug
emulador: cualquiera con API 26+
```

**La variante `debug` apunta a la laptop; la `release` apunta a los
dominios de producción.** Para la demostración en el emulador va `debug` —
con `release`, el emulador intenta resolver dominios que no existen y
parece que la aplicación está rota cuando lo que está mal es la variante.
Esa confusión está anotada en el registro de incidencias.

Entrar con `ana.perez@nexum.com.mx` / `demo123`.

---

## 9. Qué revisar antes de una demostración

1. Docker Desktop encendido.
2. `http://localhost:8000/admin/servicios` con los 24 en verde.
3. Una sesión abierta en el portal, otra en el escritorio y el emulador
   corriendo con la variante `debug`.
4. El bucket: subir una evidencia y abrir su URL firmada.
5. Tener a mano un segundo correo para los cinco intentos fallidos, que no
   sea `carlos.ramirez`.
