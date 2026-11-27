"""
auth-service — autenticación y ciclo de vida de la sesión.

Responsabilidad única: emitir, renovar, validar y revocar tokens. No sabe
nada del negocio; no consulta encuestas ni agregados. Cualquier otro
servicio que necesite saber quién es el llamante usa la librería común,
que verifica la firma y consulta Redis, sin tener que llamar a este
servicio en cada petición.

Por qué el token de acceso dura 15 minutos y hay uno de renovación: un
token de acceso robado deja de servir pronto, y el de renovación se puede
revocar de golpe. Un token de acceso de larga duración no se puede
cancelar sin una lista negra enorme.
"""
import datetime as dt
from email.message import EmailMessage
import hashlib
import hmac
import inspect
import os
import secrets
import smtplib
import uuid

import jwt
from flask import Blueprint, g, request

from comun import (ErrorApi, VERSION_API, crear_servicio, cuerpo_peticion, limite_consumo,
                   obtener_redis, responder, requiere_token)
from comun.datos import consultar_uno, cursor, ping as ping_pg
from comun.seguridad import JWT_ALGORITMO, JWT_SECRETO

MINUTOS_ACCESO = int(os.environ.get("JWT_MINUTOS", "15"))
DIAS_RENOVACION = int(os.environ.get("JWT_DIAS_RENOVACION", "7"))
INTENTOS_MAXIMOS = int(os.environ.get("INTENTOS_MAXIMOS", "5"))
VENTANA_BLOQUEO = int(os.environ.get("VENTANA_BLOQUEO", "900"))
RECUPERACION_TTL = int(os.environ.get("RECUPERACION_TTL", "600"))
RECUPERACION_MAX_INTENTOS = int(os.environ.get("RECUPERACION_MAX_INTENTOS", "3"))

os.environ.setdefault("NOMBRE_SERVICIO", "auth-service")


def _ping_redis():
    obtener_redis().ping()


app = crear_servicio(
    "auth-service",
    "Emite, renueva, valida y revoca tokens de acceso",
    comprobaciones={"postgresql": ping_pg, "redis": _ping_redis})

from contrato import montar as _montar_contrato
_montar_contrato(app)

BASE = f"/api/{VERSION_API}/auth"


# ------------------------------------------------------------ utilidades
def _emitir(usuario: dict):
    jti = uuid.uuid4().hex
    ahora = dt.datetime.now(dt.timezone.utc)
    acceso = jwt.encode({
        "sub": usuario["usuario_id"],
        "perfil_id": usuario["perfil_id"],
        "perfil": usuario["perfil"],
        "unidad_alcance": usuario["unidad_alcance_id"],
        "jti": jti, "tipo": "acceso",
        "iat": ahora, "exp": ahora + dt.timedelta(minutes=MINUTOS_ACCESO),
    }, JWT_SECRETO, algorithm=JWT_ALGORITMO)

    renovacion = jwt.encode({
        "sub": usuario["usuario_id"], "jti": jti, "tipo": "renovacion",
        "iat": ahora, "exp": ahora + dt.timedelta(days=DIAS_RENOVACION),
    }, JWT_SECRETO, algorithm=JWT_ALGORITMO)

    r = obtener_redis()
    r.hset(f"sesion:{jti}", mapping={
        "usuario_id": usuario["usuario_id"], "perfil": usuario["perfil"],
        "emitido": ahora.isoformat(), "origen": "auth-service"})
    # La sesion vive lo que el token de renovacion, no lo que el de acceso:
    # si expirara con el de acceso, renovar seria imposible.
    r.expire(f"sesion:{jti}", DIAS_RENOVACION * 86400)

    return {
        "token_acceso": acceso,
        "token_renovacion": renovacion,
        "tipo_token": "Bearer",
        "expira_en": MINUTOS_ACCESO * 60,
        "emitido_en": ahora.isoformat(),
        "usuario": {
            "usuario_id": usuario["usuario_id"],
            "nombre": f"{usuario['nombre']} {usuario['apellido_paterno']}",
            "correo": usuario["correo"],
            "perfil": usuario["perfil"],
            "perfil_id": usuario["perfil_id"],
            "unidad_alcance": usuario["unidad_alcance_id"],
        },
    }


