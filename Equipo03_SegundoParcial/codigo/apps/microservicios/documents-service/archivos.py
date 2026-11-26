"""
Validación, almacenamiento y recuperación de archivos de evidencia.

Soporta almacenamiento dual mediante ``ALMACEN_MODO``:
  - ``local`` (por defecto): carpeta en ``ALMACEN_EVIDENCIAS`` + URLs firmadas con HMAC-SHA256.
  - ``gcs``: Google Cloud Storage en ``GCS_BUCKET_NAME`` + ``blob.generate_signed_url``.
"""
import datetime as dt
import hashlib
import hmac
import os
import re
import time
import unicodedata

from comun import ErrorApi

# 8 MB. Un acta, una minuta o una foto de una sesión caben de sobra; un
# video no, y no es lo que una evidencia de intervención debe ser.
TAMANO_MAXIMO = int(os.environ.get("EVIDENCIA_TAMANO_MAXIMO", str(8 * 1024 * 1024)))

# Firma real de cada formato admitido.
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
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "txt": "text/plain; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
}


def modo_almacen() -> str:
    return (os.environ.get("ALMACEN_MODO") or "local").strip().lower()


def bucket_gcs() -> str:
    return (os.environ.get("GCS_BUCKET_NAME") or os.environ.get("GCS_BUCKET") or "").strip()


def _llave_gcs() -> str:
    llave = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    return llave if llave and os.path.isfile(llave) else ""


def ttl_url_firmada() -> int:
    try:
        ttl = int(os.environ.get("URL_FIRMADA_TTL_SEG", "300"))
    except ValueError:
        ttl = 300
    return max(10, min(ttl, 3600))


def almacen():
    """Carpeta del almacén local, leída en cada operación."""
    return os.environ.get("ALMACEN_EVIDENCIAS", "/var/lib/bienestar/evidencias")


def _secreto_firma() -> str:
    secreto = os.environ.get("JWT_SECRETO")
    if secreto:
        return secreto
    if os.environ.get("APP_AMBIENTE", "developer") == "developer":
        return "secreto-solo-para-developer"
    raise ErrorApi("CONFIGURACION", "Falta JWT_SECRETO para firmar descargas.", 500)


def _bucket_cliente_gcs():
    nombre = bucket_gcs()
    if not nombre:
        raise ErrorApi(
            "CONFIGURACION",
            "Falta GCS_BUCKET_NAME (o GCS_BUCKET) para el modo de almacenamiento gcs.",
            500,
        )
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise ErrorApi(
            "CONFIGURACION",
            f"Falta dependencia google-cloud-storage: {exc}",
            500,
        )
    llave = _llave_gcs()
    cliente = (
        storage.Client.from_service_account_json(llave)
        if llave
        else storage.Client()
    )
    return cliente.bucket(nombre)


def extension_de(nombre):
    nombre = nombre or ""
    return nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""


def nombre_presentable(nombre):
    """Limpia el nombre para MOSTRARLO. Nunca se usa como ruta."""
    nombre = unicodedata.normalize("NFKD", nombre or "")
    nombre = nombre.encode("ascii", "ignore").decode("ascii")
    nombre = re.sub(r"[^A-Za-z0-9._ -]", "_", nombre).strip()
    nombre = re.sub(r"\.{2,}", ".", nombre).lstrip("._-")
    return (nombre or "sin_nombre")[:120]


def firma_coincide(contenido, extension):
    firmas = FIRMAS.get(extension)
    if firmas is None:
        return False
    if not firmas:                        # txt y csv: tiene que ser texto
        try:
            contenido[:4096].decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return any(contenido.startswith(f) for f in firmas)


def ruta_objeto_de(sha256: str) -> str:
    return f"{sha256[:2]}/{sha256[2:4]}/{sha256}"


def ruta_logica_de(sha256: str) -> str:
    objeto = ruta_objeto_de(sha256)
    if modo_almacen() == "gcs":
        return f"gs://{bucket_gcs()}/{objeto}"
    return objeto


def ruta_de(sha256):
    """Dos niveles de subcarpeta por los primeros caracteres del hash."""
    return os.path.join(almacen(), sha256[:2], sha256[2:4], sha256)


def validar(contenido, nombre_original):
    """Valida formato y tamaño. Devuelve (extension, sha256, nombre)."""
    problemas = []

    if not contenido:
        problemas.append({"campo": "archivo", "problema": "esta vacio"})
    elif len(contenido) > TAMANO_MAXIMO:
        problemas.append({
            "campo": "archivo",
            "problema": f"pesa {len(contenido)} bytes y el maximo son "
                        f"{TAMANO_MAXIMO} ({TAMANO_MAXIMO // 1024 // 1024} MB)"})

    extension = extension_de(nombre_original)
    if extension not in FIRMAS:
        problemas.append({
            "campo": "nombre_archivo",
            "problema": f"formato '{extension or 'sin extension'}' no admitido; "
                        f"validos: {', '.join(sorted(FIRMAS))}"})
    elif contenido and not firma_coincide(contenido, extension):
        problemas.append({
            "campo": "archivo",
            "problema": f"el contenido no corresponde a un archivo {extension}; "
                        f"la extension dice una cosa y los primeros bytes otra"})

    if problemas:
        raise ErrorApi("ARCHIVO_INVALIDO",
                       "El archivo no cumple las reglas de formato o tamano.",
                       422, problemas)

    return extension, hashlib.sha256(contenido).hexdigest(), \
        nombre_presentable(nombre_original)


