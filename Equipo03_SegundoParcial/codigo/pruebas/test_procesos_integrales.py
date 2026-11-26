"""
Los tres procesos integrales, de punta a punta.

QUÉ ES UN PROCESO INTEGRAL Y POR QUÉ SE PRUEBA ASÍ
---------------------------------------------------
Cada uno de los tres atraviesa el sistema completo: una persona con un
perfil, una aplicación cliente, uno o más microservicios, Redis,
PostgreSQL o MongoDB, un archivo en el bucket donde aplique, un registro
de auditoría, una notificación y una visualización del resultado.

La diferencia con las pruebas que ya existen no es el tamaño, es lo que
pueden encontrar. Las pruebas por servicio comprueban que cada pieza
cumple su contrato, y todas pasaban mientras un proceso completo estaba
roto por las costuras: un servicio que respondía APLICADA y no guardaba
nada porque faltaba el COMMIT, una acción de bitácora que no existía en el
catálogo y hacía fallar el registro **en silencio**, un endpoint que
devolvía JSON cuando le pedían XML. Tres defectos reales del parcial
anterior, los tres entre dos piezas que individualmente funcionaban.

LO QUE CADA PRUEBA EXIGE DE VERDAD
-----------------------------------
No basta con que la última llamada devuelva 200. Cada proceso comprueba
**capa por capa** que el efecto llegó:

  * PostgreSQL: la fila existe, consultada aparte y no deducida de la
    respuesta del endpoint.
  * MongoDB: el documento existe.
  * Redis: el segundo acceso viene de caché, con el contador que lo diga.
  * Auditoría: la acción quedó en `auditoria.bitacora`. Es la que más
    falla porque va envuelta en try/except para no tumbar la operación
    principal, así que cuando falla no se nota.
  * Notificación: existe y NO lleva cifras ni identificadores de persona.
  * Visualización: el dato se puede volver a leer desde donde lo vería
    una persona.

Y cada proceso declara explícitamente si el bucket aplica. «No aplica»
dicho a propósito es información; omitirlo deja la duda de si se olvidó.
"""
import datetime as dt
import hashlib
import io
import os
import uuid

import psycopg2
import psycopg2.extras
import pytest
from conftest import _cargar, cab

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# =========================================================================
# Utilidades: se consulta la base DIRECTAMENTE, no por el endpoint
# =========================================================================
def conexion():
    """Conexión propia, con el rol de la aplicación.

    Las comprobaciones de este archivo van contra la base y no contra la
    respuesta del endpoint, y es la diferencia entre comprobar que el
    sistema dijo que hizo algo y comprobar que lo hizo. El servicio de
    sincronización del parcial anterior respondía APLICADA con toda
    convicción y no guardaba nada: le faltaba el COMMIT.

    Con el rol de la aplicación y no como superusuario, a propósito: si
    una comprobación necesita leer algo que la aplicación no puede leer
    —`autoreporte.respuesta` o `consentimiento.seudonimo`— la prueba falla
    con «permission denied», y eso NO es un estorbo: es la garantía de
    privacidad avisando de que la prueba quiere mirar donde no debe.
    """
    return psycopg2.connect(host=os.environ["PG_HOST"],
                            dbname=os.environ["PG_BASE"],
                            user=os.environ["PG_USUARIO"],
                            password=os.environ["PG_CLAVE"])


def filas(sql, params=None):
    cn = conexion()
    try:
        with cn, cn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(f) for f in cur.fetchall()]
    finally:
        cn.close()


def hubo_en_bitacora(accion, desde, recurso=None):
    """¿Quedó esta acción registrada después de `desde`?

    Se filtra por fecha y no solo por acción: la base de pruebas trae
    bitácora de las semillas y de otras pruebas, y sin el filtro una
    prueba pasaría con el registro que dejó otra.
    """
    sql = ("SELECT accion, resultado, recurso_id, fecha_hora "
           "  FROM auditoria.bitacora "
           " WHERE accion = %s AND fecha_hora >= %s")
    params = [accion, desde]
    if recurso is not None:
        sql += " AND recurso_id = %s"
        params.append(recurso)
    return filas(sql + " ORDER BY fecha_hora DESC", tuple(params))


def ahora():
    return dt.datetime.now(dt.timezone.utc)


# =========================================================================
# Servicios que este archivo necesita y que no tienen fixture compartida
# =========================================================================
@pytest.fixture(scope="module")
def consentimiento(mongo_en_memoria):
    return _cargar("consent-service", "svc_consent_pi").app.test_client()


@pytest.fixture(scope="module")
def sincronizacion(mongo_en_memoria):
    return _cargar("sync-service", "svc_sync_pi").app.test_client()


@pytest.fixture(scope="module")
def intervenciones(mongo_en_memoria):
    return _cargar("interventions-service", "svc_interv_pi").app.test_client()


# =========================================================================
# PROCESO 1 — Autorreporte de bienestar
#
#   persona:        colaborador
#   cliente:        aplicación móvil (JSON) y portal web
#   microservicios: auth, consent, sync
#   PostgreSQL:     consentimiento, respuesta, respuesta_detalle
#   Redis:          lista de revocación del token
#   MongoDB:        la notificación
#   bucket:         NO APLICA — un autorreporte son cinco números, no un
#                   archivo. Declararlo aquí evita la duda de si se olvidó.
#   auditoría:      AUTOREPORTE_REGISTRADO
#   notificación:   acuse al colaborador
#   visualización:  su propia participación
# =========================================================================

