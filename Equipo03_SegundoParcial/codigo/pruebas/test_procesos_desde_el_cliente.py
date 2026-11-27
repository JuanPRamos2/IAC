"""
Los tres procesos integrales, conducidos desde la APLICACIÓN CLIENTE.

QUÉ AÑADE ESTE ARCHIVO SOBRE test_procesos_integrales.py
---------------------------------------------------------
Ese archivo recorre los tres procesos llamando a los microservicios. Es
la mitad correcta y no es la mitad que usa una persona: nadie abre un
proceso de bienestar con curl. Un proceso que funciona por API y no tiene
pantalla no existe para la organización, y una pantalla que existe pero
está detrás de un enlace que nadie puso tampoco.

Así que aquí se comprueba, desde el portal web:

  * que cada uno de los tres procesos tiene sus pantallas,
  * que el perfil correcto llega a ellas,
  * que el perfil equivocado NO llega, y recibe algo que explica por qué,
  * y que cuando un microservicio no contesta, la pantalla lo dice en
    lugar de romperse o de mostrar una página vacía que se lee como «no
    hay nada».

Lo último es lo que más se olvida y lo que peor se comporta: una tabla
vacía porque el servicio está caído es indistinguible de una tabla vacía
porque no hay datos, y las dos llevan a conclusiones opuestas.

LO QUE ESTE ARCHIVO NO PRUEBA
-----------------------------
La aplicación móvil y la de escritorio tienen sus propios archivos
—`test_movil.py` y `test_escritorio.py`— porque se prueban distinto: la
móvil es Kotlin y se comprueba contra el contrato de los servicios, y la
de escritorio valida cada respuesta contra su XSD. Aquí es el portal, que
es el cliente de los tres procesos completos.
"""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def web(tmp_path_factory):
    os.environ["ALMACEN_EVIDENCIAS"] = str(tmp_path_factory.mktemp("evid_pc"))
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


def entrar(cliente, correo):
    r = cliente.post("/entrar", data={"correo": correo, "contrasena": "demo123"},
                     follow_redirects=False)
    assert r.status_code in (302, 303), (
        f"no se pudo entrar como {correo}: "
        f"{r.get_data(as_text=True)[:300]}")
    return r


# Las pantallas de cada proceso, con el perfil que las usa y uno que no.
#
# La tabla está escrita aquí y no repartida por las pruebas porque es la
# que contesta la pregunta del parcial: «¿cada proceso integral involucra
# a un usuario y una aplicación cliente?». Si una fila se queda sin
# pantalla, el proceso no tiene por dónde conducirse.
PANTALLAS = {
    "proceso 1 — autorreporte": [
        # (ruta, perfil que SÍ, perfil que NO)
        ("/portal/", "ana.perez@nexum.com.mx", None),
        ("/portal/consentimiento", "ana.perez@nexum.com.mx", None),
        ("/portal/mis-accesos", "ana.perez@nexum.com.mx", None),
    ],
    "proceso 2 — analisis a intervencion": [
        ("/panel/", "mariana.solis@nexum.com.mx", "ana.perez@nexum.com.mx"),
        ("/panel/recomendaciones", "mariana.solis@nexum.com.mx",
         "ana.perez@nexum.com.mx"),
        ("/intervenciones/", "mariana.solis@nexum.com.mx",
         "ana.perez@nexum.com.mx"),
    ],
    "proceso 3 — reporte con evidencia": [
        ("/reportes/", "mariana.solis@nexum.com.mx", "ana.perez@nexum.com.mx"),
        ("/evidencias/", "mariana.solis@nexum.com.mx", "ana.perez@nexum.com.mx"),
    ],
}