def _bitacora(accion, resultado, actor=None, perfil=None, recurso=None):
    try:
        with cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO auditoria.bitacora (actor_usuario_id, actor_perfil, "
                " accion, tipo_recurso, recurso_id, resultado, correlacion_id, "
                " direccion_origen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (actor, (perfil or "ANONIMO")[:30], accion, "USUARIO",
                 (str(recurso)[:80] if recurso is not None else None),
                 resultado, getattr(g, "correlacion_id", ""),
                 (request.headers.get("X-Forwarded-For", request.remote_addr) or "")
                 .split(",")[0].strip() or None))
    except Exception:
        app.logger.error("No se pudo escribir en la bitacora: %s/%s", accion, resultado)


def _limite_estricto(maximo: int, ventana: int, recurso: str):
    """Aplica limite de consumo y registra RATE_LIMIT_EXCEDIDO si se rebasa."""
    try:
        limite_consumo(maximo=maximo, ventana=ventana)
    except ErrorApi as e:
        if e.codigo == "LIMITE_EXCEDIDO":
            _bitacora("RATE_LIMIT_EXCEDIDO", "RECHAZADO", recurso=recurso)
        raise


def _revocar_sesiones_usuario(usuario_id: str) -> int:
    """Revoca en Redis todas las sesiones activas de un usuario tras cambio de clave."""
    try:
        r = obtener_redis()
        revocadas = 0
        for clave in r.scan_iter("sesion:*", count=500):
            if r.hget(clave, "usuario_id") == usuario_id:
                jti = clave.split(":", 1)[1]
                r.setex(f"revocado:{jti}", DIAS_RENOVACION * 86400, "1")
                r.delete(clave)
                revocadas += 1
        return revocadas
    except Exception:
        app.logger.error("No se pudieron revocar las sesiones de %s", usuario_id)
        return 0


def _despachar_notificacion_recuperacion(usuario: dict, codigo: str):
    """Intenta enviar el OTP via notificador interno y, opcionalmente, SMTP.

    Ambos canales van aislados con try/except porque una falla de entrega
    no debe provocar errores 500 ni revelar si el correo existe.
    """
    usuario_id = usuario["usuario_id"]
    titulo = "Codigo de recuperacion de acceso"
    mensaje = (
        f"Tu codigo temporal de recuperacion es {codigo}. "
        f"Expira en {RECUPERACION_TTL // 60} minutos."
    )

    try:
        from comun.notificador import notificar_evento_interno
        notificar_evento_interno(
            tipo="RECUPERACION_ACCESO",
            destinatarios=[usuario_id],
            titulo=titulo,
            mensaje=mensaje,
            metadata={"expira_segundos": RECUPERACION_TTL},
        )
    except Exception as exc:
        app.logger.warning("No se pudo despachar notificacion interna de recuperacion: %s", exc)

    smtp_host = (os.environ.get("SMTP_HOST") or "").strip()
    if smtp_host:
        try:
            smtp_puerto = int(os.environ.get("SMTP_PUERTO") or os.environ.get("SMTP_PORT", "587"))
            smtp_usuario = os.environ.get("SMTP_USUARIO") or os.environ.get("SMTP_USER", "")
            smtp_clave = os.environ.get("SMTP_CLAVE") or os.environ.get("SMTP_PASSWORD", "")
            smtp_remitente = (
                os.environ.get("SMTP_REMITENTE")
                or os.environ.get("SMTP_FROM")
                or smtp_usuario
                or "no-reply@nexum.com.mx"
            )
            usar_tls = os.environ.get("SMTP_TLS", "true").lower() in ("1", "true", "si", "yes")

            correo_msg = EmailMessage()
            correo_msg["Subject"] = "Bienestar Nexum — Codigo de recuperacion de acceso"
            correo_msg["From"] = smtp_remitente
            correo_msg["To"] = usuario["correo"]
            correo_msg.set_content(
                f"Hola {usuario.get('nombre', '')},\n\n"
                f"{mensaje}\n\n"
                "Si no solicitaste este restablecimiento, ignora este mensaje.\n"
            )
            with smtplib.SMTP(smtp_host, smtp_puerto, timeout=5) as smtp:
                if usar_tls:
                    smtp.starttls()
                if smtp_usuario and smtp_clave:
                    smtp.login(smtp_usuario, smtp_clave)
                smtp.send_message(correo_msg)
        except Exception as exc:
            app.logger.warning("No se pudo enviar correo SMTP de recuperacion: %s", exc)


