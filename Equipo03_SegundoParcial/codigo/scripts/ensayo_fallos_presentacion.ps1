# Demostracion de tolerancia a fallos para la presentacion, en Windows.
#
# En CMD, desde la carpeta codigo:
#   powershell -ExecutionPolicy Bypass -File scripts\ensayo_fallos_presentacion.ps1
#
# Hace lo mismo que ensayo_fallos_presentacion.sh. En la laptop usa los
# puertos 8101-8109. No tumba PostgreSQL ni MongoDB. Si se interrumpe,
# vuelve a encender algorithms-service y Redis.
# La sobrecarga son 35 peticiones. No usa carlos.ramirez.

$ErrorActionPreference = "Continue"
$script:Token = ""
$script:UltimoCodigo = ""
$script:UltimoCuerpo = ""

function Pausa {
    Write-Host ""
    Read-Host "  Pulsa Enter para el siguiente paso" | Out-Null
    Write-Host ""
}

function Contenedor([string]$Nombre) {
    $id = @(docker ps -aq --filter "name=bienestar-nexum-$Nombre") | Select-Object -First 1
    if (-not $id) {
        $id = @(docker ps -aq --filter "name=$Nombre") | Select-Object -First 1
    }
    return "$id"
}

function Encender([string]$Nombre) {
    $id = Contenedor $Nombre
    if ($id) { docker start $id | Out-Null }
}

function Apagar([string]$Nombre) {
    $id = Contenedor $Nombre
    if ($id) { docker stop $id | Out-Null }
}

function Contar-Usuarios {
    $id = Contenedor "datos-1"
    if (-not $id) { return "" }
    $n = docker exec $id psql -U postgres -d bienestar -tAc "SELECT count(*) FROM usuarios.usuario;" 2>$null
    return ("$n" -replace "\s", "")
}

function Ultimas-Bitacoras {
    $id = Contenedor "datos-1"
    Write-Host "  Ultimas filas de auditoria.bitacora:"
    if (-not $id) {
        Write-Host "  (no se pudo leer la bitacora)"
        return
    }
    docker exec $id psql -U postgres -d bienestar -c "SELECT to_char(fecha_hora, 'HH24:MI:SS') AS hora, accion, resultado FROM auditoria.bitacora ORDER BY bitacora_id DESC LIMIT 6;"
    if ($LASTEXITCODE -ne 0) { Write-Host "  (no se pudo leer la bitacora)" }
}

$script:Modo = "interno"
$vivo = & curl.exe -sS -m 3 -o NUL -w "%{http_code}" "http://127.0.0.1:8101/health/live" 2>$null
if ("$vivo" -eq "200") { $script:Modo = "host" }

function Base([string]$Servicio) {
    if ($script:Modo -eq "host") {
        switch ($Servicio) {
            "auth" { return "http://127.0.0.1:8101" }
            "users" { return "http://127.0.0.1:8102" }
            "documents" { return "http://127.0.0.1:8105" }
            "algorithms" { return "http://127.0.0.1:8109" }
        }
    }
    switch ($Servicio) {
        "auth" { return "http://auth-service:8000" }
        "users" { return "http://users-service:8000" }
        "documents" { return "http://documents-service:8000" }
        "algorithms" { return "http://algorithms-service:8000" }
    }
}

function Pedir([string]$Metodo, [string]$Url, [string]$Cuerpo, [string]$Token, [switch]$Silencio) {
    $archivo = Join-Path $env:TEMP "nexum_cuerpo.txt"
    if (Test-Path $archivo) { Remove-Item $archivo -Force }
    $curl = @("-sS", "-m", "25", "-o", $archivo, "-w", "%{http_code}", "-X", $Metodo)
    if ($Token) { $curl += @("-H", "Authorization: Bearer $Token") }
    if ($Cuerpo) { $curl += @("-H", "Content-Type: application/json", "--data-binary", $Cuerpo) }
    $codigo = & curl.exe @curl $Url 2>$null
    if (-not $codigo) { $codigo = "000" }
    $respuesta = ""
    if (Test-Path $archivo) { $respuesta = Get-Content -Raw -ErrorAction SilentlyContinue $archivo }
    $script:UltimoCodigo = "$codigo".Trim()
    $script:UltimoCuerpo = "$respuesta"
    if ($Silencio) { return }
    Write-Host "HTTP $($script:UltimoCodigo)"
    if ($respuesta) { Write-Host $respuesta }
}

