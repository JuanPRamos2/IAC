"""Notificador resiliente servicio-a-servicio para notificaciones internas.

Firma el cuerpo JSON con HMAC-SHA256 usando ``JWT_SECRETO`` y envia los
encabezados ``X-Servicio-Timestamp``, ``X-Servicio-Firma`` y
``X-Correlacion-Id`` hacia ``{NOTIFICATIONS_SERVICE_URL}/api/v1/notificaciones/evento-interno``.

Nunca lanza excepciones: si ``notifications-service`` no responde o rechaza la
peticion, registra una advertencia tecnica y devuelve ``False`` para que el
flujo principal del negocio nunca se interrumpa por un aviso accesorio.
"""
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request

_log = logging.getLogger("comun.notificador")


def _secreto() -> str:
    secreto = os.environ.get("JWT_SECRETO")
    if secreto:
        return secreto
    if os.environ.get("APP_AMBIENTE", "developer") == "developer":
        return "secreto-solo-para-developer"
    return ""


def _correlacion_actual(correlacion_id: str | None) -> str:
    if correlacion_id:
        return str(correlacion_id)
    try:
        from flask import g, has_request_context
        if has_request_context():
            return str(getattr(g, "correlacion_id", "") or "")
    except Exception:
        pass
    return ""


def notificar_evento_interno(
    tipo,
    destinatarios,
    titulo,
    mensaje,
    metadata=None,
    timeout=1.5,
    unidad_organizacional_id=None,
    correlacion_id=None,
) -> bool:
    """Envia un evento interno firmado a notifications-service.

    Devuelve ``True`` si el servicio respondio 2xx y ``False`` en cualquier fallo.
    """
    secreto = _secreto()
    if not secreto:
        _log.warning("No hay JWT_SECRETO configurado para firmar notificacion interna")
        return False

    base_url = (
        os.environ.get("NOTIFICATIONS_SERVICE_URL") or "http://notifications-service:8000"
    ).rstrip("/")
    url = f"{base_url}/api/v1/notificaciones/evento-interno"

    payload = {
        "tipo": tipo,
        "destinatarios": list(destinatarios or []),
        "titulo": titulo,
        "mensaje": mensaje,
        "metadata": metadata if isinstance(metadata, dict) else {},
    }
    if unidad_organizacional_id:
        payload["unidad_organizacional_id"] = unidad_organizacional_id

    try:
        cuerpo = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ts = str(int(time.time()))
        firma = hmac.new(
            secreto.encode("utf-8"),
            f"{ts}.".encode("utf-8") + cuerpo,
            hashlib.sha256,
        ).hexdigest()

        req = urllib.request.Request(
            url,
            data=cuerpo,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Servicio-Timestamp": ts,
                "X-Servicio-Firma": firma,
                "X-Correlacion-Id": _correlacion_actual(correlacion_id),
            },
        )
        with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        _log.warning("Fallo notificacion interna (%s) hacia %s: %s", tipo, url, exc)
        return False
