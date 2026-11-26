"""
La sonda de listo: que una dependencia OPCIONAL caída no la haga lenta.

POR QUÉ ESTE ARCHIVO EXISTE
---------------------------
`algorithms-service` declara MongoDB como dependencia opcional: evalúa
leyendo agregados de PostgreSQL y solo usa MongoDB para guardar el
historial de corridas. Con MongoDB caído el servicio atiende
perfectamente, y por eso la sonda responde «degradado» con 200 en lugar
de sacarlo de rotación con un 503.

Eso estaba bien y seguía estando roto por otro lado, y se midió:

    sonda de algorithms-service con MongoDB abajo:  1286 ms
    panel de monitoreo (sondea los 24 en paralelo):  1.6 s

La causa: el cliente de MongoDB espera 1.2 s antes de rendirse, y la
sonda lo esperaba en cada llamada. El efecto anula el sentido de haber
declarado la dependencia opcional — un orquestador que sondea con un
segundo de paciencia declara muerto a un servicio que está atendiendo
bien, y justamente por preguntar si algo que no necesita está disponible.

Las dos correcciones, y las dos están aquí:

  1. **Presupuesto propio** para las comprobaciones opcionales (300 ms):
     si no contesta en ese plazo se da por caída sin esperarla más.
  2. **Recuerdo del fallo** (15 s): un fallo ES una espera agotada, así
     que recordarlo evita pagarla otra vez. Solo se recuerdan los fallos
     y solo de las opcionales.

Y la asimetría, que es la decisión que de verdad importa: una
dependencia ESENCIAL no se recuerda nunca y no tiene presupuesto. Su
resultado decide si mandar tráfico, y ahí vale más la respuesta correcta
que la rápida: un «listo» viejo sobre una esencial manda tráfico a un
servicio roto, y una esencial que vuelve tiene que detectarse en la
siguiente sonda y no quince segundos después.
"""
import importlib
import time

import pytest


@pytest.fixture
def servicio_limpio():
    """Un módulo `servicio` recién importado por prueba.

    El recuerdo de fallos vive en el módulo, así que dos pruebas que lo
    comparten se contaminan: la segunda vería el fallo que recordó la
    primera y pasaría o fallaría por el motivo equivocado.
    """
    from comun import servicio
    importlib.reload(servicio)
    return servicio


def _cliente(servicio, comprobaciones):
    app = servicio.crear_servicio("prueba", "sonda", comprobaciones=comprobaciones)
    app.config.update(TESTING=True)
    return app.test_client()


def test_una_opcional_lenta_no_hace_lenta_la_sonda(servicio_limpio):
    """El caso que motivó todo: 1286 ms de sonda por algo opcional.

    La comprobación tarda dos segundos a propósito. El presupuesto es de
    300 ms, así que la sonda tiene que contestar muy por debajo de eso y
    reportar la dependencia como caída.
    """
    servicio_limpio.PRESUPUESTO_OPCIONAL_S = 0.3

    def lentisima():
        time.sleep(2.0)

    c = _cliente(servicio_limpio, {"lenta": (lentisima, "opcional")})

    t0 = time.perf_counter()
    r = c.get("/health/ready")
    transcurrido = time.perf_counter() - t0

    assert r.status_code == 200, (
        "Una dependencia OPCIONAL caida no puede sacar al servicio de "
        "rotacion: atiende sin ella.")
    cuerpo = r.get_json()
    assert cuerpo["estado"] == "degradado"
    assert cuerpo["degradado_por"] == ["lenta"]
    assert transcurrido < 1.0, (
        f"La sonda tardo {transcurrido * 1000:.0f} ms esperando una "
        f"dependencia opcional. Con un orquestador que sondea con un "
        f"segundo de paciencia, un servicio sano queda fuera de rotacion.")


