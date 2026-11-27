#!/usr/bin/env bash
# Demostracion de tolerancia a fallos para la presentacion.
#
# Cubre las ocho situaciones que el profesor puede pedir y, en cada una,
# deja visible lo que el sistema debe demostrar: detecta, registra, informa,
# no corrompe datos y se recupera.
#
# Se corre en la maquina donde ya esta levantado el proyecto:
#   - laptop:  cd codigo && bash scripts/ensayo_fallos_presentacion.sh
#   - nube:    ssh a nexum-equipo03, cd ~/IAC/Equipo03_SegundoParcial/codigo
#              bash scripts/ensayo_fallos_presentacion.sh
#
# No tumba PostgreSQL ni MongoDB. Redis y un microservicio se detienen y
# el script los vuelve a encender aunque se interrumpa con Ctrl+C.
# La sobrecarga es un limite de ritmo (35 peticiones), no un ataque.
# Usa ana.perez solo para permisos y revocacion. No usa carlos.ramirez.
set -u

PAUSA() {
  echo
  read -r -p "  Pulsa Enter para el siguiente paso... " _
  echo
}

D="docker"
if ! docker info >/dev/null 2>&1; then
  D="sudo docker"
fi

contenedor() {
  local id
  id="$($D ps -aqf "name=bienestar-nexum-$1" | head -1)"
  if [[ -z "$id" ]]; then
    id="$($D ps -aqf "name=$1" | head -1)"
  fi
  printf '%s' "$id"
}

encender() {
  local id
  id="$(contenedor "$1")"
  if [[ -n "$id" ]]; then
    $D start "$id" >/dev/null
  fi
}

apagar() {
  local id
  id="$(contenedor "$1")"
  if [[ -n "$id" ]]; then
    $D stop "$id" >/dev/null
  fi
}

limpiar() {
  echo
  echo "Restaurando lo que este ensayo haya detenido..."
  encender "algorithms-service-1"
  encender "cache-1"
  echo "Listo. algorithms-service y Redis quedaron encendidos."
}
trap limpiar EXIT

contar_usuarios() {
  local id
  id="$(contenedor "datos-1")"
  $D exec "$id" psql -U postgres -d bienestar -tAc \
    "SELECT count(*) FROM usuarios.usuario;" 2>/dev/null | tr -d '[:space:]'
}

ultimas_bitacoras() {
  local id
  id="$(contenedor "datos-1")"
  echo "  Ultimas filas de auditoria.bitacora:"
  $D exec "$id" psql -U postgres -d bienestar -c \
    "SELECT to_char(fecha_hora, 'HH24:MI:SS') AS hora, accion, resultado
       FROM auditoria.bitacora
      ORDER BY bitacora_id DESC
      LIMIT 6;" 2>/dev/null || echo "  (no se pudo leer la bitacora)"
}

# Modo host: puertos 8101+ publicados (laptop).
# Modo interno: solo la red de compose (la VM de GCP).
MODO="interno"
if curl -sf -m 3 -o /dev/null "http://127.0.0.1:8101/health/live"; then
  MODO="host"
fi

base_de() {
  case "$1" in
    auth)       [[ "$MODO" == host ]] && echo "http://127.0.0.1:8101" || echo "http://auth-service:8000" ;;
    users)      [[ "$MODO" == host ]] && echo "http://127.0.0.1:8102" || echo "http://users-service:8000" ;;
    documents)  [[ "$MODO" == host ]] && echo "http://127.0.0.1:8105" || echo "http://documents-service:8000" ;;
    algorithms) [[ "$MODO" == host ]] && echo "http://127.0.0.1:8109" || echo "http://algorithms-service:8000" ;;
  esac
}