# ---------------------------------------------------------------- rutas
@app.post(f"{BASE}/login")
def login():
    limite_consumo(maximo=30, ventana=60)
    cuerpo = cuerpo_peticion()
    correo = (cuerpo.get("correo") or "").strip()
    contrasena = cuerpo.get("contrasena") or ""

    faltantes = [c for c, v in (("correo", correo), ("contrasena", contrasena)) if not v]
    if faltantes:
        raise ErrorApi("CAMPOS_OBLIGATORIOS",
                       "Faltan campos obligatorios en la solicitud.", 400,
                       [{"campo": c, "problema": "requerido"} for c in faltantes])

    r = obtener_redis()
    clave_intentos = f"intentos:{correo.lower()}"
    try:
        if int(r.get(clave_intentos) or 0) >= INTENTOS_MAXIMOS:
            _bitacora("LOGIN_FALLIDO", "RECHAZADO", recurso=correo)
            raise ErrorApi("CUENTA_BLOQUEADA",
                           "Demasiados intentos fallidos. Intenta mas tarde.", 429)
    except ErrorApi:
        raise
    except Exception:
        pass

    usuario = consultar_uno(
        """
        SELECT u.usuario_id, u.nombre, u.apellido_paterno, u.correo,
               up.perfil_id, pf.nombre AS perfil, up.unidad_alcance_id
          FROM usuarios.usuario u
          JOIN usuarios.usuario_perfil up USING (usuario_id)
          JOIN usuarios.perfil pf USING (perfil_id)
         WHERE lower(u.correo) = lower(%s) AND u.activo
           AND u.contrasena_hash = crypt(%s, u.contrasena_hash)
        """, (correo, contrasena))

    if not usuario:
        try:
            n = r.incr(clave_intentos)
            if n == 1:
                r.expire(clave_intentos, VENTANA_BLOQUEO)
        except Exception:
            pass
        _bitacora("LOGIN_FALLIDO", "RECHAZADO", recurso=correo)
        # El mensaje no distingue correo inexistente de contrasena incorrecta:
        # hacerlo permitiria averiguar que correos existen.
        raise ErrorApi("CREDENCIALES_INVALIDAS",
                       "Correo o contrasena incorrectos.", 401)

    try:
        r.delete(clave_intentos)
    except Exception:
        pass

    datos = _emitir(usuario)
    _bitacora("LOGIN_EXITOSO", "EXITO", actor=usuario["usuario_id"],
              perfil=usuario["perfil"], recurso=usuario["usuario_id"])
    return responder(datos, 200, raiz="sesion")


