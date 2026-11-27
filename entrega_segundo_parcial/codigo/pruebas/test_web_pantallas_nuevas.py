"""
Pruebas de las tres pantallas que el sistema web no tenía: perfiles,
bandeja de notificaciones y carga de evidencias.

CÓMO SE PRUEBAN LAS QUE LLAMAN A UN MICROSERVICIO
-------------------------------------------------
La bandeja y las evidencias llaman por HTTP a notifications-service y a
documents-service, que viven sobre MongoDB. En lugar de levantarlos, se
sustituye `requests.request` por un doble que devuelve las MISMAS formas de
respuesta que esos servicios producen —las de su contrato OpenAPI, no unas
inventadas—. Lo que se prueba así es lo que el sistema web hace con esas
respuestas: cómo valida un archivo antes de guardarlo, qué deja en la
bitácora, y qué le dice al operador cuando el servicio no contesta.

La prueba de que los servicios responden eso de verdad está en
test_documentos_y_notificaciones.py, que corre contra los servicios reales.
Las dos capas se prueban por separado a propósito: así, cuando algo falla,
se sabe de qué lado está.
"""
import hashlib
import io
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def almacen(tmp_path_factory):
    return str(tmp_path_factory.mktemp("evidencias"))


@pytest.fixture(scope="module")
def web(almacen):
    """El sistema web, con su almacén de evidencias en un directorio temporal."""
    os.environ["ALMACEN_EVIDENCIAS"] = almacen
    os.environ.setdefault("DOCUMENTS_SERVICE_URL", "http://documents-service:8000")
    os.environ.setdefault("NOTIFICATIONS_SERVICE_URL",
                          "http://notifications-service:8000")
    sys.path.insert(0, os.path.join(RAIZ, "apps", "web"))
    try:
        from app import crear_app
        aplicacion = crear_app()
        aplicacion.config["TESTING"] = True
        return aplicacion
    finally:
        sys.path.pop(0)


@pytest.fixture
def cliente(web):
    return web.test_client()


def _entrar(cliente, correo="carlos.ramirez@nexum.com.mx"):
    r = cliente.post("/entrar", data={"correo": correo, "contrasena": "demo123"},
                     follow_redirects=False)
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:400]
    return r


class RespuestaFalsa:
    def __init__(self, cuerpo, codigo=200):
        self._cuerpo = cuerpo
        self.status_code = codigo

    def json(self):
        return self._cuerpo


@pytest.fixture
def microservicio(monkeypatch):
    """Doble de los microservicios. Devuelve la lista de llamadas hechas."""
    llamadas = []
    guion = {}

    def falso(metodo, url, **kw):
        llamadas.append((metodo, url, kw.get("json")))
        # Gana el patron MAS ESPECIFICO, no el primero declarado: la ruta
        # de un documento concreto empieza igual que la de la coleccion, y
        # con la regla del primero una respuesta de alta se devolveria
        # tambien para la consulta por identificador.
        for patron in sorted(guion, key=len, reverse=True):
            if patron in url:
                respuesta = guion[patron]
                if isinstance(respuesta, Exception):
                    raise respuesta
                return respuesta
        return RespuestaFalsa({"elementos": [], "paginacion": {}}, 200)

    import requests
    monkeypatch.setattr(requests, "request", falso)
    return {"llamadas": llamadas, "guion": guion}


# =========================================================================
# Perfiles
# =========================================================================

def test_la_pantalla_de_perfiles_lista_los_cinco(cliente):
    _entrar(cliente)
    r = cliente.get("/administracion/perfiles/")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    for codigo in ("COLABORADOR", "LIDER", "ESPECIALISTA", "AUDITOR",
                   "ADMINISTRADOR"):
        assert codigo in texto


def test_un_colaborador_no_entra_a_perfiles(cliente):
    """Esconder el menú es comodidad; la ruta vuelve a validar en el servidor."""
    _entrar(cliente, "ana.perez@nexum.com.mx")
    r = cliente.get("/administracion/perfiles/", follow_redirects=False)
    assert r.status_code == 302
    assert "denegado" in r.headers["Location"]


