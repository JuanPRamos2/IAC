"""
Administración de usuarios, perfiles y permisos en el sistema web.

Es la parte de interfaz del Integrante 1. Las pantallas llaman a
users-service cuando está disponible, y caen a la base de datos cuando no:
el sistema web debe seguir funcionando de manera independiente, que es un
requisito explícito de la arquitectura obligatoria.

Esa caída no es un parche: está escrita a propósito y la pantalla dice al
operador por cuál de las dos vías obtuvo los datos, para que durante la
demostración se pueda apagar el microservicio y ver que el portal aguanta.
"""
import os
from datetime import datetime, timedelta, timezone

import requests
from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, url_for)

from ..bitacora import registrar
from ..datos import consultar, consultar_uno, cursor
from ..seguridad import COOKIE, requiere_permiso

bp = Blueprint("administracion", __name__, url_prefix="/administracion")

def _servicio():
    """Se lee en cada peticion, no al importar el modulo."""
    return os.environ.get("USERS_SERVICE_URL", "")


def _tiempo_limite():
    return float(os.environ.get("MICROSERVICIO_TIMEOUT", "2.5"))


def _llamar_microservicio(ruta, metodo="GET", json_cuerpo=None):
    """Devuelve (datos, origen) u (None, 'base de datos') si no se pudo.

    Nunca lanza: si el microservicio no responde, la pantalla sigue.
    """
    servicio = _servicio()
    if not servicio:
        return None, "base de datos"
    try:
        token = request.cookies.get(COOKIE, "")
        r = requests.request(
            metodo, f"{servicio}{ruta}", json=json_cuerpo,
            headers={"Authorization": f"Bearer {token}",
                     "X-Correlacion-Id": getattr(g, "correlacion_id", "")},
            timeout=_tiempo_limite())
        if r.status_code >= 500:
            return None, "base de datos"
        return (r.json(), "users-service")
    except Exception as e:
        current_app.logger.warning("users-service no respondio (%s); se usa la base", e)
        return None, "base de datos"