def test_tras_un_fallo_se_reintenta_con_presupuesto_corto(servicio_limpio):
    """El recuerdo cambia la PREGUNTA, no la cancela.

    La primera versión de esto no reintentaba: devolvía el fallo
    recordado y seguía. Era rápido y estaba mal, y lo encontró
    `test_la_recuperacion_de_una_opcional_se_detecta_de_inmediato`: una
    dependencia que volvía seguía anunciándose caída quince segundos, y
    quien opera estaría mirando una falla que ya no existe.

    Sí se reintenta, con un presupuesto mucho más corto, porque con un
    fallo recordado la pregunta es más fácil: no «¿funciona?» sino «¿ya
    volvió?». Una dependencia local viva contesta a un ping en menos de
    un milisegundo, así que si no contesta en cincuenta sigue caída.
    """
    servicio_limpio.PRESUPUESTO_OPCIONAL_S = 0.4
    servicio_limpio.PRESUPUESTO_REINTENTO_S = 0.05
    servicio_limpio.RECUERDO_FALLO_OPCIONAL_S = 30

    llamadas = []

    def lenta_y_rota():
        llamadas.append(1)
        time.sleep(1.0)
        raise RuntimeError("documentos:27017 no responde")

    c = _cliente(servicio_limpio, {"opcional": (lenta_y_rota, "opcional")})

    t0 = time.perf_counter()
    c.get("/health/ready")
    primera = time.perf_counter() - t0

    # La comprobación tarda 1 s y el presupuesto es 0.4 s, así que la
    # primera sonda se rindió antes de que el cliente dijera su error. El
    # hilo sigue su curso: se le da el tiempo de terminar y apuntar la
    # causa de verdad, que es lo que la siguiente sonda tiene que
    # reportar. Sin esto lo único que quedaría es «no contestó», que no
    # distingue un nombre de host que no resuelve de una conexión
    # rechazada.
    time.sleep(0.9)

    t0 = time.perf_counter()
    r = c.get("/health/ready")
    segunda = time.perf_counter() - t0

    assert len(llamadas) >= 2, (
        "No se reintento. Entonces una dependencia que vuelve no se "
        "detecta hasta que caduque el recuerdo.")
    assert segunda < primera / 3, (
        f"La segunda sonda tardo {segunda * 1000:.0f} ms contra "
        f"{primera * 1000:.0f} ms de la primera: no se esta usando el "
        f"presupuesto corto del reintento.")
    assert segunda < 0.15, (
        f"La segunda sonda tardo {segunda * 1000:.0f} ms. Con un "
        f"orquestador que sondea con un segundo de paciencia esto tiene "
        f"que quedar muy por debajo.")

    detalle = r.get_json()["dependencias"]["opcional"]
    assert detalle["ok"] is False
    # El error que se reporta es el PRIMERO, no el del reintento corto:
    # «no contesto en 50 ms» no informa de nada, y «documentos:27017 no
    # responde» dice qué arreglar.
    assert "27017" in detalle["error"], (
        f"Se perdio la causa original y quedo el error del reintento "
        f"corto: {detalle['error']}")
    assert "caida_desde_hace_s" in detalle, (
        "El detalle no dice desde cuando esta caida. Sin eso no se "
        "distingue un fallo que acaba de empezar de uno de hace una hora.")
    assert r.get_json()["estado"] == "degradado"


def test_el_exito_de_una_opcional_no_se_recuerda(servicio_limpio):
    """Solo se recuerdan los fallos, y el motivo es que solo los fallos cuestan.

    Una comprobación que funciona cuesta medio milisegundo: no hay nada
    que ahorrar. Y recordar un éxito sería peligroso justo al revés —
    seguiría diciendo «listo» quince segundos después de que la
    dependencia se cayera.
    """
    llamadas = []

    def bien():
        llamadas.append(1)

    c = _cliente(servicio_limpio, {"opcional": (bien, "opcional")})
    for _ in range(4):
        assert c.get("/health/ready").get_json()["estado"] == "listo"

    assert len(llamadas) == 4, (
        f"Se llamo {len(llamadas)} veces en 4 sondas: se esta recordando el "
        f"exito, y entonces una dependencia que se cae seguiria "
        f"reportandose como viva.")


