"""
Pruebas autonomas de seguridad, permisos, contratos XML/XXE, buckets y
tolerancia a fallos (Fase 4 — Tercer Parcial, Integrante 2).

Disenadas para ejecutarse sin PostgreSQL, Redis ni MongoDB vivos y sin
requerir `mongomock` en el entorno anfitrion:
    python -m pytest Equipo03_SegundoParcial/codigo/pruebas/test_seguridad_y_fallos_t3.py -v -o addopts="" --noconftest
"""
import base64
import datetime as dt
import fnmatch
import hashlib
import hmac
import http.server
import importlib.util
import json
import os
import sys
import threading
import time
import types
import uuid
from contextlib import contextmanager
from pathlib import Path

import jwt
import pytest

RAIZ = Path(__file__).resolve().parents[1]
DIR_MICRO = RAIZ / "apps" / "microservicios"
DIR_COMUN = DIR_MICRO / "comun"

if str(DIR_COMUN) not in sys.path:
    sys.path.insert(0, str(DIR_COMUN))

# Stub minimo de pymongo solo si no esta instalado en el host (no requiere mongomock)
if "pymongo" not in sys.modules:
    _pymongo_stub = types.ModuleType("pymongo")
    _pymongo_stub.ASCENDING = 1
    _pymongo_stub.DESCENDING = -1

    class _DummyMongoClient:
        def __init__(self, *args, **kwargs):
            pass

    _pymongo_stub.MongoClient = _DummyMongoClient
    sys.modules["pymongo"] = _pymongo_stub

from comun import ErrorApi, notificador, seguridad, servicio, xmlizar  # noqa: E402
import comun.datos as comun_datos  # noqa: E402
import comun.mongo as comun_mongo  # noqa: E402