@bp.get("/usuarios")
@requiere_permiso("USUARIO_ADMIN")
def usuarios():
    busqueda = (request.args.get("busqueda") or "").strip()
    perfil = request.args.get("perfil_id") or ""
    try:
        pagina = max(1, int(request.args.get("pagina", 1)))
    except ValueError:
        pagina = 1
    tamano = 15

    consulta = f"?pagina={pagina}&tamano={tamano}"
    if busqueda:
        consulta += f"&busqueda={busqueda}"
    if perfil:
        consulta += f"&perfil_id={perfil}"

    datos, origen = _llamar_microservicio(f"/api/v1/usuarios{consulta}")

    if datos and "usuarios" in datos:
        filas = datos["usuarios"]
        paginacion = datos["paginacion"]
    else:
        # Camino autónomo: la misma consulta contra PostgreSQL.
        filtros, params = ["1=1"], []
        if busqueda:
            filtros.append("(u.nombre ILIKE %s OR u.apellido_paterno ILIKE %s "
                           "OR u.correo ILIKE %s OR u.usuario_id ILIKE %s)")
            params += [f"%{busqueda}%"] * 4
        if perfil.isdigit():
            filtros.append("up.perfil_id = %s")
            params.append(int(perfil))
        donde = " AND ".join(filtros)
        total = consultar_uno(
            f"SELECT count(*) AS n FROM usuarios.usuario u "
            f"LEFT JOIN usuarios.usuario_perfil up USING (usuario_id) WHERE {donde}",
            tuple(params))["n"]
        filas = consultar(
            f"""SELECT u.usuario_id, u.nombre, u.apellido_paterno, u.correo,
                       u.activo, u.fecha_ultimo_acceso, up.perfil_id,
                       pf.nombre AS perfil, up.unidad_alcance_id
                  FROM usuarios.usuario u
                  LEFT JOIN usuarios.usuario_perfil up USING (usuario_id)
                  LEFT JOIN usuarios.perfil pf USING (perfil_id)
                 WHERE {donde} ORDER BY u.usuario_id LIMIT %s OFFSET %s""",
            tuple(params) + (tamano, (pagina - 1) * tamano))
        total_paginas = max(1, (total + tamano - 1) // tamano)
        paginacion = {"pagina": pagina, "tamano": tamano, "total": total,
                      "total_paginas": total_paginas,
                      "tiene_siguiente": pagina < total_paginas,
                      "tiene_anterior": pagina > 1}

    perfiles = consultar("SELECT perfil_id, nombre FROM usuarios.perfil ORDER BY perfil_id")
    unidades = consultar("SELECT unidad_organizacional_id, nombre "
                         "FROM organizacion.unidad_organizacional WHERE activa "
                         "ORDER BY nivel_jerarquico, nombre")
    return render_template("admin/usuarios.html", filas=filas, paginacion=paginacion,
                           perfiles=perfiles, unidades=unidades, origen=origen,
                           busqueda=busqueda, perfil_filtro=perfil)


@bp.post("/usuarios")
@requiere_permiso("USUARIO_ADMIN")
def crear_usuario():
    cuerpo = {
        "usuario_id": (request.form.get("usuario_id") or "").strip().upper(),
        "nombre": (request.form.get("nombre") or "").strip(),
        "apellido_paterno": (request.form.get("apellido_paterno") or "").strip(),
        "apellido_materno": (request.form.get("apellido_materno") or "").strip(),
        "correo": (request.form.get("correo") or "").strip(),
        "contrasena": request.form.get("contrasena") or "",
        "perfil_id": int(request.form.get("perfil_id") or 0) or None,
        "unidad_alcance_id": request.form.get("unidad_alcance_id") or None,
    }

    datos, origen = _llamar_microservicio("/api/v1/usuarios", "POST", cuerpo)
    if datos is not None:
        if "error" in datos:
            detalles = datos["error"].get("detalles") or []
            texto = "; ".join(f"{d['campo']}: {d['problema']}" for d in detalles)
            flash(f"{datos['error']['mensaje']} {texto}".strip(), "error")
        else:
            flash(f"Usuario {cuerpo['usuario_id']} creado mediante users-service.", "ok")
        return redirect(url_for("administracion.usuarios"))

    # Camino autónomo. Se repiten las validaciones: el sistema web no puede
    # confiar en que el microservicio haya validado si no lo llamó.
    problemas = []
    import re
    if not re.match(r"^USR-\d{5}$", cuerpo["usuario_id"]):
        problemas.append("el identificador debe tener la forma USR-00000")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", cuerpo["correo"]):
        problemas.append("el correo no es valido")
    if len(cuerpo["nombre"]) < 2 or len(cuerpo["apellido_paterno"]) < 2:
        problemas.append("nombre y apellido requieren al menos 2 caracteres")
    if len(cuerpo["contrasena"]) < 8:
        problemas.append("la contrasena requiere al menos 8 caracteres")
    if not cuerpo["perfil_id"]:
        problemas.append("falta el perfil")
    if problemas:
        flash("No se pudo crear: " + "; ".join(problemas) + ".", "error")
        return redirect(url_for("administracion.usuarios"))

    if consultar_uno("SELECT 1 AS x FROM usuarios.usuario WHERE usuario_id = %s "
                     "OR lower(correo) = lower(%s)",
                     (cuerpo["usuario_id"], cuerpo["correo"])):
        flash("Ya existe un usuario con ese identificador o ese correo.", "error")
        return redirect(url_for("administracion.usuarios"))

    try:
        with cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO usuarios.usuario (usuario_id, nombre, apellido_paterno, "
                " apellido_materno, correo, contrasena_hash) "
                "VALUES (%s,%s,%s,%s,%s, crypt(%s, gen_salt('bf')))",
                (cuerpo["usuario_id"], cuerpo["nombre"], cuerpo["apellido_paterno"],
                 cuerpo["apellido_materno"] or None, cuerpo["correo"],
                 cuerpo["contrasena"]))
            cur.execute("INSERT INTO usuarios.usuario_perfil "
                        "(usuario_id, perfil_id, unidad_alcance_id) VALUES (%s,%s,%s)",
                        (cuerpo["usuario_id"], cuerpo["perfil_id"],
                         cuerpo["unidad_alcance_id"]))
    except Exception as e:
        registrar("PERFIL_MODIFICADO", "ERROR_TECNICO",
                  tipo_recurso="USUARIO", recurso=cuerpo["usuario_id"])
        flash(f"No se pudo crear el usuario: {e}", "error")
        return redirect(url_for("administracion.usuarios"))

    registrar("PERFIL_MODIFICADO", "EXITO", tipo_recurso="USUARIO",
              recurso=cuerpo["usuario_id"])
    flash(f"Usuario {cuerpo['usuario_id']} creado (sin microservicio).", "ok")
    return redirect(url_for("administracion.usuarios"))


@bp.post("/usuarios/<usuario_id>/perfil")
@requiere_permiso("USUARIO_ADMIN")
def cambiar_perfil(usuario_id):
    try:
        perfil_id = int(request.form.get("perfil_id") or 0)
    except ValueError:
        perfil_id = 0
    alcance = request.form.get("unidad_alcance_id") or None
    if not perfil_id:
        flash("Perfil invalido.", "error")
        return redirect(url_for("administracion.usuarios"))

    datos, origen = _llamar_microservicio(
        f"/api/v1/usuarios/{usuario_id}/perfil", "PUT",
        {"perfil_id": perfil_id, "unidad_alcance_id": alcance})

    if datos is not None and "error" not in datos:
        flash(f"Perfil actualizado mediante users-service. "
              f"Sesiones revocadas: {datos.get('sesiones_revocadas', 0)}.", "ok")
        return redirect(url_for("administracion.usuarios"))

    with cursor(commit=True) as cur:
        cur.execute("DELETE FROM usuarios.usuario_perfil WHERE usuario_id = %s",
                    (usuario_id,))
        cur.execute("INSERT INTO usuarios.usuario_perfil "
                    "(usuario_id, perfil_id, unidad_alcance_id) VALUES (%s,%s,%s)",
                    (usuario_id, perfil_id, alcance))
    registrar("PERFIL_MODIFICADO", "EXITO", tipo_recurso="USUARIO", recurso=usuario_id)
    flash(f"Perfil de {usuario_id} actualizado.", "ok")
    return redirect(url_for("administracion.usuarios"))


@bp.post("/usuarios/<usuario_id>/estado")
@requiere_permiso("USUARIO_ADMIN")
def cambiar_estado(usuario_id):
    activo = request.form.get("activo") == "1"
    if usuario_id == g.sesion["sub"] and not activo:
        flash("No puedes desactivar tu propia cuenta: dejaria al sistema "
              "potencialmente sin administradores operativos.", "error")
        return redirect(url_for("administracion.usuarios"))

    datos, origen = _llamar_microservicio(
        f"/api/v1/usuarios/{usuario_id}/estado", "PUT", {"activo": activo})
    if datos is not None and "error" not in datos:
        flash(f"Estado actualizado mediante users-service.", "ok")
        return redirect(url_for("administracion.usuarios"))

    with cursor(commit=True) as cur:
        cur.execute("UPDATE usuarios.usuario SET activo = %s, "
                    "fecha_actualizacion = now() WHERE usuario_id = %s",
                    (activo, usuario_id))
    registrar("PERFIL_MODIFICADO", "EXITO", tipo_recurso="USUARIO", recurso=usuario_id)
    flash(f"Usuario {usuario_id} {'activado' if activo else 'desactivado'}.", "ok")
    return redirect(url_for("administracion.usuarios"))


@bp.get("/permisos")
@requiere_permiso("USUARIO_ADMIN", "BITACORA_CONSULTAR")
def permisos():
    """Matriz de perfiles contra permisos, calculada desde la base.

    Es la misma matriz del documento de actores, pero viva: si alguien
    cambia un permiso, esta pantalla lo muestra sin que nadie actualice
    un documento.
    """
    perfiles = consultar("SELECT perfil_id, codigo, nombre FROM usuarios.perfil "
                         "ORDER BY perfil_id")
    permisos_lista = consultar("SELECT permiso_id, codigo, descripcion, sensible "
                               "FROM usuarios.permiso ORDER BY permiso_id")
    asignados = consultar("SELECT perfil_id, permiso_id FROM usuarios.perfil_permiso")
    matriz = {(a["perfil_id"], a["permiso_id"]) for a in asignados}
    return render_template("admin/permisos.html", perfiles=perfiles,
                           permisos=permisos_lista, matriz=matriz)


def _clasificar_sonda(respuesta):
    """Separa proceso caído, dependencia esencial caída y degradado.

    Un 503 con cuerpo es un servicio vivo que dice qué le falta. Tratarlo
    como degradado escondía esa diferencia en el panel: el operador no
    sabía si había que reiniciar el contenedor o revisar la base.
    """
    cuerpo = {}
    try:
        cuerpo = respuesta.json()
    except Exception:
        cuerpo = {}
    bruto = (cuerpo.get("estado") or "").lower()
    if respuesta.status_code == 200 and bruto == "degradado":
        estado = "DEGRADADO"
    elif respuesta.status_code == 200:
        estado = "DISPONIBLE"
    elif respuesta.status_code == 503 or bruto == "no_listo":
        estado = "NO_LISTO"
    else:
        estado = "DEGRADADO"
    if cuerpo.get("falta"):
        detalle = "falta: " + ", ".join(cuerpo["falta"])
    elif cuerpo.get("degradado_por"):
        detalle = "degradado por: " + ", ".join(cuerpo["degradado_por"])
    else:
        detalle = cuerpo.get("estado") or ""
    return (estado, detalle, cuerpo.get("dependencias") or {},
            cuerpo.get("version_desplegada") or "",
            cuerpo.get("no_aplican") or [])


def _guardar_sondas(filas):
    """Deja el sondeo en la base. Sin la migración 022 el panel sigue igual."""
    try:
        with cursor(commit=True) as cur:
            for fila in filas:
                cur.execute(
                    "INSERT INTO auditoria.sonda_disponibilidad "
                    "(servicio, estado, latencia_ms, detalle) VALUES (%s,%s,%s,%s)",
                    (fila["servicio"], fila["estado"], fila["ms"],
                     (fila["detalle"] or "")[:200]))
    except Exception:
        current_app.logger.info(
            "Historial de disponibilidad no disponible; aplica la migracion 022.")


def _historial_24h():
    try:
        filas = consultar(
            "SELECT servicio, count(*) AS muestras, "
            "       count(*) FILTER (WHERE estado = 'DISPONIBLE') AS disponibles, "
            "       count(*) FILTER (WHERE estado = 'DEGRADADO') AS degradados, "
            "       count(*) FILTER (WHERE estado = 'NO_LISTO') AS sin_dependencia, "
            "       count(*) FILTER (WHERE estado = 'CAIDO') AS caidos, "
            "       max(momento) AS ultima "
            "  FROM auditoria.sonda_disponibilidad "
            " WHERE momento > now() - interval '24 hours' "
            " GROUP BY servicio ORDER BY servicio")
    except Exception:
        return []
    salida = []
    for fila in filas:
        muestras = fila["muestras"] or 0
        fila = dict(fila)
        fila["disponibilidad"] = round(100.0 * (fila["disponibles"] or 0) / muestras, 1) if muestras else 0
        salida.append(fila)
    return salida


def _errores_24h():
    try:
        total = consultar_uno(
            "SELECT count(*) AS n FROM auditoria.bitacora "
            " WHERE fecha_hora > now() - interval '24 hours' "
            "   AND resultado <> 'EXITO'")
        por_accion = consultar(
            "SELECT accion, resultado, count(*) AS n, max(fecha_hora) AS ultimo "
            "  FROM auditoria.bitacora "
            " WHERE fecha_hora > now() - interval '24 hours' "
            "   AND resultado <> 'EXITO' "
            " GROUP BY accion, resultado ORDER BY n DESC LIMIT 8")
    except Exception:
        return None, []
    return (total or {}).get("n", 0), por_accion


@bp.get("/servicios")
@requiere_permiso("PARAMETRO_ADMIN", "USUARIO_ADMIN")
def servicios():
    """Monitoreo de los microservicios: disponible, degradado, sin dependencia o caído.

    Consulta el endpoint de salud de cada uno. Es lo que permite demostrar
    que el sistema web sigue operando con los microservicios apagados.
    """
    # Los veinticuatro, con el integrante y el lenguaje. La pregunta que
    # sigue a "esta caido" es "de quien es".
    catalogo = [
        ("auth-service", "Integrante 1", "Python",
         os.environ.get("AUTH_SERVICE_URL", "http://auth-service:8000")),
        ("users-service", "Integrante 1", "Python",
         os.environ.get("USERS_SERVICE_URL", "http://users-service:8000")),
        ("catalog-service", "Integrante 2", "Node",
         os.environ.get("CATALOG_SERVICE_URL", "http://catalog-service:8000")),
        ("main-process-service", "Integrante 2", "Node",
         os.environ.get("MAIN_PROCESS_SERVICE_URL",
                        "http://main-process-service:8000")),
        ("documents-service", "Integrante 4", "Python",
         os.environ.get("DOCUMENTS_SERVICE_URL", "http://documents-service:8000")),
        ("notifications-service", "Integrante 4", "Python",
         os.environ.get("NOTIFICATIONS_SERVICE_URL",
                        "http://notifications-service:8000")),
        ("queries-service", "Integrante 3", "Python",
         os.environ.get("QUERIES_SERVICE_URL", "http://queries-service:8000")),
        ("reports-service", "Integrante 3", "Python",
         os.environ.get("REPORTS_SERVICE_URL", "http://reports-service:8000")),
        ("algorithms-service", "Integrante 3", "Python",
         os.environ.get("ALGORITHMS_SERVICE_URL", "http://algorithms-service:8000")),
        ("consent-service", "Integrante 1", "Python",
         os.environ.get("CONSENT_SERVICE_URL", "http://consent-service:8000")),
        ("privacy-service", "Integrante 1", "Python",
         os.environ.get("PRIVACY_SERVICE_URL", "http://privacy-service:8000")),
        ("survey-service", "Integrante 2", "Node",
         os.environ.get("SURVEY_SERVICE_URL", "http://survey-service:8000")),
        ("indicators-service", "Integrante 2", "Node",
         os.environ.get("INDICATORS_SERVICE_URL", "http://indicators-service:8000")),
        ("trends-service", "Integrante 3", "Python",
         os.environ.get("TRENDS_SERVICE_URL", "http://trends-service:8000")),
        ("interventions-service", "Integrante 3", "Python",
         os.environ.get("INTERVENTIONS_SERVICE_URL",
                        "http://interventions-service:8000")),
        ("support-service", "Integrante 2", "Node",
         os.environ.get("SUPPORT_SERVICE_URL", "http://support-service:8000")),
        ("organizational-service", "Integrante 2", "Node",
         os.environ.get("ORGANIZATIONAL_SERVICE_URL",
                        "http://organizational-service:8000")),
        ("audit-service", "Integrante 1", "Python",
         os.environ.get("AUDIT_SERVICE_URL", "http://audit-service:8000")),
        ("data-governance-service", "Integrante 1", "Python",
         os.environ.get("DATA_GOVERNANCE_SERVICE_URL",
                        "http://data-governance-service:8000")),
        ("sync-service", "Integrante 4", "Python",
         os.environ.get("SYNC_SERVICE_URL", "http://sync-service:8000")),
        ("export-service", "Integrante 3", "Python",
         os.environ.get("EXPORT_SERVICE_URL", "http://export-service:8000")),
        ("configuration-service", "Integrante 4", "Python",
         os.environ.get("CONFIGURATION_SERVICE_URL",
                        "http://configuration-service:8000")),
        ("monitoring-service", "Integrante 4", "Python",
         os.environ.get("MONITORING_SERVICE_URL", "http://monitoring-service:8000")),
        ("integration-service", "Integrante 4", "Python",
         os.environ.get("INTEGRATION_SERVICE_URL",
                        "http://integration-service:8000")),
    ]
    import time
    filas = []
    for nombre, responsable, lenguaje, url in catalogo:
        inicio = time.perf_counter()
        estado, detalle, dependencias, version, no_aplican = "CAIDO", "", {}, "", []
        try:
            r = requests.get(f"{url}/health/ready", timeout=_tiempo_limite())
            estado, detalle, dependencias, version, no_aplican = _clasificar_sonda(r)
        except Exception as e:
            detalle = str(e)[:120]
        filas.append({
            "servicio": nombre, "responsable": responsable, "lenguaje": lenguaje,
            "url": url, "estado": estado, "detalle": detalle, "version": version,
            "ms": round((time.perf_counter() - inicio) * 1000, 1),
            "dependencias": dependencias, "no_aplican": no_aplican,
        })
    _guardar_sondas(filas)
    errores_n, errores = _errores_24h()
    verificacion = datetime.now(timezone(timedelta(hours=-6))).strftime("%Y-%m-%d %H:%M:%S")
    return render_template("admin/servicios.html", filas=filas,
                           verificacion=verificacion, errores_n=errores_n,
                           errores=errores, historial=_historial_24h())