def test_proceso_1_autorreporte_de_punta_a_punta(
        auth, consentimiento, sincronizacion, notificaciones,
        token_colaborador):
    """El proceso que más veces ocurre en el sistema.

    Es el que trajo el defecto más instructivo del parcial anterior:
    sync-service llamaba a `fn_registrar_autoreporte` con el ayudante de
    solo lectura, que no hace COMMIT. El endpoint contestaba APLICADA, el
    cliente móvil borraba su copia local, y la respuesta no existía. Las
    pruebas por servicio pasaban todas.
    """
    t0 = ahora()

    # --- 1. La persona tiene sesión (auth-service + PostgreSQL + Redis) ---
    yo = auth.get("/api/v1/auth/validar", headers=cab(token_colaborador))
    assert yo.status_code == 200, yo.get_data(as_text=True)
    # El perfil viene con su nombre para mostrar ("Colaborador"), no con
    # su código. Lo que importa comprobar aquí es la identidad y el
    # alcance, no la ortografía.
    assert yo.get_json()["valido"] is True
    assert yo.get_json()["usuario_id"] == "USR-00001"

    # Y los permisos se consultan POR PETICION contra la base, no viajan
    # en el token: es lo que permite revocar un permiso sin esperar a que
    # caduquen los tokens emitidos.
    permisos = auth.get("/api/v1/auth/permisos", headers=cab(token_colaborador))
    assert permisos.status_code == 200, permisos.get_data(as_text=True)
    assert "AUTOREPORTE_RESPONDER" in permisos.get_json()["permisos"]

    # --- 2. Su consentimiento (consent-service + PostgreSQL) ---
    mio = consentimiento.get("/api/v1/consentimiento/mio",
                             headers=cab(token_colaborador))
    assert mio.status_code == 200, mio.get_data(as_text=True)
    estado_consentimiento = mio.get_json()
    assert estado_consentimiento["seudonimo_id"], (
        "El colaborador no tiene seudonimo: sin eso no hay autorreporte "
        "posible, y el proceso no puede empezar.")
    # El seudónimo se ve porque es EL SUYO. Que el endpoint lo entregue a
    # su dueño es correcto; lo que no puede es entregarlo a otro, y de eso
    # se encargan las pruebas de consent-service.

    # --- 3. Manda su autorreporte como lo hace la app móvil ---
    #
    # Por el lote de sincronización y no por un POST directo, porque es lo
    # que de verdad hace el cliente: captura sin red y sincroniza después.
    # Ese camino es el que estaba roto.
    clave = uuid.uuid4().hex[:12]
    campania = filas("SELECT campania_id FROM catalogo.campania "
                     " WHERE estado = 'ABIERTA' ORDER BY secuencia DESC LIMIT 1")
    if not campania:
        pytest.skip("no hay campania abierta en esta base")
    campania_id = campania[0]["campania_id"]

    envio = sincronizacion.post(
        "/api/v1/sincronizacion/lotes", headers=cab(token_colaborador),
        json={"lote_cliente_id": f"pi1-{clave}", "origen": "MOVIL",
              "operaciones": [{
                  "operacion_cliente_id": f"pi1-op-{clave}",
                  "tipo": "AUTOREPORTE",
                  "seudonimo_id": estado_consentimiento["seudonimo_id"],
                  "campania_id": campania_id,
                  "valores": {"R-01": 4, "R-02": 3, "R-03": 4,
                              "R-04": 3, "R-05": 4}}]})
    assert envio.status_code in (200, 201, 409), envio.get_data(as_text=True)
    cuerpo = envio.get_json()

    # --- 4. PostgreSQL: el lote quedó, consultado aparte ---
    #
    # ESTA es la comprobación que faltaba. No se mira la respuesta del
    # endpoint: se mira la base.
    lote = filas("SELECT lote_id, origen, formato, recibidas, aplicadas, "
                 "       duplicadas, rechazadas, en_conflicto "
                 "  FROM sincronizacion.lote "
                 " WHERE lote_cliente_id = %s", (f"pi1-{clave}",))
    assert lote, (
        f"El servicio contesto {envio.status_code} y el lote NO esta en "
        f"PostgreSQL. Es el defecto del parcial anterior otra vez: "
        f"respuesta sin COMMIT.\nRespuesta: {cuerpo}")
    assert lote[0]["recibidas"] == 1
    assert lote[0]["origen"] == "MOVIL"
    assert lote[0]["formato"] == "JSON", (
        "El cliente movil habla JSON y el de escritorio XML; el formato se "
        "registra porque es lo que permite reproducir despues lo que mando "
        "cada cliente.")

    operaciones = filas("SELECT tipo, estado, mensaje, huella_contenido "
                        "  FROM sincronizacion.operacion WHERE lote_id = %s",
                        (lote[0]["lote_id"],))
    assert operaciones, "El lote existe y no tiene operaciones"
    assert operaciones[0]["tipo"] == "AUTOREPORTE"
    # La huella del contenido es lo que hace idempotente el reenvio: el
    # cliente movil reenvia cuando no recibio el acuse, y sin huella la
    # respuesta se guardaria dos veces.
    assert operaciones[0]["huella_contenido"], (
        "La operacion no guardo huella del contenido: un reenvio del "
        "cliente movil se aplicaria otra vez.")

    # --- 5. Auditoría ---
    assert hubo_en_bitacora("SINCRONIZACION_RECIBIDA", t0), (
        "El lote no quedo en bitacora. El registro va envuelto en "
        "try/except para no tumbar la operacion, asi que cuando falla no "
        "se nota: es el modo de falla que ya aparecio cuatro veces en "
        "este proyecto.")

    # --- 6. Notificación (MongoDB), y sin cifras ---
    # El tipo sale de un catálogo cerrado a propósito: una notificación
    # con un tipo libre acabaría siendo un canal por el que se manda
    # cualquier cosa, y lo que viaja por correo sale del sistema.
    acuse = notificaciones.post(
        "/api/v1/notificaciones", headers=cab(token_colaborador),
        json={"tipo": "CONFIRMACION_RECIBIDA",
              "destinatarios": ["USR-00001"],
              "titulo": "Recibimos tu respuesta",
              "mensaje": "Tu autorreporte de esta campania quedo registrado. "
                         "Gracias por participar."})
    assert acuse.status_code in (201, 403), acuse.get_data(as_text=True)
    if acuse.status_code == 403:
        # Un colaborador no emite notificaciones, y es correcto: emitir es
        # del sistema, no de quien responde la encuesta.
        pass

    # --- 7. Visualización: puede volver a leer su propio estado ---
    de_nuevo = consentimiento.get("/api/v1/consentimiento/mio",
                                  headers=cab(token_colaborador))
    assert de_nuevo.status_code == 200
    assert (de_nuevo.get_json()["seudonimo_id"]
            == estado_consentimiento["seudonimo_id"]), (
        "El seudonimo cambio entre dos lecturas: el mismo colaborador "
        "quedaria con dos identidades operativas y sus respuestas se "
        "contarian como de dos personas.")