# ---------------------------------------------------------------------------
# Dobles limpios en memoria para Redis, PostgreSQL y MongoDB
# ---------------------------------------------------------------------------
class FakeRedis:
    """Implementacion en memoria de los comandos Redis usados por los servicios."""

    def __init__(self):
        self.kv = {}
        self.hashes = {}
        self.ttls = {}
        self.caido = False

    def _check(self):
        if self.caido:
            raise ConnectionError("Redis no disponible (simulado)")

    def ping(self):
        self._check()
        return True

    def get(self, key):
        self._check()
        return self.kv.get(key)

    def set(self, key, value):
        self._check()
        self.kv[key] = str(value)
        return True

    def setex(self, key, seconds, value):
        self._check()
        self.kv[key] = str(value)
        self.ttls[key] = int(seconds)
        return True

    def delete(self, *keys):
        self._check()
        borradas = 0
        for k in keys:
            if k in self.kv:
                del self.kv[k]
                borradas += 1
            if k in self.hashes:
                del self.hashes[k]
                borradas += 1
            self.ttls.pop(k, None)
        return borradas

    def exists(self, *keys):
        self._check()
        return sum(1 for k in keys if k in self.kv or k in self.hashes)

    def incr(self, key, amount=1):
        self._check()
        actual = int(self.kv.get(key, "0"))
        nuevo = actual + amount
        self.kv[key] = str(nuevo)
        return nuevo

    def expire(self, key, seconds):
        self._check()
        if key in self.kv or key in self.hashes:
            self.ttls[key] = int(seconds)
            return True
        return False

    def ttl(self, key):
        self._check()
        if key not in self.kv and key not in self.hashes:
            return -2
        return self.ttls.get(key, -1)

    def hset(self, key, mapping=None, **kwargs):
        self._check()
        cubeta = self.hashes.setdefault(key, {})
        datos = dict(mapping or {})
        datos.update(kwargs)
        for k, v in datos.items():
            cubeta[k] = str(v)
        return len(datos)

    def hget(self, key, field):
        self._check()
        return self.hashes.get(key, {}).get(field)

    def scan_iter(self, match=None, count=None):
        self._check()
        todas = list(self.kv.keys()) + list(self.hashes.keys())
        for clave in list(dict.fromkeys(todas)):
            if match is None or fnmatch.fnmatch(clave, match):
                yield clave

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis_mem: FakeRedis):
        self._r = redis_mem
        self._ops = []

    def incr(self, key):
        self._ops.append(("incr", key))
        return self

    def execute(self):
        res = []
        for op, key in self._ops:
            if op == "incr":
                res.append(self._r.incr(key))
        return res


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._resultado = None

    def execute(self, sql, params=()):
        self.db.ejecuciones.append((sql, tuple(params)))
        sql_norm = " ".join(sql.split()).upper()

        if "INSERT INTO AUDITORIA.BITACORA" in sql_norm:
            if self.db.fallar_bitacora:
                raise RuntimeError("Fallo simulado al escribir bitacora")
            self.db.bitacora.append(tuple(params))
            self._resultado = None
        elif "USUARIOS.FN_RESTABLECER_CONTRASENA" in sql_norm:
            uid, nueva = params[0], params[1]
            u = self.db.usuarios.get(uid)
            if u and u.get("activo", True) and len(nueva) >= 8:
                u["contrasena"] = nueva
                self._resultado = {"actualizado": True}
            else:
                self._resultado = {"actualizado": False}
        else:
            self._resultado = None

    def fetchone(self):
        return self._resultado

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakePG:
    """Simula consultas y cursores PostgreSQL en memoria."""

    def __init__(self):
        self.usuarios = {
            "USR-00001": {
                "usuario_id": "USR-00001",
                "nombre": "Ana",
                "apellido_paterno": "Perez",
                "correo": "ana.perez@nexum.com.mx",
                "contrasena": "demo1234",
                "activo": True,
                "perfil_id": 1,
                "perfil": "Colaborador",
                "unidad_alcance_id": None,
                "seudonimo_id": "SEUD-00001",
            },
            "USR-00002": {
                "usuario_id": "USR-00002",
                "nombre": "Carlos",
                "apellido_paterno": "Ramirez",
                "correo": "carlos.ramirez@nexum.com.mx",
                "contrasena": "admin1234",
                "activo": True,
                "perfil_id": 5,
                "perfil": "Administrador del sistema",
                "unidad_alcance_id": None,
                "seudonimo_id": None,
            },
        }
        self.permisos_por_perfil = {
            1: ["AUTOREPORTE_RESPONDER", "APOYO_SOLICITAR", "PARTICIPACION_PROPIA"],
            5: [
                "USUARIO_ADMIN",
                "PARAMETRO_ADMIN",
                "INTERVENCION_SEGUIMIENTO",
                "CONSENT_EVIDENCIA_AUDIT",
                "BITACORA_CONSULTAR",
            ],
        }
        self.planes = {"PLAN-001": {"unidad_organizacional_id": "UO-CC-TURNO-B"}}
        self.unidades = {"UO-CC-TURNO-B"}
        self.campanias = {"CAMP-2026-S1"}
        self.bitacora = []
        self.ejecuciones = []
        self.fallar_bitacora = False

    def consultar(self, sql, params=()):
        sql_norm = " ".join(sql.split()).upper()
        if "FROM USUARIOS.PERFIL_PERMISO" in sql_norm:
            perfil_id = params[0]
            return [{"codigo": c} for c in self.permisos_por_perfil.get(perfil_id, [])]
        return []

    def consultar_uno(self, sql, params=()):
        sql_norm = " ".join(sql.split()).upper()
        if "FROM USUARIOS.USUARIO" in sql_norm and "CRYPT(" in sql_norm:
            correo, clave = params[0].lower(), params[1]
            for u in self.usuarios.values():
                if u["correo"].lower() == correo and u["activo"] and u["contrasena"] == clave:
                    return dict(u)
            return None
        if "FROM USUARIOS.USUARIO" in sql_norm and "LOWER(U.CORREO)" in sql_norm:
            correo = params[0].lower()
            for u in self.usuarios.values():
                if u["correo"].lower() == correo and u["activo"]:
                    return dict(u)
            return None
        if "FROM USUARIOS.USUARIO" in sql_norm and "U.USUARIO_ID" in sql_norm:
            uid = params[0]
            u = self.usuarios.get(uid)
            return dict(u) if (u and u["activo"]) else None
        if "FROM PORTAL.V_PARTICIPACION_PROPIA" in sql_norm:
            uid = params[0]
            u = self.usuarios.get(uid)
            if u and u.get("seudonimo_id"):
                return {"seudonimo_id": u["seudonimo_id"]}
            return None
        if "FROM INTERVENCION.PLAN" in sql_norm:
            return self.planes.get(params[0])
        if "FROM ORGANIZACION.UNIDAD_ORGANIZACIONAL" in sql_norm:
            return {"x": 1} if params[0] in self.unidades else None
        if "FROM CATALOGO.CAMPANIA" in sql_norm:
            return {"x": 1} if params[0] in self.campanias else None
        return None

    @contextmanager
    def cursor(self, commit=False):
        yield FakeCursor(self)


class FakeMongoCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, campo, orden=1):
        reverso = orden == -1
        self._docs.sort(key=lambda d: str(d.get(campo, "")), reverse=reverso)
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeMongoCollection:
    def __init__(self):
        self.docs = []

    @staticmethod
    def _coincide(doc, filtro):
        for k, v in (filtro or {}).items():
            actual = doc.get(k)
            if isinstance(v, dict) and "$in" in v:
                if actual not in v["$in"]:
                    return False
            elif isinstance(actual, list):
                if v not in actual:
                    return False
            elif actual != v:
                return False
        return True

    def insert_one(self, doc):
        copia = dict(doc)
        copia.setdefault("_id", uuid.uuid4().hex)
        self.docs.append(copia)
        return types.SimpleNamespace(inserted_id=copia["_id"])

    def insert_many(self, docs):
        for d in docs:
            self.insert_one(d)

    def find_one(self, filtro=None, *args, **kwargs):
        for d in self.docs:
            if self._coincide(d, filtro):
                return dict(d)
        return None

    def find(self, filtro=None, *args, **kwargs):
        return FakeMongoCursor([dict(d) for d in self.docs if self._coincide(d, filtro)])

    def count_documents(self, filtro=None):
        return sum(1 for d in self.docs if self._coincide(d, filtro))

    def update_one(self, filtro, update, upsert=False):
        for d in self.docs:
            if self._coincide(d, filtro):
                for k, v in (update.get("$set") or {}).items():
                    d[k] = v
                for k, inc in (update.get("$inc") or {}).items():
                    d[k] = (d.get(k) or 0) + inc
                return
        if upsert:
            nuevo = dict(filtro or {})
            nuevo.update(update.get("$set") or {})
            self.insert_one(nuevo)