def test_la_recuperacion_de_una_opcional_se_detecta_de_inmediato(servicio_limpio):
    """Cuando vuelve, la siguiente sonda ya dice «listo».

    El recuerdo se borra al primer éxito en lugar de esperar a que
    caduque: si no, un servicio recuperado seguiría anunciándose
    degradado hasta quince segundos después, y quien opera estaría
    mirando una falla que ya no existe.
    """
    servicio_limpio.RECUERDO_FALLO_OPCIONAL_S = 30
    estado = {"rota": True}

    def intermitente():
        if estado["rota"]:
            raise RuntimeError("abajo")

    c = _cliente(servicio_limpio, {"opcional": (intermitente, "opcional")})
    assert c.get("/health/ready").get_json()["estado"] == "degradado"

    estado["rota"] = False
    # El recuerdo del fallo duraria 30 s, pero el intento se hace igual
    # porque un intento que funciona es barato.
    assert c.get("/health/ready").get_json()["estado"] == "listo", (
        "La dependencia opcional volvio y la sonda sigue diciendo "
        "degradado: el recuerdo no se borra al recuperarse.")


def test_una_esencial_caida_si_saca_el_servicio_de_rotacion(servicio_limpio):
    """La otra mitad, para que el arreglo no se haya llevado la garantía."""

    def rota():
        raise RuntimeError("PostgreSQL no responde")

    c = _cliente(servicio_limpio, {"esencial": rota})
    r = c.get("/health/ready")
    assert r.status_code == 503, (
        "Una dependencia ESENCIAL caida tiene que dar 503: el servicio no "
        "puede atender y hay que dejar de mandarle trafico.")
    cuerpo = r.get_json()
    assert cuerpo["estado"] == "no_listo"
    assert cuerpo["falta"] == ["esencial"]


def test_el_fallo_de_una_esencial_NO_se_recuerda(servicio_limpio):
    """La asimetría deliberada, y la prueba que la fija.

    Es tentador recordar también los fallos esenciales: la sonda sería
    rápida siempre. No se hace, y el motivo es la recuperación: un
    servicio cuyo PostgreSQL vuelve tiene que poder recibir tráfico en la
    siguiente sonda, no quince segundos después. Mientras está roto, una
    sonda lenta no cuesta nada real — el veredicto es «no listo» de todas
    formas, y el orquestador ya no le manda tráfico.
    """
    servicio_limpio.RECUERDO_FALLO_OPCIONAL_S = 30
    llamadas = []

    def rota():
        llamadas.append(1)
        raise RuntimeError("abajo")

    c = _cliente(servicio_limpio, {"esencial": rota})
    for _ in range(3):
        assert c.get("/health/ready").status_code == 503

    assert len(llamadas) == 3, (
        f"Se llamo {len(llamadas)} veces en 3 sondas: se esta recordando el "
        f"fallo de una dependencia ESENCIAL. Entonces un servicio cuya base "
        f"de datos vuelve seguiria fuera de rotacion hasta que caduque el "
        f"recuerdo.")


def test_una_esencial_lenta_se_espera_lo_que_haga_falta(servicio_limpio):
    """Las esenciales no tienen presupuesto, y es a propósito.

    Rendirse pronto con una esencial significa declarar caída una base de
    datos que solo estaba ocupada, y sacar de rotación un servicio que
    podía atender. Ahí vale más la respuesta correcta que la rápida.
    """
    servicio_limpio.PRESUPUESTO_OPCIONAL_S = 0.05

    def lenta_pero_viva():
        time.sleep(0.3)

    c = _cliente(servicio_limpio, {"esencial": lenta_pero_viva})
    t0 = time.perf_counter()
    r = c.get("/health/ready")
    transcurrido = time.perf_counter() - t0

    assert r.get_json()["estado"] == "listo", (
        "Una dependencia esencial lenta pero viva se declaro caida: el "
        "presupuesto de las opcionales se esta aplicando tambien a las "
        "esenciales.")
    assert transcurrido >= 0.3, (
        "La sonda contesto antes de que terminara la comprobacion esencial.")


