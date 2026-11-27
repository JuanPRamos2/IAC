"""Pruebas unitarias Fase 2 para comun, documents-service y notifications-service."""
import base64
import hashlib
import hmac
import http.server
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "comun"))

# Stub minimo de pymongo si no esta instalado en el entorno local de pruebas
if "pymongo" not in sys.modules:
    pymongo_stub = types.ModuleType("pymongo")
    pymongo_stub.ASCENDING = 1
    pymongo_stub.DESCENDING = -1
    pymongo_stub.MongoClient = lambda *a, **kw: None
    sys.modules["pymongo"] = pymongo_stub

from comun import datos, notificador, servicio


def test_datos_statement_timeout(monkeypatch):
    monkeypatch.setenv("PG_STATEMENT_TIMEOUT_MS", "4200")
    assert datos._statement_timeout_ms() == 4200
    monkeypatch.delenv("PG_STATEMENT_TIMEOUT_MS", raising=False)
    assert datos._statement_timeout_ms() == 5000


def test_servicio_health_version_desplegada(monkeypatch):
    monkeypatch.setenv("VERSION_DESPLIEGUE", "2026.11.17")
    app = servicio.crear_servicio("svc-py", "Prueba Py")
    client = app.test_client()
    live = client.get("/health/live").get_json()
    assert live["estado"] == "vivo"
    assert live["version_desplegada"] == "2026.11.17"
    health = client.get("/health").get_json()
    assert health["version_desplegada"] == "2026.11.17"


def test_notificador_firma_y_resiliencia(monkeypatch):
    monkeypatch.setenv("JWT_SECRETO", "secreto-py-test")
    capturado = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            capturado["path"] = self.path
            capturado["ts"] = self.headers.get("X-Servicio-Timestamp")
            capturado["firma"] = self.headers.get("X-Servicio-Firma")
            capturado["corr"] = self.headers.get("X-Correlacion-Id")
            capturado["raw"] = raw
            self.send_response(201)
            self.end_headers()
            self.wfile.write(b'{"enviadas":1}')

        def log_message(self, *args):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        monkeypatch.setenv("NOTIFICATIONS_SERVICE_URL", f"http://127.0.0.1:{srv.server_port}")
        ok = notificador.notificar_evento_interno(
            tipo="PLAN_APROBADO",
            destinatarios=["USR-00001"],
            titulo="Plan aprobado",
            mensaje="Se aprobo el plan 10 para la unidad UO-01.",
            metadata={"intervencion_id": 10},
            unidad_organizacional_id="UO-01",
            correlacion_id="corr-py-99",
        )
        assert ok is True
        assert capturado["path"] == "/api/v1/notificaciones/evento-interno"
        assert capturado["corr"] == "corr-py-99"
        esperada = hmac.new(
            b"secreto-py-test",
            f"{capturado['ts']}.".encode("utf-8") + capturado["raw"],
            hashlib.sha256,
        ).hexdigest()
        assert capturado["firma"] == esperada

        # Falla silenciosa ante puerto cerrado
        monkeypatch.setenv("NOTIFICATIONS_SERVICE_URL", "http://127.0.0.1:1")
        assert notificador.notificar_evento_interno(
            tipo="PLAN_APROBADO",
            destinatarios=["USR-00001"],
            titulo="Plan aprobado",
            mensaje="No debe lanzar excepcion cuando falla.",
            timeout=0.3,
        ) is False
    finally:
        srv.shutdown()
        srv.server_close()