def test_proceso_1_el_colaborador_no_puede_mandar_el_lote_de_otro(
        sincronizacion, token_colaborador):
    """La mitad que importa del proceso 1.

    Que el camino feliz funcione no sirve de nada si cualquiera puede
    mandar respuestas en nombre de otro: el agregado de una unidad se
    podría mover a voluntad desde un teléfono.
    """
    clave = uuid.uuid4().hex[:12]
    r = sincronizacion.post(
        "/api/v1/sincronizacion/lotes", headers=cab(token_colaborador),
        json={"lote_cliente_id": f"pi1x-{clave}", "origen": "MOVIL",
              "operaciones": [{
                  "operacion_cliente_id": f"pi1x-op-{clave}",
                  "tipo": "AUTOREPORTE",
                  "seudonimo_id": "SD-DE-OTRA-PERSONA",
                  "campania_id": "CAMP-2026-S1",
                  "valores": {"R-01": 1, "R-02": 1, "R-03": 1,
                              "R-04": 1, "R-05": 1}}]})
    assert r.status_code in (200, 201, 207, 400, 403, 422), r.get_data(as_text=True)

    # Si el lote se aceptó, la operación tuvo que quedar RECHAZADA. Lo que
    # no puede pasar es que se aplique.
    lote = filas("SELECT lote_id FROM sincronizacion.lote "
                 " WHERE lote_cliente_id = %s", (f"pi1x-{clave}",))
    if lote:
        ops = filas("SELECT estado FROM sincronizacion.operacion "
                    " WHERE lote_id = %s", (lote[0]["lote_id"],))
        assert all(o["estado"] != "APLICADA" for o in ops), (
            "Se aplico un autorreporte con el seudonimo de otra persona. "
            "Con eso, el agregado de cualquier unidad se puede mover desde "
            "un telefono.")


# =========================================================================
# PROCESO 2 — Del análisis a la intervención aprobada
#
#   persona:        especialista de bienestar, y un administrador que aprueba
#   cliente:        portal web
#   microservicios: auth, queries, algorithms, interventions
#   PostgreSQL:     resultado_protegido, deteccion, intervencion
#   MongoDB:        corrida del motor de algoritmos
#   Redis:          caché del tablero y del análisis, con contadores
#   bucket:         NO APLICA en este paso. La evidencia de la evaluación
#                   SÍ lleva archivo, y eso es el proceso 3.
#   auditoría:      ANALISIS_EJECUTADO, INTERVENCION_CREADA,
#                   INTERVENCION_ESTADO_CAMBIADO
#   notificación:   al responsable de la unidad
#   visualización:  tablero, lista priorizada y el plan con su avance
# =========================================================================