def guardar(contenido, sha256):
    """Escribe el blob en almacenamiento local o GCS. Devuelve True si era nuevo."""
    if modo_almacen() == "gcs":
        bucket = _bucket_cliente_gcs()
        blob = bucket.blob(ruta_objeto_de(sha256))
        if blob.exists():
            return False
        blob.upload_from_string(contenido)
        return True

    ruta = ruta_de(sha256)
    if os.path.exists(ruta):
        return False
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    temporal = f"{ruta}.parcial"
    with open(temporal, "wb") as f:
        f.write(contenido)
    os.replace(temporal, ruta)
    return True


def leer(sha256):
    """Devuelve el contenido desde local o GCS, o lanza si no está o fue alterado."""
    if modo_almacen() == "gcs":
        bucket = _bucket_cliente_gcs()
        blob = bucket.blob(ruta_objeto_de(sha256))
        if not blob.exists():
            raise ErrorApi("ARCHIVO_NO_ENCONTRADO",
                           "El registro del documento existe pero su archivo no "
                           "esta en el bucket.", 404,
                           [{"campo": "sha256", "problema": sha256}])
        contenido = blob.download_as_bytes()
    else:
        ruta = ruta_de(sha256)
        if not os.path.exists(ruta):
            raise ErrorApi("ARCHIVO_NO_ENCONTRADO",
                           "El registro del documento existe pero su archivo no "
                           "esta en el almacen.", 404,
                           [{"campo": "sha256", "problema": sha256}])
        with open(ruta, "rb") as f:
            contenido = f.read()

    real = hashlib.sha256(contenido).hexdigest()
    if real != sha256:
        raise ErrorApi("ARCHIVO_ALTERADO",
                       "El archivo almacenado no coincide con su sello. No se "
                       "entrega: una evidencia que cambio despues de "
                       "registrarse ya no respalda nada.", 409,
                       [{"campo": "sello_registrado", "problema": sha256},
                        {"campo": "sello_real", "problema": real}])
    return contenido


def ping_bucket():
    """Sonda de salud del almacen de archivos (local o GCS)."""
    if modo_almacen() == "gcs":
        bucket = _bucket_cliente_gcs()
        if not bucket.exists():
            raise RuntimeError(f"Bucket GCS no accesible: {bucket_gcs()}")
        return
    carpeta = almacen()
    os.makedirs(carpeta, exist_ok=True)
    if not os.path.isdir(carpeta) or not os.access(carpeta, os.W_OK):
        raise RuntimeError(f"Almacen local no escribible: {carpeta}")


def firmar_descarga(documento_id: str, expira: int) -> str:
    secreto = _secreto_firma()
    return hmac.new(
        secreto.encode("utf-8"),
        f"{documento_id}:{expira}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verificar_firma_descarga(documento_id: str, expira_str: str, firma: str) -> None:
    if not expira_str or not firma:
        raise ErrorApi("FIRMA_INVALIDA",
                       "Faltan los parametros 'expira' y 'firma'.", 403)
    try:
        expira = int(expira_str)
    except ValueError:
        raise ErrorApi("FIRMA_INVALIDA",
                       "El parametro 'expira' no es valido.", 403)
    if int(time.time()) > expira:
        raise ErrorApi("URL_EXPIRADA",
                       "La URL firmada expiro. Solicita una nueva.", 403)
    esperada = firmar_descarga(documento_id, expira)
    if not hmac.compare_digest(str(firma).lower(), esperada.lower()):
        raise ErrorApi("FIRMA_INVALIDA",
                       "La firma de la URL de descarga no es valida.", 403)


def url_firmada(sha256, minutos=10):
    """URL temporal de Cloud Storage, o None si este ambiente no firma.

    En developer el archivo se descarga por el propio servicio. En la
    máquina de Google, GCS_BUCKET (o GCS_BUCKET_NAME) y la llave de la
    cuenta de servicio permiten entregar el archivo sin abrirlo al mundo:
    la dirección deja de servir cuando vence.
    """
    bucket = bucket_gcs()
    llave = _llave_gcs()
    if not bucket or not llave:
        return None
    from datetime import timedelta
    from google.cloud import storage
    cliente = storage.Client.from_service_account_json(llave)
    blob = cliente.bucket(bucket).blob(f"{sha256[:2]}/{sha256[2:4]}/{sha256}")
    return blob.generate_signed_url(
        version="v4", expiration=timedelta(minutes=minutos), method="GET")


def generar_url_firmada(
    documento_id: str,
    sha256: str,
    base_url_local: str,
    ttl: int | None = None,
    nombre_archivo: str = "",
    tipo_mime: str = "",
) -> dict:
    ttl_efectivo = ttl_url_firmada() if ttl is None else max(10, min(int(ttl), 3600))
    expira = int(time.time()) + ttl_efectivo
    usar_gcs = modo_almacen() == "gcs" or bool(bucket_gcs() and _llave_gcs())
    if usar_gcs:
        bucket = _bucket_cliente_gcs()
        blob = bucket.blob(ruta_objeto_de(sha256))
        kwargs = {
            "version": "v4",
            "expiration": dt.timedelta(seconds=ttl_efectivo),
            "method": "GET",
            "response_disposition": f'attachment; filename="{nombre_archivo or sha256}"',
        }
        if tipo_mime:
            kwargs["response_type"] = tipo_mime
        url = blob.generate_signed_url(**kwargs)
        return {"url": url, "expira": expira, "ttl_segundos": ttl_efectivo, "modo": "gcs"}

    firma = firmar_descarga(documento_id, expira)
    prefijo = (base_url_local or "").rstrip("/")
    url = (
        f"{prefijo}/api/v1/documentos/archivos/{documento_id}/descarga-firmada"
        f"?expira={expira}&firma={firma}"
    )
    return {"url": url, "expira": expira, "ttl_segundos": ttl_efectivo, "modo": "local"}
