"""
Genera los esquemas JSON a partir de los contratos OpenAPI.

Por qué generarlos y no escribirlos aparte: si el esquema JSON se escribe a
mano junto al OpenAPI, los dos se desincronizan en cuanto alguien cambia un
campo en uno solo. Aquí hay una sola fuente —el contrato que publica cada
servicio— y los archivos de contratos/json/ se derivan de ella.

    python3 contratos/generar_json.py

Produce un archivo por esquema, en JSON Schema draft 2020-12, con las
referencias internas reescritas para que cada archivo se valide solo.
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "contratos", "json")
COMUN_PY = os.path.join(RAIZ, "apps", "microservicios", "comun")
if COMUN_PY not in sys.path:
    sys.path.insert(0, COMUN_PY)

SERVICIOS = {
    "auth-service": "svc_auth_gen",
    "users-service": "svc_users_gen",
    "documents-service": "svc_docs_gen",
    "notifications-service": "svc_notif_gen",
    "queries-service": "svc_queries_gen",
    "reports-service": "svc_reports_gen",
    "algorithms-service": "svc_alg_gen",
    "audit-service": "svc_audit_gen",
    "configuration-service": "svc_config_gen",
    "consent-service": "svc_consent_gen",
    "data-governance-service": "svc_datagov_gen",
    "export-service": "svc_export_gen",
    "integration-service": "svc_integ_gen",
    "interventions-service": "svc_interv_gen",
    "monitoring-service": "svc_monit_gen",
    "privacy-service": "svc_priv_gen",
    "sync-service": "svc_sync_gen",
    "trends-service": "svc_trends_gen",
}

# Servicios en Node: su contrato vive en openapi.yaml junto al servicio.
# Se leen del archivo para que sus esquemas salgan en el mismo lote y con
# la misma conversion a JSON Schema draft 2020-12.
SERVICIOS_YAML = {
    "catalog-service": "openapi.yaml",
    "main-process-service": "openapi.yaml",
    "survey-service": "openapi.yaml",
    "indicators-service": "openapi.yaml",
    "support-service": "openapi.yaml",
    "organizational-service": "openapi.yaml",
}


def _crear_cliente_mongo_memoria():
    """Shim ligero en memoria para importar servicios cuando falta mongomock/pymongo."""
    class _ColeccionMemoria:
        def create_index(self, *args, **kwargs):
            return "idx_memoria"

        def find(self, *args, **kwargs):
            return []

        def find_one(self, *args, **kwargs):
            return None

    class _BaseMemoria:
        def __getitem__(self, _nombre):
            return _ColeccionMemoria()

    class _AdminMemoria:
        def command(self, *args, **kwargs):
            return {"ok": 1}

    class _ClienteMemoria:
        def __init__(self, *args, **kwargs):
            self.admin = _AdminMemoria()

        def __getitem__(self, _nombre):
            return _BaseMemoria()

    return _ClienteMemoria


def _asegurar_mongo_en_memoria():
    """Sustituye MongoDB en memoria para importar los servicios Python sin BD viva."""
    try:
        import pymongo  # noqa: F401
    except ModuleNotFoundError:
        import types
        modulo_pymongo = types.ModuleType("pymongo")
        modulo_pymongo.ASCENDING = 1
        modulo_pymongo.DESCENDING = -1
        modulo_pymongo.MongoClient = _crear_cliente_mongo_memoria()
        sys.modules["pymongo"] = modulo_pymongo

    try:
        import mongomock
        cliente = mongomock.MongoClient()
    except ModuleNotFoundError:
        cliente = _crear_cliente_mongo_memoria()()

    import comun.mongo as m
    m.obtener_cliente = lambda: cliente
    m.base = lambda: cliente["bienestar"]
    m.ping = lambda: None


def cargar_contrato(servicio, alias):
    """Importa el servicio solo para leer su contrato, sin levantarlo."""
    import importlib.util
    carpeta = os.path.join(RAIZ, "apps", "microservicios", servicio)
    sys.path.insert(0, carpeta)
    try:
        spec = importlib.util.spec_from_file_location(alias,
                                                      os.path.join(carpeta, "app.py"))
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[alias] = modulo
        spec.loader.exec_module(modulo)
        cliente = modulo.app.test_client()
        return cliente.get("/openapi.json").get_json()
    finally:
        sys.path.remove(carpeta)
        for mod_local in ("contrato", "archivos", "preferencias"):
            sys.modules.pop(mod_local, None)


def cargar_contrato_yaml(servicio, archivo):
    """Lee el openapi.yaml de un servicio de Node.

    No se importa nada: el archivo es el contrato. Si el servicio de Node
    cambiara su YAML sin regenerar esta carpeta, la prueba de contratos lo
    detecta, que es justo lo que se quiere.
    """
    import yaml
    ruta = os.path.join(RAIZ, "apps", "microservicios", servicio, archivo)
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)


def convertir(nodo):
    """Traduce de OpenAPI 3.0 a JSON Schema 2020-12.

    Dos diferencias que importan:

      - Las referencias cambian de #/components/schemas/X a #/$defs/X,
        porque cada archivo generado se valida por si solo.
      - OpenAPI 3.0 expresa "puede venir sin dato" con nullable: true;
        JSON Schema lo expresa poniendo "null" entre los tipos. Sin esta
        traduccion, un campo nulo legitimo —por ejemplo un alcance
        organizacional que significa "toda la organizacion"— haria fallar
        la validacion.
    """
    if isinstance(nodo, dict):
        salida = {}
        for k, v in nodo.items():
            if k == "$ref" and isinstance(v, str) \
                    and v.startswith("#/components/schemas/"):
                salida[k] = "#/$defs/" + v.rsplit("/", 1)[1]
            elif k == "nullable":
                continue          # se resuelve mas abajo sobre 'type'
            else:
                salida[k] = convertir(v)
        if nodo.get("nullable") is True:
            tipo = salida.get("type")
            if isinstance(tipo, str):
                salida["type"] = [tipo, "null"]
            elif isinstance(tipo, list) and "null" not in tipo:
                salida["type"] = tipo + ["null"]
            elif tipo is None:
                salida.setdefault("type", ["null"])
        return salida
    if isinstance(nodo, list):
        return [convertir(x) for x in nodo]
    return nodo


# Nombre conservado por compatibilidad con llamadas previas.
reescribir_refs = convertir


def main():
    os.makedirs(SALIDA, exist_ok=True)
    # Sustitucion en memoria para poder importar los servicios que usan MongoDB.
    _asegurar_mongo_en_memoria()

    contratos = [(s, cargar_contrato(s, a)) for s, a in SERVICIOS.items()]
    contratos += [(s, cargar_contrato_yaml(s, a))
                  for s, a in SERVICIOS_YAML.items()]

    escritos = []
    for servicio, contrato in contratos:
        todos = (contrato.get("components") or {}).get("schemas") or {}
        if not todos:
            print(f"  aviso: {servicio} no declara components.schemas")
            continue
        for nombre, esquema in todos.items():
            doc = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"https://nexum.com.mx/bienestar/contratos/{nombre}.schema.json",
                "title": nombre,
                "description": f"Generado desde el contrato OpenAPI de {servicio}. "
                               f"No editar a mano: ejecutar contratos/generar_json.py.",
                **reescribir_refs(esquema),
                "$defs": {k: reescribir_refs(v) for k, v in todos.items()
                          if k != nombre},
            }
            ruta = os.path.join(SALIDA, f"{nombre}.schema.json")
            with open(ruta, "w", encoding="utf8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
                f.write("\n")
            escritos.append(os.path.basename(ruta))

    print(f"{len(escritos)} esquemas JSON generados en contratos/json/")
    for e in sorted(set(escritos)):
        print("  ", e)


if __name__ == "__main__":
    main()