def test_crear_un_perfil_y_asignarle_un_permiso(cliente):
    """La prueba de que el RBAC es dirigido por datos y no por código.

    Nota sobre la limpieza: el rol de la aplicación NO tiene DELETE sobre
    `usuarios.perfil`, y eso es deliberado —un perfil se desactiva, nunca se
    borra, porque la bitácora histórica lo sigue citando—. Así que la prueba
    es idempotente por otra vía: reutiliza el perfil si ya existe, le limpia
    los permisos (eso sí está permitido) y lo deja desactivado al terminar,
    que es el ciclo de vida que el sistema realmente soporta.
    """
    _entrar(cliente)
    import psycopg2
    cn = psycopg2.connect(host=os.environ["PG_HOST"], dbname=os.environ["PG_BASE"],
                          user=os.environ["PG_USUARIO"],
                          password=os.environ["PG_CLAVE"])
    with cn, cn.cursor() as cur:
        cur.execute("SELECT perfil_id FROM usuarios.perfil WHERE codigo = %s",
                    ("PRUEBA_COORD",))
        previo = cur.fetchone()
        if previo:
            cur.execute("DELETE FROM usuarios.perfil_permiso WHERE perfil_id = %s",
                        (previo[0],))
            cur.execute("UPDATE usuarios.perfil SET activo = TRUE "
                        " WHERE perfil_id = %s", (previo[0],))

    if not previo:
        r = cliente.post("/administracion/perfiles/",
                         data={"codigo": "PRUEBA_COORD",
                               "nombre": "Coordinador de prueba",
                               "descripcion": "Perfil creado por la suite"},
                         follow_redirects=False)
        assert r.status_code == 302

    with cn, cn.cursor() as cur:
        cur.execute("SELECT perfil_id FROM usuarios.perfil WHERE codigo = %s",
                    ("PRUEBA_COORD",))
        fila = cur.fetchone()
    assert fila, "el perfil no se creo"
    perfil_id = fila[0]

    # Nace SIN permisos: un perfil que naciera con un conjunto "razonable"
    # concederia accesos que nadie decidio conceder.
    with cn, cn.cursor() as cur:
        cur.execute("SELECT count(*) FROM usuarios.perfil_permiso WHERE perfil_id = %s",
                    (perfil_id,))
        assert cur.fetchone()[0] == 0

    # Un permiso ordinario se concede sin mas.
    with cn, cn.cursor() as cur:
        cur.execute("SELECT permiso_id FROM usuarios.permiso WHERE codigo = %s",
                    ("AVISO_CONSULTAR",))
        ordinario = cur.fetchone()[0]
    r = cliente.post(f"/administracion/perfiles/{perfil_id}/permisos",
                     data={"permiso_id": ordinario, "conceder": "1"},
                     follow_redirects=False)
    assert r.status_code == 302
    with cn, cn.cursor() as cur:
        cur.execute("SELECT count(*) FROM usuarios.perfil_permiso "
                    " WHERE perfil_id = %s AND permiso_id = %s",
                    (perfil_id, ordinario))
        assert cur.fetchone()[0] == 1

    # Y el permiso recien concedido autoriza de inmediato en la MISMA base
    # que consultan los ocho microservicios: eso es lo que significa que el
    # RBAC sea dirigido por datos.
    with cn, cn.cursor() as cur:
        cur.execute("SELECT p.codigo FROM usuarios.perfil_permiso pp "
                    "  JOIN usuarios.permiso p USING (permiso_id) "
                    " WHERE pp.perfil_id = %s", (perfil_id,))
        assert {f[0] for f in cur.fetchall()} == {"AVISO_CONSULTAR"}

    # Se deja desactivado por la pantalla, que es la operacion soportada.
    cliente.post(f"/administracion/perfiles/{perfil_id}/estado",
                 data={"activo": "0"}, follow_redirects=False)
    with cn, cn.cursor() as cur:
        cur.execute("DELETE FROM usuarios.perfil_permiso WHERE perfil_id = %s",
                    (perfil_id,))
        cur.execute("SELECT activo FROM usuarios.perfil WHERE perfil_id = %s",
                    (perfil_id,))
        assert cur.fetchone()[0] is False, "el perfil no quedo desactivado"
    cn.close()