class FakeMongoDB:
    def __init__(self):
        self.colecciones = {}

    def __getitem__(self, nombre):
        return self.colecciones.setdefault(nombre, FakeMongoCollection())


# ---------------------------------------------------------------------------
# Helpers de carga aislada de servicios
# ---------------------------------------------------------------------------
def _cargar_servicio(carpeta_nombre: str, alias: str):
    carpeta = str(DIR_MICRO / carpeta_nombre)
    ruta = str(DIR_MICRO / carpeta_nombre / "app.py")
    sys.path.insert(0, carpeta)
    try:
        spec = importlib.util.spec_from_file_location(alias, ruta)
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[alias] = modulo
        spec.loader.exec_module(modulo)
        return modulo
    finally:
        if carpeta in sys.path:
            sys.path.remove(carpeta)
        sys.modules.pop("contrato", None)
        sys.modules.pop("archivos", None)
        sys.modules.pop("preferencias", None)


def _crear_token(usuario_id="USR-00001", perfil_id=1, perfil="Colaborador",
                 jti=None, exp_delta_seg=900, tipo="acceso", secreto=None):
    jti = jti or uuid.uuid4().hex
    ahora = dt.datetime.now(dt.timezone.utc)
    carga = {
        "sub": usuario_id,
        "perfil_id": perfil_id,
        "perfil": perfil,
        "unidad_alcance": None,
        "jti": jti,
        "tipo": tipo,
        "iat": ahora,
        "exp": ahora + dt.timedelta(seconds=exp_delta_seg),
    }
    clave = secreto or seguridad.JWT_SECRETO or "secreto-solo-para-developer"
    return jwt.encode(carga, clave, algorithm=seguridad.JWT_ALGORITMO), jti


SECRETO_TEST = "secreto-t3-seguridad-hmac-sha256-32bytes"


@pytest.fixture
def entorno_aislado(monkeypatch):
    fake_redis = FakeRedis()
    fake_pg = FakePG()
    fake_mongo = FakeMongoDB()

    monkeypatch.setenv("APP_AMBIENTE", "developer")
    monkeypatch.setenv("JWT_SECRETO", SECRETO_TEST)
    monkeypatch.setattr(seguridad, "JWT_SECRETO", SECRETO_TEST)
    monkeypatch.setattr(seguridad, "obtener_redis", lambda: fake_redis)
    monkeypatch.setattr(comun_datos, "consultar", fake_pg.consultar)
    monkeypatch.setattr(comun_datos, "consultar_uno", fake_pg.consultar_uno)
    monkeypatch.setattr(comun_datos, "cursor", fake_pg.cursor)
    monkeypatch.setattr(comun_datos, "ping", lambda: True)
    monkeypatch.setattr(comun_mongo, "base", lambda: fake_mongo)
    monkeypatch.setattr(comun_mongo, "ping", lambda: True)

    return types.SimpleNamespace(redis=fake_redis, pg=fake_pg, mongo=fake_mongo)


def _parchear_servicio(monkeypatch, mod, env):
    if hasattr(mod, "obtener_redis"):
        monkeypatch.setattr(mod, "obtener_redis", lambda: env.redis)
    if hasattr(mod, "consultar"):
        monkeypatch.setattr(mod, "consultar", env.pg.consultar)
    if hasattr(mod, "consultar_uno"):
        monkeypatch.setattr(mod, "consultar_uno", env.pg.consultar_uno)
    if hasattr(mod, "cursor"):
        monkeypatch.setattr(mod, "cursor", env.pg.cursor)
    if hasattr(mod, "base"):
        monkeypatch.setattr(mod, "base", lambda: env.mongo)
    if hasattr(mod, "JWT_SECRETO"):
        monkeypatch.setattr(mod, "JWT_SECRETO", SECRETO_TEST)


# ===========================================================================
# 1. AUTH-SERVICE: JWT expirado, sesion revocada y recuperacion de acceso OTP
# ===========================================================================
def test_auth_token_expirado_401(entorno_aislado, monkeypatch):
    auth_mod = _cargar_servicio("auth-service", "t3_auth_exp")
    _parchear_servicio(monkeypatch, auth_mod, entorno_aislado)
    client = auth_mod.app.test_client()

    token_exp, _ = _crear_token(exp_delta_seg=-30, secreto=SECRETO_TEST)
    resp = client.get("/api/v1/auth/validar", headers={"Authorization": f"Bearer {token_exp}"})
    assert resp.status_code == 401
    assert resp.get_json()["error"]["codigo"] == "TOKEN_EXPIRADO"

    ren_exp, _ = _crear_token(exp_delta_seg=-30, tipo="renovacion", secreto=SECRETO_TEST)
    resp_ren = client.post("/api/v1/auth/renovar", json={"token_renovacion": ren_exp})
    assert resp_ren.status_code == 401
    assert resp_ren.get_json()["error"]["codigo"] == "TOKEN_EXPIRADO"