function TokenDe([string]$Correo) {
    $json = '{"correo":"' + $Correo + '","contrasena":"demo123"}'
    Pedir "POST" "$(Base auth)/api/v1/auth/login" $json ""
    $script:Token = ""
    if ($script:UltimoCuerpo -match '"token_acceso"\s*:\s*"([^"]+)"') {
        $script:Token = $Matches[1]
    }
}

if ($script:Modo -ne "host") {
    Write-Host "auth-service no responde en http://127.0.0.1:8101."
    Write-Host "En la laptop el proyecto tiene que estar levantado (docker compose up -d) y Docker Desktop en ejecucion."
    exit 1
}

try {
    Write-Host "============================================================"
    Write-Host " Nexum - demostracion de tolerancia a fallos"
    Write-Host " Modo de red: $($script:Modo)"
    Write-Host " Panel: http://127.0.0.1:8000/administracion/servicios"
    Write-Host "============================================================"
    Write-Host ""
    Write-Host "Antes de empezar, abre el panel en el navegador."
    Write-Host "La clave de las cuentas de demostracion es demo123."
    $Antes = Contar-Usuarios
    if (-not $Antes) { $Antes = "no se pudo contar" }
    Write-Host "Usuarios en la base ahora: $Antes"
    Pausa

    Write-Host "1) DETENER UN MICROSERVICIO"
    Write-Host "   Se apaga algorithms-service."
    Write-Host "   Detecta: el panel pasa de LISTO a CAIDO."
    Write-Host "   Informa: el navegador no muestra datos a medias; muestra el fallo."
    Write-Host "   No corrompe: las campanas y los agregados siguen en PostgreSQL."
    Write-Host "   Recupera: al encenderlo vuelve a LISTO sin volver a sembrar datos."
    Apagar "algorithms-service-1"
    Write-Host "   Servicio detenido. Recarga el panel: algorithms-service debe decir CAIDO."
    Pedir "GET" "$(Base algorithms)/health/ready" "" ""
    Pausa
    Encender "algorithms-service-1"
    Write-Host "   Esperando a que arranque..."
    Start-Sleep -Seconds 8
    Pedir "GET" "$(Base algorithms)/health/ready" "" ""
    Write-Host "   Recarga el panel: debe volver a LISTO."
    Pausa

    Write-Host "2) REVOCAR UN TOKEN"
    Write-Host "   ana.perez entra, cierra sesion y se reutiliza el mismo token."
    Write-Host "   Detecta: auth-service consulta Redis y encuentra el jti revocado."
    Write-Host "   Registra: la bitacora guarda el cierre de sesion."
    Write-Host "   Informa: 401 SESION_REVOCADA, no un 200 con datos."
    TokenDe "ana.perez@nexum.com.mx"
    $TokenAna = $script:Token
    $prefijo = $TokenAna
    if ($prefijo.Length -gt 24) { $prefijo = $prefijo.Substring(0, 24) }
    Write-Host "   Token obtenido (primeros 24 caracteres): $prefijo..."
    Pedir "POST" "$(Base auth)/api/v1/auth/logout" "" $TokenAna
    Write-Host "   El mismo token, despues de revocarlo:"
    Pedir "GET" "$(Base auth)/api/v1/auth/validar" "" $TokenAna
    Ultimas-Bitacoras
    Pausa

    Write-Host "3) DESACTIVAR REDIS UN MOMENTO"
    Write-Host "   Se apaga el contenedor cache."
    Write-Host "   Detecta: /health/ready de auth deja de estar listo."
    Write-Host "   Informa: el servicio no finge que la sesion es valida."
    Write-Host "   No corrompe: PostgreSQL no se toca. El conteo de usuarios no cambia."
    Write-Host "   Recupera: al encender Redis, ready vuelve a 200."
    Write-Host "   monitoring-service sigue vivo: su trabajo es reportar que Redis cayo."
    Apagar "cache-1"
    Pedir "GET" "$(Base auth)/health/ready" "" ""
    Pausa
    Encender "cache-1"
    Write-Host "   Esperando a Redis..."
    Start-Sleep -Seconds 5
    Pedir "GET" "$(Base auth)/health/ready" "" ""
    $Despues = Contar-Usuarios
    Write-Host "   Usuarios antes: $Antes   despues: $Despues"
    Pausa

    Write-Host "4) PROVOCAR UNA RESPUESTA INVALIDA"
    Write-Host "   Login sin contrasena. El cuerpo no cumple el contrato."
    Write-Host "   Detecta: validacion antes de tocar la base."
    Write-Host "   Informa: 400 CAMPOS_OBLIGATORIOS."
    Write-Host "   No corrompe: no se crea usuario ni sesion."
    Pedir "POST" "$(Base auth)/api/v1/auth/login" '{"correo":"ana.perez@nexum.com.mx"}' ""
    $Despues = Contar-Usuarios
    Write-Host "   Usuarios antes: $Antes   despues: $Despues  (debe ser el mismo numero)"
    Pausa

    Write-Host "5) CONSULTAR UN ARCHIVO QUE NO EXISTE"
    Write-Host "   mariana.solis pide un sha256 que no esta registrado."
    Write-Host "   Detecta: documents-service busca el hash y no lo encuentra."
    Write-Host "   Informa: 404 NO_ENCONTRADO."
    Write-Host "   No corrompe: no se inventa un archivo ni se borra otro."
    TokenDe "mariana.solis@nexum.com.mx"
    $TokenMariana = $script:Token
    $sello = "abababababababababababababababababababababababababababababababab"
    Pedir "GET" "$(Base documents)/api/v1/documentos/archivos/$sello" "" $TokenMariana
    Pausa

    Write-Host "6) SIMULAR UNA SOBRECARGA"
    Write-Host "   35 peticiones de login vacias, seguidas, desde esta misma maquina."
    Write-Host "   El limite es 30 por minuto. A partir de ahi responde 429."
    Write-Host "   Detecta: el limitador cuenta antes de procesar el cuerpo."
    Write-Host "   Informa: 429, y el servicio sigue respondiendo /health/live."
    Write-Host "   No es un ataque: son 35 peticiones y luego paramos."
    Write-Host "   No usa carlos.ramirez, asi que no bloquea la cuenta del administrador."
    Write-Host "   El token de ana para el paso 7 se pide ANTES de llenar el limite."
    TokenDe "ana.perez@nexum.com.mx"
    $TokenAna = $script:Token
    $ok400 = 0
    $ok429 = 0
    foreach ($i in 1..35) {
        Pedir "POST" "$(Base auth)/api/v1/auth/login" "{}" "" -Silencio
        Write-Host "." -NoNewline
        if ($script:UltimoCodigo -eq "400") { $ok400++ }
        if ($script:UltimoCodigo -eq "429") { $ok429++ }
    }
    Write-Host ""
    Write-Host "   Respuestas 400 (cuerpo invalido, rechazado sin escribir): $ok400"
    Write-Host "   Respuestas 429 (el limite corto el exceso): $ok429"
    Write-Host "   Si aparece 429, el servicio detecto la rafaga y siguio vivo."
    Write-Host "   Salud del servicio, que debe seguir en pie:"
    Pedir "GET" "$(Base auth)/health/live" "" ""
    Pausa

    Write-Host "7) INTENTO SIN PERMISOS"
    Write-Host "   ana.perez es colaboradora. Pide el listado de usuarios."
    Write-Host "   Ese listado exige USUARIO_ADMIN."
    Write-Host "   Detecta: el permiso se revisa antes de la consulta."
    Write-Host "   Informa: 403 SIN_PERMISO."
    Write-Host "   Registra: la bitacora queda con resultado denegado."
    Write-Host "   Se reutiliza el token de ana pedido antes de la sobrecarga."
    Pedir "GET" "$(Base users)/api/v1/usuarios" "" $TokenAna
    Ultimas-Bitacoras
    Pausa

    Write-Host "8) EXPLICAR UN ERROR EN LOS LOGS"
    Write-Host "   Estas son las ultimas lineas de auth-service."
    Write-Host "   Como leerlas en voz alta:"
    Write-Host "   - correlacion_id: el mismo identificador en la respuesta y en el log."
    Write-Host "   - codigo: CAMPOS_OBLIGATORIOS, SESION_REVOCADA, LIMITE_EXCEDIDO o similar."
    Write-Host "   - No aparece la contrasena ni el contenido de un cuestionario."
    $authId = Contenedor "auth-service-1"
    if ($authId) { docker logs --tail 30 $authId }
    Write-Host ""
    $final = Contar-Usuarios
    Write-Host "Conteo final de usuarios: $final   (al inicio era $Antes)"
    Write-Host "Si los dos numeros coinciden, ningun ensayo escribio ni borro cuentas."
    Write-Host ""
    Write-Host "Fin del guion."
}
finally {
    Write-Host ""
    Write-Host "Restaurando lo que este ensayo haya detenido..."
    Encender "algorithms-service-1"
    Encender "cache-1"
    Write-Host "Listo. algorithms-service y Redis quedaron encendidos."
}