def test_un_permiso_sensible_exige_motivo(cliente):
    """Sin motivo escrito no se concede, y el motivo queda en la bitácora."""
    _entrar(cliente)
    import psycopg2
    cn = psycopg2.connect(host=os.environ["PG_HOST"], dbname=os.environ["PG_BASE"],
                          user=os.environ["PG_USUARIO"],
                          password=os.environ["PG_CLAVE"])
    with cn, cn.cursor() as cur:
        cur.execute("SELECT perfil_id FROM usuarios.perfil WHERE codigo = 'COLABORADOR'")
        perfil_id = cur.fetchone()[0]
        cur.execute("SELECT permiso_id FROM usuarios.permiso "
                    " WHERE codigo = 'TENDENCIA_CONSULTAR'")
        sensible = cur.fetchone()[0]
        cur.execute("DELETE FROM usuarios.perfil_permiso "
                    " WHERE perfil_id = %s AND permiso_id = %s",
                    (perfil_id, sensible))

    # Sin motivo: no se concede.
    cliente.post(f"/administracion/perfiles/{perfil_id}/permisos",
                 data={"permiso_id": sensible, "conceder": "1", "motivo": "corto"},
                 follow_redirects=False)
    with cn, cn.cursor() as cur:
        cur.execute("SELECT count(*) FROM usuarios.perfil_permiso "
                    " WHERE perfil_id = %s AND permiso_id = %s",
                    (perfil_id, sensible))
        assert cur.fetchone()[0] == 0, "se concedio un permiso sensible sin motivo"

    # Con motivo: se concede y queda escrito.
    motivo = "Piloto de tableros por unidad aprobado por el comite"
    cliente.post(f"/administracion/perfiles/{perfil_id}/permisos",
                 data={"permiso_id": sensible, "conceder": "1", "motivo": motivo},
                 follow_redirects=False)
    with cn, cn.cursor() as cur:
        cur.execute("SELECT count(*) FROM usuarios.perfil_permiso "
                    " WHERE perfil_id = %s AND permiso_id = %s",
                    (perfil_id, sensible))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT recurso_id FROM auditoria.bitacora "
                    " WHERE accion = 'PERFIL_MODIFICADO' "
                    "   AND recurso_id LIKE %s "
                    " ORDER BY fecha_hora DESC LIMIT 1",
                    ("COLABORADOR:TENDENCIA_CONSULTAR%",))
        linea = cur.fetchone()
    assert linea and "motivo=" in linea[0], (
        "la concesion de un permiso sensible no dejo el motivo en la bitacora")

    with cn, cn.cursor() as cur:
        cur.execute("DELETE FROM usuarios.perfil_permiso "
                    " WHERE perfil_id = %s AND permiso_id = %s",
                    (perfil_id, sensible))
    cn.close()


def test_nadie_se_quita_a_si_mismo_la_administracion(cliente):
    """El resguardo contra dejar el sistema sin administradores."""
    _entrar(cliente)
    import psycopg2
    cn = psycopg2.connect(host=os.environ["PG_HOST"], dbname=os.environ["PG_BASE"],
                          user=os.environ["PG_USUARIO"],
                          password=os.environ["PG_CLAVE"])
    with cn, cn.cursor() as cur:
        cur.execute("SELECT perfil_id FROM usuarios.perfil "
                    " WHERE codigo = 'ADMINISTRADOR'")
        perfil_id = cur.fetchone()[0]
        cur.execute("SELECT permiso_id FROM usuarios.permiso "
                    " WHERE codigo = 'USUARIO_ADMIN'")
        permiso_id = cur.fetchone()[0]

    r = cliente.post(f"/administracion/perfiles/{perfil_id}/permisos",
                     data={"permiso_id": permiso_id, "conceder": "0"},
                     follow_redirects=True)
    assert r.status_code == 200
    assert "tu propio perfil" in r.get_data(as_text=True)

    with cn, cn.cursor() as cur:
        cur.execute("SELECT count(*) FROM usuarios.perfil_permiso "
                    " WHERE perfil_id = %s AND permiso_id = %s",
                    (perfil_id, permiso_id))
        assert cur.fetchone()[0] == 1, "se quito USUARIO_ADMIN del propio perfil"
    cn.close()


