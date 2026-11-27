"""
Pruebas de carga de Bienestar Nexum.

QUÉ SE SIMULA Y POR QUÉ ESOS PERFILES
--------------------------------------
Cuatro perfiles, porque la plataforma tiene cuatro formas de uso con
patrones de carga **opuestos**, y medirlas juntas escondería a las dos
que importan:

* **Colaborador** (móvil): muchos, cada uno pide poco y escribe de vez en
  cuando. Es el volumen.
* **Especialista** (escritorio): pocos, pero cada consulta recorre
  agregados de muchas unidades. Es el peso.
* **Administrador** (web): abre paneles que tocan varios servicios a la
  vez. Es el abanico.
* **Proceso automático**: sincroniza lotes sin pensar en nadie. Es el
  que satura.

Un escenario único con «usuarios genéricos» daría un promedio que no
describe a ninguno: el p95 saldría bueno porque lo dominan las consultas
baratas del colaborador, y la consulta cara del especialista —la que de
verdad se va a quejar— quedaría enterrada.

POR QUÉ CADA PETICIÓN LLEVA SU `name`
--------------------------------------
Locust agrupa por nombre de ruta. Sin `name`, cada
`/tablero/unidad/UO-XXX` sería una fila distinta en el informe y no
habría forma de ver el p95 de «consultar un tablero». Con `name` fijo,
las mediciones se agregan por OPERACIÓN, que es lo que se compara entre
corridas.

CÓMO SE CORRE
-------------
    locust -f pruebas/carga/locustfile.py --host http://127.0.0.1:8000

    # sin interfaz, para el informe:
    locust -f pruebas/carga/locustfile.py --host http://127.0.0.1:8000 \\
           --headless -u 200 -r 20 -t 5m --csv=resultados/carga

Las variables NEXUM_* de abajo permiten apuntar a los microservicios
directamente en lugar de al portal, que es como se mide el backend sin
el ruido de la capa web.
"""
import os
import itertools
import random
import threading

from locust import HttpUser, LoadTestShape, between, events, task

# Los puertos de cada servicio. Por omisión apuntan a la máquina local;
# en GCP se cambian con variables de ambiente y el mismo archivo sirve.
SERVICIOS = {
    "auth": os.environ.get("NEXUM_AUTH", "http://127.0.0.1:8101"),
    "consultas": os.environ.get("NEXUM_CONSULTAS", "http://127.0.0.1:8107"),
    "reportes": os.environ.get("NEXUM_REPORTES", "http://127.0.0.1:8108"),
    "algoritmos": os.environ.get("NEXUM_ALGORITMOS", "http://127.0.0.1:8109"),
    "tendencias": os.environ.get("NEXUM_TENDENCIAS", "http://127.0.0.1:8114"),
    "sincronizacion": os.environ.get("NEXUM_SYNC", "http://127.0.0.1:8120"),
    "monitoreo": os.environ.get("NEXUM_MONITOREO", "http://127.0.0.1:8123"),
    # Los dos que usa de verdad la aplicación móvil del colaborador.
    "consentimiento": os.environ.get("NEXUM_CONSENT", "http://127.0.0.1:8110"),
    "catalogo": os.environ.get("NEXUM_CATALOGO", "http://127.0.0.1:8103"),
    "organizacion": os.environ.get("NEXUM_ORGANIZACION", "http://127.0.0.1:8117"),
}

USUARIOS = {
    "colaborador": ("ana.perez@nexum.com.mx", "demo123"),
    "especialista": ("mariana.solis@nexum.com.mx", "demo123"),
    "administrador": ("carlos.ramirez@nexum.com.mx", "demo123"),
    "auditor": ("roberto.garcia@nexum.com.mx", "demo123"),
}