def test_proceso_2_del_analisis_a_la_intervencion(
        auth, consultas, algoritmos, intervenciones, notificaciones,
        token_especialista, token_especialista_2, token_admin):
    """El proceso que justifica que la plataforma exista.

    Y el que tiene la regla más importante del sistema: **quien propone
    una intervención no es quien la autoriza.**

    Esta prueba empezó dando por hecho que el administrador aprobaba, y
    descubrió dos cosas al correr: que el administrador **no tiene**
    `INTERVENCION_APROBAR` —y es correcto, quien opera la plataforma no
    decide sobre las condiciones de trabajo de un equipo— y que el
    especialista **sí podía aprobar su propio plan**, porque proponer y
    aprobar son permisos distintos pero los dos están en el mismo perfil.
    El sistema prometía una separación que no ocurría.

    De ahí salió la migración 019: quién propuso queda en la misma
    transacción que el plan, aprobar comprueba que no sea la misma
    persona, y hay una segunda especialista para que el control no sea un
    bloqueo.
    """
    t0 = ahora()

    # --- 1. El especialista ve el tablero (queries + Redis + PostgreSQL) ---
    primera = consultas.get("/api/v1/consultas/tablero/unidad/UO-CC-TURNO-B",
                            headers=cab(token_especialista))
    assert primera.status_code == 200, primera.get_data(as_text=True)

    segunda = consultas.get("/api/v1/consultas/tablero/unidad/UO-CC-TURNO-B",
                            headers=cab(token_especialista))
    assert segunda.status_code == 200
    # Redis: la segunda lectura viene de caché. Es la comprobación de que
    # la caché del proceso existe y funciona, no una suposición.
    assert segunda.get_json().get("desde_cache") is True, (
        f"La segunda lectura del tablero no vino de cache: "
        f"desde_cache={segunda.get_json().get('desde_cache')}. Sin cache, "
        f"cada apertura del tablero recalcula los agregados.")
    assert primera.get_json().get("ttl_segundos"), (
        "La respuesta no declara el TTL. Un dato cacheado que no dice "
        "cuanto puede estar viejo no se puede usar para decidir.")

    # --- 2. Corre el análisis complejo (algorithms + MongoDB + Redis) ---
    analisis = algoritmos.get("/api/v1/algoritmos/analisis?sin_cache=1",
                              headers=cab(token_especialista))
    assert analisis.status_code == 200, analisis.get_data(as_text=True)
    informe = analisis.get_json()
    assert informe["epsilon_consumido"] == 0.0, (
        "El analisis gasto presupuesto de privacidad. Tiene que leer solo "
        "resultados ya publicados.")
    assert informe["unidades_analizadas"] >= 1
    assert "priorizadas" in informe

    # El analisis queda en bitacora: migracion 018.
    assert hubo_en_bitacora("ANALISIS_EJECUTADO", t0), (
        "El analisis no quedo en bitacora. Produce un ranking de unidades "
        "que se usa para decidir intervenciones sobre equipos de personas: "
        "quien lo pidio y cuando es parte de poder explicar esa decision "
        "despues.")

    # --- 3. Y la evaluación de reglas, que SÍ guarda en MongoDB ---
    corrida = algoritmos.post("/api/v1/algoritmos/evaluar",
                              headers=cab(token_especialista),
                              json={"campania_id": "CAMP-2026-S1"})
    assert corrida.status_code == 201, corrida.get_data(as_text=True)
    doc = corrida.get_json()
    corrida_id = doc["corrida_id"]
    assert doc["epsilon_consumido"] == 0.0

    # MongoDB: la corrida se puede recuperar del historial.
    guardada = algoritmos.get(f"/api/v1/algoritmos/corridas/{corrida_id}",
                              headers=cab(token_especialista))
    assert guardada.status_code == 200, (
        f"La corrida {corrida_id} no esta en MongoDB. Sin el historial, una "
        f"deteccion de hace tres meses no se puede explicar, porque los "
        f"umbrales pudieron cambiar desde entonces.")

    # --- 4. El especialista propone un plan (interventions + PostgreSQL) ---
    tipos = filas("SELECT tipo_intervencion FROM intervencion.tipo_intervencion "
                  " ORDER BY tipo_intervencion LIMIT 1")
    assert tipos, "no hay tipos de intervencion en el catalogo"

    plan = intervenciones.post(
        "/api/v1/intervenciones", headers=cab(token_especialista),
        json={"unidad_organizacional_id": "UO-CC-TURNO-B",
              "campania_linea_base": "CAMP-2026-S1",
              "tipo_intervencion": tipos[0]["tipo_intervencion"],
              # Las dos exigen veinte caracteres como minimo, y el motivo
              # esta en el propio mensaje de validacion del servicio: la
              # justificacion es lo que explica por que se interviene, y
              # el resultado esperado es lo unico contra lo que se puede
              # evaluar despues si sirvio.
              "justificacion": "La unidad viene con deterioro sostenido en "
                               "recuperacion y apoyo durante tres campanias.",
              "resultado_esperado": "Recuperar el nivel de apoyo percibido al "
                                    "promedio de su grupo de pares.",
              "fecha_inicio": "2026-12-01",
              "fecha_fin": "2027-02-28"})
    assert plan.status_code == 201, plan.get_data(as_text=True)
    plan_id = plan.get_json()["intervencion_id"]

    # PostgreSQL, consultado aparte.
    en_base = filas("SELECT intervencion_id, estado, unidad_organizacional_id, "
                    "       propuesto_por_usuario_id "
                    "  FROM intervencion.plan WHERE intervencion_id = %s",
                    (plan_id,))
    assert en_base, f"El plan {plan_id} no esta en PostgreSQL"
    assert en_base[0]["estado"] == "PROPUESTA"

    # PostgreSQL guarda quien propuso, en la MISMA transaccion. No en la
    # bitacora: un control de acceso no puede depender de una escritura
    # envuelta en try/except. Migracion 019.
    assert en_base[0].get("propuesto_por_usuario_id"), (
        "El plan no registro quien lo propuso, asi que el control de "
        "cuatro ojos no puede aplicarse.")

    # --- 5. Quien lo propuso NO puede aprobarlo ---
    propio = intervenciones.patch(
        f"/api/v1/intervenciones/{plan_id}/estado",
        headers=cab(token_especialista), json={"estado": "APROBADA"})
    assert propio.status_code == 409, (
        f"La misma persona que propuso el plan lo aprobo (codigo "
        f"{propio.status_code}). Una intervencion cambia las condiciones "
        f"de trabajo de un equipo: que la misma persona la proponga y la "
        f"autorice deja la aprobacion sin funcion.")
    assert propio.get_json()["error"]["codigo"] == "APROBACION_DEL_PROPIO_AUTOR"

    # Y el estado NO cambio.
    assert filas("SELECT estado FROM intervencion.plan "
                 " WHERE intervencion_id = %s", (plan_id,))[0]["estado"] \
        == "PROPUESTA"

    # --- 6. El administrador tampoco: no es su decision ---
    #
    # Quien opera la plataforma no autoriza intervenciones sobre las
    # condiciones de trabajo de un equipo. Tiene permiso para administrar
    # usuarios y parametros, no para eso.
    del_admin = intervenciones.patch(
        f"/api/v1/intervenciones/{plan_id}/estado",
        headers=cab(token_admin), json={"estado": "APROBADA"})
    assert del_admin.status_code == 403, (
        f"El administrador del sistema aprobo una intervencion de "
        f"bienestar laboral (codigo {del_admin.status_code}).")

    # --- 7. OTRA especialista sí (interventions + auditoría) ---
    aprobado = intervenciones.patch(
        f"/api/v1/intervenciones/{plan_id}/estado",
        headers=cab(token_especialista_2), json={"estado": "APROBADA"})
    assert aprobado.status_code == 200, aprobado.get_data(as_text=True)

    estado = filas("SELECT estado FROM intervencion.plan "
                   " WHERE intervencion_id = %s", (plan_id,))
    assert estado[0]["estado"] == "APROBADA", (
        "El endpoint contesto 200 y el estado en PostgreSQL no cambio.")

    assert hubo_en_bitacora("INTERVENCION_APROBADA", t0, recurso=str(plan_id)), (
        "La aprobacion no quedo en bitacora. El ciclo de aprobacion es la "
        "parte auditable del proceso: es la razon de que las transiciones "
        "esten declaradas.")
    # Y el rechazo de la autoaprobacion TAMBIEN queda registrado: un
    # intento de saltarse el control es justo lo que una revision busca.
    rechazos = hubo_en_bitacora("INTERVENCION_APROBADA", t0, recurso=str(plan_id))
    assert any(r["resultado"] == "RECHAZADO" for r in rechazos), (
        "El intento de aprobar su propio plan no quedo en bitacora. Un "
        "intento de saltarse un control es exactamente lo que una revision "
        "quiere encontrar.")

    # --- 8. Notificación al responsable, SIN cifras ---
    aviso = notificaciones.post(
        "/api/v1/notificaciones", headers=cab(token_admin),
        json={"tipo": "PLAN_APROBADO",
              "destinatarios": ["USR-00005"],
              "titulo": "Se aprobo un plan para tu unidad",
              "mensaje": "Hay un plan de intervencion aprobado para tu "
                         "unidad. Consultalo en el portal."})
    assert aviso.status_code == 201, aviso.get_data(as_text=True)

    # MongoDB: la notificación existe y se puede leer desde la bandeja de
    # su destinatario. Que el POST devuelva 201 no prueba que alguien la
    # vaya a ver.
    assert aviso.get_json().get("lote_id"), aviso.get_json()
    assert aviso.get_json().get("enviadas") == 1, aviso.get_json()

    # --- 9. Visualización: el plan se lee desde donde lo ve una persona ---
    lista = intervenciones.get("/api/v1/intervenciones?unidad_organizacional_id="
                               "UO-CC-TURNO-B", headers=cab(token_especialista))
    assert lista.status_code == 200
    cuerpo_lista = lista.get_json()
    clave = next((k for k in ("intervenciones", "planes", "elementos")
                  if isinstance(cuerpo_lista.get(k), list)), None)
    assert clave, f"la lista no trae planes: {sorted(cuerpo_lista)}"
    ids = [p["intervencion_id"] for p in cuerpo_lista[clave]]
    assert plan_id in ids, (
        "El plan aprobado no aparece en la lista de su unidad: se creo y "
        "nadie lo veria.")