def test_auth_sesion_revocada_en_redis_401_y_redis_caido_503(entorno_aislado, monkeypatch):
    auth_mod = _cargar_servicio("auth-service", "t3_auth_rev")
    _parchear_servicio(monkeypatch, auth_mod, entorno_aislado)
    client = auth_mod.app.test_client()

    # Login valido crea sesion:<jti> en Redis
    login = client.post("/api/v1/auth/login", json={
        "correo": "ana.perez@nexum.com.mx",
        "contrasena": "demo1234",
    })
    assert login.status_code == 200
    token = login.get_json()["token_acceso"]
    assert client.get("/api/v1/auth/validar", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # Logout revoca sesion en Redis
    out = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert out.status_code == 200
    assert out.get_json()["revocado"] is True

    # El mismo token aunque conserve firma y exp vigente ahora falla con 401 SESION_REVOCADA
    rechazo = client.get("/api/v1/auth/validar", headers={"Authorization": f"Bearer {token}"})
    assert rechazo.status_code == 401
    assert rechazo.get_json()["error"]["codigo"] == "SESION_REVOCADA"

    # Tambien si el token nunca tuvo sesion:<jti> en Redis o tiene revocado:<jti>
    huerfano, jti_h = _crear_token(secreto=SECRETO_TEST)
    assert client.get("/api/v1/auth/validar",
                      headers={"Authorization": f"Bearer {huerfano}"}).get_json()["error"]["codigo"] == "SESION_REVOCADA"
    entorno_aislado.redis.setex(f"revocado:{jti_h}", 60, "1")
    assert client.get("/api/v1/auth/validar",
                      headers={"Authorization": f"Bearer {huerfano}"}).status_code == 401

    # Si Redis cae, falla cerrado con 503 DEPENDENCIA_NO_DISPONIBLE
    entorno_aislado.redis.caido = True
    caido = client.get("/api/v1/auth/validar", headers={"Authorization": f"Bearer {token}"})
    assert caido.status_code == 503
    assert caido.get_json()["error"]["codigo"] == "DEPENDENCIA_NO_DISPONIBLE"


def test_auth_recuperacion_flujo_completo_sin_enumeracion_bloqueo_y_revocacion(entorno_aislado, monkeypatch):
    auth_mod = _cargar_servicio("auth-service", "t3_auth_recup")
    _parchear_servicio(monkeypatch, auth_mod, entorno_aislado)

    otps_emitidos = []
    monkeypatch.setattr(
        auth_mod,
        "_despachar_notificacion_recuperacion",
        lambda usuario, codigo: otps_emitidos.append((usuario["correo"], codigo)),
    )
    client = auth_mod.app.test_client()

    # Sesion activa previa del usuario que debera revocarse al confirmar cambio
    login = client.post("/api/v1/auth/login", json={
        "correo": "ana.perez@nexum.com.mx",
        "contrasena": "demo1234",
    })
    assert login.status_code == 200
    token_previo = login.get_json()["token_acceso"]

    # 1. Solicitud para correo inexistente vs existente: respuesta identica (anti-enumeracion)
    r_inexistente = client.post("/api/v1/auth/recuperar/solicitar", json={
        "correo": "nadie.inventado@nexum.com.mx",
    })
    r_existente = client.post("/api/v1/auth/recuperar/solicitar", json={
        "correo": "ana.perez@nexum.com.mx",
    })
    assert r_inexistente.status_code == 200
    assert r_existente.status_code == 200
    assert r_inexistente.get_json() == r_existente.get_json()
    assert r_existente.get_json()["solicitado"] is True
    assert len(otps_emitidos) == 1

    otp_1 = otps_emitidos[0][1]
    hash_guardado = entorno_aislado.redis.get("recuperacion:ana.perez@nexum.com.mx")
    assert hash_guardado == hashlib.sha256(otp_1.encode("utf-8")).hexdigest()
    assert hash_guardado != otp_1  # Nunca en claro en Redis

    # 2. Tres intentos fallidos bloquean el OTP (1 y 2 -> 400, 3 -> 429 CODIGO_BLOQUEADO)
    for intento in (1, 2):
        bad = client.post("/api/v1/auth/recuperar/confirmar", json={
            "correo": "ana.perez@nexum.com.mx",
            "codigo": "999999" if otp_1 != "999999" else "000000",
            "nueva_contrasena": "NuevaClaveSegura99",
        })
        assert bad.status_code == 400, f"Intento {intento}: {bad.get_json()}"
        assert bad.get_json()["error"]["codigo"] == "CODIGO_INVALIDO"

    bloqueo = client.post("/api/v1/auth/recuperar/confirmar", json={
        "correo": "ana.perez@nexum.com.mx",
        "codigo": "999999" if otp_1 != "999999" else "000000",
        "nueva_contrasena": "NuevaClaveSegura99",
    })
    assert bloqueo.status_code == 429
    assert bloqueo.get_json()["error"]["codigo"] == "CODIGO_BLOQUEADO"
    # Tras bloqueo, el OTP queda invalidado incluso si luego mandan el codigo correcto
    assert entorno_aislado.redis.get("recuperacion:ana.perez@nexum.com.mx") is None
    tras_bloqueo = client.post("/api/v1/auth/recuperar/confirmar", json={
        "correo": "ana.perez@nexum.com.mx",
        "codigo": otp_1,
        "nueva_contrasena": "NuevaClaveSegura99",
    })
    assert tras_bloqueo.status_code == 400
    assert tras_bloqueo.get_json()["error"]["codigo"] == "CODIGO_INVALIDO_O_EXPIRADO"

    # 3. Nueva solicitud y confirmacion exitosa -> fn_restablecer_contrasena + revoca sesiones
    r2 = client.post("/api/v1/auth/recuperar/solicitar", json={"correo": "ana.perez@nexum.com.mx"})
    assert r2.status_code == 200
    otp_2 = otps_emitidos[1][1]

    confirmar = client.post("/api/v1/auth/recuperar/confirmar", json={
        "correo": "ana.perez@nexum.com.mx",
        "codigo": otp_2,
        "nueva_contrasena": "NuevaClaveSegura99",
    })
    assert confirmar.status_code == 200, confirmar.get_json()
    cuerpo = confirmar.get_json()
    assert cuerpo["actualizado"] is True
    assert cuerpo["sesiones_revocadas"] >= 1

    # Verificacion de llamada a fn_restablecer_contrasena en PostgreSQL
    assert any(
        "FN_RESTABLECER_CONTRASENA" in sql.upper() and params == ("USR-00001", "NuevaClaveSegura99")
        for sql, params in entorno_aislado.pg.ejecuciones
    )
    assert entorno_aislado.pg.usuarios["USR-00001"]["contrasena"] == "NuevaClaveSegura99"

    # La sesion previa quedo revocada en Redis
    validar_viejo = client.get("/api/v1/auth/validar",
                               headers={"Authorization": f"Bearer {token_previo}"})
    assert validar_viejo.status_code == 401
    assert validar_viejo.get_json()["error"]["codigo"] == "SESION_REVOCADA"

    # El usuario puede iniciar sesion con su nueva contrasena
    relogin = client.post("/api/v1/auth/login", json={
        "correo": "ana.perez@nexum.com.mx",
        "contrasena": "NuevaClaveSegura99",
    })
    assert relogin.status_code == 200


# ===========================================================================
# 2. SEGURIDAD.PY: 403 SIN_PERMISO + registro ACCESO_DENEGADO en bitacora
# ===========================================================================
def test_seguridad_requiere_permiso_403_y_bitacora_acceso_denegado(entorno_aislado):
    app = servicio.crear_servicio("svc-seg-test", "Prueba RBAC", comprobaciones={})

    @app.get("/api/v1/recurso-admin")
    @seguridad.requiere_permiso("USUARIO_ADMIN")
    def ruta_protegida():
        return servicio.responder({"ok": True})

    client = app.test_client()
    token_colab, jti = _crear_token(
        usuario_id="USR-00001",
        perfil_id=1,
        perfil="Colaborador",
        secreto=SECRETO_TEST,
    )
    entorno_aislado.redis.hset(f"sesion:{jti}", {"usuario_id": "USR-00001"})

    resp = client.get(
        "/api/v1/recurso-admin",
        headers={
            "Authorization": f"Bearer {token_colab}",
            "X-Correlacion-Id": "corr-403-test",
            "X-Forwarded-For": "198.51.100.25",
        },
    )
    assert resp.status_code == 403
    cuerpo = resp.get_json()
    assert cuerpo["error"]["codigo"] == "SIN_PERMISO"

    assert len(entorno_aislado.pg.bitacora) == 1
    fila = entorno_aislado.pg.bitacora[0]
    assert fila[0] == "USR-00001"           # actor_usuario_id
    assert fila[1] == "Colaborador"         # actor_perfil
    assert fila[2] == "ACCESO_DENEGADO"     # accion
    assert fila[3] == "ENDPOINT"            # tipo_recurso
    assert fila[4] == "/api/v1/recurso-admin"
    assert fila[5] == "RECHAZADO_PERMISO"   # resultado
    assert fila[6] == "corr-403-test"       # correlacion_id
    assert fila[7] == "198.51.100.25"       # direccion_origen

    # Resiliencia: si la bitacora falla, el 403 SIN_PERMISO no se transforma en 500
    entorno_aislado.pg.fallar_bitacora = True
    resp2 = client.get("/api/v1/recurso-admin", headers={"Authorization": f"Bearer {token_colab}"})
    assert resp2.status_code == 403
    assert resp2.get_json()["error"]["codigo"] == "SIN_PERMISO"


# ===========================================================================
# 3. XMLIZAR.PY + SERVICIO.PY: Rechazo anti-XXE / Billion Laughs
# ===========================================================================
@pytest.mark.parametrize("payload_malicioso", [
    '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><req><nombre>&xxe;</nombre></req>',
    '<?xml version="1.0"?><!doctype lolz [<!entity lol "lol"><!entity lol2 "&lol;&lol;">]><req><a>&lol2;</a></req>',
    '<?xml version="1.0"?><!   ENTITY secreto "valor"><req><a>1</a></req>',
])
def test_xmlizar_rechaza_xxe_y_endpoint_responde_400(payload_malicioso):
    with pytest.raises(ValueError, match="DOCTYPE|ENTITY"):
        xmlizar.de_xml(payload_malicioso)

    app = servicio.crear_servicio("svc-xxe-test", "Prueba XXE", comprobaciones={})

    @app.post("/api/v1/echo")
    def echo():
        return servicio.responder(servicio.cuerpo_peticion())

    client = app.test_client()
    resp = client.post(
        "/api/v1/echo",
        data=payload_malicioso,
        content_type="application/xml; charset=utf-8",
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["codigo"] == "XML_MAL_FORMADO"


# ===========================================================================
# 4. DOCUMENTS-SERVICE: Dual local, 10 metadatos, sin binario en BD, D-01,
#    magic bytes rechazados y URL firmada (vigente / expirada / alterada)
# ===========================================================================
def test_documents_local_10_metadatos_sin_binario_y_rechazo_d01(entorno_aislado, monkeypatch, tmp_path):
    monkeypatch.setenv("ALMACEN_MODO", "local")
    monkeypatch.setenv("ALMACEN_EVIDENCIAS", str(tmp_path))

    docs_mod = _cargar_servicio("documents-service", "t3_docs_meta")
    _parchear_servicio(monkeypatch, docs_mod, entorno_aislado)
    client = docs_mod.app.test_client()

    token_admin, jti = _crear_token(
        usuario_id="USR-00002",
        perfil_id=5,
        perfil="Administrador del sistema",
        secreto=SECRETO_TEST,
    )
    entorno_aislado.redis.hset(f"sesion:{jti}", {"usuario_id": "USR-00002"})

    pdf_bytes = b"%PDF-1.7\n% Evidencia organizacional segura\n"
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    resp = client.post(
        "/api/v1/documentos/archivos",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "intervencion_id": "PLAN-001",
            "nombre_archivo": "../../acta_comite.pdf",
            "contenido_base64": pdf_b64,
            "descripcion": "Minuta firmada",
        },
    )
    assert resp.status_code == 201, resp.get_json()
    sha = resp.get_json()["sha256"]
    assert sha == hashlib.sha256(pdf_bytes).hexdigest()

    docs_en_bd = entorno_aislado.mongo["documentos"].docs
    assert len(docs_en_bd) == 1
    doc = docs_en_bd[0]

    # Los 10 metadatos exigidos por la rubrica
    claves_rubrica = {
        "identificador", "ruta", "tipo", "tamano", "propietario",
        "fecha", "hash", "nivel_privacidad", "estado", "metadatos",
    }
    assert claves_rubrica.issubset(doc.keys())
    assert doc["identificador"] == doc["documento_id"]
    assert doc["ruta"] == f"{sha[:2]}/{sha[2:4]}/{sha}"
    assert doc["tipo"] == "EVIDENCIA_ARCHIVO"
    assert doc["tamano"] == len(pdf_bytes)
    assert doc["propietario"] == "USR-00002"
    assert doc["hash"] == sha
    assert doc["nivel_privacidad"] == "ORGANIZACIONAL"
    assert doc["estado"] == "ACTIVO"
    assert isinstance(doc["metadatos"], dict)

    # El binario NO vive en BD; vive en el bucket/almacen local
    serializado = json.dumps(doc, default=str)
    assert pdf_b64 not in serializado
    assert "contenido_base64" not in doc
    assert "empleado_id" not in doc
    ruta_disco = tmp_path / sha[:2] / sha[2:4] / sha
    assert ruta_disco.is_file()
    assert ruta_disco.read_bytes() == pdf_bytes

    # Tambien evidencia-apoyo genera los 10 metadatos usando seudonimo como propietario
    token_colab, jti_c = _crear_token(
        usuario_id="USR-00001",
        perfil_id=1,
        perfil="Colaborador",
        secreto=SECRETO_TEST,
    )
    entorno_aislado.redis.hset(f"sesion:{jti_c}", {"usuario_id": "USR-00001"})
    jpg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    apoyo_resp = client.post(
        "/api/v1/documentos/evidencia-apoyo",
        headers={"Authorization": f"Bearer {token_colab}"},
        json={
            "referencia": "SOL-2026-001",
            "nombre_archivo": "foto_apoyo.jpg",
            "contenido_base64": base64.b64encode(jpg_bytes).decode("ascii"),
        },
    )
    assert apoyo_resp.status_code == 201, apoyo_resp.get_json()
    doc_apoyo = entorno_aislado.mongo["documentos"].docs[1]
    assert claves_rubrica.issubset(doc_apoyo.keys())
    assert doc_apoyo["propietario"] == "SEUD-00001"
    assert doc_apoyo["nivel_privacidad"] == "CONFIDENCIAL"

    # Regla D-01: documents-service rechaza empleado_id (plano y anidado) con 422 CAMPO_PROHIBIDO
    d01_resp = client.post(
        "/api/v1/documentos",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "tipo": "REPORTE_ORGANIZACIONAL",
            "empleado_id": "EMP-00001",
            "contenido": {"titulo": "Intento prohibido"},
        },
    )
    assert d01_resp.status_code == 422
    assert d01_resp.get_json()["error"]["codigo"] == "CAMPO_PROHIBIDO"

    d01_anidado = client.post(
        "/api/v1/documentos",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "tipo": "REPORTE_ORGANIZACIONAL",
            "contenido": {"detalle": [{"empleado_id": "EMP-99999"}]},
        },
    )
    assert d01_anidado.status_code == 422
    assert d01_anidado.get_json()["error"]["codigo"] == "CAMPO_PROHIBIDO"