def _cargar_modulo(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, str(ruta))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_documents_archivos_local_y_firmas(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ALMACEN_MODO", "local")
        monkeypatch.setenv("ALMACEN_EVIDENCIAS", tmp)
        monkeypatch.setenv("JWT_SECRETO", "secreto-docs-test")
        archivos = _cargar_modulo("docs_archivos", ROOT / "documents-service" / "archivos.py")

        contenido = b"%PDF-1.4\ncontenido de prueba"
        ext, sha, nombre = archivos.validar(contenido, "../acta.pdf")
        assert ext == "pdf"
        assert nombre == "acta.pdf"
        assert archivos.guardar(contenido, sha) is True
        assert archivos.guardar(contenido, sha) is False
        assert archivos.leer(sha) == contenido
        archivos.ping_bucket()

        res = archivos.generar_url_firmada(
            "DOC-ABC123DEF456", sha, "http://localhost:8105", ttl=60
        )
        assert res["modo"] == "local"
        assert "/api/v1/documentos/archivos/DOC-ABC123DEF456/descarga-firmada?" in res["url"]

        qs = res["url"].split("?", 1)[1]
        params = dict(part.split("=", 1) for part in qs.split("&"))
        archivos.verificar_firma_descarga("DOC-ABC123DEF456", params["expira"], params["firma"])

        # Firma invalida -> 403
        try:
            archivos.verificar_firma_descarga("DOC-ABC123DEF456", params["expira"], "0" * 64)
            assert False, "Debio fallar firma invalida"
        except Exception as e:
            assert getattr(e, "http", None) == 403

        # Expirada -> 403
        exp_pasado = str(int(time.time()) - 10)
        firma_pasada = archivos.firmar_descarga("DOC-ABC123DEF456", int(exp_pasado))
        try:
            archivos.verificar_firma_descarga("DOC-ABC123DEF456", exp_pasado, firma_pasada)
            assert False, "Debio fallar expirada"
        except Exception as e:
            assert getattr(e, "http", None) == 403


def test_documents_archivos_modo_gcs_mock(monkeypatch):
    monkeypatch.setenv("ALMACEN_MODO", "gcs")
    monkeypatch.setenv("GCS_BUCKET_NAME", "bienestar-evidencias-test")
    archivos = _cargar_modulo("docs_archivos_gcs", ROOT / "documents-service" / "archivos.py")

    almacen_mem = {}

    class FakeBlob:
        def __init__(self, key):
            self.key = key

        def exists(self):
            return self.key in almacen_mem

        def upload_from_string(self, data):
            almacen_mem[self.key] = data

        def download_as_bytes(self):
            return almacen_mem[self.key]

        def generate_signed_url(self, **kwargs):
            return f"https://storage.googleapis.com/bienestar-evidencias-test/{self.key}?X-Goog-Signature=fake"

    class FakeBucket:
        def exists(self):
            return True

        def blob(self, key):
            return FakeBlob(key)

    class FakeStorageModule:
        class Client:
            def bucket(self, name):
                assert name == "bienestar-evidencias-test"
                return FakeBucket()

    google_mod = types.ModuleType("google")
    cloud_mod = types.ModuleType("google.cloud")
    cloud_mod.storage = FakeStorageModule
    google_mod.cloud = cloud_mod
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud_mod)

    contenido = b"%PDF-1.7\ngcs test"
    sha = hashlib.sha256(contenido).hexdigest()
    assert archivos.guardar(contenido, sha) is True
    assert archivos.leer(sha) == contenido
    archivos.ping_bucket()
    url_info = archivos.generar_url_firmada("DOC-111", sha, "http://localhost:8105", ttl=120)
    assert url_info["modo"] == "gcs"
    assert url_info["url"].startswith("https://storage.googleapis.com/bienestar-evidencias-test/")


def test_documents_ping_bucket_gcs_con_permiso_solo_objetos(monkeypatch):
    monkeypatch.setenv("ALMACEN_MODO", "gcs")
    monkeypatch.setenv("GCS_BUCKET_NAME", "bienestar-evidencias-solo-objetos")
    archivos = _cargar_modulo("docs_archivos_gcs_403", ROOT / "documents-service" / "archivos.py")

    class Error403(Exception):
        code = 403

    blob_consultado = []

    class FakeBlob:
        def __init__(self, key):
            self.key = key

        def exists(self):
            blob_consultado.append(self.key)
            return False

    class FakeBucketSoloObjetos:
        def exists(self):
            raise Error403("403 GET does not have storage.buckets.get access to the Google Cloud Storage bucket.")

        def blob(self, key):
            return FakeBlob(key)

    class FakeBucketInexistente:
        def exists(self):
            return False

    estado = {"modo": "solo_objetos"}

    class FakeStorageModule:
        class Client:
            def bucket(self, name):
                assert name == "bienestar-evidencias-solo-objetos"
                if estado["modo"] == "solo_objetos":
                    return FakeBucketSoloObjetos()
                return FakeBucketInexistente()

    google_mod = types.ModuleType("google")
    cloud_mod = types.ModuleType("google.cloud")
    cloud_mod.storage = FakeStorageModule
    google_mod.cloud = cloud_mod
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud_mod)

    archivos.ping_bucket()
    assert blob_consultado == ["__healthcheck_probe__"]

    estado["modo"] = "no_existe"
    with pytest.raises(RuntimeError, match="Bucket GCS no accesible"):
        archivos.ping_bucket()