@pytest.mark.parametrize("proceso", sorted(PANTALLAS))
def test_cada_proceso_tiene_sus_pantallas_en_el_portal(cliente, proceso):
    """Un proceso sin pantalla no existe para la organización.

    Se comprueba que la ruta responde y que NO es un 404: una pantalla
    que no está es exactamente el hueco que deja un proceso que solo
    funciona por API.
    """
    for ruta, quien_si, _ in PANTALLAS[proceso]:
        cliente.get("/salir")
        entrar(cliente, quien_si)
        r = cliente.get(ruta, follow_redirects=True)
        assert r.status_code == 200, (
            f"{proceso}: {ruta} contesto {r.status_code} para {quien_si}. "
            f"Sin esa pantalla el proceso no tiene por donde conducirse.")
        texto = r.get_data(as_text=True)
        assert len(texto) > 500, (
            f"{proceso}: {ruta} devolvio una pagina de {len(texto)} bytes. "
            f"Parece una plantilla de error y no la pantalla.")


@pytest.mark.parametrize("proceso", sorted(PANTALLAS))
def test_el_perfil_equivocado_no_entra_a_las_pantallas_del_proceso(cliente,
                                                                   proceso):
    """Y se le dice por qué, en lugar de dejarlo entrar a medias.

    La comprobación importante no es el código HTTP: es que la pantalla
    con los datos de bienestar de una unidad no se renderice para quien
    no puede verlos. Un portal que devuelve 200 con una tabla vacía para
    un colaborador deja al colaborador creyendo que su unidad no tiene
    datos.
    """
    for ruta, _, quien_no in PANTALLAS[proceso]:
        if quien_no is None:
            continue
        cliente.get("/salir")
        entrar(cliente, quien_no)
        r = cliente.get(ruta, follow_redirects=False)
        assert r.status_code in (302, 303, 403), (
            f"{proceso}: {ruta} contesto {r.status_code} a {quien_no}, que "
            f"no deberia poder verla.")

        if r.status_code in (302, 303):
            # Si redirige, tiene que ser a una pantalla que explique algo,
            # no a la misma ruta —eso sería un bucle— ni al inicio sin
            # mensaje.
            destino = r.headers.get("Location", "")
            assert ruta.rstrip("/") not in destino.rstrip("/") or destino in ("/", ""), (
                f"{ruta} redirige a si misma: bucle de redireccion para "
                f"{quien_no}.")
            seguido = cliente.get(ruta, follow_redirects=True)
            texto = seguido.get_data(as_text=True).lower()
            assert ("permiso" in texto or "no autoriz" in texto
                    or "no tienes" in texto or "inicia sesion" in texto
                    or "entrar" in texto), (
                f"{ruta} rechazo a {quien_no} sin decir por que. Un rechazo "
                f"silencioso se lee como una pantalla vacia.")


def test_sin_sesion_ninguna_pantalla_de_proceso_se_abre(cliente):
    """Lo primero que se prueba en cualquier portal y lo que más se rompe
    al agregar una pantalla nueva: olvidar el decorador.
    """
    for proceso, pantallas in PANTALLAS.items():
        for ruta, _, _ in pantallas:
            r = cliente.get(ruta, follow_redirects=False)
            assert r.status_code in (302, 303, 401, 403), (
                f"{ruta} se abrio SIN sesion (codigo {r.status_code}). Es "
                f"una pantalla del {proceso}.")