def test_el_codigo_de_un_perfil_tiene_forma_acotada(cliente):
    _entrar(cliente)
    r = cliente.post("/administracion/perfiles/",
                     data={"codigo": "Lider de Area (nuevo)",
                           "nombre": "Nombre valido"},
                     follow_redirects=True)
    assert "MAYUSCULAS" in r.get_data(as_text=True)


# =========================================================================
# Bandeja de notificaciones
# =========================================================================

def test_la_bandeja_muestra_las_notificaciones(cliente, microservicio):
    _entrar(cliente)
    microservicio["guion"]["/notificaciones/mias"] = RespuestaFalsa({
        "notificaciones": [{
            "notificacion_id": "NTF-0123456789AB",
            "tipo": "CONDICION_DETECTADA",
            "titulo": "Condicion detectada en tu unidad",
            "mensaje": "El motor de reglas detecto una condicion sostenida.",
            "leida": False, "fecha_creacion": "2026-10-13T10:00:00+00:00",
            "fecha_expiracion": "2027-01-11T10:00:00+00:00",
            "unidad_organizacional_id": "UO-CC-TURNO-B", "campania_id": None}],
        "paginacion": {"pagina": 1, "tamano": 20, "total": 1, "total_paginas": 1,
                       "tiene_siguiente": False, "tiene_anterior": False},
        "sin_leer": 1})
    r = cliente.get("/notificaciones/")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "Condicion detectada en tu unidad" in texto
    assert "1 sin leer" in texto
    assert "Marcar como leída" in texto


def test_cuando_el_servicio_no_responde_la_bandeja_lo_dice(cliente, microservicio):
    """No se finge una bandeja vacía.

    Las notificaciones viven solo en MongoDB: no hay segunda copia a la que
    caer. Mostrar una lista vacía haría creer al usuario que no tiene avisos
    pendientes cuando lo que pasa es que el servicio está caído.
    """
    import requests
    _entrar(cliente)
    microservicio["guion"]["/notificaciones/mias"] = requests.Timeout("agotado")
    r = cliente.get("/notificaciones/")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "No se pudo cargar la bandeja" in texto
    assert "no respondio" in texto
    # Y explica por que aqui no hay caida a PostgreSQL.
    assert "únicamente en MongoDB" in texto


def test_marcar_leida_queda_en_la_bitacora(cliente, microservicio):
    _entrar(cliente)
    microservicio["guion"]["/leida"] = RespuestaFalsa(
        {"notificacion_id": "NTF-0123456789AB", "leida": True})
    cliente.post("/notificaciones/NTF-0123456789AB/leida", data={},
                 follow_redirects=False)

    import psycopg2
    cn = psycopg2.connect(host=os.environ["PG_HOST"], dbname=os.environ["PG_BASE"],
                          user=os.environ["PG_USUARIO"],
                          password=os.environ["PG_CLAVE"])
    with cn, cn.cursor() as cur:
        cur.execute("SELECT count(*) FROM auditoria.bitacora "
                    " WHERE accion = 'NOTIFICACION_LEIDA' AND recurso_id = %s",
                    ("NTF-0123456789AB",))
        assert cur.fetchone()[0] >= 1
    cn.close()


def test_una_cifra_en_el_mensaje_se_explica_al_operador(cliente, microservicio):
    """El servicio rechaza; la pantalla tiene que explicar por qué."""
    _entrar(cliente)
    microservicio["guion"]["/api/v1/notificaciones"] = RespuestaFalsa({
        "error": {"codigo": "CIFRA_NO_PERMITIDA",
                  "mensaje": "El mensaje contiene un valor numerico decimal.",
                  "detalles": [], "correlacion_id": "abc"}}, 422)
    r = cliente.post("/notificaciones/enviar", follow_redirects=True, data={
        "tipo": "CONDICION_DETECTADA", "titulo": "Condicion detectada",
        "mensaje": "La carga percibida bajo a 2.9 puntos",
        "unidad_organizacional_id": "UO-CC-TURNO-B"})
    texto = r.get_data(as_text=True)
    assert "cifra" in texto.lower()
    assert "presupuesto de epsilon" in texto or "presupuesto de épsilon" in texto