def test_notifications_evento_interno_hmac_y_privacidad(monkeypatch):
    monkeypatch.setenv("JWT_SECRETO", "secreto-notif-test")
    notif_dir = str(ROOT / "notifications-service")
    sys.path.insert(0, notif_dir)
    try:
        notif_app_mod = _cargar_modulo("notif_app", ROOT / "notifications-service" / "app.py")
    finally:
        if notif_dir in sys.path:
            sys.path.remove(notif_dir)
        for mod_name in ("contrato", "preferencias"):
            sys.modules.pop(mod_name, None)

    assert "RECUPERACION_ACCESO" in notif_app_mod.TIPOS

    insertados = []
    redis_counts = {}

    class FakeCol:
        def __init__(self, name):
            self.name = name

        def find(self, *a, **kw):
            return []

        def insert_many(self, docs):
            insertados.extend(docs)

    class FakePipeline:
        def incr(self, k):
            redis_counts[k] = redis_counts.get(k, 0) + 1

        def execute(self):
            pass

    class FakeRedis:
        def pipeline(self):
            return FakePipeline()

    monkeypatch.setattr(notif_app_mod, "base", lambda: {
        "preferencias_notificacion": FakeCol("prefs"),
        "dispositivos_push": FakeCol("disp"),
        "notificaciones": FakeCol("notificaciones"),
        "cola_push": FakeCol("cola_push"),
    })
    monkeypatch.setattr(notif_app_mod, "obtener_redis", lambda: FakeRedis())
    monkeypatch.setattr(notif_app_mod, "_bitacora", lambda *a, **kw: None)

    client = notif_app_mod.app.test_client()

    def _firmar(payload, ts=None):
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ts_val = str(ts if ts is not None else int(time.time()))
        firma = hmac.new(
            b"secreto-notif-test",
            f"{ts_val}.".encode("utf-8") + raw,
            hashlib.sha256,
        ).hexdigest()
        return raw, {
            "Content-Type": "application/json",
            "X-Servicio-Timestamp": ts_val,
            "X-Servicio-Firma": firma,
        }

    # 1. Sin firma -> 401
    r_sin = client.post("/api/v1/notificaciones/evento-interno", json={"tipo": "RECUPERACION_ACCESO"})
    assert r_sin.status_code == 401

    # 2. Timestamp expirado -> 401
    raw_exp, h_exp = _firmar({
        "tipo": "RECUPERACION_ACCESO",
        "destinatarios": ["USR-00001"],
        "titulo": "Codigo temporal",
        "mensaje": "Tu codigo de recuperacion fue generado.",
    }, ts=int(time.time()) - 120)
    r_exp = client.post("/api/v1/notificaciones/evento-interno", data=raw_exp, headers=h_exp)
    assert r_exp.status_code == 401

    # 3. Cifra decimal prohibida -> 422
    raw_cifra, h_cifra = _firmar({
        "tipo": "CONFIRMACION_RECIBIDA",
        "destinatarios": ["USR-00001"],
        "titulo": "Resultado promedio",
        "mensaje": "Tu unidad tiene 3.45 puntos de estres.",
    })
    r_cifra = client.post("/api/v1/notificaciones/evento-interno", data=raw_cifra, headers=h_cifra)
    assert r_cifra.status_code == 422

    # 4. empleado_id prohibido (D-01) -> 422
    raw_d01, h_d01 = _firmar({
        "tipo": "CONFIRMACION_RECIBIDA",
        "destinatarios": ["USR-00001"],
        "titulo": "Confirmacion",
        "mensaje": "Se registro tu respuesta correctamente.",
        "metadata": {"empleado_id": "EMP-001"},
    })
    r_d01 = client.post("/api/v1/notificaciones/evento-interno", data=raw_d01, headers=h_d01)
    assert r_d01.status_code == 422

    # 5. Valido -> 201 + guarda en Mongo + incrementa Redis
    raw_ok, h_ok = _firmar({
        "tipo": "RECUPERACION_ACCESO",
        "destinatarios": ["USR-00001"],
        "titulo": "Recuperacion de acceso",
        "mensaje": "Se genero un codigo temporal para tu cuenta.",
    })
    r_ok = client.post("/api/v1/notificaciones/evento-interno", data=raw_ok, headers=h_ok)
    assert r_ok.status_code == 201
    assert len(insertados) == 1
    assert insertados[0]["tipo"] == "RECUPERACION_ACCESO"
    assert redis_counts["notif_sin_leer:USR-00001"] == 1