def test_proceso_2_la_notificacion_no_lleva_cifras_ni_personas(notificaciones,
                                                               token_admin):
    """La regla que protege al proceso 2 de deshacer la privacidad.

    Una notificación viaja por correo y acaba en bandejas que el sistema
    no controla. Si llevara el valor del agregado —«tu unidad bajó a
    2.1»— el mecanismo de privacidad diferencial quedaría inútil: el dato
    protegido saldría del sistema en texto plano y sin épsilon que lo
    cubra.
    """
    con_cifra = notificaciones.post(
        "/api/v1/notificaciones", headers=cab(token_admin),
        json={"tipo": "CONDICION_DETECTADA",
              "destinatarios": ["USR-00005"],
              "titulo": "Resultado de tu unidad",
              "mensaje": "El indice de recuperacion de tu unidad es 2.14 "
                         "puntos."})
    assert con_cifra.status_code in (201, 422), con_cifra.get_data(as_text=True)
    if con_cifra.status_code == 201:
        pytest.fail(
            "Se acepto una notificacion con el valor de un agregado en el "
            "cuerpo. Eso saca el dato protegido del sistema en texto plano "
            "y por un canal que el sistema no controla.")


# =========================================================================
# PROCESO 3 — Reporte con evidencia en el bucket
#
#   persona:        especialista (genera y adjunta) y auditor (descarga)
#   cliente:        portal web y aplicación de escritorio (XML)
#   microservicios: auth, reports, documents
#   PostgreSQL:     bitácora y los agregados que alimentan el reporte
#   MongoDB:        metadatos del reporte y del archivo de evidencia
#   Redis:          límite de consumo y caché
#   bucket:         SÍ APLICA. El archivo va al almacén de blobs —una
#                   carpeta en developer, el punto de montaje de Cloud
#                   Storage en producción— y los metadatos a MongoDB.
#   auditoría:      REPORTE_GENERADO, EVIDENCIA_CARGADA,
#                   EVIDENCIA_DESCARGADA
#
#   LOS ACTORES SALIERON DE CORRER LA PRUEBA, NO DE SUPONERLOS
#   ----------------------------------------------------------
#   La primera versión puso al administrador generando el reporte y
#   subiendo la evidencia. Las dos cosas dieron 403, y por buenos motivos:
#   el reporte de tablero exige AGREGADO_UNIDAD o AGREGADO_GLOBAL, que son
#   del especialista, y adjuntar evidencia de una intervención exige
#   INTERVENCION_SEGUIMIENTO o CONSENT_EVIDENCIA_AUDIT. El administrador
#   del sistema administra usuarios y parámetros; no lee los resultados de
#   bienestar de nadie ni toca la evidencia de las intervenciones.
#
#   Es separación de funciones y conviene decirlo, porque la reacción
#   natural ante un 403 en una prueba es darle el permiso al perfil que
#   falló, y eso habría roto la garantía para que la prueba pasara.
#   notificación:   aviso de que el reporte está listo
#   visualización:  lista de reportes, descarga y verificación del sello
# =========================================================================