def test_la_sonda_de_vida_no_consulta_dependencias(servicio_limpio):
    """`/health/live` dice si el proceso está vivo, nada más.

    Mezclar las dos sondas es un error común y tiene una consecuencia
    concreta: un orquestador que usa la sonda de vida para decidir si
    REINICIAR el contenedor lo reiniciaría en bucle cada vez que
    PostgreSQL tarda, cuando el proceso está perfectamente.
    """
    llamadas = []

    def comprobacion():
        llamadas.append(1)

    c = _cliente(servicio_limpio, {"algo": comprobacion})
    r = c.get("/health/live")
    assert r.status_code == 200
    assert r.get_json()["estado"] == "vivo"
    assert not llamadas, (
        "La sonda de vida consulto una dependencia. Un orquestador que la "
        "usa para reiniciar el contenedor lo reiniciaria en bucle cada vez "
        "que una dependencia tarde.")
    # Y trae la identidad de la instancia, para que un contenedor que se
    # reinicia en bucle se pueda detectar: sin eso, cada peticion llega a
    # un proceso recien arrancado que contesta «vivo» con toda honestidad.
    assert r.get_json()["instancia"]
    assert r.get_json()["arrancado_en"]


# =========================================================================
# El estado del bucket, y lo que la sonda dice de lo que NO comprueba
# =========================================================================
def test_la_sonda_declara_las_dependencias_que_el_servicio_no_usa(servicio_limpio):
    """Una clave ausente no puede significar dos cosas opuestas.

    Un panel que recibe `dependencias: {postgresql, redis}` no puede
    distinguir «este servicio no usa MongoDB» de «la comprobacion de
    MongoDB no se ejecuto». Las dos se ven igual —la clave no esta— y las
    dos consecuencias son opuestas: la primera es normal, la segunda es un
    hueco de observabilidad.
    """
    c = _cliente(servicio_limpio, {"postgresql": lambda: None,
                                   "redis": lambda: None})
    cuerpo = c.get("/health/ready").get_json()
    assert set(cuerpo["no_aplican"]) == {"mongodb", "almacen"}, (
        f"La sonda no declara lo que no comprueba: {cuerpo.get('no_aplican')}")
    # La invariante: toda dependencia del sistema esta declarada, de un
    # lado o del otro. Si alguna falta en los dos, es un error de
    # declaracion y tiene que notarse.
    declaradas = set(cuerpo["dependencias"]) | set(cuerpo["no_aplican"])
    assert declaradas >= servicio_limpio.DEPENDENCIAS_DEL_SISTEMA


def test_el_bucket_caido_degrada_el_servicio_pero_no_lo_saca_de_rotacion(
        servicio_limpio):
    """Con el almacen caido, documents-service sigue sirviendo metadatos.

    Sacarlo con un 503 apagaria el listado de documentos, la busqueda por
    hash y la consulta de quien subio que —la mayoria del trafico— por una
    falla que solo afecta a la carga y a la descarga.
    """
    def almacen_caido():
        raise RuntimeError("/var/lib/bienestar/evidencias no admite escritura")

    c = _cliente(servicio_limpio, {"postgresql": lambda: None,
                                   "almacen": (almacen_caido, "opcional")})
    r = c.get("/health/ready")
    assert r.status_code == 200, (
        "El almacen caido devolvio 503: eso saca de rotacion un servicio "
        "que todavia atiende toda la consulta de metadatos.")
    cuerpo = r.get_json()
    assert cuerpo["estado"] == "degradado"
    assert cuerpo["degradado_por"] == ["almacen"]
    assert cuerpo["dependencias"]["almacen"]["ok"] is False
    assert cuerpo["dependencias"]["almacen"]["esencial"] is False


def test_documents_service_comprueba_el_almacen():
    """El requisito nombra el bucket, y es el servicio que tiene bucket.

    Se lee la declaracion del servicio y no se sondea: sondearlo requiere
    la base y Mongo arriba, y lo que esta prueba cuida es que la
    comprobacion este DECLARADA. Sin ella el servicio contesta «listo»
    con el almacen muerto, acepta una carga, escribe los metadatos en
    MongoDB y falla al escribir el blob: queda un documento registrado
    cuyo archivo no existe, que es el peor de los dos fallos posibles.
    """
    import pathlib
    import re
    fuente = (pathlib.Path(__file__).resolve().parents[1]
              / "apps/microservicios/documents-service/app.py").read_text()
    bloque = re.search(r"comprobaciones=\{(.*?)\}\)", fuente, re.S)
    assert bloque, "No se encontro la declaracion de comprobaciones."
    assert '"almacen"' in bloque.group(1), (
        "documents-service no comprueba el almacen en su sonda de salud.")
    assert '"opcional"' in bloque.group(1), (
        "El almacen tiene que ser opcional: esencial sacaria el servicio "
        "de rotacion y apagaria la consulta de metadatos.")


