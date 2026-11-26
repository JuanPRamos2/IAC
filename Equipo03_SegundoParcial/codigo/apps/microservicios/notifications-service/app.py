"""
notifications-service — notificaciones internas.

Responsabilidad única: avisar. Campaña abierta, recordatorio de encuesta,
detección de riesgo en una unidad, plan de intervención aprobado.

Dos restricciones del dominio que el código hace cumplir:

1. Una notificación NUNCA contiene un valor de bienestar ni un resultado
   individual. Dice "hay una condición detectada en tu unidad", no "tu
   unidad tiene 2.9 de carga percibida". Publicar una cifra por esta vía
   saltaría el mecanismo de privacidad diferencial y el presupuesto de
   épsilon por completo.

2. Una notificación dirigida a un perfil con autoridad laboral no puede
   referirse a una persona. Se dirige a un usuario (su propio recordatorio)
   o a una unidad (una condición organizacional), nunca "fulano tiene
   riesgo alto".
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import time
import uuid

from flask import g, request

from comun import (ErrorApi, VERSION_API, crear_servicio, cuerpo_peticion, limite_consumo,
                   obtener_redis, pagina, responder, requiere_permiso,
                   requiere_token, sobre_pagina)
from comun.datos import consultar, consultar_uno, cursor, ping as ping_pg
from comun.mongo import (ASCENDING, DESCENDING, asegurar_indices, base,
                         ping as ping_mongo, verificar_sin_identidad)
from comun.seguridad import JWT_SECRETO

os.environ.setdefault("NOMBRE_SERVICIO", "notifications-service")

TIPOS = {
    "CAMPANIA_ABIERTA": "Hay una campania abierta para tu unidad",
    "RECORDATORIO_ENCUESTA": "Te falta responder una campania",
    "CONDICION_DETECTADA": "El motor de reglas detecto una condicion en una unidad",
    "PLAN_APROBADO": "Se aprobo un plan de intervencion organizacional",
    "CONSENTIMIENTO_POR_VENCER": "Tu consentimiento esta por vencer",
    # Los dos que nombra la especificacion y no existian.
    "SOLICITUD_APOYO_ACTUALIZADA": "Cambio el estado de tu solicitud de apoyo",
    "CONFIRMACION_RECIBIDA": "Se registro tu respuesta",
    "RECUPERACION_ACCESO": "Se genero un codigo temporal para recuperar tu acceso",
}

# Una notificacion con una cifra de bienestar seria una fuga del mecanismo
# de privacidad. Se rechaza en el servidor, no solo por convencion.
CIFRA = re.compile(r"\b\d+[.,]\d+\b")

INDICES = {
    "notificaciones": [
        ([("notificacion_id", ASCENDING)], {"unique": True, "name": "ix_notif_id"}),
        ([("destinatario_usuario_id", ASCENDING), ("leida", ASCENDING),
          ("fecha_creacion", DESCENDING)], {"name": "ix_destinatario"}),
        ([("tipo", ASCENDING), ("fecha_creacion", DESCENDING)], {"name": "ix_tipo"}),
        # TTL: las notificaciones se borran solas a los 90 dias. Minimizacion
        # de datos: no se conserva lo que ya no sirve.
        ([("fecha_expiracion", ASCENDING)],
         {"expireAfterSeconds": 0, "name": "ix_ttl"}),
    ],
    "preferencias_notificacion": [
        ([("usuario_id", ASCENDING)], {"unique": True, "name": "ix_prefs_usuario"}),
    ],
    "dispositivos_push": [
        ([("usuario_id", ASCENDING), ("token", ASCENDING)],
         {"unique": True, "name": "ix_dispositivo"}),
    ],
    "cola_push": [
        ([("push_id", ASCENDING)], {"unique": True, "name": "ix_push_id"}),
        ([("estado", ASCENDING), ("fecha_encolado", ASCENDING)],
         {"name": "ix_pendientes"}),
    ],
}


def _ping_redis():
    obtener_redis().ping()


app = crear_servicio(
    "notifications-service",
    "Envia y consulta notificaciones internas, sin exponer cifras de bienestar",
    comprobaciones={"postgresql": ping_pg, "mongodb": ping_mongo,
                    "redis": _ping_redis})

import preferencias as _prefs
from contrato import montar as _montar_contrato
_montar_contrato(app)

BASE = f"/api/{VERSION_API}/notificaciones"


def _bitacora(accion, resultado, recurso=None):
    try:
        with cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO auditoria.bitacora (actor_usuario_id, actor_perfil, "
                " accion, tipo_recurso, recurso_id, resultado, correlacion_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                ((g.get("actor") or {}).get("sub"),
                 ((g.get("actor") or {}).get("perfil") or "ANONIMO")[:30],
                 accion, "NOTIFICACION", recurso, resultado,
                 getattr(g, "correlacion_id", "")))
    except Exception:
        app.logger.error("No se pudo escribir en la bitacora: %s", accion)


def _limpiar(doc):
    doc = dict(doc)
    doc.pop("_id", None)
    for k, v in list(doc.items()):
        if isinstance(v, dt.datetime):
            doc[k] = v.isoformat()
    return doc


def _contador_clave(usuario_id):
    return f"notif_sin_leer:{usuario_id}"


@app.post(f"{BASE}/indices")
@requiere_permiso("PARAMETRO_ADMIN")
def crear_indices():
    creados = asegurar_indices(INDICES)
    return responder({"indices": creados, "total": len(creados)},
                     200, raiz="indices_respuesta")


# ----------------------------------------------------------------- envío
def _validar_y_despachar(cuerpo, enviada_por, error_si_todos_silenciados=True):
    problemas = []
    tipo = (cuerpo.get("tipo") or "").strip().upper()
    if tipo not in TIPOS:
        problemas.append({"campo": "tipo",
                          "problema": f"debe ser uno de: {', '.join(sorted(TIPOS))}"})
    titulo = (cuerpo.get("titulo") or "").strip()
    mensaje = (cuerpo.get("mensaje") or "").strip()
    if len(titulo) < 5:
        problemas.append({"campo": "titulo", "problema": "minimo 5 caracteres"})
    if len(mensaje) < 10:
        problemas.append({"campo": "mensaje", "problema": "minimo 10 caracteres"})

    destinatarios = list(cuerpo.get("destinatarios") or [])
    unidad = cuerpo.get("unidad_organizacional_id")
    metadata = cuerpo.get("metadata") if isinstance(cuerpo.get("metadata"), dict) else {}
    seudonimo = cuerpo.get("seudonimo_id") or metadata.get("seudonimo_id")

    if not destinatarios and not unidad and not seudonimo:
        problemas.append({"campo": "destinatarios",
                          "problema": "indica destinatarios o una unidad"})
    if problemas:
        raise ErrorApi("VALIDACION", "La solicitud tiene campos invalidos.",
                       422, problemas)

    verificar_sin_identidad(cuerpo)

    # Ninguna cifra de bienestar puede viajar en una notificacion.
    for campo, texto in (("titulo", titulo), ("mensaje", mensaje)):
        if CIFRA.search(texto):
            raise ErrorApi(
                "CIFRA_NO_PERMITIDA",
                "Una notificacion no puede contener valores de bienestar. "
                "Publicar una cifra por esta via saltaria el mecanismo de "
                "privacidad diferencial y el presupuesto de epsilon.", 422,
                [{"campo": campo, "problema": "contiene un valor numerico decimal"}])

    # Si se indica unidad, los destinatarios son quienes tienen alcance ahi.
    if unidad:
        if not consultar_uno("SELECT 1 AS x FROM organizacion.unidad_organizacional "
                             "WHERE unidad_organizacional_id = %s AND activa", (unidad,)):
            raise ErrorApi("UNIDAD_NO_EXISTE",
                           f"La unidad {unidad} no existe o esta inactiva.", 422)
        filas = consultar(
            "SELECT up.usuario_id FROM usuarios.usuario_perfil up "
            "JOIN usuarios.usuario u USING (usuario_id) "
            "WHERE u.activo AND (up.unidad_alcance_id = %s OR up.unidad_alcance_id IS NULL)",
            (unidad,))
        destinatarios = sorted({f["usuario_id"] for f in filas} | set(destinatarios))
    elif not destinatarios and seudonimo:
        fila_seudo = consultar_uno(
            "SELECT usuario_id FROM portal.v_participacion_propia WHERE seudonimo_id = %s",
            (seudonimo,))
        if fila_seudo and fila_seudo.get("usuario_id"):
            destinatarios = [fila_seudo["usuario_id"]]

    destinatarios = sorted({str(d).strip() for d in destinatarios if d})
    if not destinatarios:
        if error_si_todos_silenciados:
            raise ErrorApi("SIN_DESTINATARIOS",
                           "No hay usuarios activos que puedan recibir esta notificacion.", 422)
        return {"lote_id": None, "tipo": tipo, "enviadas": 0, "omitidas": 0,
                "omitidos": [], "push_encolados": 0, "destinatarios": []}, 200

    ahora = dt.datetime.now(dt.timezone.utc)
    expira = ahora + dt.timedelta(days=int(os.environ.get("NOTIF_DIAS", "90")))
    lote = f"LOTE-{uuid.uuid4().hex[:10].upper()}"

    metadata_limpia = {k: v for k, v in metadata.items() if k != "seudonimo_id"}

    prefs_por_usuario = {
        d["usuario_id"]: _prefs.normalizar(d.get("preferencias"))
        for d in base()["preferencias_notificacion"].find(
            {"usuario_id": {"$in": destinatarios}})}

    dispositivos_por_usuario = {}
    for d in base()["dispositivos_push"].find(
            {"usuario_id": {"$in": destinatarios}}):
        dispositivos_por_usuario.setdefault(d["usuario_id"], []).append(d["token"])

    documentos, cola, omitidos = [], [], []
    for destino in destinatarios:
        doc_notif = {
            "notificacion_id": f"NTF-{uuid.uuid4().hex[:12].upper()}",
            "lote_id": lote,
            "tipo": tipo,
            "titulo": titulo,
            "mensaje": mensaje,
            "unidad_organizacional_id": unidad,
            "campania_id": cuerpo.get("campania_id"),
            "destinatario_usuario_id": destino,
            "leida": False,
            "fecha_lectura": None,
            "enviada_por": enviada_por,
            "fecha_creacion": ahora,
            "fecha_expiracion": expira,
        }
        if metadata_limpia:
            doc_notif["metadata"] = metadata_limpia
        documentos.append(doc_notif)

    obligatorios = {"CONSENTIMIENTO_POR_VENCER", "RECUPERACION_ACCESO"}
    entregables = []
    for documento in documentos:
        destino = documento["destinatario_usuario_id"]
        preferencias = prefs_por_usuario.get(destino, _prefs.normalizar(None))
        if (tipo not in obligatorios
                and tipo in preferencias.get("tipos_silenciados", [])):
            omitidos.append({"usuario_id": destino,
                             "motivo": f"el usuario silencio el tipo {tipo}"})
            continue
        entregables.append(documento)

        quiere, _ = _prefs.debe_encolar_push(preferencias, tipo)
        tokens = dispositivos_por_usuario.get(destino) or []
        if quiere and tokens:
            cola.append(_prefs.sobre_push(documento, tokens))

    documentos = entregables
    if not documentos:
        if error_si_todos_silenciados:
            raise ErrorApi("TODOS_SILENCIARON",
                           "Todos los destinatarios silenciaron este tipo de "
                           "notificacion. No se envio nada.", 422)
        return {"lote_id": lote, "tipo": tipo, "enviadas": 0,
                "omitidas": len(omitidos), "omitidos": omitidos[:50],
                "push_encolados": 0, "destinatarios": []}, 200

    base()["notificaciones"].insert_many(documentos)
    if cola:
        base()["cola_push"].insert_many(cola)

    try:
        r = obtener_redis()
        tuberia = r.pipeline()
        for documento in documentos:
            tuberia.incr(_contador_clave(documento["destinatario_usuario_id"]))
        tuberia.execute()
    except Exception:
        app.logger.warning("No se pudo actualizar el contador en Redis")

    _bitacora("CATALOGO_MODIFICADO", "EXITO", recurso=lote)
    return {"lote_id": lote, "tipo": tipo,
            "enviadas": len(documentos),
            "omitidas": len(omitidos),
            "omitidos": omitidos[:50],
            "push_encolados": len(cola),
            "destinatarios": [d["destinatario_usuario_id"] for d in documentos][:50],
            "expira": expira.isoformat()}, 201


@app.post(BASE)
@requiere_permiso("CAMPANIA_ADMIN", "INTERVENCION_APROBAR", "PARAMETRO_ADMIN")
def enviar():
    limite_consumo(maximo=60)
    cuerpo = cuerpo_peticion()
    resultado, codigo = _validar_y_despachar(
        cuerpo,
        enviada_por=(g.actor or {}).get("sub"),
        error_si_todos_silenciados=True,
    )
    return responder(resultado, codigo, raiz="notificaciones_enviadas")


@app.post(f"{BASE}/evento-interno")
def evento_interno():
    """Recibe notificaciones internas firmadas servicio-a-servicio con HMAC-SHA256."""
    ts_str = (request.headers.get("X-Servicio-Timestamp") or "").strip()
    firma = (request.headers.get("X-Servicio-Firma") or "").strip()
    if not ts_str or not firma:
        raise ErrorApi("FIRMA_AUSENTE",
                       "Faltan cabeceras de autenticacion entre servicios.", 401)
    try:
        ts = int(ts_str)
    except ValueError:
        raise ErrorApi("FIRMA_INVALIDA",
                       "El encabezado X-Servicio-Timestamp es invalido.", 401)
    if abs(time.time() - ts) > 60:
        raise ErrorApi("TIMESTAMP_EXPIRADO",
                       "La marca de tiempo de la firma excedio la tolerancia de 60s.", 401)

    secreto = os.environ.get("JWT_SECRETO") or JWT_SECRETO
    if not secreto:
        raise ErrorApi("CONFIGURACION", "Falta JWT_SECRETO en este ambiente", 500)

    crudo = request.get_data() or b""
    esperada = hmac.new(
        secreto.encode("utf-8"),
        f"{ts_str}.".encode("utf-8") + crudo,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(firma.lower(), esperada.lower()):
        raise ErrorApi("FIRMA_INVALIDA",
                       "La firma HMAC-SHA256 del evento interno no es valida.", 401)

    try:
        cuerpo = json.loads(crudo.decode("utf-8") or "{}")
    except Exception:
        raise ErrorApi("JSON_INVALIDO", "El cuerpo del evento interno no es JSON valido.", 400)
    if not isinstance(cuerpo, dict):
        raise ErrorApi("VALIDACION", "El cuerpo del evento debe ser un objeto JSON.", 422)

    resultado, codigo = _validar_y_despachar(
        cuerpo,
        enviada_por="sistema-interno",
        error_si_todos_silenciados=False,
    )
    return responder(resultado, codigo, raiz="notificaciones_enviadas")


# --------------------------------------------------- preferencias
@app.get(f"{BASE}/preferencias")
@requiere_token
def leer_preferencias():
    """Las preferencias del usuario que llama. Siempre completas.

    Un usuario que nunca guardó nada recibe los valores por omisión en
    lugar de un 404: la pantalla que las dibuja no tiene por qué saber si
    alguna vez se guardaron, y un 404 la obligaría a tener dos caminos
    para algo que siempre tiene respuesta.
    """
    limite_consumo(maximo=120)
    usuario = (g.actor or {}).get("sub")
    guardadas = base()["preferencias_notificacion"].find_one({"usuario_id": usuario})
    return responder(
        {"usuario_id": usuario,
         "preferencias": _prefs.normalizar((guardadas or {}).get("preferencias")),
         "tipos_disponibles": sorted(TIPOS),
         "nota": "El push viene apagado por omision. Si viniera encendido, la "
                 "primera notificacion llegaria a la pantalla bloqueada de "
                 "alguien que nunca eligio eso, y para entonces ya paso."},
        200, raiz="preferencias_respuesta")


@app.put(f"{BASE}/preferencias")
@requiere_token
def guardar_preferencias():
    """Guarda las preferencias del usuario que llama, y de nadie más.

    El usuario sale del token, nunca del cuerpo: si viniera del cuerpo,
    cualquiera podría apagarle las notificaciones a otra persona.
    """
    limite_consumo(maximo=60)
    usuario = (g.actor or {}).get("sub")
    cuerpo = cuerpo_peticion()
    crudas = cuerpo.get("preferencias", cuerpo)

    problemas = _prefs.validar(crudas)
    desconocidos = [t for t in (crudas.get("tipos_silenciados") or [])
                    if str(t).upper() not in TIPOS]
    if desconocidos:
        problemas.append({
            "campo": "tipos_silenciados",
            "problema": f"tipos que no existen: {', '.join(map(str, desconocidos))}"})
    if problemas:
        raise ErrorApi("VALIDACION", "Las preferencias tienen campos invalidos.",
                       422, problemas)

    preferencias = _prefs.normalizar(crudas)
    base()["preferencias_notificacion"].update_one(
        {"usuario_id": usuario},
        {"$set": {"usuario_id": usuario, "preferencias": preferencias,
                  "fecha_actualizacion": dt.datetime.now(dt.timezone.utc)}},
        upsert=True)

    _bitacora("CATALOGO_MODIFICADO", "EXITO", recurso=f"prefs:{usuario}")
    return responder({"usuario_id": usuario, "preferencias": preferencias},
                     200, raiz="preferencias_respuesta")


# ------------------------------------------------------ dispositivos
@app.post(f"{BASE}/dispositivos")
@requiere_token
def registrar_dispositivo():
    """Registra el token de push de un teléfono.

    Se guarda por (usuario, token) y no solo por usuario: una persona
    puede tener el teléfono y la tableta, y guardar solo el último dejaría
    al otro aparato sin avisos sin que nadie lo note.
    """
    limite_consumo(maximo=30)
    cuerpo = cuerpo_peticion()
    token = (cuerpo.get("token") or "").strip()
    plataforma = (cuerpo.get("plataforma") or "").strip().upper()

    problemas = []
    if len(token) < 20:
        problemas.append({"campo": "token", "problema": "no parece un token valido"})
    if plataforma not in ("ANDROID", "IOS", "ESCRITORIO"):
        problemas.append({"campo": "plataforma",
                          "problema": "debe ser ANDROID, IOS o ESCRITORIO"})
    if problemas:
        raise ErrorApi("VALIDACION", "La solicitud tiene campos invalidos.",
                       422, problemas)

    usuario = (g.actor or {}).get("sub")
    base()["dispositivos_push"].update_one(
        {"usuario_id": usuario, "token": token},
        {"$set": {"usuario_id": usuario, "token": token,
                  "plataforma": plataforma,
                  "fecha_registro": dt.datetime.now(dt.timezone.utc)}},
        upsert=True)
    return responder({"registrado": True, "plataforma": plataforma},
                     201, raiz="dispositivo_registrado")


@app.delete(f"{BASE}/dispositivos")
@requiere_token
def borrar_dispositivo():
    """Da de baja un token. Lo llama la aplicación al cerrar sesión.

    Sin esto, un teléfono del que alguien cerró sesión seguiría recibiendo
    avisos de una cuenta que ya no está abierta ahí.
    """
    limite_consumo(maximo=30)
    token = (cuerpo_peticion().get("token") or "").strip()
    usuario = (g.actor or {}).get("sub")
    resultado = base()["dispositivos_push"].delete_one(
        {"usuario_id": usuario, "token": token})
    return responder({"borrados": resultado.deleted_count},
                     200, raiz="dispositivo_borrado")


# -------------------------------------------------------- cola de push
@app.get(f"{BASE}/push/pendientes")
@requiere_permiso("PARAMETRO_ADMIN")
def push_pendientes():
    """Lo que el repartidor tiene que entregar.

    Este servicio NO habla con Firebase ni con APNs: decide quién debe
    recibir un push y lo deja aquí. La entrega la hace un repartidor
    aparte, que es el único componente que necesita las credenciales del
    proveedor.

    No es una tarea pendiente, es una separación a propósito: meter esas
    credenciales en el servicio que además lee la base de notificaciones
    significa que cualquier fallo aquí las expone.
    """
    limite_consumo(maximo=240)
    p, t = pagina()
    cursor_mongo = (base()["cola_push"]
                    .find({"estado": "PENDIENTE"}, {"_id": 0})
                    .sort("fecha_encolado", ASCENDING)
                    .skip((p - 1) * t).limit(t))
    total = base()["cola_push"].count_documents({"estado": "PENDIENTE"})
    elementos = [_limpiar(d) for d in cursor_mongo]
    return responder(sobre_pagina(elementos, total, p, t, clave="pendientes"),
                     200, raiz="push_pendientes_respuesta")


@app.put(f"{BASE}/push/<push_id>")
@requiere_permiso("PARAMETRO_ADMIN")
def marcar_push(push_id):
    """El repartidor informa cómo le fue.

    Un envío fallido NO se borra: se le suma un intento y se deja
    pendiente, salvo que el proveedor diga que el token ya no existe. Esa
    distinción es la que separa «reintentar» de «este teléfono se
    desinstaló»; sin ella, la cola reintentaría para siempre contra
    aparatos que ya no están.
    """
    limite_consumo(maximo=240)
    cuerpo = cuerpo_peticion()
    estado = (cuerpo.get("estado") or "").strip().upper()
    if estado not in ("ENTREGADO", "FALLIDO", "TOKEN_INVALIDO"):
        raise ErrorApi("ESTADO_INVALIDO",
                       "Estado valido: ENTREGADO, FALLIDO o TOKEN_INVALIDO.", 400)

    cola = base()["cola_push"]
    if estado == "FALLIDO":
        cola.update_one({"push_id": push_id},
                        {"$inc": {"intentos": 1},
                         "$set": {"ultimo_error": (cuerpo.get("error") or "")[:300]}})
    else:
        cola.update_one({"push_id": push_id},
                        {"$set": {"estado": estado,
                                  "fecha_cierre": dt.datetime.now(dt.timezone.utc)}})
        if estado == "TOKEN_INVALIDO":
            # El teléfono ya no tiene la aplicación: se deja de intentar.
            registro = cola.find_one({"push_id": push_id}) or {}
            for token in registro.get("dispositivos") or []:
                base()["dispositivos_push"].delete_one({"token": token})

    return responder({"push_id": push_id, "estado": estado},
                     200, raiz="push_actualizado")


# -------------------------------------------------------------- bandeja
@app.get(f"{BASE}/mias")
@requiere_token
def mias():
    """Cada quien ve solo lo suyo. El destinatario sale del token, no de la URL."""
    limite_consumo()
    p, t = pagina()
    usuario = g.actor.get("sub")
    filtro = {"destinatario_usuario_id": usuario}
    if request.args.get("solo_sin_leer") == "true":
        filtro["leida"] = False

    col = base()["notificaciones"]
    total = col.count_documents(filtro)
    filas = [_limpiar(d) for d in col.find(filtro)
             .sort("fecha_creacion", DESCENDING).skip((p - 1) * t).limit(t)]
    sin_leer = col.count_documents({"destinatario_usuario_id": usuario, "leida": False})

    datos = sobre_pagina(filas, total, p, t, clave="notificaciones")
    datos["sin_leer"] = sin_leer
    return responder(datos, 200, raiz="notificaciones_respuesta")


@app.get(f"{BASE}/sin-leer")
@requiere_token
def sin_leer():
    """Contador rápido, servido desde Redis cuando está disponible."""
    usuario = g.actor.get("sub")
    try:
        valor = obtener_redis().get(_contador_clave(usuario))
        if valor is not None:
            return responder({"usuario_id": usuario, "sin_leer": int(valor),
                              "origen": "redis"}, 200, raiz="contador")
    except Exception:
        pass
    n = base()["notificaciones"].count_documents(
        {"destinatario_usuario_id": usuario, "leida": False})
    return responder({"usuario_id": usuario, "sin_leer": n, "origen": "mongodb"},
                     200, raiz="contador")


@app.put(f"{BASE}/<notificacion_id>/leida")
@requiere_token
def marcar_leida(notificacion_id):
    limite_consumo()
    usuario = g.actor.get("sub")
    col = base()["notificaciones"]
    # El filtro incluye al destinatario: nadie puede marcar como leida la
    # notificacion de otra persona, ni siquiera conociendo su identificador.
    resultado = col.update_one(
        {"notificacion_id": notificacion_id, "destinatario_usuario_id": usuario,
         "leida": False},
        {"$set": {"leida": True,
                  "fecha_lectura": dt.datetime.now(dt.timezone.utc)}})
    if resultado.matched_count == 0:
        existe = col.count_documents({"notificacion_id": notificacion_id,
                                      "destinatario_usuario_id": usuario})
        if existe:
            return responder({"notificacion_id": notificacion_id, "leida": True,
                              "mensaje": "Ya estaba marcada como leida."},
                             200, raiz="notificacion_actualizada")
        raise ErrorApi("NOTIFICACION_NO_ENCONTRADA",
                       "No existe esa notificacion para este usuario.", 404)

    try:
        r = obtener_redis()
        if int(r.get(_contador_clave(usuario)) or 0) > 0:
            r.decr(_contador_clave(usuario))
    except Exception:
        pass

    return responder({"notificacion_id": notificacion_id, "leida": True},
                     200, raiz="notificacion_actualizada")


@app.get(f"{BASE}/resumen")
@requiere_permiso("BITACORA_CONSULTAR", "PARAMETRO_ADMIN", "CAMPANIA_ADMIN")
def resumen():
    """Agregación: cuántas se enviaron por tipo y cuántas se leyeron."""
    limite_consumo()
    tuberia = [
        {"$group": {"_id": "$tipo",
                    "enviadas": {"$sum": 1},
                    "leidas": {"$sum": {"$cond": ["$leida", 1, 0]}}}},
        {"$sort": {"enviadas": -1}},
    ]
    filas = []
    for r in base()["notificaciones"].aggregate(tuberia):
        enviadas = r["enviadas"]
        filas.append({"tipo": r["_id"], "enviadas": enviadas, "leidas": r["leidas"],
                      "porcentaje_lectura": round(100.0 * r["leidas"] / enviadas, 1)
                      if enviadas else 0.0})
    return responder({"resumen": filas, "tipos_disponibles":
                      [{"tipo": k, "descripcion": v} for k, v in sorted(TIPOS.items())]},
                     200, raiz="resumen_respuesta")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PUERTO", "8104")))