# El lote de cuentas de carga: una por usuario virtual, como en
# producción. Las crea `scripts/cuentas_de_carga.sql`, que explica por
# qué hacen falta. Los rangos vienen de ahí.
#
# Sin esto, todos los usuarios virtuales de un perfil comparten un token
# y con él el límite de 120 peticiones por minuto POR TOKEN: se midió, y
# daba 1 012 rechazos con 429 y un 37.9% de errores que hablaban del
# limitador y no del sistema.
# Factor para acortar las esperas entre tareas.
#
# POR QUÉ EXISTE
# --------------
# La rampa normal usa esperas de persona —entre 2 y 15 segundos, según el
# perfil— porque es lo que hace un cliente real. Con 140 usuarios eso dio
# 23 peticiones por segundo, la mediana se quedó PLANA en 14 ms de 7 a
# 140 usuarios y las peticiones por segundo escalaron linealmente: no se
# encontró ningún punto de saturación.
#
# Eso es un buen resultado y es una medición incompleta: «no saturó» sin
# haber encontrado el techo no dice dónde está el techo. Con
# NEXUM_PRISA=20 las esperas se dividen entre veinte y la misma cantidad
# de usuarios genera veinte veces más peticiones, que es la forma de
# llegar al codo sin necesitar tres mil usuarios virtuales ni tres
# máquinas para generarlos.
#
# No pretende ser realista: ningún colaborador abre la aplicación cada
# 100 ms. Pretende encontrar el límite del sistema, que es otra pregunta
# y se reporta aparte.
PRISA = float(os.environ.get("NEXUM_PRISA", "1"))


def espera(minimo, maximo):
    return between(minimo / PRISA, maximo / PRISA)


CUENTAS_DE_CARGA = {
    "colaborador": [(f"carga{n}@nexum.com.mx", "carga123")
                    for n in range(1, 101)],
    "especialista": [(f"carga{n}@nexum.com.mx", "carga123")
                     for n in range(101, 133)],
    "administrador": [(f"carga{n}@nexum.com.mx", "carga123")
                      for n in range(133, 155)],
    "auditor": [(f"carga{n}@nexum.com.mx", "carga123")
                for n in range(155, 167)],
}
_siguiente_cuenta = {perfil: itertools.count()
                     for perfil in CUENTAS_DE_CARGA}
_candado_cuentas = threading.Lock()


def tomar_cuenta(perfil):
    """Una cuenta distinta por usuario virtual, dando la vuelta si se acaban.

    Dar la vuelta en lugar de fallar: si alguien corre con más usuarios
    virtuales que cuentas, lo peor que pasa es que dos compartan el
    límite por token, y es mejor que una corrida que no arranca. Se avisa
    al pasar.
    """
    cuentas = CUENTAS_DE_CARGA.get(perfil) or []
    if not cuentas:
        return USUARIOS[perfil]
    with _candado_cuentas:
        i = next(_siguiente_cuenta[perfil])
    if i and i % len(cuentas) == 0:
        print(f"[carga] se agotaron las {len(cuentas)} cuentas de "
              f"{perfil}: desde aqui se reutilizan y comparten el limite "
              f"por token")
    return cuentas[i % len(cuentas)]

# Unidades contra las que consultar. Se descubren al arrancar para no
# fijarlas a mano: con datos masivos los identificadores cambian, y una
# lista escrita a mano produciría 404 en masa que se leerían como errores
# del sistema cuando el problema sería la prueba.
UNIDADES = []
CAMPANIAS = []

# Servicios que la sonda declaró NO listos antes de empezar. Sus tareas se
# saltan.
#
# POR QUÉ SE SALTAN EN LUGAR DE DEJARLOS FALLAR
# ---------------------------------------------
# Un servicio al que le falta una dependencia esencial responde 503 a
# todo, y esos 503 entrarían en la tasa de error de la corrida. El informe
# diría «4% de errores bajo carga» cuando lo que hubo fue un servicio que
# nunca estuvo arriba: se mezclaría un problema del ambiente con un
# problema de capacidad, que son las dos cosas que una prueba de carga
# existe para distinguir.
#
# Se consulta la sonda, no se adivina. Y se IMPRIME lo que se saltó: una
# corrida que mide la mitad del sistema sin decirlo es peor que no medir.
NO_LISTOS = set()

