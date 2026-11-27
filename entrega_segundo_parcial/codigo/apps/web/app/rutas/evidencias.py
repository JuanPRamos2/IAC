"""
Carga de archivos de evidencia.

QUÉ ES UNA EVIDENCIA AQUÍ
-------------------------
El acta de una sesión de acompañamiento, la minuta de un comité, el
material de una campaña de descanso: documentos que respaldan que un plan
de intervención se ejecutó de verdad. Sin ellos, el seguimiento de una
intervención es la palabra de quien la reporta.

DÓNDE QUEDA CADA COSA
---------------------
El archivo queda en el almacén de blobs (una carpeta en developer, un
bucket de objetos en production) y los METADATOS en MongoDB, a través de
documents-service. La separación importa: MongoDB no es un almacén de
archivos, y guardar un PDF de 8 MB como documento haría lenta cualquier
consulta de la colección.

SEIS DECISIONES QUE NO SE VEN EN LA PANTALLA
--------------------------------------------
1. **El nombre del archivo que manda el navegador NO se usa como ruta.**
   Un nombre como `../../etc/passwd` escribiría fuera de la carpeta. El
   archivo se guarda bajo el SHA-256 de su contenido, y el nombre original
   se conserva solo como metadato.

2. **El tipo se decide por el contenido, no por la extensión.** Un
   ejecutable renombrado a `.pdf` pasaría cualquier validación de
   extensión. Se leen los primeros bytes y se compara con la firma del
   formato declarado.

3. **El hash es la identidad.** Subir dos veces el mismo archivo no lo
   duplica: se reconoce y se reutiliza. Y ese mismo hash permite después
   verificar que el archivo que alguien descargó es el que se subió.

4. **Una evidencia no se modifica.** Una corrección es un archivo nuevo
   con su propia fecha; el anterior se conserva. Es la misma regla que
   documents-service aplica a las evidencias de consentimiento, y por el
   mismo motivo: una evidencia editable no es evidencia.

5. **No se aceptan archivos sin intervención ni unidad.** Un archivo
   suelto, sin saber a qué plan pertenece, es basura que nadie podrá
   interpretar en seis meses.

6. **Se registra la descarga, no solo la carga.** La carga es trabajo
   normal; la descarga es el momento en que la información sale del
   sistema, y es la que un comité querrá revisar.
"""
import hashlib
import os
import re
import unicodedata

import requests
from flask import (Blueprint, Response, current_app, flash, g, redirect,
                   render_template, request, url_for)

from ..bitacora import registrar
from ..datos import consultar, consultar_uno
from ..seguridad import COOKIE, requiere_permiso

bp = Blueprint("evidencias", __name__, url_prefix="/evidencias")

def _servicio():
    """Se lee en cada peticion, no al importar el modulo."""
    return os.environ.get("DOCUMENTS_SERVICE_URL", "")


def _tiempo_limite():
    return float(os.environ.get("MICROSERVICIO_TIMEOUT", "2.5"))

# En developer es una carpeta; en production, el punto de montaje del
# bucket de objetos. El codigo no cambia: lo que cambia es la variable.
def _almacen():
    """La carpeta del almacén, leída en cada operación.

    En developer es una carpeta; en production, el punto de montaje del
    bucket de objetos. Leerla en cada operación en lugar de al importar
    permite que un envoltorio de arranque la defina después de cargar los
    módulos, que es lo que hacen varios servidores de aplicación.
    """
    return os.environ.get("ALMACEN_EVIDENCIAS", "/var/lib/bienestar/evidencias")

TAMANO_MAXIMO = int(os.environ.get("EVIDENCIA_TAMANO_MAXIMO", str(8 * 1024 * 1024)))