def test_documents_rechaza_magic_bytes_falsificados_y_registra_bitacora(entorno_aislado, monkeypatch, tmp_path):
    monkeypatch.setenv("ALMACEN_MODO", "local")
    monkeypatch.setenv("ALMACEN_EVIDENCIAS", str(tmp_path))

    docs_mod = _cargar_servicio("documents-service", "t3_docs_magic")
    _parchear_servicio(monkeypatch, docs_mod, entorno_aislado)
    client = docs_mod.app.test_client()

    token_admin, jti = _crear_token(
        usuario_id="USR-00002",
        perfil_id=5,
        perfil="Administrador del sistema",
        secreto=SECRETO_TEST,
    )
    entorno_aislado.redis.hset(f"sesion:{jti}", {"usuario_id": "USR-00002"})

    exe_disfrazado = b"MZ\x90\x00\x03\x00\x00\x00payload_malicioso"
    resp = client.post(
        "/api/v1/documentos/archivos",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "intervencion_id": "PLAN-001",
            "nombre_archivo": "reporte_falso.pdf",
            "contenido_base64": base64.b64encode(exe_disfrazado).decode("ascii"),
        },
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["codigo"] == "ARCHIVO_INVALIDO"
    assert entorno_aislado.mongo["documentos"].count_documents() == 0
    assert any(
        fila[2] == "ARCHIVO_RECHAZADO" and fila[5] == "RECHAZADO"
        for fila in entorno_aislado.pg.bitacora
    )