# El límite de peticiones, que es lo que de verdad hay que respetar
# -----------------------------------------------------------------
# `/auth/login` admite **30 inicios de sesión por minuto y por IP**
# (`limite_consumo(maximo=30, ventana=60)` en auth-service) y el resto de
# los endpoints **120 peticiones por minuto y por token**. Los dos
# límites están bien y protegen de un abuso real.
#
# Lo que hacen es castigar una prueba de carga mal preparada, y se midió
# dos veces antes de llegar a la versión de ahora:
#
#   * un inicio de sesión por usuario virtual a 30 nacimientos por
#     segundo: 65 rechazos con 429 y 899 peticiones con 401 después, de
#     los usuarios que se quedaron sin token. 34.6% de errores.
#   * un token compartido por perfil: 1 012 rechazos con 429, ahora por
#     el límite por token repartido entre cien colaboradores. 37.9%.
#
# Las dos cifras hablaban del limitador y no del sistema. La solución es
# parecerse a producción en las dos cosas: una CUENTA por usuario virtual
# (`CUENTAS_DE_CARGA`) y un RITMO DE LLEGADA creíble (`RampaYVuelta`).



@events.test_start.add_listener
def descubrir(environment, **kwargs):
    """Antes de empezar, averigua contra qué se va a consultar.

    Se hace una sola vez y fuera de la medición: incluirlo en las tareas
    contaminaría los tiempos con peticiones que un cliente real no hace.
    """
    import json
    import urllib.request

    def pedir(url, token=None, datos=None):
        peticion = urllib.request.Request(url)
        peticion.add_header("Content-Type", "application/json")
        if token:
            peticion.add_header("Authorization", f"Bearer {token}")
        cuerpo = json.dumps(datos).encode() if datos else None
        with urllib.request.urlopen(peticion, cuerpo, timeout=10) as r:
            return json.loads(r.read().decode())

    # --- qué está arriba, según su propia sonda ---
    for nombre, base in SERVICIOS.items():
        try:
            with urllib.request.urlopen(f"{base}/health/ready", timeout=5) as r:
                estado = json.loads(r.read().decode()).get("estado")
        except Exception as error:                        # noqa: BLE001
            estado, detalle = "inalcanzable", str(error)[:80]
        else:
            detalle = ""
        # «degradado» SÍ se mide: el servicio atiende con una dependencia
        # opcional caída, y medirlo así es justo el caso interesante.
        if estado not in ("listo", "degradado"):
            NO_LISTOS.add(nombre)
            print(f"[carga] SE SALTA {nombre} ({base}): estado={estado} "
                  f"{detalle}")
        elif estado == "degradado":
            print(f"[carga] {nombre} atiende DEGRADADO: se mide igual")

    try:
        correo, clave = USUARIOS["administrador"]
        sesion = pedir(f"{SERVICIOS['auth']}/api/v1/auth/login",
                       datos={"correo": correo, "contrasena": clave})
        token = sesion["token_acceso"]
        # Las unidades y las campañas se piden a quien las tiene, no al
        # resumen del catálogo: ese endpoint devuelve CONTEOS
        # (`campanias_totales: 17`) y no listas. La primera versión de
        # esto leía `catalogo["unidades"]`, que no existe, y se iba por el
        # `except` sin que nada lo dijera salvo un «descubiertas 0
        # unidades» en medio de la salida. La corrida entonces medía las
        # dos unidades de reserva, que con datos masivos ni existen.
        unidades = pedir(
            f"{SERVICIOS['organizacion']}/api/v1/organizacion/unidades"
            f"?tamano=200", token)
        UNIDADES.extend(u["unidad_organizacional_id"]
                        for u in unidades.get("unidades", []))
        campanias = pedir(
            f"{SERVICIOS['catalogo']}/api/v1/catalogos/campanias?tamano=20",
            token)
        CAMPANIAS.extend(c["campania_id"]
                         for c in campanias.get("campanias", []))
        if not UNIDADES or not CAMPANIAS:
            raise RuntimeError(
                f"el descubrimiento devolvio {len(UNIDADES)} unidades y "
                f"{len(CAMPANIAS)} campanias: la forma de la respuesta "
                f"cambio")
        print(f"[carga] descubiertas {len(UNIDADES)} unidades y "
              f"{len(CAMPANIAS)} campanias")
    except Exception as error:                            # noqa: BLE001
        # Que el descubrimiento falle NO debe tumbar la corrida: se avisa
        # y se sigue con valores por omisión. Una prueba de carga que no
        # arranca por un detalle de preparación no mide nada.
        print(f"[carga] no se pudo descubrir el catalogo: {error}")
        UNIDADES.extend(["UO-CC-TURNO-A", "UO-CC-TURNO-B"])
        CAMPANIAS.extend(["CAMP-2026-S1"])