# =========================================================================
# Carga de evidencias
# =========================================================================

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"


def _plan_existente():
    import psycopg2
    cn = psycopg2.connect(host=os.environ["PG_HOST"], dbname=os.environ["PG_BASE"],
                          user=os.environ["PG_USUARIO"],
                          password=os.environ["PG_CLAVE"])
    with cn, cn.cursor() as cur:
        cur.execute("SELECT intervencion_id FROM intervencion.plan LIMIT 1")
        fila = cur.fetchone()
    cn.close()
    return fila[0] if fila else None


def test_subir_un_pdf_lo_guarda_bajo_su_hash(cliente, microservicio, almacen):
    plan = _plan_existente()
    if not plan:
        pytest.skip("la base de demostracion no trae planes de intervencion")
    _entrar(cliente, "mariana.solis@nexum.com.mx")
    microservicio["guion"]["/api/v1/documentos"] = RespuestaFalsa(
        {"documento_id": "DOC-0123456789AB", "version": 1}, 201)

    r = cliente.post("/evidencias/", follow_redirects=True, data={
        "intervencion_id": plan,
        "descripcion": "Minuta de la sesion del comite",
        "archivo": (io.BytesIO(PDF), "minuta.pdf")},
        content_type="multipart/form-data")
    assert r.status_code == 200
    assert "Evidencia cargada" in r.get_data(as_text=True)

    sha = hashlib.sha256(PDF).hexdigest()
    ruta = os.path.join(almacen, sha[:2], sha[2:4], sha)
    assert os.path.exists(ruta), "el archivo no quedo en el almacen"
    with open(ruta, "rb") as f:
        assert f.read() == PDF

    # Los metadatos se mandaron a documents-service SIN el contenido del
    # archivo: MongoDB no es un almacen de archivos.
    envios = [c for c in microservicio["llamadas"]
              if c[0] == "POST" and "/api/v1/documentos" in c[1]]
    assert envios, microservicio["llamadas"]
    contenido = envios[-1][2]["contenido"]
    assert contenido["sha256"] == sha
    assert contenido["bytes"] == len(PDF)
    assert "datos" not in contenido and "base64" not in contenido


def test_un_ejecutable_renombrado_a_pdf_se_rechaza(cliente, microservicio, almacen):
    """El tipo se decide por el contenido, no por la extensión."""
    plan = _plan_existente()
    if not plan:
        pytest.skip("la base de demostracion no trae planes de intervencion")
    _entrar(cliente, "mariana.solis@nexum.com.mx")
    falso = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 50

    antes = sum(len(f) for _, _, f in os.walk(almacen))
    r = cliente.post("/evidencias/", follow_redirects=True, data={
        "intervencion_id": plan,
        "descripcion": "Intento de subir un binario disfrazado",
        "archivo": (io.BytesIO(falso), "documento.pdf")},
        content_type="multipart/form-data")
    texto = r.get_data(as_text=True)
    assert "no corresponde a un pdf" in texto
    assert "firma del formato" in texto

    sha = hashlib.sha256(falso).hexdigest()
    assert not os.path.exists(os.path.join(almacen, sha[:2], sha[2:4], sha)), \
        "se guardo un archivo cuyo contenido no corresponde al formato"
    assert sum(len(f) for _, _, f in os.walk(almacen)) == antes


def test_un_nombre_con_rutas_no_escribe_fuera_del_almacen(cliente, microservicio,
                                                          almacen):
    """El nombre del cliente nunca se usa como ruta.

    Se guarda bajo el SHA-256 del contenido, así que un nombre como
    ../../etc/passwd no tiene a dónde escapar.
    """
    plan = _plan_existente()
    if not plan:
        pytest.skip("la base de demostracion no trae planes de intervencion")
    _entrar(cliente, "mariana.solis@nexum.com.mx")
    microservicio["guion"]["/api/v1/documentos"] = RespuestaFalsa(
        {"documento_id": "DOC-0123456789AC", "version": 1}, 201)
    contenido = PDF + b"%otro\n"

    cliente.post("/evidencias/", follow_redirects=True, data={
        "intervencion_id": plan,
        "descripcion": "Prueba de nombre con rutas relativas",
        "archivo": (io.BytesIO(contenido), "../../../../tmp/escapado.pdf")},
        content_type="multipart/form-data")

    sha = hashlib.sha256(contenido).hexdigest()
    assert os.path.exists(os.path.join(almacen, sha[:2], sha[2:4], sha))
    assert not os.path.exists("/tmp/escapado.pdf")
    # El nombre original se conserva como metadato, ya limpiado.
    envios = [c for c in microservicio["llamadas"]
              if c[0] == "POST" and "/api/v1/documentos" in c[1]]
    assert envios, microservicio["llamadas"]
    nombre = envios[-1][2]["contenido"]["nombre_original"]
    assert "/" not in nombre and ".." not in nombre