# Firma real de cada formato admitido. Un ejecutable renombrado a .pdf
# pasaria una validacion de extension; no pasa esta.
FIRMAS = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    # Office moderno es un ZIP: la firma es la del contenedor.
    "docx": [b"PK\x03\x04", b"PK\x05\x06"],
    "xlsx": [b"PK\x03\x04", b"PK\x05\x06"],
    # Texto plano y CSV no tienen firma; se valida que sea decodificable.
    "txt": [],
    "csv": [],
}
TIPOS_MIME = {
    "pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "txt": "text/plain; charset=utf-8", "csv": "text/csv; charset=utf-8",
}


def _extension(nombre):
    return (nombre or "").rsplit(".", 1)[-1].lower() if "." in (nombre or "") else ""


def _nombre_presentable(nombre):
    """Limpia el nombre para MOSTRARLO. Nunca se usa como ruta."""
    nombre = unicodedata.normalize("NFKD", nombre or "")
    nombre = nombre.encode("ascii", "ignore").decode("ascii")
    nombre = re.sub(r"[^A-Za-z0-9._ -]", "_", nombre).strip()
    # Las secuencias de puntos se colapsan: el nombre nunca se usa como
    # ruta, pero uno que se muestre como "..__..__tmp_acta.pdf" solo
    # confunde a quien lo lee en la tabla.
    nombre = re.sub(r"\.{2,}", ".", nombre).lstrip("._-")
    return (nombre or "sin_nombre")[:120]


def _firma_coincide(contenido, extension):
    firmas = FIRMAS.get(extension)
    if firmas is None:
        return False
    if not firmas:                       # txt y csv: tiene que ser texto
        try:
            contenido[:4096].decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return any(contenido.startswith(f) for f in firmas)


def _ruta_de(sha256):
    """Dos niveles de subcarpeta por los primeros caracteres del hash.

    Un directorio plano con decenas de miles de archivos se vuelve lento
    de listar en casi cualquier sistema de archivos.
    """
    return os.path.join(_almacen(), sha256[:2], sha256[2:4], sha256)


def _llamar_documentos(ruta, metodo="GET", json_cuerpo=None):
    servicio = _servicio()
    if not servicio:
        return None, ("Este ambiente no tiene configurada la direccion de "
                      "documents-service (DOCUMENTS_SERVICE_URL).")
    try:
        token = request.cookies.get(COOKIE, "")
        r = requests.request(
            metodo, f"{servicio}{ruta}", json=json_cuerpo,
            headers={"Authorization": f"Bearer {token}",
                     "X-Correlacion-Id": getattr(g, "correlacion_id", "")},
            timeout=_tiempo_limite())
        if r.status_code >= 500:
            return None, f"documents-service respondio {r.status_code}."
        return r.json(), None
    except Exception as e:
        current_app.logger.warning("documents-service no respondio: %s", e)
        return None, ("No se pudo contactar a documents-service. Los "
                      "metadatos de las evidencias viven en MongoDB a traves "
                      "de ese servicio: sin el, el archivo se podria guardar "
                      "pero quedaria sin registro, que es peor que no "
                      "guardarlo.")


@bp.get("/")
@requiere_permiso("INTERVENCION_SEGUIMIENTO", "INTERVENCION_APROBAR",
                  "BITACORA_CONSULTAR")
def listar():
    intervencion = request.args.get("intervencion_id") or ""
    consulta = "?tipo=REPORTE_ORGANIZACIONAL&tamano=50"
    datos, problema = _llamar_documentos(f"/api/v1/documentos{consulta}")

    evidencias = []
    for d in (datos or {}).get("elementos", []):
        contenido = d.get("contenido") or {}
        if contenido.get("clase") != "EVIDENCIA_ARCHIVO":
            continue
        if intervencion and contenido.get("intervencion_id") != intervencion:
            continue
        evidencias.append({**d, **contenido})

    planes = consultar(
        "SELECT p.intervencion_id, p.tipo_intervencion, p.estado, "
        "       uo.nombre AS unidad, p.unidad_organizacional_id "
        "  FROM intervencion.plan p "
        "  JOIN organizacion.unidad_organizacional uo "
        "       USING (unidad_organizacional_id) "
        " ORDER BY p.fecha_inicio DESC LIMIT 50")

    return render_template("intervencion/evidencias.html", evidencias=evidencias,
                           planes=planes, problema=problema,
                           intervencion=intervencion,
                           formatos=sorted(FIRMAS),
                           tamano_maximo_mb=round(TAMANO_MAXIMO / 1024 / 1024, 1))