@app.post(f"{BASE}/renovar")
def renovar():
    limite_consumo(maximo=60, ventana=60)
    cuerpo = cuerpo_peticion()
    token = cuerpo.get("token_renovacion") or ""
    if not token:
        raise ErrorApi("CAMPOS_OBLIGATORIOS", "Falta 'token_renovacion'.", 400,
                       [{"campo": "token_renovacion", "problema": "requerido"}])

    try:
        carga = jwt.decode(token, JWT_SECRETO, algorithms=[JWT_ALGORITMO])
    except jwt.ExpiredSignatureError:
        raise ErrorApi("TOKEN_EXPIRADO",
                       "El token de renovacion expiro. Inicia sesion de nuevo.", 401)
    except jwt.PyJWTError:
        raise ErrorApi("TOKEN_INVALIDO", "El token de renovacion no es valido.", 401)

    if carga.get("tipo") != "renovacion":
        # Un token de acceso NO sirve para renovar: si sirviera, robar uno
        # permitiria extender la sesion indefinidamente.
        raise ErrorApi("TIPO_DE_TOKEN_INCORRECTO",
                       "Se esperaba un token de renovacion.", 401)

    jti_viejo = carga.get("jti", "")
    r = obtener_redis()
    if r.exists(f"revocado:{jti_viejo}") or not r.exists(f"sesion:{jti_viejo}"):
        raise ErrorApi("SESION_REVOCADA", "La sesion ya no esta activa.", 401)

    usuario = consultar_uno(
        """
        SELECT u.usuario_id, u.nombre, u.apellido_paterno, u.correo,
               up.perfil_id, pf.nombre AS perfil, up.unidad_alcance_id
          FROM usuarios.usuario u
          JOIN usuarios.usuario_perfil up USING (usuario_id)
          JOIN usuarios.perfil pf USING (perfil_id)
         WHERE u.usuario_id = %s AND u.activo
        """, (carga.get("sub"),))
    if not usuario:
        raise ErrorApi("USUARIO_INACTIVO",
                       "El usuario ya no esta activo.", 401)

    # Rotacion: la sesion anterior se revoca al emitir la nueva. Asi, si
    # alguien robo el token de renovacion, su uso deja rastro y solo uno de
    # los dos (el legitimo o el atacante) conserva la sesion.
    r.setex(f"revocado:{jti_viejo}", DIAS_RENOVACION * 86400, "1")
    r.delete(f"sesion:{jti_viejo}")

    datos = _emitir(usuario)
    _bitacora("LOGIN_EXITOSO", "EXITO", actor=usuario["usuario_id"],
              perfil=usuario["perfil"], recurso="renovacion")
    return responder(datos, 200, raiz="sesion")


@app.post(f"{BASE}/logout")
@requiere_token
def logout():
    jti = g.actor.get("jti", "")
    r = obtener_redis()
    r.setex(f"revocado:{jti}", DIAS_RENOVACION * 86400, "1")
    r.delete(f"sesion:{jti}")
    _bitacora("LOGOUT", "EXITO", actor=g.actor.get("sub"),
              perfil=g.actor.get("perfil"), recurso=g.actor.get("sub"))
    return responder({"revocado": True, "jti": jti,
                      "mensaje": "La sesion quedo revocada en todos los componentes."},
                     200, raiz="logout")


@app.get(f"{BASE}/validar")
@requiere_token
def validar():
    """Permite a un cliente comprobar si su token sigue sirviendo."""
    return responder({
        "valido": True,
        "usuario_id": g.actor.get("sub"),
        "perfil": g.actor.get("perfil"),
        "perfil_id": g.actor.get("perfil_id"),
        "unidad_alcance": g.actor.get("unidad_alcance"),
        "jti": g.actor.get("jti"),
        "expira": g.actor.get("exp"),
    }, 200, raiz="validacion")


@app.get(f"{BASE}/permisos")
@requiere_token
def permisos():
    """Los permisos se consultan, no viajan en el token.

    Asi, revocarle un permiso a un perfil surte efecto de inmediato, sin
    esperar a que caduquen los tokens ya emitidos.
    """
    filas = consultar_uno(
        "SELECT array_agg(p.codigo ORDER BY p.codigo) AS codigos "
        "FROM usuarios.perfil_permiso pp JOIN usuarios.permiso p USING (permiso_id) "
        "WHERE pp.perfil_id = %s", (g.actor.get("perfil_id"),))
    return responder({"perfil": g.actor.get("perfil"),
                      "permisos": (filas or {}).get("codigos") or []},
                     200, raiz="permisos_respuesta")