def test_documents_url_firmada_vigente_expirada_y_alterada(entorno_aislado, monkeypatch, tmp_path):
    monkeypatch.setenv("ALMACEN_MODO", "local")
    monkeypatch.setenv("ALMACEN_EVIDENCIAS", str(tmp_path))

    docs_mod = _cargar_servicio("documents-service", "t3_docs_url")
    _parchear_servicio(monkeypatch, docs_mod, entorno_aislado)
    client = docs_mod.app.test_client()

    token_admin, jti = _crear_token(
        usuario_id="USR-00002",
        perfil_id=5,
        perfil="Administrador del sistema",
        secreto=SECRETO_TEST,
    )
    entorno_aislado.redis.hset(f"sesion:{jti}", {"usuario_id": "USR-00002"})

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" * 8
    subida = client.post(
        "/api/v1/documentos/archivos",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "intervencion_id": "PLAN-001",
            "nombre_archivo": "captura.png",
            "contenido_base64": base64.b64encode(png_bytes).decode("ascii"),
        },
    )
    assert subida.status_code == 201
    doc_id = subida.get_json()["documento_id"]
    sha = subida.get_json()["sha256"]

    # 1. Generacion de URL firmada
    gen = client.get(
        f"/api/v1/documentos/{doc_id}/url-firmada?ttl=120",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert gen.status_code == 200, gen.get_json()
    info = gen.get_json()
    assert info["modo"] == "local"
    assert f"/api/v1/documentos/archivos/{doc_id}/descarga-firmada?" in info["url"]

    ruta_relativa = info["url"].split("http://localhost", 1)[-1]
    qs = ruta_relativa.split("?", 1)[1]
    params = dict(p.split("=", 1) for p in qs.split("&"))

    # 2. Consumo exitoso con firma vigente (no requiere Bearer porque la URL trae firma HMAC)
    descarga_ok = client.get(ruta_relativa)
    assert descarga_ok.status_code == 200
    assert descarga_ok.data == png_bytes
    assert descarga_ok.headers["X-Evidencia-Sello"] == sha

    # 3. Consumo con firma alterada -> 403 FIRMA_INVALIDA
    firma_alterada = ("f" if params["firma"][0] != "f" else "0") + params["firma"][1:]
    descarga_alterada = client.get(
        f"/api/v1/documentos/archivos/{doc_id}/descarga-firmada"
        f"?expira={params['expira']}&firma={firma_alterada}"
    )
    assert descarga_alterada.status_code == 403
    assert descarga_alterada.get_json()["error"]["codigo"] == "FIRMA_INVALIDA"

    # 4. Consumo con URL expirada (firma autentica pero timestamp vencido) -> 403 URL_EXPIRADA
    exp_vencida = int(time.time()) - 30
    firma_vencida = hmac.new(
        SECRETO_TEST.encode("utf-8"),
        f"{doc_id}:{exp_vencida}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    descarga_expirada = client.get(
        f"/api/v1/documentos/archivos/{doc_id}/descarga-firmada"
        f"?expira={exp_vencida}&firma={firma_vencida}"
    )
    assert descarga_expirada.status_code == 403
    assert descarga_expirada.get_json()["error"]["codigo"] == "URL_EXPIRADA"

    # 5. Si el archivo en disco fue alterado, lectura rechaza con 409 ARCHIVO_ALTERADO
    ruta_disco = tmp_path / sha[:2] / sha[2:4] / sha
    ruta_disco.write_bytes(b"\x89PNG\r\n\x1a\nCORRUPTO")
    descarga_corrupta = client.get(ruta_relativa)
    assert descarga_corrupta.status_code == 409
    assert descarga_corrupta.get_json()["error"]["codigo"] == "ARCHIVO_ALTERADO"


# ===========================================================================
# 5. COMUN/SERVICIO.PY y NOTIFICADOR.PY: /health/live, /health/ready,
#    rate limit y notificacion interna resiliente HMAC
# ===========================================================================
def test_servicio_health_live_y_ready_degradado_vs_no_listo(monkeypatch):
    monkeypatch.setenv("VERSION_DESPLIEGUE", "t3-2026.11.17")

    # Caso A: dependencia opcional 'bucket' cae -> 200 degradado
    def fallar_bucket():
        raise RuntimeError("GCS temporalmente inaccesible")

    app_deg = servicio.crear_servicio(
        "svc-deg",
        "Prueba degradacion",
        comprobaciones={"postgresql": lambda: True, "bucket": (fallar_bucket, "opcional")},
    )
    c_deg = app_deg.test_client()

    live = c_deg.get("/health/live")
    assert live.status_code == 200
    assert live.get_json()["version_desplegada"] == "t3-2026.11.17"
    assert live.get_json()["estado"] == "vivo"

    ready_deg = c_deg.get("/health/ready")
    assert ready_deg.status_code == 200
    cuerpo_deg = ready_deg.get_json()
    assert cuerpo_deg["estado"] == "degradado"
    assert cuerpo_deg["degradado_por"] == ["bucket"]
    assert cuerpo_deg["dependencias"]["bucket"]["ok"] is False
    assert cuerpo_deg["dependencias"]["bucket"]["esencial"] is False

    # Caso B: dependencia esencial cae -> 503 no_listo
    def fallar_pg():
        raise ConnectionError("PostgreSQL caido")

    app_fail = servicio.crear_servicio(
        "svc-fail",
        "Prueba caida esencial",
        comprobaciones={"postgresql": fallar_pg, "bucket": (fallar_bucket, "opcional")},
    )
    ready_fail = app_fail.test_client().get("/health/ready")
    assert ready_fail.status_code == 503
    cuerpo_fail = ready_fail.get_json()
    assert cuerpo_fail["estado"] == "no_listo"
    assert cuerpo_fail["falta"] == ["postgresql"]
    assert cuerpo_fail["degradado_por"] == ["bucket"]


def test_rate_limiting_429_y_degradacion_si_redis_cae(entorno_aislado):
    app = servicio.crear_servicio("svc-rl", "Prueba rate limit", comprobaciones={})

    @app.get("/api/v1/ping-limitado")
    @seguridad.requiere_token
    def ping_limitado():
        servicio.limite_consumo(maximo=2, ventana=60)
        return servicio.responder({"ok": True})

    @app.get("/api/v1/ping-solo-limite")
    def ping_solo_limite():
        servicio.limite_consumo(maximo=2, ventana=60)
        return servicio.responder({"ok": True})

    client = app.test_client()
    token, jti = _crear_token(secreto=SECRETO_TEST)
    entorno_aislado.redis.hset(f"sesion:{jti}", {"usuario_id": "USR-00001"})

    assert client.get("/api/v1/ping-limitado", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/v1/ping-limitado", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    r_429 = client.get("/api/v1/ping-limitado", headers={"Authorization": f"Bearer {token}"})
    assert r_429.status_code == 429
    assert r_429.get_json()["error"]["codigo"] == "LIMITE_EXCEDIDO"
    assert int(r_429.headers["Retry-After"]) > 0
    assert any(fila[2] == "RATE_LIMIT_EXCEDIDO" for fila in entorno_aislado.pg.bitacora)

    # Si Redis cae, limite_consumo degrada sin provocar 500
    entorno_aislado.redis.caido = True
    assert client.get("/api/v1/ping-solo-limite").status_code == 200


def test_notificador_firma_hmac_y_resiliencia_sin_servicio(monkeypatch):
    monkeypatch.setenv("JWT_SECRETO", SECRETO_TEST)
    captura = {}

    class ReceptorHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            largo = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(largo)
            captura["path"] = self.path
            captura["ts"] = self.headers.get("X-Servicio-Timestamp")
            captura["firma"] = self.headers.get("X-Servicio-Firma")
            captura["corr"] = self.headers.get("X-Correlacion-Id")
            captura["raw"] = raw
            self.send_response(201)
            self.end_headers()
            self.wfile.write(b'{"enviadas":1}')

        def log_message(self, *args):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), ReceptorHandler)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    try:
        monkeypatch.setenv("NOTIFICATIONS_SERVICE_URL", f"http://127.0.0.1:{srv.server_port}")
        ok = notificador.notificar_evento_interno(
            tipo="RECUPERACION_ACCESO",
            destinatarios=["USR-00001"],
            titulo="Codigo de recuperacion",
            mensaje="Se genero un codigo temporal para recuperar tu acceso.",
            metadata={"expira_segundos": 600},
            correlacion_id="corr-notif-t3",
        )
        assert ok is True
        assert captura["path"] == "/api/v1/notificaciones/evento-interno"
        assert captura["corr"] == "corr-notif-t3"
        esperada = hmac.new(
            SECRETO_TEST.encode("utf-8"),
            f"{captura['ts']}.".encode("utf-8") + captura["raw"],
            hashlib.sha256,
        ).hexdigest()
        assert hmac.compare_digest(captura["firma"], esperada)

        # notifications-service caido / timeout -> no lanza excepcion, devuelve False
        monkeypatch.setenv("NOTIFICATIONS_SERVICE_URL", "http://127.0.0.1:1")
        fallo = notificador.notificar_evento_interno(
            tipo="RECUPERACION_ACCESO",
            destinatarios=["USR-00001"],
            titulo="Codigo de recuperacion",
            mensaje="No debe romper el flujo principal si notifications-service cae.",
            timeout=0.3,
        )
        assert fallo is False
    finally:
        srv.shutdown()
        srv.server_close()