@bp.post("/")
@requiere_permiso("INTERVENCION_SEGUIMIENTO", "INTERVENCION_APROBAR")
def subir():
    archivo = request.files.get("archivo")
    intervencion_id = (request.form.get("intervencion_id") or "").strip()
    descripcion = (request.form.get("descripcion") or "").strip()

    if not archivo or not archivo.filename:
        flash("Elige un archivo.", "error")
        return redirect(url_for("evidencias.listar"))
    if not intervencion_id:
        flash("Indica a que plan de intervencion pertenece. Un archivo suelto, "
              "sin saber a que plan corresponde, es basura que nadie podra "
              "interpretar en seis meses.", "error")
        return redirect(url_for("evidencias.listar"))
    if len(descripcion) < 10:
        flash("Describe que es el archivo (al menos 10 caracteres).", "error")
        return redirect(url_for("evidencias.listar"))

    plan = consultar_uno(
        "SELECT intervencion_id, unidad_organizacional_id, campania_linea_base "
        "  FROM intervencion.plan WHERE intervencion_id = %s", (intervencion_id,))
    if not plan:
        flash(f"No existe el plan {intervencion_id}.", "error")
        return redirect(url_for("evidencias.listar"))

    extension = _extension(archivo.filename)
    if extension not in FIRMAS:
        flash(f"Formato no admitido. Validos: {', '.join(sorted(FIRMAS))}.",
              "error")
        return redirect(url_for("evidencias.listar"))

    contenido = archivo.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        flash(f"El archivo pasa de {TAMANO_MAXIMO // 1024 // 1024} MB.", "error")
        return redirect(url_for("evidencias.listar"))
    if not contenido:
        flash("El archivo esta vacio.", "error")
        return redirect(url_for("evidencias.listar"))

    # El tipo se decide por el CONTENIDO. Un ejecutable renombrado a .pdf
    # pasaria una validacion de extension; no pasa esta.
    if not _firma_coincide(contenido, extension):
        registrar("EVIDENCIA_CARGADA", "RECHAZADO",
                  tipo_recurso="EVIDENCIA", recurso=intervencion_id)
        flash(f"El contenido del archivo no corresponde a un {extension}. "
              f"La extension se puede cambiar; la firma del formato, no, y es "
              f"la que se comprueba.", "error")
        return redirect(url_for("evidencias.listar"))

    sha256 = hashlib.sha256(contenido).hexdigest()
    destino = _ruta_de(sha256)

    try:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        if os.path.exists(destino):
            # Mismo contenido ya almacenado: no se duplica. El hash es la
            # identidad del archivo, no su nombre.
            ya_estaba = True
        else:
            ya_estaba = False
            # Se escribe a un temporal y se renombra: un fallo a la mitad no
            # deja un archivo truncado con un hash que no le corresponde.
            temporal = destino + ".parcial"
            with open(temporal, "wb") as f:
                f.write(contenido)
            os.replace(temporal, destino)
    except OSError as e:
        current_app.logger.error("No se pudo escribir la evidencia: %s", e)
        flash("No se pudo guardar el archivo en el almacen. Revisa que "
              "ALMACEN_EVIDENCIAS exista y tenga permiso de escritura.", "error")
        return redirect(url_for("evidencias.listar"))

    # Los metadatos van a MongoDB por documents-service. El documento NO
    # lleva el contenido del archivo: solo su hash, su tamano y su ruta.
    cuerpo = {
        "tipo": "REPORTE_ORGANIZACIONAL",
        "unidad_organizacional_id": plan["unidad_organizacional_id"],
        "campania_id": plan.get("campania_linea_base"),
        "contenido": {
            "clase": "EVIDENCIA_ARCHIVO",
            "intervencion_id": intervencion_id,
            "descripcion": descripcion,
            "nombre_original": _nombre_presentable(archivo.filename),
            "formato": extension,
            "tipo_mime": TIPOS_MIME[extension],
            "bytes": len(contenido),
            "sha256": sha256,
            "cargado_por": g.sesion.get("sub"),
        },
    }
    datos, problema = _llamar_documentos("/api/v1/documentos", "POST", cuerpo)
    if problema:
        flash(problema, "error")
        return redirect(url_for("evidencias.listar"))
    error = (datos or {}).get("error")
    if error:
        flash(f"{error.get('codigo')}: {error.get('mensaje')}", "error")
        return redirect(url_for("evidencias.listar"))

    registrar("EVIDENCIA_CARGADA", "EXITO", tipo_recurso="EVIDENCIA",
              recurso=f"{intervencion_id}:{sha256[:16]}")
    if ya_estaba:
        flash(f"Archivo registrado. El contenido ya estaba almacenado (mismo "
              f"SHA-256): no se duplico, se reutilizo.", "ok")
    else:
        flash(f"Evidencia cargada ({len(contenido) // 1024} KB). "
              f"Sello SHA-256: {sha256[:16]}…", "ok")
    return redirect(url_for("evidencias.listar", intervencion_id=intervencion_id))