# Blueprints separados para aislar los contadores de `limite_consumo` por ruta
# sin modificar comun/servicio.py.
bp_recuperar_solicitar = Blueprint("recuperar_solicitar", __name__)
bp_recuperar_confirmar = Blueprint("recuperar_confirmar", __name__)


@bp_recuperar_solicitar.post(f"{BASE}/recuperar/solicitar")
def recuperar_solicitar():
    _limite_estricto(maximo=5, ventana=60, recurso="recuperar_solicitar")
    cuerpo = cuerpo_peticion()
    correo = (cuerpo.get("correo") or "").strip()
    if not correo:
        raise ErrorApi("CAMPOS_OBLIGATORIOS",
                       "Faltan campos obligatorios en la solicitud.", 400,
                       [{"campo": "correo", "problema": "requerido"}])

    correo_lower = correo.lower()
    usuario = consultar_uno(
        """
        SELECT u.usuario_id, u.nombre, u.correo, pf.nombre AS perfil
          FROM usuarios.usuario u
          LEFT JOIN usuarios.usuario_perfil up USING (usuario_id)
          LEFT JOIN usuarios.perfil pf USING (perfil_id)
         WHERE lower(u.correo) = lower(%s) AND u.activo
        """,
        (correo_lower,),
    )

    if usuario:
        # OTP criptograficamente seguro; en Redis se guarda solo el SHA-256
        # para que una lectura de cache no exponga codigos en claro.
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        codigo_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
        r = obtener_redis()
        try:
            r.setex(f"recuperacion:{correo_lower}", RECUPERACION_TTL, codigo_hash)
            r.setex(f"recuperacion_intentos:{correo_lower}", RECUPERACION_TTL, "0")
        except Exception:
            app.logger.error("Redis no disponible al guardar OTP de recuperacion")
            raise ErrorApi("DEPENDENCIA_NO_DISPONIBLE",
                           "No se pudo procesar la solicitud de recuperacion.", 503)

        _despachar_notificacion_recuperacion(usuario, codigo)
        if os.environ.get("APP_AMBIENTE", "developer") == "developer":
            app.logger.debug("[DEV] OTP de recuperacion para %s: %s", correo_lower, codigo)

        _bitacora("RECUPERACION_SOLICITADA", "EXITO",
                  actor=usuario["usuario_id"],
                  perfil=usuario.get("perfil"),
                  recurso=usuario["usuario_id"])
    else:
        _bitacora("RECUPERACION_SOLICITADA", "RECHAZADO", recurso=correo_lower)

    # Respuesta generica identica exista o no el correo: evita enumeracion de cuentas.
    return responder({
        "solicitado": True,
        "mensaje": "Si el correo esta registrado y activo, recibiras un codigo de recuperacion.",
    }, 200, raiz="recuperacion_solicitada")