def test_el_mismo_archivo_dos_veces_no_se_duplica(cliente, microservicio, almacen):
    plan = _plan_existente()
    if not plan:
        pytest.skip("la base de demostracion no trae planes de intervencion")
    _entrar(cliente, "mariana.solis@nexum.com.mx")
    microservicio["guion"]["/api/v1/documentos"] = RespuestaFalsa(
        {"documento_id": "DOC-0123456789AD", "version": 1}, 201)
    contenido = PDF + b"%repetido\n"

    for _ in range(2):
        cliente.post("/evidencias/", follow_redirects=True, data={
            "intervencion_id": plan,
            "descripcion": "Archivo repetido a proposito",
            "archivo": (io.BytesIO(contenido), "repetido.pdf")},
            content_type="multipart/form-data")

    sha = hashlib.sha256(contenido).hexdigest()
    carpeta = os.path.join(almacen, sha[:2], sha[2:4])
    assert os.listdir(carpeta) == [sha], os.listdir(carpeta)


def test_sin_plan_no_se_acepta_el_archivo(cliente, microservicio):
    _entrar(cliente, "mariana.solis@nexum.com.mx")
    r = cliente.post("/evidencias/", follow_redirects=True, data={
        "intervencion_id": "",
        "descripcion": "Archivo sin plan asociado",
        "archivo": (io.BytesIO(PDF), "suelto.pdf")},
        content_type="multipart/form-data")
    assert "a que plan de intervencion pertenece" in r.get_data(as_text=True)


def test_un_colaborador_no_carga_evidencias(cliente):
    _entrar(cliente, "ana.perez@nexum.com.mx")
    r = cliente.get("/evidencias/", follow_redirects=False)
    assert r.status_code == 302
    assert "denegado" in r.headers["Location"]


def test_un_archivo_alterado_en_el_almacen_no_se_entrega(cliente, microservicio,
                                                         almacen):
    """Guardar el sello y no comprobarlo nunca sería tenerlo de adorno."""
    plan = _plan_existente()
    if not plan:
        pytest.skip("la base de demostracion no trae planes de intervencion")
    _entrar(cliente, "mariana.solis@nexum.com.mx")
    contenido = PDF + b"%para-alterar\n"
    sha = hashlib.sha256(contenido).hexdigest()
    microservicio["guion"]["/api/v1/documentos"] = RespuestaFalsa(
        {"documento_id": "DOC-0123456789AE", "version": 1}, 201)
    cliente.post("/evidencias/", follow_redirects=True, data={
        "intervencion_id": plan, "descripcion": "Archivo que sera alterado",
        "archivo": (io.BytesIO(contenido), "alterado.pdf")},
        content_type="multipart/form-data")

    ruta = os.path.join(almacen, sha[:2], sha[2:4], sha)
    assert os.path.exists(ruta)
    with open(ruta, "ab") as f:
        f.write(b"%alteracion-posterior\n")

    microservicio["guion"]["/api/v1/documentos/DOC-0123456789AE"] = RespuestaFalsa({
        "documento_id": "DOC-0123456789AE",
        "contenido": {"clase": "EVIDENCIA_ARCHIVO", "sha256": sha,
                      "nombre_original": "alterado.pdf", "formato": "pdf",
                      "tipo_mime": "application/pdf"}})
    r = cliente.get("/evidencias/DOC-0123456789AE/archivo", follow_redirects=True)
    texto = r.get_data(as_text=True)
    assert "no coincide con su sello" in texto
    assert "No se entrega" in texto or "no se entrega" in texto