@bp.get("/<documento_id>/archivo")
@requiere_permiso("INTERVENCION_SEGUIMIENTO", "INTERVENCION_APROBAR",
                  "BITACORA_CONSULTAR")
def descargar(documento_id):
    """Entrega el archivo. Los metadatos deciden qué se entrega, no la URL."""
    datos, problema = _llamar_documentos(f"/api/v1/documentos/{documento_id}")
    if problema:
        flash(problema, "error")
        return redirect(url_for("evidencias.listar"))
    documento = (datos or {}).get("documento") or datos or {}
    contenido = documento.get("contenido") or {}
    sha256 = contenido.get("sha256") or ""

    # El identificador del archivo sale del documento registrado, nunca de
    # la peticion: asi nadie puede pedir un archivo arbitrario del almacen
    # pasando un hash en la URL.
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        flash("Ese documento no es una evidencia con archivo.", "error")
        return redirect(url_for("evidencias.listar"))

    ruta = _ruta_de(sha256)
    if not os.path.exists(ruta):
        flash("El registro existe pero el archivo no esta en el almacen. "
              "Es exactamente el caso que el sello permite detectar.", "error")
        return redirect(url_for("evidencias.listar"))

    with open(ruta, "rb") as f:
        bytes_archivo = f.read()

    # Se vuelve a calcular el hash: si el archivo del almacen fue alterado,
    # no se entrega. Guardar el sello y no comprobarlo nunca seria tenerlo
    # de adorno.
    if hashlib.sha256(bytes_archivo).hexdigest() != sha256:
        registrar("EVIDENCIA_DESCARGADA", "RECHAZADO",
                  tipo_recurso="EVIDENCIA", recurso=documento_id)
        flash("El archivo del almacen no coincide con su sello SHA-256: fue "
              "alterado despues de cargarse. No se entrega.", "error")
        return redirect(url_for("evidencias.listar"))

    registrar("EVIDENCIA_DESCARGADA", "EXITO", tipo_recurso="EVIDENCIA",
              recurso=documento_id)
    nombre = contenido.get("nombre_original") or f"evidencia.{contenido.get('formato', 'bin')}"
    return Response(
        bytes_archivo, 200,
        {"Content-Type": contenido.get("tipo_mime", "application/octet-stream"),
         "Content-Disposition": f'attachment; filename="{_nombre_presentable(nombre)}"',
         "X-Evidencia-Sello": sha256,
         # Sin esto, un navegador podria interpretar el archivo en lugar de
         # descargarlo.
         "X-Content-Type-Options": "nosniff"})