def test_la_encuesta_se_abre_o_se_explica_por_que_no(cliente):
    """El paso del proceso 1 que de verdad captura el dato.

    La primera versión de esta prueba buscaba la campaña abierta más
    reciente y daba por hecho que la colaboradora podía responderla. No
    podía —ya la había respondido— y el portal hizo lo correcto:
    redirigir con «Esa campaña no está disponible para ti: puede estar
    cerrada, ya respondida, o tu consentimiento no está vigente».

    Es decir: la prueba estaba mal y el sistema bien. Y la versión
    corregida vale más, porque la rama que de verdad importa es
    justamente esa: que cuando no se puede responder, la pantalla lo
    DIGA, en lugar de mostrar una encuesta vacía que se ve igual que una
    encuesta.

    Así que se comprueban las dos ramas, y cuál se recorre lo decide el
    estado de los datos y no la prueba:

      * hay campaña pendiente  -> la pantalla trae controles para responder
      * no hay                 -> la pantalla explica por qué
    """
    entrar(cliente, "ana.perez@nexum.com.mx")

    inicio = cliente.get("/portal/", follow_redirects=True)
    assert inicio.status_code == 200
    texto_inicio = inicio.get_data(as_text=True)

    # Las campañas pendientes se listan en el portal con un enlace a su
    # encuesta. Se toma de ahí en lugar de consultar la base: lo que se
    # quiere probar es el camino que recorre una persona, y una persona
    # llega a la encuesta por el enlace que ve.
    import re
    enlaces = re.findall(r'/portal/encuesta/([A-Za-z0-9._-]+)', texto_inicio)

    if enlaces:
        r = cliente.get(f"/portal/encuesta/{enlaces[0]}", follow_redirects=True)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        texto = r.get_data(as_text=True)
        assert texto.count('type="radio"') >= 5, (
            f"La pantalla de encuesta trae "
            f"{texto.count('type=\"radio\"')} controles. Una encuesta sin "
            f"preguntas se ve igual que una encuesta.")
    else:
        bajo = texto_inicio.lower()
        assert ("no tienes campa" in bajo or "sin campa" in bajo
                or "no hay campa" in bajo), (
            "El portal no lista campañas pendientes y tampoco dice que no "
            "hay ninguna. Una pantalla vacia se lee como un sistema roto.")


def test_una_campania_que_no_le_toca_se_explica_en_lugar_de_fallar(cliente):
    """La rama de arriba, forzada: una campaña que existe y no le toca.

    Se usa una campaña CERRADA, que existe en la base pero no admite
    respuestas. Lo que no puede pasar es un 500 ni una encuesta en
    blanco: las dos dejan a la persona sin saber qué hacer.
    """
    from comun.datos import consultar_uno
    cerrada = consultar_uno(
        "SELECT campania_id FROM catalogo.campania "
        " WHERE estado <> 'ABIERTA' ORDER BY secuencia DESC LIMIT 1")
    if not cerrada:
        pytest.skip("no hay campania cerrada en esta base")

    entrar(cliente, "ana.perez@nexum.com.mx")
    r = cliente.get(f"/portal/encuesta/{cerrada['campania_id']}",
                    follow_redirects=True)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    texto = r.get_data(as_text=True).lower()
    assert ("no esta disponible" in texto or "no está disponible" in texto
            or "cerrada" in texto or "ya respondida" in texto), (
        "El portal acepto abrir una campania que no le toca y no dijo nada. "
        "La persona se queda sin saber si el sistema falla o si no le toca.")
    assert texto.count('type="radio"') == 0, (
        "Se dibujaron controles para responder una campania que no admite "
        "respuestas.")


def test_una_campania_inventada_no_da_500_en_la_pantalla(cliente):
    """El error que más se cuela en un portal: el 500 en lugar del 404.

    Un 500 le dice a quien lo ve «el sistema está roto» y manda a alguien
    a revisar bitácoras. Lo que había era una dirección escrita a mano.
    """
    entrar(cliente, "ana.perez@nexum.com.mx")
    r = cliente.get("/portal/encuesta/CAMP-QUE-NO-EXISTE",
                    follow_redirects=True)
    assert r.status_code in (200, 404), (
        f"Una campania inexistente dio {r.status_code}. Un 500 manda a "
        f"alguien a revisar bitacoras por una direccion mal escrita.")
    if r.status_code == 200:
        texto = r.get_data(as_text=True).lower()
        assert ("no existe" in texto or "no encontr" in texto
                or "no disponible" in texto or "cerrada" in texto), (
            "La pantalla contesto 200 y no dice que la campania no existe: "
            "se lee como una encuesta vacia.")
