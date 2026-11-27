#!/usr/bin/env bash
# ============================================================================
# Las tres corridas que faltan del tercer parcial, en un solo comando.
#
#   1. Generador de datos masivos        -> informes/nube/generador.txt
#   2. Locust contra los microservicios  -> informes/nube/microservicios_*.csv
#   3. Locust contra el portal público   -> informes/nube/portal_*.csv
#
# CÓMO SE USA
# -----------
#   En la máquina virtual, dentro de la carpeta del código:
#
#       bash scripts/corrida_en_la_nube.sh
#
#   Al terminar deja todo en `informes/nube/` y escribe en pantalla qué
#   capturar y en qué orden.
#
# POR QUÉ ESTE GUION CORRE EN LA MÁQUINA VIRTUAL Y NO DESDE FUERA
# ---------------------------------------------------------------
# Dos de las tres cosas no se pueden hacer desde internet, y no por un
# descuido sino porque el sistema está bien cerrado:
#
#   - El generador escribe en PostgreSQL, y **el puerto de la base no se
#     publica**. Es la misma regla que impide exponer la base en
#     producción.
#   - El Locust de microservicios entra por `auth-service` y pide a
#     `queries-service` y `algorithms-service`, y **Caddy sólo publica el
#     portal** (34.41.26.94.sslip.io -> 127.0.0.1:8000). Abrir los
#     veinticuatro al mundo para poder medirlos sería cambiar la postura
#     de seguridad del sistema para facilitar una prueba.
#
# La tercera —el portal por HTTPS— sí sale a internet, y es la que de
# verdad mide lo que vive una persona: DNS, TLS, proxy inverso y portal.
# Por eso se corre contra la URL pública aunque estemos en la misma
# máquina: pasar por `localhost` se saltaría justo lo que se quiere medir.
# ============================================================================
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SALIDA="${NEXUM_SALIDA:-$RAIZ/informes/nube}"
URL_PUBLICA="${NEXUM_URL_PUBLICA:-https://34.41.26.94.sslip.io}"
BASE="${PG_BASE:-bienestar}"
UNIDADES="${NEXUM_UNIDADES:-120}"
CAMPANIAS="${NEXUM_CAMPANIAS:-12}"

mkdir -p "$SALIDA"
cd "$RAIZ"

echo "============================================================"
echo " Corrida en la nube — Equipo 03"
echo " base: $BASE   portal: $URL_PUBLICA"
echo " salida: $SALIDA"
echo "============================================================"
echo

# ---------------------------------------------------------------------------
# 0. Que esté lo que hace falta, ANTES de empezar
# ---------------------------------------------------------------------------
# Comprobarlo aquí y no a la mitad: el generador tarda minutos, y
# descubrir que falta Locust después de esperarlos es tiempo perdido.
faltan=0
command -v locust >/dev/null || { echo "FALTA: locust  (pip install locust)"; faltan=1; }
python3 -c "import psycopg2" 2>/dev/null || { echo "FALTA: psycopg2"; faltan=1; }
if ! curl -s -o /dev/null -m 10 "$URL_PUBLICA/salud"; then
  echo "AVISO: no contesta $URL_PUBLICA/salud — la parte 3 va a fallar."
fi
[ "$faltan" = 1 ] && { echo; echo "Instala lo que falta y vuelve a correr."; exit 1; }

# ---------------------------------------------------------------------------
# 0b. Las cuentas de carga
# ---------------------------------------------------------------------------
# El Locust de microservicios entra con 166 cuentas distintas
# (carga1..carga166). SIN ELLAS, todos los logins fallan y la corrida no
# mide el sistema sino el fracaso de autenticarse: sale una tasa de error
# enorme que no dice nada.
#
# Eso ya pasó tres veces al preparar este parcial —34.6%, 37.9% y 42.0% de
# errores— y en las tres el guion de carga estaba midiendo otra cosa: el
# limitador por IP, el limitador por token, y cuentas sin seudónimo. Por
# eso se comprueba aquí y se crean si faltan, en lugar de descubrirlo
# leyendo el CSV.
#
# El archivo NO está en db/migraciones ni en db/semilla a propósito: tiene
# contraseñas conocidas, y ahí dentro se aplicaría solo en cualquier
# despliegue. Se corre explícitamente, y sólo para medir.
echo "==> 0/3  Cuentas de carga"
existen="$(psql -d "$BASE" -tAc \
  "SELECT count(*) FROM usuarios.usuario WHERE correo LIKE 'carga%@nexum.com.mx'" \
  2>/dev/null || echo 0)"