def test_el_ping_del_almacen_detecta_una_carpeta_que_no_se_puede_escribir(tmp_path):
    """`isdir` no basta, y esta prueba es la que lo demuestra.

    En production el almacen es el punto de montaje del bucket. Un bucket
    montado de solo lectura —porque la cuenta de servicio perdio el
    permiso, que es la falla de permisos mas comun en GCS— pasa cualquier
    comprobacion de lectura y falla en cada carga.
    """
    import os
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve()
                           .parents[1] / "apps/microservicios/documents-service"))
    import archivos

    previo = os.environ.get("ALMACEN_EVIDENCIAS")
    carpeta = tmp_path / "almacen"
    carpeta.mkdir()
    try:
        os.environ["ALMACEN_EVIDENCIAS"] = str(carpeta)
        archivos.ping_almacen()          # sano: no lanza

        os.environ["ALMACEN_EVIDENCIAS"] = str(tmp_path / "no_existe")
        with pytest.raises(Exception) as caido:
            archivos.ping_almacen()
        assert "no existe" in str(caido.value)

        if os.geteuid() != 0:            # root escribe aunque no tenga el bit
            os.environ["ALMACEN_EVIDENCIAS"] = str(carpeta)
            carpeta.chmod(0o500)
            with pytest.raises(Exception) as solo_lectura:
                archivos.ping_almacen()
            assert "escritura" in str(solo_lectura.value)
    finally:
        carpeta.chmod(0o700)
        if previo is None:
            os.environ.pop("ALMACEN_EVIDENCIAS", None)
        else:
            os.environ["ALMACEN_EVIDENCIAS"] = previo


# =========================================================================
# La sexta situación de fallo: una petición excede el tiempo máximo
# =========================================================================
#
# De las seis situaciones de fallo que el proyecto tiene que demostrar,
# cinco estaban probadas: servicio detenido, Redis caído, MongoDB caído,
# PostgreSQL caído y servicio de archivos caído. Ésta no, y el único tope
# que existía era el de gunicorn, que mata al obrero: el cliente recibe
# una conexión cortada —sin código, sin mensaje, sin identificador de
# correlación—, la consulta sigue viva en PostgreSQL, y se cae además lo
# que ese obrero tenía en vuelo.

def test_una_consulta_que_excede_el_tiempo_maximo_contesta_503_y_no_corta(
        servicio_limpio):
    """PostgreSQL cancela la consulta y el servicio lo traduce.

    `QueryCanceled` caía al manejador genérico de 500 —«error interno»—,
    que manda a buscar un bug en el codigo cuando lo que pasó es que la
    consulta tardó demasiado. Se reconoce por la CLASE de la excepcion y
    no por el texto, que está en inglés y cambia entre versiones.
    """
    import psycopg2.errors

    app = servicio_limpio.crear_servicio("prueba", "tiempos")
    app.config.update(TESTING=False)        # que el manejador conteste

    @app.get("/lenta")
    def _lenta():
        raise psycopg2.errors.QueryCanceled(
            "canceling statement due to statement timeout")

    c = app.test_client()
    r = c.get("/lenta")
    assert r.status_code == 503, (
        f"Una consulta cancelada por tiempo dio {r.status_code}. Un 500 "
        f"dice «el codigo esta roto» y manda a revisar el lugar "
        f"equivocado.")
    cuerpo = r.get_json()
    assert cuerpo["error"]["codigo"] == "TIEMPO_EXCEDIDO"
    # El cliente tiene que poder decirle a quien lo usa qué hacer.
    assert "acota" in cuerpo["error"]["mensaje"].lower()
    assert r.headers.get("Retry-After") == "5"
    # Y la correlación, que es lo que una conexión cortada no deja:
    assert r.headers.get("X-Correlacion-Id")