# Imprime "HTTP <codigo>" y el cuerpo.
# $1 metodo  $2 url  $3 cuerpo  $4 token  $5 silencio (si vale "si", no imprime el cuerpo)
pedir() {
  local metodo="$1" url="$2" cuerpo="${3-}" token="${4-}" silencio="${5-}"
  local codigo="" respuesta=""
  if [[ "$MODO" == host ]]; then
    local -a args=(-sS -m 25 -o /tmp/nexum_cuerpo.txt -w "%{http_code}" -X "$metodo")
    if [[ -n "$token" ]]; then
      args+=(-H "Authorization: Bearer ${token}")
    fi
    if [[ -n "$cuerpo" ]]; then
      args+=(-H "Content-Type: application/json" --data-binary "$cuerpo")
    fi
    codigo="$(curl "${args[@]}" "$url" 2>/dev/null)" || true
    if [[ -z "$codigo" ]]; then codigo="000"; fi
    respuesta="$(cat /tmp/nexum_cuerpo.txt 2>/dev/null || true)"
  else
    local web
    web="$(contenedor "web-1")"
    local salida
    salida="$($D exec -e METODO="$metodo" -e URL="$url" -e CUERPO="$cuerpo" -e TOKEN="$token" "$web" \
      python -c '
import os, urllib.request, urllib.error
req = urllib.request.Request(os.environ["URL"], method=os.environ["METODO"])
cuerpo = os.environ.get("CUERPO") or ""
if cuerpo:
    req.data = cuerpo.encode()
    req.add_header("Content-Type", "application/json")
token = os.environ.get("TOKEN") or ""
if token:
    req.add_header("Authorization", "Bearer " + token)
try:
    with urllib.request.urlopen(req, timeout=25) as r:
        print("HTTP %s" % r.status)
        print(r.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP %s" % e.code)
    print(e.read().decode())
except Exception as e:
    print("HTTP 000")
    print(e)
' 2>/dev/null || printf 'HTTP 000\n')"
    codigo="$(printf '%s\n' "$salida" | awk 'NR==1{print $2}')"
    respuesta="$(printf '%s\n' "$salida" | tail -n +2)"
  fi
  if [[ "$silencio" == "si" ]]; then
    printf '%s' "$codigo"
    return
  fi
  echo "HTTP ${codigo}"
  printf '%s\n' "$respuesta"
}

token_de() {
  local raw token
  raw="$(pedir POST "$(base_de auth)/api/v1/auth/login" \
    "{\"correo\":\"$1\",\"contrasena\":\"demo123\"}")"
  printf '%s\n' "$raw"
  token="$(printf '%s\n' "$raw" | sed -n 's/.*"token_acceso"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
  printf '%s' "$token" > /tmp/nexum_token.txt
}

echo "============================================================"
echo " Nexum — demostracion de tolerancia a fallos"
echo " Modo de red: ${MODO}"
echo " Panel: http://127.0.0.1:8000/administracion/servicios"
echo " En la nube el mismo panel esta en el portal publico."
echo "============================================================"
echo
echo "Antes de empezar, abre el panel en el navegador."
echo "La clave de las cuentas de demostracion es demo123."
ANTES="$(contar_usuarios)"
echo "Usuarios en la base ahora: ${ANTES:-no se pudo contar}"
PAUSA

echo "1) DETENER UN MICROSERVICIO"
echo "   Se apaga algorithms-service."
echo "   Detecta: el panel pasa de LISTO a CAIDO."
echo "   Informa: el navegador no muestra datos a medias; muestra el fallo."
echo "   No corrompe: las campanas y los agregados siguen en PostgreSQL."
echo "   Recupera: al encenderlo vuelve a LISTO sin volver a sembrar datos."
apagar "algorithms-service-1"
echo "   Servicio detenido. Recarga el panel: algorithms-service debe decir CAIDO."
pedir GET "$(base_de algorithms)/health/ready" || true
PAUSA
encender "algorithms-service-1"
echo "   Esperando a que arranque..."
sleep 8
pedir GET "$(base_de algorithms)/health/ready"
echo "   Recarga el panel: debe volver a LISTO."
PAUSA

echo "2) REVOCAR UN TOKEN"
echo "   ana.perez entra, cierra sesion y se reutiliza el mismo token."
echo "   Detecta: auth-service consulta Redis y encuentra el jti revocado."
echo "   Registra: la bitacora guarda el cierre de sesion."
echo "   Informa: 401 SESION_REVOCADA, no un 200 con datos."
token_de ana.perez@nexum.com.mx
TOKEN_ANA="$(cat /tmp/nexum_token.txt)"
echo "   Token obtenido (primeros 24 caracteres): ${TOKEN_ANA:0:24}..."
pedir POST "$(base_de auth)/api/v1/auth/logout" "" "$TOKEN_ANA"
echo "   El mismo token, despues de revocarlo:"
pedir GET "$(base_de auth)/api/v1/auth/validar" "" "$TOKEN_ANA"
ultimas_bitacoras
PAUSA

echo "3) DESACTIVAR REDIS UN MOMENTO"
echo "   Se apaga el contenedor cache."
echo "   Detecta: /health/ready de auth deja de estar listo."
echo "   Informa: el servicio no finge que la sesion es valida."
echo "   No corrompe: PostgreSQL no se toca. El conteo de usuarios no cambia."
echo "   Recupera: al encender Redis, ready vuelve a 200."
echo "   monitoring-service sigue vivo: su trabajo es reportar que Redis cayo."
apagar "cache-1"
pedir GET "$(base_de auth)/health/ready"
PAUSA
encender "cache-1"
echo "   Esperando a Redis..."
sleep 5
pedir GET "$(base_de auth)/health/ready"
DESPUES="$(contar_usuarios)"
echo "   Usuarios antes: ${ANTES}   despues: ${DESPUES}"
PAUSA

echo "4) PROVOCAR UNA RESPUESTA INVALIDA"
echo "   Login sin contrasena. El cuerpo no cumple el contrato."
echo "   Detecta: validacion antes de tocar la base."
echo "   Informa: 400 CAMPOS_OBLIGATORIOS."
echo "   No corrompe: no se crea usuario ni sesion."
pedir POST "$(base_de auth)/api/v1/auth/login" \
  '{"correo":"ana.perez@nexum.com.mx"}'
DESPUES="$(contar_usuarios)"
echo "   Usuarios antes: ${ANTES}   despues: ${DESPUES}  (debe ser el mismo numero)"
PAUSA

echo "5) CONSULTAR UN ARCHIVO QUE NO EXISTE"
echo "   mariana.solis pide un sha256 que no esta registrado."
echo "   Detecta: documents-service busca el hash y no lo encuentra."
echo "   Informa: 404 NO_ENCONTRADO."
echo "   No corrompe: no se inventa un archivo ni se borra otro."
token_de mariana.solis@nexum.com.mx
TOKEN_MARIANA="$(cat /tmp/nexum_token.txt)"
SELLO="abababababababababababababababababababababababababababababababab"
pedir GET "$(base_de documents)/api/v1/documentos/archivos/${SELLO}" \
  "" "$TOKEN_MARIANA"
PAUSA

echo "6) SIMULAR UNA SOBRECARGA"
echo "   35 peticiones de login vacias, seguidas, desde esta misma maquina."
echo "   El limite es 30 por minuto. A partir de ahi responde 429."
echo "   Detecta: el limitador cuenta antes de procesar el cuerpo."
echo "   Informa: 429, y el servicio sigue respondiendo /health/live."
echo "   No es un ataque: son 35 peticiones y luego paramos."
echo "   No usa carlos.ramirez, asi que no bloquea la cuenta del administrador."
echo "   El token de ana para el paso 7 se pide ANTES de llenar el limite."
token_de ana.perez@nexum.com.mx
TOKEN_ANA="$(cat /tmp/nexum_token.txt)"
ok400=0
ok429=0
for _ in $(seq 1 35); do
  codigo="$(pedir POST "$(base_de auth)/api/v1/auth/login" '{}' "" "" si)"
  printf '.'
  if [[ "$codigo" == "400" ]]; then ok400=$((ok400 + 1)); fi
  if [[ "$codigo" == "429" ]]; then ok429=$((ok429 + 1)); fi
done
echo
echo "   Respuestas 400 (cuerpo invalido, rechazado sin escribir): ${ok400}"
echo "   Respuestas 429 (el limite corto el exceso): ${ok429}"
echo "   Si aparece 429, el servicio detecto la rafaga y siguio vivo."
echo "   Salud del servicio, que debe seguir en pie:"
pedir GET "$(base_de auth)/health/live"
PAUSA

echo "7) INTENTO SIN PERMISOS"
echo "   ana.perez es colaboradora. Pide el listado de usuarios."
echo "   Ese listado exige USUARIO_ADMIN."
echo "   Detecta: el permiso se revisa antes de la consulta."
echo "   Informa: 403 SIN_PERMISO."
echo "   Registra: la bitacora queda con resultado denegado."
echo "   Se reutiliza el token de ana pedido antes de la sobrecarga."
pedir GET "$(base_de users)/api/v1/usuarios" "" "$TOKEN_ANA"
ultimas_bitacoras
PAUSA

echo "8) EXPLICAR UN ERROR EN LOS LOGS"
echo "   Estas son las ultimas lineas de auth-service."
echo "   Como leerlas en voz alta:"
echo "   - correlacion_id: el mismo identificador en la respuesta y en el log."
echo "   - codigo: CAMPOS_OBLIGATORIOS, SESION_REVOCADA, LIMITE_EXCEDIDO o similar."
echo "   - No aparece la contrasena ni el contenido de un cuestionario."
AUTH_ID="$(contenedor "auth-service-1")"
$D logs --tail 30 "$AUTH_ID"
echo
echo "Conteo final de usuarios: $(contar_usuarios)   (al inicio era ${ANTES})"
echo "Si los dos numeros coinciden, ningun ensayo escribio ni borro cuentas."
echo
echo "Fin del guion. Al salir, el script enciende algorithms-service y Redis"
echo "por si alguno quedo detenido."