@bp_recuperar_confirmar.post(f"{BASE}/recuperar/confirmar")
def recuperar_confirmar():
    _limite_estricto(maximo=10, ventana=60, recurso="recuperar_confirmar")
    cuerpo = cuerpo_peticion()
    correo = (cuerpo.get("correo") or "").strip()
    codigo = str(cuerpo.get("codigo") or "").strip()
    nueva_contrasena = cuerpo.get("nueva_contrasena") or ""

    faltantes = [
        c for c, v in (("correo", correo), ("codigo", codigo),
                       ("nueva_contrasena", nueva_contrasena))
        if not v
    ]
    if faltantes:
        raise ErrorApi("CAMPOS_OBLIGATORIOS",
                       "Faltan campos obligatorios en la solicitud.", 400,
                       [{"campo": c, "problema": "requerido"} for c in faltantes])

    if len(nueva_contrasena) < 8:
        raise ErrorApi("VALIDACION", "La solicitud tiene campos invalidos.", 422,
                       [{"campo": "nueva_contrasena", "problema": "minimo 8 caracteres"}])

    correo_lower = correo.lower()
    clave_otp = f"recuperacion:{correo_lower}"
    clave_intentos = f"recuperacion_intentos:{correo_lower}"

    r = obtener_redis()
    try:
        hash_guardado = r.get(clave_otp)
    except Exception:
        app.logger.error("Redis no disponible al validar OTP de recuperacion")
        raise ErrorApi("DEPENDENCIA_NO_DISPONIBLE",
                       "No se pudo validar el codigo de recuperacion.", 503)

    if not hash_guardado:
        _bitacora("RECUPERACION_CONFIRMADA", "RECHAZADO", recurso=correo_lower)
        raise ErrorApi("CODIGO_INVALIDO_O_EXPIRADO",
                       "El codigo de recuperacion es invalido o expiro.", 400)

    hash_recibido = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(hash_recibido, hash_guardado):
        try:
            intentos = r.incr(clave_intentos)
            if intentos == 1:
                r.expire(clave_intentos, RECUPERACION_TTL)
            if intentos >= RECUPERACION_MAX_INTENTOS:
                r.delete(clave_otp, clave_intentos)
                _bitacora("RECUPERACION_CONFIRMADA", "RECHAZADO", recurso=correo_lower)
                raise ErrorApi("CODIGO_BLOQUEADO",
                               "Se alcanzo el maximo de intentos. Solicita un nuevo codigo.",
                               429)
        except ErrorApi:
            raise
        except Exception:
            app.logger.error("Redis no disponible al actualizar intentos de recuperacion")
            raise ErrorApi("DEPENDENCIA_NO_DISPONIBLE",
                           "No se pudo validar el codigo de recuperacion.", 503)

        _bitacora("RECUPERACION_CONFIRMADA", "RECHAZADO", recurso=correo_lower)
        raise ErrorApi("CODIGO_INVALIDO",
                       "El codigo de recuperacion es incorrecto.", 400)

    usuario = consultar_uno(
        """
        SELECT u.usuario_id, pf.nombre AS perfil
          FROM usuarios.usuario u
          LEFT JOIN usuarios.usuario_perfil up USING (usuario_id)
          LEFT JOIN usuarios.perfil pf USING (perfil_id)
         WHERE lower(u.correo) = lower(%s) AND u.activo
        """,
        (correo_lower,),
    )
    if not usuario:
        try:
            r.delete(clave_otp, clave_intentos)
        except Exception:
            pass
        _bitacora("RECUPERACION_CONFIRMADA", "RECHAZADO", recurso=correo_lower)
        raise ErrorApi("CODIGO_INVALIDO_O_EXPIRADO",
                       "El codigo de recuperacion es invalido o expiro.", 400)

    # Actualizacion mediante funcion SECURITY DEFINER para mantener menor privilegio.
    with cursor(commit=True) as cur:
        cur.execute(
            "SELECT usuarios.fn_restablecer_contrasena(%s, %s) AS actualizado",
            (usuario["usuario_id"], nueva_contrasena),
        )
        fila = cur.fetchone()
        if not fila or not fila["actualizado"]:
            raise ErrorApi("USUARIO_INACTIVO",
                           "No fue posible actualizar la contrasena.", 400)

    try:
        r.delete(clave_otp, clave_intentos, f"intentos:{correo_lower}")
    except Exception:
        pass

    revocadas = _revocar_sesiones_usuario(usuario["usuario_id"])
    _bitacora("RECUPERACION_CONFIRMADA", "EXITO",
              actor=usuario["usuario_id"],
              perfil=usuario.get("perfil"),
              recurso=usuario["usuario_id"])

    return responder({
        "actualizado": True,
        "sesiones_revocadas": revocadas,
        "mensaje": "Contrasena actualizada. Inicia sesion con tu nueva contrasena.",
    }, 200, raiz="recuperacion_confirmada")


app.register_blueprint(bp_recuperar_solicitar)
app.register_blueprint(bp_recuperar_confirmar)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PUERTO", "8101")))