def test_el_statement_timeout_viaja_en_la_cadena_de_conexion():
    """Si no está en el DSN, cada llamada tendría que acordarse de ponerlo.

    `options` lo aplica PostgreSQL a la sesión entera, así que vale para
    toda consulta que salga del pool.
    """
    from comun import datos
    assert "statement_timeout" in datos._dsn(), (
        "Sin statement_timeout, una consulta lenta no se cancela nunca y "
        "el unico tope es el de gunicorn, que mata al obrero.")
    assert datos.TIEMPO_MAXIMO_CONSULTA_MS <= 30000, (
        "El tope de la consulta tiene que quedar por debajo del de "
        "gunicorn (30 s): si gunicorn actua primero, el cliente recibe "
        "una conexion cortada y nunca ve el 503 explicado.")


def test_un_calculo_largo_en_python_se_rinde_con_un_503_explicado(servicio_limpio):
    """`statement_timeout` no puede cancelar un bucle de Python.

    El motor de análisis agrupa y ajusta tendencias con 110 unidades y 12
    campañas: miles de operaciones, ninguna de ellas una consulta. Sin un
    plazo propio, el único tope sería gunicorn matando al obrero.
    """
    servicio_limpio.TIEMPO_MAXIMO_PETICION_S = 0.2
    app = servicio_limpio.crear_servicio("prueba", "tiempos")
    app.config.update(TESTING=False)
    vueltas = {"n": 0}

    @app.get("/calculo")
    def _calculo():
        for _ in range(1000):
            vueltas["n"] += 1
            servicio_limpio.exigir_tiempo("las series por unidad")
            time.sleep(0.01)
        return {"listo": True}

    r = app.test_client().get("/calculo")
    assert r.status_code == 503, (
        f"El calculo largo dio {r.status_code}: sin plazo propio el unico "
        f"tope seria gunicorn, que no contesta nada.")
    cuerpo = r.get_json()
    assert cuerpo["error"]["codigo"] == "TIEMPO_EXCEDIDO"
    assert "series por unidad" in cuerpo["error"]["mensaje"], (
        "El mensaje no dice en que se estaba gastando el tiempo, que es "
        "lo primero que se pregunta.")
    # Se rindió pronto, no al final: el plazo sirve de algo.
    assert vueltas["n"] < 100, (
        f"Dio {vueltas['n']} vueltas con un plazo de 0.2 s: no se esta "
        f"consultando el plazo dentro del bucle.")
    assert r.headers.get("Retry-After") == "10"


def test_fuera_de_una_peticion_el_plazo_no_corta_nada(servicio_limpio):
    """Los guiones y las pruebas usan los mismos módulos.

    Si `tiempo_restante()` devolviera cero fuera de una petición, todo
    bucle que consulte el plazo se rendiría en la primera iteración y los
    guiones de carga y de rendimiento dejarían de funcionar.
    """
    assert servicio_limpio.tiempo_restante() == float("inf")
    servicio_limpio.exigir_tiempo("nada")      # no lanza


def test_el_plazo_de_la_peticion_queda_por_debajo_del_de_gunicorn():
    """El ORDEN es la decisión: el que actúa primero tiene que ser el que contesta.

    Si gunicorn actuara primero, los dos límites buenos no se verían nunca
    y el cliente seguiría recibiendo una conexión cortada. Se lee del
    Dockerfile real, no de una constante repetida aquí.
    """
    import pathlib
    import re
    raiz = pathlib.Path(__file__).resolve().parents[1]
    from comun import servicio
    from comun import datos

    revisados = 0
    for ruta in sorted((raiz / "apps/microservicios").glob("*/Dockerfile")):
        texto = ruta.read_text()
        if '"gunicorn"' not in texto:
            continue
        hallado = re.search(r'"--timeout","(\d+)"', texto)
        assert hallado, f"{ruta.parent.name} no fija --timeout en gunicorn."
        tope = int(hallado.group(1))
        assert tope > servicio.TIEMPO_MAXIMO_PETICION_S, (
            f"{ruta.parent.name}: gunicorn corta a los {tope} s y el plazo "
            f"de la peticion es {servicio.TIEMPO_MAXIMO_PETICION_S} s. "
            f"Gunicorn actuaria primero y mataria al obrero sin contestar.")
        assert tope * 1000 > datos.TIEMPO_MAXIMO_CONSULTA_MS
        revisados += 1
    assert revisados >= 15, f"Solo se revisaron {revisados} Dockerfiles."