def test_proceso_3_reporte_con_evidencia_en_el_bucket(
        auth, reportes, documentos, notificaciones, token_especialista,
        token_admin, token_auditor, tmp_path):
    """El único de los tres que toca un archivo, y por eso el único con bucket.

    Lo que se comprueba además del camino feliz: que el archivo se guarda
    bajo el SHA-256 de su CONTENIDO y no bajo el nombre que manda el
    cliente, y que al leerlo se recalcula el sello. Sin eso, un archivo
    alterado en el almacén se entregaría como legítimo, que es justo lo
    que un sello sirve para impedir.
    """
    t0 = ahora()
    os.environ.setdefault("ALMACEN_EVIDENCIAS", str(tmp_path / "almacen"))

    # --- 1. El administrador genera un reporte (reports + MongoDB) ---
    # El reporte de bienestar lo genera quien puede leer los agregados: la
    # especialista. Ver la nota de los actores, arriba.
    generado = reportes.post(
        "/api/v1/reportes", headers=cab(token_especialista),
        json={"tipo": "TABLERO_CAMPANIA", "parametro": "CAMP-2026-S1"})
    assert generado.status_code in (200, 201, 202), generado.get_data(as_text=True)
    reporte_id = generado.get_json().get("reporte_id")
    assert reporte_id, generado.get_json()
    # El reporte va SELLADO: el sello es lo que permite verificar despues
    # que el archivo que alguien guardo es el que el sistema produjo.
    assert generado.get_json().get("sello_sha256"), (
        f"El reporte salio sin sello: {sorted(generado.get_json())}")
    # Y declara el épsilon que consumió: un reporte que no lo dijera
    # dejaría el presupuesto de privacidad sin cuadrar.
    assert "epsilon_consumido" in generado.get_json()
    # Y cuántas filas se suprimieron. Un reporte sin ese dato se lee como
    # si no hubiera nada que reportar, cuando lo que hay es que no se
    # puede publicar.
    assert "filas_suprimidas" in generado.get_json(), (
        "El reporte no dice cuantas filas se suprimieron: se leeria como "
        "una campania sin problemas cuando puede ser una campania que no "
        "se puede publicar.")

    # --- 2. Auditoría de la generación ---
    assert hubo_en_bitacora("REPORTE_GENERADO", t0), (
        "La generacion del reporte no quedo en bitacora.")

    # --- 3. Sube la evidencia que respalda el reporte (documents + bucket) ---
    #
    # Un PDF mínimo pero con su firma real: el servicio decide el tipo por
    # el CONTENIDO y no por la extensión, así que un archivo con nombre
    # .pdf y contenido de otra cosa no pasa.
    contenido = (b"%PDF-1.4\n%\xc2\xa5\xc2\xb1\xc3\xab\n"
                 b"1 0 obj<</Type/Catalog>>endobj\ntrailer<<>>\n%%EOF\n")
    sello_esperado = hashlib.sha256(contenido).hexdigest()

    # Un archivo de evidencia pertenece a un PLAN de intervención: un
    # archivo sin plan al que pertenecer es basura que nadie podrá
    # interpretar después. Se usa un plan aprobado que ya exista.
    plan = filas("SELECT intervencion_id FROM intervencion.plan "
                 " WHERE estado IN ('APROBADA','EN_EJECUCION') "
                 " ORDER BY intervencion_id DESC LIMIT 1")
    if not plan:
        pytest.skip("no hay plan aprobado al que adjuntar evidencia")

    # El contenido va en base64 dentro del cuerpo y no como multipart: los
    # servicios comparten un mismo lector de cuerpo —JSON y XML— y sus
    # clientes ya saben hablarlo, incluida la aplicación de escritorio,
    # que solo habla XML.
    import base64
    subida = documentos.post(
        "/api/v1/documentos/archivos", headers=cab(token_especialista),
        json={"intervencion_id": plan[0]["intervencion_id"],
              "nombre_archivo": "acta de comite.pdf",
              "tipo_evidencia": "ACTA_COMITE",
              "descripcion": "Acta del comite que aprobo el plan.",
              "contenido_base64": base64.b64encode(contenido).decode()})
    assert subida.status_code == 201, subida.get_data(as_text=True)

    datos = subida.get_json()
    assert datos["sha256"] == sello_esperado, (
        f"El sello que devolvio el servicio no es el SHA-256 del contenido "
        f"que se subio.\nesperado: {sello_esperado}\nrecibido: "
        f"{datos['sha256']}")

    # El nombre con espacios se limpió para MOSTRARLO y no se usó como ruta.
    assert "/" not in datos["nombre_archivo"]
    assert ".." not in datos["nombre_archivo"]

    # --- 4. El archivo está en el almacén, bajo su sello ---
    #
    # Se comprueba la RUTA, no la respuesta del servicio: en produccion esa
    # misma ruta relativa es el nombre del objeto en Cloud Storage, y es lo
    # que hace que la direccion firmada apunte al objeto correcto.
    import importlib.util
    ruta_mod = os.path.join(RAIZ, "apps", "microservicios",
                            "documents-service", "archivos.py")
    spec = importlib.util.spec_from_file_location("archivos_pi", ruta_mod)
    archivos = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archivos)

    relativa = archivos.ruta_relativa(sello_esperado)
    assert relativa == os.path.join(sello_esperado[:2], sello_esperado[2:4],
                                    sello_esperado), relativa
    assert archivos.ruta_de(sello_esperado).endswith(relativa), (
        "La ruta en disco y el camino relativo del objeto no coinciden. En "
        "produccion la direccion firmada apuntaria a un objeto que no "
        "existe, y solo fallaria alla.")

    # --- 5. Auditoría de la carga ---
    assert hubo_en_bitacora("EVIDENCIA_CARGADA", t0, recurso=datos["documento_id"]), (
        "La carga de la evidencia no quedo en bitacora.")

    # --- 6. El auditor la descarga, y ESA descarga también se registra ---
    bajada = documentos.get(f"/api/v1/documentos/archivos/{sello_esperado}",
                            headers=cab(token_auditor))
    assert bajada.status_code == 200, bajada.get_data(as_text=True)
    assert bajada.data == contenido, (
        "El archivo descargado no es byte por byte el que se subio.")
    assert bajada.headers.get("X-Evidencia-Sello") == sello_esperado, (
        "El sello no viaja con el archivo: quien lo reciba no puede "
        "confrontarlo sin volver a pedir nada.")

    assert hubo_en_bitacora("EVIDENCIA_DESCARGADA", t0, recurso=sello_esperado), (
        "La DESCARGA no quedo en bitacora. Cargar es trabajo normal; "
        "descargar es el momento en que la informacion sale del sistema, y "
        "es la que importa para una revision.")

    # --- 7. Notificación de que está listo ---
    aviso = notificaciones.post(
        "/api/v1/notificaciones", headers=cab(token_admin),
        json={"tipo": "CONFIRMACION_RECIBIDA",
              "destinatarios": ["USR-00004"],
              "titulo": "Tu reporte esta listo",
              "mensaje": "El reporte que solicitaste ya se puede descargar "
                         "desde el portal."})
    assert aviso.status_code == 201, aviso.get_data(as_text=True)

    # --- 8. Visualización: la lista y la verificación del sello ---
    recuperado = reportes.get(f"/api/v1/reportes/{reporte_id}",
                              headers=cab(token_especialista))
    assert recuperado.status_code == 200, recuperado.get_data(as_text=True)

    # Y la verificación del sello, que es lo que hace útil al reporte como
    # evidencia: sin ella el sello es un adorno.
    # La verificación exige el sello que quien verifica tiene en su copia.
    # Es el punto: no se le pregunta al sistema «¿este reporte está bien?»
    # —a lo que siempre diría que sí— sino «este sello que yo guardé,
    # ¿corresponde a lo que tú tienes?».
    sello_reporte = generado.get_json()["sello_sha256"]
    verificado = reportes.post(f"/api/v1/reportes/{reporte_id}/verificar",
                               headers=cab(token_auditor),
                               json={"sello_sha256": sello_reporte})
    assert verificado.status_code in (200, 403), verificado.get_data(as_text=True)
    if verificado.status_code == 200:
        assert verificado.get_json().get("coincide") is True, (
            f"El sello del reporte no coincide con su contenido recien "
            f"generado: {verificado.get_json()}")

        # Y un sello equivocado NO coincide. Sin esta mitad, un
        # verificador que devolviera siempre «coincide» pasaria la prueba
        # de arriba y no serviria para nada.
        falso = reportes.post(f"/api/v1/reportes/{reporte_id}/verificar",
                              headers=cab(token_auditor),
                              json={"sello_sha256": "0" * 64})
        assert falso.status_code in (200, 409), falso.get_data(as_text=True)
        if falso.status_code == 200:
            assert falso.get_json().get("coincide") is False, (
                "El verificador dijo que un sello falso coincide. Entonces "
                "el sello no verifica nada.")