class UsuarioNexum(HttpUser):
    """Base: inicia sesión una vez y conserva el token.

    Pedir un token en cada tarea mediría el inicio de sesión mil veces y
    no mediría nada más, que es justo lo que no interesa: un cliente real
    inicia sesión una vez y trabaja media hora.
    """
    abstract = True
    perfil = "colaborador"

    # Locust exige un `host` base, y aquí no hay uno: el sistema son
    # veinticuatro microservicios en puertos distintos, y cada tarea
    # construye su URL completa desde `SERVICIOS`. Este valor es un
    # marcador para satisfacer a Locust —sin él se niega a arrancar con
    # «You must specify the base host»— y no lo usa ninguna petición.
    #
    # Se deja apuntando a auth-service y no a una cadena cualquiera porque
    # así, si alguien agrega una tarea con una ruta relativa por
    # descuido, llega a un servicio real y falla de forma visible en lugar
    # de producir un error de conexión que se confunde con el sistema
    # caído.
    host = SERVICIOS["auth"]

    def on_start(self):
        """Inicia sesión una vez, con su PROPIA cuenta.

        Una cuenta por usuario virtual, como en producción: así el límite
        de 120 peticiones por minuto por token no se reparte entre
        cientos de usuarios, que es lo que convertía la corrida en una
        medición del limitador.

        Y se inicia sesión de verdad en lugar de repartir tokens hechos
        de antemano, porque el inicio de sesión ES parte de la carga: una
        plataforma así recibe una oleada de ellos al empezar el turno.
        Lo que hay que respetar es el RITMO —auth-service admite 30 por
        minuto y por IP— y de eso se encarga la forma de la carga, no
        esta función. Ver `RampaYVuelta`.
        """
        correo, clave = tomar_cuenta(self.perfil)
        with self.client.post(f"{SERVICIOS['auth']}/api/v1/auth/login",
                              json={"correo": correo, "contrasena": clave},
                              name="POST /auth/login",
                              catch_response=True) as r:
            if r.status_code == 200:
                self.token = r.json().get("token_acceso")
                r.success()
                return
            self.token = None
            r.failure(f"login {r.status_code}")

        # Sin token no se puede medir nada útil, y seguir sin él produce
        # un 401 por cada tarea durante toda la corrida: se midió, y eran
        # 899 peticiones con 401 y un 34.6% de errores que no hablaban
        # del sistema. Este usuario se para y se dice por qué.
        print(f"[carga] {self.perfil} ({correo}) no pudo entrar: "
              f"este usuario virtual no corre")
        self.stop(force=True)

    @property
    def cab(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def unidad(self):
        return random.choice(UNIDADES) if UNIDADES else "UO-CC-TURNO-B"

    def campania(self):
        return random.choice(CAMPANIAS) if CAMPANIAS else "CAMP-2026-S1"


class Colaborador(UsuarioNexum):
    """El volumen: muchos usuarios móviles pidiendo poco.

    Peso 10 porque en una organización real los colaboradores son el 95%
    de las cuentas. Un reparto equitativo entre perfiles mediría una
    plataforma que no existe.
    """
    weight = 10
    perfil = "colaborador"
    wait_time = espera(2, 8)        # mira el telefono, no martillea

    # CADA PERFIL LLAMA SOLO LO QUE SU PERFIL PUEDE LLAMAR
    # ----------------------------------------------------
    # La primera versión de esta clase pedía /consultas/participacion y
    # /consultas/tablero/unidad/{id}, que exigen AGREGADO_UNIDAD. Un
    # colaborador no tiene ese permiso —y no debe tenerlo: son cifras
    # agregadas de su área, no suyas— así que los dos endpoints
    # devolvían 403.
    #
    # Y el peso del colaborador es 10 de 16, así que esos 403 eran el
    # 52% de las peticiones de la corrida. El informe habría dicho
    # «52% de errores bajo carga» cuando lo que había era el sistema de
    # autorización funcionando correctamente contra una prueba mal
    # escrita. Un número así invalida la corrida entera: nadie puede
    # saber si el 52% es capacidad o es esto.
    #
    # El tablero y la participación se movieron al especialista y al
    # administrador, que son los perfiles que los usan.

    @task(5)
    def mi_estado_de_consentimiento(self):
        """Lo primero que abre la aplicación móvil al arrancar."""
        self.client.get(
            f"{SERVICIOS['consentimiento']}/api/v1/consentimiento/mio",
            headers=self.cab, name="GET /consentimiento/mio")

    @task(3)
    def el_cuestionario(self):
        """Las preguntas que la aplicación dibuja para responder."""
        self.client.get(
            f"{SERVICIOS['catalogo']}/api/v1/catalogos/instrumentos",
            headers=self.cab, name="GET /catalogos/instrumentos")

    @task(1)
    def sincronizar_lote(self):
        """Lo que manda la aplicación móvil tras capturar sin red."""
        import uuid
        clave = uuid.uuid4().hex[:16]
        self.client.post(
            f"{SERVICIOS['sincronizacion']}/api/v1/sincronizacion/lotes",
            headers=self.cab, name="POST /sincronizacion/lotes",
            json={"lote_cliente_id": f"carga-{clave}", "origen": "MOVIL",
                  "operaciones": [{
                      "operacion_cliente_id": f"carga-op-{clave}",
                      "tipo": "AUTOREPORTE", "seudonimo_id": "SD-NO-EXISTE",
                      "campania_id": self.campania(),
                      "valores": {"R-01": 4, "R-02": 3, "R-03": 4,
                                  "R-04": 3, "R-05": 4}}]})


class Especialista(UsuarioNexum):
    """El peso: pocas sesiones, cada consulta recorre muchas unidades."""
    weight = 3
    perfil = "especialista"
    wait_time = espera(5, 15)       # analiza, no navega

    @task(3)
    def tendencia_de_unidad(self):
        self.client.get(
            f"{SERVICIOS['tendencias']}/api/v1/tendencias/unidad/{self.unidad()}",
            headers=self.cab, name="GET /tendencias/unidad/{id}")

    @task(4)
    def tablero_de_unidad(self):
        """Movido aquí del colaborador: exige AGREGADO_UNIDAD."""
        self.client.get(
            f"{SERVICIOS['consultas']}/api/v1/consultas/tablero/unidad/{self.unidad()}",
            headers=self.cab, name="GET /consultas/tablero/unidad/{id}")

    @task(2)
    def participacion(self):
        """Movido aquí del colaborador: exige AGREGADO_UNIDAD."""
        self.client.get(
            f"{SERVICIOS['consultas']}/api/v1/consultas/participacion",
            headers=self.cab, name="GET /consultas/participacion")

    @task(2)
    def descensos(self):
        """La consulta más cara del sistema: recorre todas las series."""
        self.client.get(f"{SERVICIOS['tendencias']}/api/v1/tendencias/descensos",
                        headers=self.cab, name="GET /tendencias/descensos")

    @task(2)
    def detecciones(self):
        self.client.get(f"{SERVICIOS['algoritmos']}/api/v1/algoritmos/detecciones",
                        headers=self.cab, name="GET /algoritmos/detecciones")

    @task(3)
    def analisis_completo(self):
        """El algoritmo complejo sobre una campaña entera, con caché.

        Es el camino real: el informe se cachea diez minutos porque
        depende solo de agregados publicados, y publicar es una operación
        deliberada que nadie hace cada minuto.
        """
        self.client.get(
            f"{SERVICIOS['algoritmos']}/api/v1/algoritmos/analisis"
            f"?campania_id={self.campania()}",
            headers=self.cab, name="GET /algoritmos/analisis [cache]")

    @task(1)
    def analisis_sin_cache(self):
        """El MISMO análisis forzando el recálculo.

        Existe porque sin esto la prueba de carga no mediría el
        algoritmo. Con un TTL de diez minutos, el primer usuario virtual
        calienta la caché y los demás leen de Redis: el informe saldría
        con una latencia preciosa que no dice nada de cuánto cuesta
        agrupar 110 unidades y estimar 550 series.

        Va con peso 1 contra 3 del camino cacheado porque eso se parece a
        la realidad —la mayoría de las consultas aciertan en caché— y
        porque las dos mediciones salen separadas en el informe: la
        comparación entre los dos nombres ES la evidencia del valor de la
        caché bajo carga, no una tabla aparte hecha en reposo.
        """
        self.client.get(
            f"{SERVICIOS['algoritmos']}/api/v1/algoritmos/analisis"
            f"?campania_id={self.campania()}&sin_cache=1",
            headers=self.cab, name="GET /algoritmos/analisis [sin cache]")


class Administrador(UsuarioNexum):
    """El abanico: un panel que toca varios servicios a la vez."""
    weight = 2
    perfil = "administrador"
    wait_time = espera(3, 10)

    @task(3)
    def panel_de_monitoreo(self):
        self.client.get(f"{SERVICIOS['monitoreo']}/api/v1/monitoreo/componentes",
                        headers=self.cab, name="GET /monitoreo/componentes")

    @task(2)
    def presupuesto_de_privacidad(self):
        self.client.get(f"{SERVICIOS['consultas']}/api/v1/consultas/presupuesto",
                        headers=self.cab, name="GET /consultas/presupuesto")

    @task(1)
    def catalogo_de_reportes(self):
        if "reportes" in NO_LISTOS:
            return
        self.client.get(f"{SERVICIOS['reportes']}/api/v1/reportes/catalogo",
                        headers=self.cab, name="GET /reportes/catalogo")


class Auditor(UsuarioNexum):
    """El que revisa: consultas de bitácora, pocas y pesadas."""
    weight = 1
    perfil = "auditor"
    wait_time = espera(10, 30)

    @task
    def errores_recientes(self):
        self.client.get(f"{SERVICIOS['monitoreo']}/api/v1/monitoreo/errores?horas=24",
                        headers=self.cab, name="GET /monitoreo/errores")


# =========================================================================
# El informe
# =========================================================================
@events.quitting.add_listener
def resumen(environment, **kwargs):
    """Imprime lo que la rúbrica pide, con su lectura.

    Locust ya saca p95 y p99 en su CSV; esto los pone juntos con el
    criterio de aceptación, que es lo que convierte una tabla de números
    en una conclusión.
    """
    estadisticas = environment.stats
    total = estadisticas.total
    if not total.num_requests:
        print("\n[carga] no se ejecuto ninguna peticion")
        return

    print("\n" + "=" * 72)
    print("RESUMEN DE CARGA")
    print("=" * 72)
    print(f"  peticiones:          {total.num_requests:,}")
    print(f"  fallidas:            {total.num_failures:,} "
          f"({100.0 * total.num_failures / max(1, total.num_requests):.2f}%)")
    print(f"  peticiones/segundo:  {total.total_rps:.1f}")
    print(f"  tiempo medio:        {total.avg_response_time:.0f} ms")
    print(f"  mediana:             {total.median_response_time:.0f} ms")
    print(f"  p95:                 {total.get_response_time_percentile(0.95):.0f} ms")
    print(f"  p99:                 {total.get_response_time_percentile(0.99):.0f} ms")
    print(f"  maximo:              {total.max_response_time:.0f} ms")

    print("\n  --- los mas lentos, por p95 ---")
    filas = [(e.get_response_time_percentile(0.95), e.name, e.num_requests,
              e.num_failures)
             for e in estadisticas.entries.values() if e.num_requests]
    for p95, nombre, n, fallos in sorted(filas, reverse=True)[:8]:
        print(f"    {p95:7.0f} ms  {nombre:42} ({n:,} pet, {fallos} fallos)")

    # El criterio se dice aquí y no en un documento aparte: un numero sin
    # criterio no es un resultado, es una curiosidad.
    p95 = total.get_response_time_percentile(0.95)
    tasa_error = 100.0 * total.num_failures / max(1, total.num_requests)
    print("\n  --- criterio ---")
    print(f"    p95 < 800 ms:        {'CUMPLE' if p95 < 800 else 'NO CUMPLE'} "
          f"({p95:.0f} ms)")
    print(f"    errores < 1%:        {'CUMPLE' if tasa_error < 1 else 'NO CUMPLE'} "
          f"({tasa_error:.2f}%)")
    print("=" * 72)


# =========================================================================
# La forma de la carga: rampa escalonada y vuelta
# =========================================================================
class RampaYVuelta(LoadTestShape):
    """Sube por escalones, pasa del punto de saturación, y baja.

    POR QUÉ UNA FORMA Y NO TRES CORRIDAS
    ------------------------------------
    El punto de saturación se puede encontrar con corridas separadas a 10,
    25, 50 y 100 usuarios, y así se midió primero. Lo que NO se puede
    medir así es la **recuperación**: si el sistema vuelve a su latencia
    normal después de haber estado saturado, o si queda arrastrando una
    cola de conexiones y consultas pendientes.

    Eso solo se ve en una corrida continua que suba, se pase, y baje. Y es
    la pregunta que de verdad importa en producción: un sistema que
    aguanta un pico y se recupera es distinto de uno que aguanta el pico y
    después tarda veinte minutos en volver, aunque los dos den el mismo
    p95 en el pico.

    Se activa con `--shape` o la variable NEXUM_FORMA=rampa; sin eso
    Locust usa `-u` y `-r` como siempre, que es lo que conviene para una
    medición puntual.

    Los escalones duran 45 s: lo bastante para que la caché se caliente y
    los percentiles se estabilicen, y lo bastante poco para que la corrida
    completa quepa en cinco minutos.
    """
    # EL RITMO DE LLEGADA ES PARTE DE LA PRUEBA, NO UN DETALLE
    # --------------------------------------------------------
    # La primera versión subía a 150 usuarios a 30 nacimientos por
    # segundo. Resultado: 65 inicios de sesión rechazados con 429, porque
    # auth-service admite 30 por minuto y por IP, y después 899
    # peticiones con 401 de los usuarios que se quedaron sin token.
    # 34.6% de errores que no decían nada del sistema.
    #
    # Y el guión estaba mal, no el límite: **treinta inicios de sesión
    # por segundo no es un patrón de llegada real**. Ni el cambio de
    # turno de una planta produce eso; produce una oleada de decenas por
    # minuto. Medir con un ritmo que ningún cliente real genera mide una
    # situación que nunca ocurre, y además tapa todo lo demás.
    #
    # Medio nacimiento por segundo son 30 por minuto: justo el límite, y
    # un ritmo creíble. Llegar a 140 usuarios tarda cuatro minutos y
    # medio, que es lo que tarda.
    #
    # La CAÍDA sí es brusca (50 por segundo) y no hay problema: irse no
    # consume inicios de sesión, y una caída brusca es exactamente lo que
    # hace falta para medir la recuperación.
    ESCALONES = [
        # (segundo en que termina, usuarios, nacimientos por segundo)
        (90,   40, 0.5),   # linea base
        (200,  90, 0.5),
        (320, 140, 0.5),   # aqui se busca el codo
        (380, 140, 0.5),   # se sostiene el pico
        (440,  10, 50),    # caida brusca: se mide la RECUPERACION
        (500,  10, 0.5),   # y se le da tiempo de volver
    ]

    def tick(self):
        transcurrido = self.get_run_time()
        for hasta, usuarios, nacimientos in self.ESCALONES:
            if transcurrido < hasta:
                return (usuarios, nacimientos)
        return None


# Locust usa la clase de forma solo si está presente en el archivo, y
# entonces ignora -u y -r. Como este archivo sirve para las dos cosas —una
# medición puntual y la rampa— la clase se expone bajo un nombre distinto
# y solo se activa con la variable de ambiente.
if os.environ.get("NEXUM_FORMA", "").lower() != "rampa":
    del RampaYVuelta