if [ "${existen:-0}" -lt 166 ]; then
  echo "    hay $existen de 166; creándolas con scripts/cuentas_de_carga.sql"
  if psql -v ON_ERROR_STOP=1 -q -d "$BASE" -f scripts/cuentas_de_carga.sql; then
    echo "    listas"
  else
    echo "    FALLO al crearlas. Sin ellas la corrida 2/3 no mide nada."
    echo "    Revisa que el usuario de psql tenga permiso de escritura."
    exit 1
  fi
else
  echo "    las 166 ya están"
fi
echo

# ---------------------------------------------------------------------------
# 1. Datos masivos
# ---------------------------------------------------------------------------
echo "==> 1/3  Generador de datos masivos (toma varios minutos)"
echo "         El cálculo de agregados es el 98% del tiempo y va limitado"
echo "         por CPU: es la tubería de privacidad, no el disco."
echo
if python3 scripts/datos_masivos.py \
      --base "$BASE" --unidades "$UNIDADES" --campanias "$CAMPANIAS" \
      2>&1 | tee "$SALIDA/generador.txt"; then
  echo
  echo "    -> $SALIDA/generador.txt"
else
  echo "    FALLO el generador. Revisa $SALIDA/generador.txt antes de seguir."
  exit 1
fi
echo

# ---------------------------------------------------------------------------
# 2. Locust contra los microservicios, aquí dentro
# ---------------------------------------------------------------------------
echo "==> 2/3  Locust contra los microservicios (en esta máquina)"
echo "         Rampa escalonada y vuelta: la vuelta importa tanto como la"
echo "         subida, porque mide si el sistema se RECUPERA al bajar la"
echo "         carga, y eso no se ve si la prueba sólo sube."
echo
NEXUM_FORMA=rampa locust -f pruebas/carga/locustfile.py \
    --headless --csv "$SALIDA/microservicios" \
    --html "$SALIDA/microservicios.html" \
    2>&1 | tee "$SALIDA/microservicios.txt"
echo
echo "    -> $SALIDA/microservicios_stats.csv"
echo

# ---------------------------------------------------------------------------
# 3. Locust contra el portal público, por HTTPS
# ---------------------------------------------------------------------------
echo "==> 3/3  Locust contra el portal público, por HTTPS"
echo "         Ésta sí sale a internet: mide DNS, TLS, Caddy y portal, que"
echo "         es el camino real de una persona."
echo
locust -f pruebas/carga/locustfile_portal.py \
    --host "$URL_PUBLICA" \
    --headless -u "${NEXUM_USUARIOS_PORTAL:-40}" -r 2 -t "${NEXUM_TIEMPO_PORTAL:-3m}" \
    --csv "$SALIDA/portal" --html "$SALIDA/portal.html" \
    2>&1 | tee "$SALIDA/portal.txt"
echo
echo "    -> $SALIDA/portal_stats.csv"
echo

# ---------------------------------------------------------------------------
# Qué capturar
# ---------------------------------------------------------------------------
cat <<FIN

============================================================
 LISTO. Lo que queda es capturar, en este orden:
============================================================

 1. La salida del generador
    Ya está en $SALIDA/generador.txt
    Captura el bloque RESUMEN y el de CONSUMO DE RECURSOS.
    Son las cifras que pide el requisito: empleados, respuestas,
    tiempo, CPU y memoria.

 2. La tabla de Locust
    Abre $SALIDA/microservicios.html y $SALIDA/portal.html
    Captura la tabla de estadísticas: peticiones por segundo,
    mediana, p95, p99 y errores.

 3. El análisis en el portal DESPUÉS de la carga
    Entra a $URL_PUBLICA con mariana.solis@nexum.com.mx / demo123
    Ve a Análisis. Captura la pantalla con las unidades priorizadas.
    Es el punto del requisito: el algoritmo corriendo sobre los datos
    masivos que se acaban de generar, no sobre los de demostración.

 Extra que vale la pena y cuesta un minuto:
 4. El panel de servicios en $URL_PUBLICA/administracion/servicios
    con carlos.ramirez@nexum.com.mx — ahí se ve la versión desplegada,
    el historial de disponibilidad y el "no aplica" de cada servicio.

FIN