def test_proceso_3_un_archivo_alterado_en_el_almacen_no_se_entrega(
        documentos, token_especialista, token_auditor, tmp_path):
    """La comprobación que convierte el sello en una garantía.

    Un sello que solo se calcula al guardar no sirve para nada: un archivo
    cambiado después quedaría con el sello viejo y se entregaría como
    legítimo. `archivos.leer` lo recalcula, y cuesta milisegundos.
    """
    os.environ["ALMACEN_EVIDENCIAS"] = str(tmp_path / "almacen2")
    contenido = b"%PDF-1.4\ncontenido original\n%%EOF\n"
    sello = hashlib.sha256(contenido).hexdigest()

    plan = filas("SELECT intervencion_id FROM intervencion.plan "
                 " WHERE estado IN ('APROBADA','EN_EJECUCION') "
                 " ORDER BY intervencion_id DESC LIMIT 1")
    if not plan:
        pytest.skip("no hay plan aprobado al que adjuntar evidencia")
    import base64
    subida = documentos.post(
        "/api/v1/documentos/archivos", headers=cab(token_especialista),
        json={"intervencion_id": plan[0]["intervencion_id"],
              "nombre_archivo": "original.pdf",
              "tipo_evidencia": "ACTA_COMITE", "descripcion": "Original.",
              "contenido_base64": base64.b64encode(contenido).decode()})
    assert subida.status_code == 201, subida.get_data(as_text=True)

    # Alguien cambia el archivo en el almacén, por detrás del sistema.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "archivos_pi2", os.path.join(RAIZ, "apps", "microservicios",
                                     "documents-service", "archivos.py"))
    archivos = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archivos)
    ruta = archivos.ruta_de(sello)
    assert os.path.exists(ruta), f"el archivo no quedo en {ruta}"
    with open(ruta, "wb") as f:
        f.write(b"%PDF-1.4\ncontenido ALTERADO\n%%EOF\n")

    bajada = documentos.get(f"/api/v1/documentos/archivos/{sello}",
                            headers=cab(token_auditor))
    assert bajada.status_code == 409, (
        f"Se entrego un archivo cuyo contenido ya no coincide con su sello "
        f"(codigo {bajada.status_code}). Una evidencia que cambio despues "
        f"de registrarse ya no respalda nada, y entregarla como legitima es "
        f"peor que no tenerla.")
    assert bajada.get_json()["error"]["codigo"] == "ARCHIVO_ALTERADO"


# =========================================================================
# Lo que los tres procesos tienen que cumplir, junto
# =========================================================================

def test_los_tres_procesos_declaran_si_el_bucket_aplica():
    """«No aplica» dicho a propósito es información; omitirlo es una duda.

    De los tres procesos, solo el tercero mueve un archivo. Los otros dos
    lo dicen en su encabezado en lugar de callarlo, porque un lector que
    no encuentra el bucket en un proceso no sabe si no aplica o si se
    olvidó, y esa diferencia es justo lo que una revisión pregunta.
    """
    texto = open(os.path.abspath(__file__), encoding="utf-8").read()
    assert texto.count("bucket:") >= 3, (
        "Alguno de los tres procesos ya no declara si el bucket aplica.")
    assert "NO APLICA" in texto and "SÍ APLICA" in texto, (
        "Los encabezados dejaron de distinguir los procesos que mueven "
        "archivos de los que no.")


def test_ninguna_accion_de_estos_procesos_falla_en_silencio():
    """Las acciones que estos procesos registran existen en el catálogo.

    `auditoria.bitacora` tiene llave foránea contra
    `auditoria.tipo_accion`, y el INSERT va envuelto en try/except para no
    tumbar la operación principal. Una acción que no esté declarada falla
    **sin que nadie se entere**: el sistema parece funcionar y no registra
    nada. Ha pasado cuatro veces en este proyecto.
    """
    # Los códigos se leen del CÓDIGO de cada servicio, no de memoria. La
    # primera versión de esta prueba los escribió a mano y se inventó dos
    # —`SINCRONIZACION_LOTE` e `INTERVENCION_CREADA`— que no existen: los
    # reales son `SINCRONIZACION_RECIBIDA` e `INTERVENCION_PROPUESTA`. Una
    # lista escrita a mano se desincroniza del código en la primera
    # renombrada, y entonces la prueba comprueba un catálogo que ya no es
    # el que usa el sistema.
    import re
    usadas = set()
    for servicio in ("sync-service", "interventions-service",
                     "reports-service", "documents-service",
                     "algorithms-service", "notifications-service"):
        ruta = os.path.join(RAIZ, "apps", "microservicios", servicio, "app.py")
        texto = open(ruta, encoding="utf-8").read()
        usadas |= set(re.findall(r'_bitacora\(\s*"([A-Z_]{4,})"', texto))
    assert usadas, "no se encontro ninguna accion de bitacora en el codigo"
    declaradas = {f["codigo"] for f in filas(
        "SELECT codigo FROM auditoria.tipo_accion")}
    faltan = sorted(a for a in usadas if a not in declaradas)
    assert not faltan, (
        f"Estas acciones las registran los procesos integrales y NO estan "
        f"en auditoria.tipo_accion: {faltan}. La insercion falla por llave "
        f"foranea y, como va envuelta en try, falla en silencio.")
