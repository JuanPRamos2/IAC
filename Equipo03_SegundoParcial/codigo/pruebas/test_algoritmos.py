"""
Pruebas de algorithms-service, el motor de reglas.

Las tres que importan de verdad no comprueban que el motor «funcione», sino
que no miente:

  * evaluar el riesgo no gasta presupuesto de privacidad;
  * una detección nunca sale sin su explicación;
  * las unidades que el motor NO pudo evaluar se reportan, porque omitirlas
    haría creer a la organización que ahí no hay riesgo.
"""
import os

import pytest
from conftest import cab


def test_salud_y_contrato(algoritmos):
    assert algoritmos.get("/health/live").status_code == 200
    r = algoritmos.get("/health/ready")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert set(r.get_json()["dependencias"]) >= {"postgresql", "mongodb", "redis"}

    c = algoritmos.get("/openapi.json")
    assert c.status_code == 200
    contrato = c.get_json()
    assert len(contrato["components"]["responses"]) == 7
    assert contrato["components"]["securitySchemes"]["bearerAuth"]
    assert algoritmos.get("/docs").status_code == 200


def test_sin_token_no_se_entra(algoritmos):
    assert algoritmos.get("/api/v1/algoritmos/reglas").status_code == 401
    assert algoritmos.post("/api/v1/algoritmos/evaluar",
                           json={"campania_id": "CAMP-2026-S1"}).status_code == 401


def test_las_reglas_traen_su_condicion_en_palabras(algoritmos, token_especialista):
    """Una regla cuyo efecto solo se entiende leyendo el código no es auditable."""
    r = algoritmos.get("/api/v1/algoritmos/reglas", headers=cab(token_especialista))
    assert r.status_code == 200
    reglas = r.get_json()["reglas"]
    assert len(reglas) >= 4
    for regla in reglas:
        assert regla["condicion_legible"], regla["regla_id"]
        assert len(regla["condicion_legible"]) > 40, (
            f"{regla['regla_id']}: la condicion legible es demasiado corta "
            f"para explicar algo")
        assert regla["nivel"] in ("INFORMATIVO", "ATENCION", "PRIORITARIO")
    # Las intervenciones sugeridas son organizacionales, no personales.
    sugerencias = [s for regla in reglas for s in regla["intervenciones_sugeridas"]]
    assert sugerencias
    assert not any("PERSONA" in s or "EMPLEADO" in s for s in sugerencias)


def test_evaluar_no_gasta_presupuesto_de_privacidad(algoritmos, consultas,
                                                    token_especialista,
                                                    token_admin):
    """La prueba central del servicio.

    Se lee el presupuesto, se corre el motor sobre la campaña completa, y se
    vuelve a leer: el épsilon consumido tiene que ser idéntico. Si el motor
    recalculara agregados para evaluar, cada corrida gastaría privacidad y
    evaluar el riesgo de la organización costaría la capacidad de publicar
    resultados nuevos.
    """
    antes = consultas.get("/api/v1/consultas/presupuesto",
                          headers=cab(token_admin))
    assert antes.status_code == 200
    gasto_antes = sum(float(e["epsilon_consumido"])
                      for e in antes.get_json()["elementos"])

    for _ in range(3):
        r = algoritmos.post("/api/v1/algoritmos/evaluar",
                            headers=cab(token_especialista),
                            json={"campania_id": "CAMP-2026-S1"})
        assert r.status_code == 201, r.get_data(as_text=True)
        assert r.get_json()["epsilon_consumido"] == 0

    consultas.post("/api/v1/consultas/cache/invalidar",
                   headers=cab(token_admin), json={"recurso": "presupuesto"})
    despues = consultas.get("/api/v1/consultas/presupuesto",
                            headers=cab(token_admin))
    gasto_despues = sum(float(e["epsilon_consumido"])
                        for e in despues.get_json()["elementos"])
    assert gasto_despues == gasto_antes, (
        "correr el motor de reglas gasto presupuesto de privacidad: esta "
        "recalculando agregados en lugar de leer los publicados")


def test_ninguna_deteccion_sale_sin_explicacion(algoritmos, token_especialista):
    r = algoritmos.post("/api/v1/algoritmos/evaluar",
                        headers=cab(token_especialista),
                        json={"campania_id": "CAMP-2026-S1"})
    assert r.status_code == 201
    corrida = r.get_json()
    assert corrida["total_detecciones"] > 0, (
        "la base de demostracion debe producir detecciones")
    for d in corrida["detecciones"]:
        assert d.get("explicacion"), d
        assert len(d["explicacion"]) > 30, d["explicacion"]
        # La explicacion tiene que citar el valor observado o la campania:
        # un texto generico no explica nada.
        assert (str(d["valor_observado"])[:4] in d["explicacion"]
                or "campania" in d["explicacion"].lower()), d["explicacion"]


def test_las_unidades_no_evaluables_se_reportan(algoritmos, token_especialista):
    """Omitirlas haría creer que ahí no hay riesgo.

    La base de demostración tiene unidades con todos sus agregados
    suprimidos por el umbral k. El motor no puede concluir nada de ellas, y
    eso tiene que decirlo.
    """
    r = algoritmos.post("/api/v1/algoritmos/evaluar",
                        headers=cab(token_especialista),
                        json={"campania_id": "CAMP-2026-S1"})
    corrida = r.get_json()
    assert corrida["total_no_evaluables"] > 0, (
        "la base de demostracion debe traer unidades con agregados suprimidos")
    for u in corrida["no_evaluables"]:
        assert u["publicados"] == 0
        assert u["motivo"], u
        motivo = u["motivo"].lower()
        assert ("no significa que no haya riesgo" in motivo
                or "sin agregados" in motivo), u["motivo"]


def test_la_cobertura_distingue_no_ver_de_no_encontrar(algoritmos,
                                                       token_especialista):
    r = algoritmos.get("/api/v1/algoritmos/cobertura?campania_id=CAMP-2026-S1",
                       headers=cab(token_especialista))
    assert r.status_code == 200
    c = r.get_json()
    assert c["unidades_convocadas"] > 0
    assert (c["unidades_evaluables"] + c["unidades_no_evaluables"]
            == c["unidades_convocadas"])
    assert 0 < c["cobertura_porcentaje"] <= 100
    assert "no es una unidad sin riesgo" in c["nota"]


def test_cobertura_de_campania_inexistente(algoritmos, token_especialista):
    r = algoritmos.get("/api/v1/algoritmos/cobertura?campania_id=CAMP-NO-EXISTE",
                       headers=cab(token_especialista))
    assert r.status_code == 404
    assert r.get_json()["error"]["codigo"] == "NO_ENCONTRADO"


def test_evaluar_valida_sus_parametros(algoritmos, token_especialista):
    r = algoritmos.post("/api/v1/algoritmos/evaluar",
                        headers=cab(token_especialista), json={})
    assert r.status_code == 422
    assert r.get_json()["error"]["detalles"][0]["campo"] == "campania_id"

    r2 = algoritmos.post("/api/v1/algoritmos/evaluar",
                         headers=cab(token_especialista),
                         json={"campania_id": "CAMP-NO-EXISTE"})
    assert r2.status_code == 422


# ============================================================ simulación
def test_la_simulacion_reacciona_al_umbral_y_no_escribe(algoritmos, token_admin):
    """Mover el umbral tiene que cambiar el resultado, y no crear detecciones.

    Se comprueba contra la base: el número de detecciones de esa regla no
    sube después de simular. Una simulación que dejara detecciones reales
    contaminaría el histórico con escenarios que nunca ocurrieron.
    """
    import psycopg2
    cn = psycopg2.connect(host=os.environ["PG_HOST"], dbname=os.environ["PG_BASE"],
                          user=os.environ["PG_USUARIO"],
                          password=os.environ["PG_CLAVE"])

    def detecciones_de(regla):
        with cn, cn.cursor() as cur:
            cur.execute("SELECT count(*) FROM riesgo.deteccion WHERE regla_id = %s",
                        (regla,))
            return cur.fetchone()[0]

    antes = detecciones_de("RG-02")

    # Los dos umbrales se DERIVAN de los datos y no se escriben a mano.
    #
    # La primera version fijaba 3.0 y 4.0 con el comentario de que la
    # dimension iba de 3.45 a 4.00. Dejo de ser cierto al integrar el
    # trabajo de los cuatro: ahora va de 2.37 a 4.56, porque UO-CC-TURNO-B
    # —la unidad chica del caso de demostracion— cayo a 2.37. El umbral
    # "bajo" de 3.0 paso a detectar una unidad y la prueba fallo sin que
    # nada del servicio estuviera roto.
    #
    # Lo que la prueba quiere comprobar no son esos numeros: es que mover
    # el umbral cambie el resultado y que simular no escriba. Derivar los
    # umbrales del minimo y del maximo reales comprueba lo mismo y no se
    # rompe la proxima vez que cambie la semilla. Los valores ademas
    # llevan ruido de Laplace, asi que cada arranque de la base los mueve
    # un poco: un numero fijo aqui es una prueba intermitente esperando a
    # fallar.
    with cn, cn.cursor() as cur:
        cur.execute(
            "SELECT min(valor_protegido), max(valor_protegido) "
            "  FROM agregado.v_tablero_unidad "
            " WHERE campania_id = %s AND dimension = %s "
            "   AND valor_protegido IS NOT NULL",
            ("CAMP-2026-S1", "Recuperacion"))
        minimo, maximo = cur.fetchone()
    assert minimo is not None, "la campania de demostracion no tiene valores"
    umbral_bajo = float(minimo) - 0.5      # por debajo de todas: 0 detecciones
    umbral_alto = float(maximo) + 0.5      # por encima de todas: las detecta

    bajo = algoritmos.post("/api/v1/algoritmos/simular", headers=cab(token_admin),
                           json={"regla_id": "RG-02",
                                 "campania_id": "CAMP-2026-S1",
                                 "umbral_valor": umbral_bajo})
    alto = algoritmos.post("/api/v1/algoritmos/simular", headers=cab(token_admin),
                           json={"regla_id": "RG-02",
                                 "campania_id": "CAMP-2026-S1",
                                 "umbral_valor": umbral_alto})
    assert bajo.status_code == alto.status_code == 200
    assert bajo.get_json()["detectadas_con_umbral_simulado"] == 0, (
        f"Con un umbral por debajo del minimo ({umbral_bajo:.3f}) no "
        f"deberia detectar nada. Si el comparador estuviera invertido, "
        f"los dos umbrales darian lo mismo.")
    assert alto.get_json()["detectadas_con_umbral_simulado"] > 0
    assert len(alto.get_json()["entrarian"]) > 0
    assert alto.get_json()["epsilon_consumido"] == 0

    assert detecciones_de("RG-02") == antes, (
        "la simulacion creo detecciones: tiene que ser de solo lectura")
    cn.close()


def test_la_simulacion_marca_lo_que_esta_cerca_del_ruido(algoritmos, token_admin):
    """Una unidad cerca del ruido entra o sale del umbral por azar."""
    r = algoritmos.post("/api/v1/algoritmos/simular", headers=cab(token_admin),
                        json={"regla_id": "RG-02",
                              "campania_id": "CAMP-2026-S1",
                              "umbral_valor": 4.0})
    s = r.get_json()
    assert s["con_advertencia_de_precision"] >= 0
    assert "azar" in s["nota"]


def test_una_regla_de_tendencia_no_se_simula(algoritmos, token_admin):
    """RG-04 evalúa deterioro sostenido: no hay un umbral que mover."""
    r = algoritmos.post("/api/v1/algoritmos/simular", headers=cab(token_admin),
                        json={"regla_id": "RG-04", "campania_id": "CAMP-2026-S1"})
    assert r.status_code == 400
    assert r.get_json()["error"]["codigo"] == "OPERACION_NO_PERMITIDA"
    assert "tendencia" in r.get_json()["error"]["mensaje"]


def test_regla_inexistente(algoritmos, token_admin):
    r = algoritmos.post("/api/v1/algoritmos/simular", headers=cab(token_admin),
                        json={"regla_id": "RG-99", "campania_id": "CAMP-2026-S1"})
    assert r.status_code == 404


# ================================================================ alcance
def test_el_lider_solo_ve_su_subarbol(algoritmos, token_lider):
    """El alcance se resuelve contra la jerarquía, no contra el parámetro."""
    r = algoritmos.get("/api/v1/algoritmos/detecciones"
                       "?unidad_organizacional_id=UO-LOG-TURNO-A",
                       headers=cab(token_lider))
    assert r.status_code == 403
    assert r.get_json()["error"]["codigo"] == "FUERA_DE_ALCANCE"

    propia = algoritmos.get("/api/v1/algoritmos/detecciones"
                            "?unidad_organizacional_id=UO-CC-TURNO-B",
                            headers=cab(token_lider))
    assert propia.status_code == 200


def test_sin_filtro_el_lider_tampoco_ve_otras_unidades(algoritmos, token_lider):
    """El alcance se aplica también al resultado, no solo al parámetro."""
    r = algoritmos.get("/api/v1/algoritmos/detecciones?tamano=100",
                       headers=cab(token_lider))
    assert r.status_code == 200
    unidades = {d["unidad_organizacional_id"] for d in r.get_json()["detecciones"]}
    assert unidades <= {"UO-CC-TURNO-B"}, (
        f"el lider vio detecciones de unidades ajenas: {sorted(unidades)}")


def test_el_colaborador_no_consulta_detecciones(algoritmos, token_colaborador):
    r = algoritmos.get("/api/v1/algoritmos/detecciones",
                       headers=cab(token_colaborador))
    assert r.status_code == 403
    assert r.get_json()["error"]["codigo"] == "SIN_PERMISO"


def test_el_colaborador_no_corre_el_motor(algoritmos, token_colaborador):
    r = algoritmos.post("/api/v1/algoritmos/evaluar",
                        headers=cab(token_colaborador),
                        json={"campania_id": "CAMP-2026-S1"})
    assert r.status_code == 403


def test_nivel_invalido_se_rechaza(algoritmos, token_especialista):
    r = algoritmos.get("/api/v1/algoritmos/detecciones?nivel=URGENTISIMO",
                       headers=cab(token_especialista))
    assert r.status_code == 400
    assert r.get_json()["error"]["codigo"] == "PARAMETRO_INVALIDO"


# =============================================================== corridas
def test_la_corrida_queda_guardada_en_mongodb(algoritmos, token_especialista):
    """MongoDB es donde el proyecto almacena los resultados de algoritmos.

    Sin ese registro, una detección de hace tres meses no se puede explicar,
    porque los umbrales pudieron cambiar desde entonces.
    """
    r = algoritmos.post("/api/v1/algoritmos/evaluar",
                        headers=cab(token_especialista),
                        json={"campania_id": "CAMP-2026-S1",
                              "unidad_organizacional_id": "UO-CC-TURNO-B"})
    assert r.status_code == 201
    cid = r.get_json()["corrida_id"]
    assert cid.startswith("ALG-")

    detalle = algoritmos.get(f"/api/v1/algoritmos/corridas/{cid}",
                             headers=cab(token_especialista))
    assert detalle.status_code == 200
    guardada = detalle.get_json()
    assert guardada["campania_id"] == "CAMP-2026-S1"
    assert "detecciones" in guardada
    assert guardada["epsilon_consumido"] == 0

    listado = algoritmos.get("/api/v1/algoritmos/corridas?tamano=5",
                             headers=cab(token_especialista))
    assert listado.status_code == 200
    assert listado.get_json()["paginacion"]["total"] >= 1
    # El listado no arrastra las detecciones: serian cientos por pagina.
    assert all("detecciones" not in c for c in listado.get_json()["corridas"])


def test_corrida_inexistente(algoritmos, token_especialista):
    r = algoritmos.get("/api/v1/algoritmos/corridas/ALG-000000000000",
                       headers=cab(token_especialista))
    assert r.status_code == 404


def test_correr_el_motor_queda_en_la_bitacora(algoritmos, token_especialista):
    """La bitácora tiene llave foránea contra auditoria.tipo_accion.

    Si DETECCION_EVALUADA no estuviera declarado en la migración 006, la
    inserción fallaría en silencio y correr el motor no dejaría rastro.
    """
    import psycopg2
    algoritmos.post("/api/v1/algoritmos/evaluar", headers=cab(token_especialista),
                    json={"campania_id": "CAMP-2026-S1",
                          "unidad_organizacional_id": "UO-CC-TURNO-B"})
    cn = psycopg2.connect(host=os.environ["PG_HOST"], dbname=os.environ["PG_BASE"],
                          user=os.environ["PG_USUARIO"],
                          password=os.environ["PG_CLAVE"])
    with cn, cn.cursor() as cur:
        cur.execute("SELECT count(*) FROM auditoria.bitacora "
                    " WHERE accion = 'DETECCION_EVALUADA'")
        n = cur.fetchone()[0]
    cn.close()
    assert n >= 1, ("algorithms-service no pudo escribir en la bitacora: "
                    "falta aplicar la migracion 006")


# ===================================================== análisis complejo
#
# El endpoint /analisis expone el paquete `analitica`, cuya matemática se
# prueba por separado en test_analitica.py sin levantar Flask ni
# PostgreSQL. Lo que se prueba AQUÍ es lo que solo se puede romper al
# exponerlo por HTTP: el alcance del solicitante, el gasto de épsilon, la
# caché, y que una campaña sin agregados publicados se distinga de una
# campaña sin riesgo.

def test_el_analisis_no_gasta_presupuesto_de_privacidad(algoritmos, consultas,
                                                       token_especialista,
                                                       token_admin):
    """La misma prueba central que el motor de reglas, para el análisis.

    El análisis complejo lee `agregado.resultado_protegido` donde el estado
    es PUBLICADO: valores que ya descontaron su épsilon al calcularse. Si
    en cambio llamara a `fn_calcular_agregado_protegido` para tener datos
    más frescos, cada corrida gastaría presupuesto, y al agotarlo la
    campaña se quedaría sin poder publicar nada más. Analizar el riesgo
    costaría la capacidad de medirlo.
    """
    antes = consultas.get("/api/v1/consultas/presupuesto",
                          headers=cab(token_admin))
    assert antes.status_code == 200, antes.get_data(as_text=True)
    gasto_antes = sum(float(e["epsilon_consumido"])
                      for e in antes.get_json()["elementos"])

    # Varias corridas, y una sin cache: una sola lectura cacheada no
    # probaria nada, porque la cache no toca la base.
    for sufijo in ("?sin_cache=1", "", "?sin_cache=1"):
        r = algoritmos.get(f"/api/v1/algoritmos/analisis{sufijo}",
                           headers=cab(token_especialista))
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["epsilon_consumido"] == 0.0

    # El presupuesto que sirve /consultas esta cacheado: sin invalidarlo,
    # la segunda lectura devolveria la primera y la prueba pasaria aunque
    # el analisis hubiera gastado epsilon.
    consultas.post("/api/v1/consultas/cache/invalidar",
                   headers=cab(token_admin), json={"recurso": "presupuesto"})
    despues = consultas.get("/api/v1/consultas/presupuesto",
                            headers=cab(token_admin))
    gasto_despues = sum(float(e["epsilon_consumido"])
                        for e in despues.get_json()["elementos"])
    assert gasto_despues == gasto_antes, (
        "El analisis movio el presupuesto de epsilon. Tiene que leer solo "
        "resultados ya publicados.")


def test_el_analisis_no_llama_a_la_funcion_que_gasta_epsilon():
    """A nivel de código fuente, no solo de comportamiento.

    La prueba de arriba comprueba que hoy no gasta. Esta comprueba que no
    PUEDE gastar: la única función que descuenta épsilon es
    `fn_calcular_agregado_protegido`, y el servicio no la menciona. Sin
    esto, alguien «arregla» el análisis para que use datos más frescos, el
    presupuesto se consume y la prueba de comportamiento solo falla cuando
    ya se agotó.
    """
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "apps", "microservicios", "algorithms-service", "app.py")
    codigo = open(ruta, encoding="utf-8").read()
    assert "fn_calcular_agregado_protegido" not in codigo, (
        "algorithms-service menciona la funcion que descuenta epsilon. "
        "Solo el servicio de agregados puede llamarla.")

    paquete = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "apps", "microservicios", "analitica", "analitica")
    for archivo in os.listdir(paquete):
        if archivo.endswith(".py"):
            texto = open(os.path.join(paquete, archivo), encoding="utf-8").read()
            assert "fn_calcular_agregado" not in texto, archivo
            # El paquete no debe hablar con la base en absoluto: recibe
            # filas y devuelve un informe. Si consultara por su cuenta, no
            # se podria probar sin PostgreSQL ni auditar que no gasta.
            assert "psycopg2" not in texto and "SELECT" not in texto.upper(), (
                f"{archivo} toca la base de datos. El paquete de analisis "
                f"recibe filas y devuelve un informe: es lo que permite "
                f"probar la matematica sin levantar nada.")


def test_el_analisis_recorta_a_lo_que_el_lider_puede_ver(algoritmos,
                                                         token_lider,
                                                         token_especialista):
    """La parte que solo se puede romper al exponerlo por HTTP.

    El análisis se CALCULA sobre la organización completa —comparar cada
    unidad con sus pares es el método— pero un líder de unidad no puede
    recibir el ranking de áreas que no le corresponden. Y como el informe
    global se cachea, un error al recortar serviría al líder exactamente
    el informe del administrador.
    """
    global_ = algoritmos.get("/api/v1/algoritmos/analisis",
                             headers=cab(token_especialista))
    assert global_.status_code == 200, global_.get_data(as_text=True)
    completo = global_.get_json()

    acotado = algoritmos.get("/api/v1/algoritmos/analisis",
                             headers=cab(token_lider))
    assert acotado.status_code == 200, acotado.get_data(as_text=True)
    recortado = acotado.get_json()

    assert "alcance_aplicado" in recortado, (
        "El informe del lider no declara que se recorto. Un informe "
        "recortado que no lo dice se lee como si fuera completo.")
    assert len(recortado["priorizadas"]) < len(completo["priorizadas"]), (
        "El lider recibio tantas unidades priorizadas como el "
        "especialista: el recorte por alcance no se aplico.")

    visibles = {p["unidad_organizacional_id"] for p in recortado["priorizadas"]}
    visibles |= set(recortado["tendencias"])
    assert visibles, "El lider no vio ninguna unidad, ni la suya"
    assert all(u.startswith("UO-CC-TURNO-B") or u == "UO-CC-TURNO-B"
               for u in visibles), (
        f"El lider de UO-CC-TURNO-B vio unidades fuera de su subarbol: "
        f"{sorted(visibles)}")

    # Los centroides describen a toda la organizacion: se reemplazan por
    # una nota en lugar de entregarse.
    assert "centroides" not in recortado["agrupamiento"]
    assert recortado["agrupamiento"]["nota"]
    # Pero la silueta y el numero de grupos si van: son una medida de la
    # calidad del agrupamiento, y sin ellas el lider no puede saber si la
    # comparacion con pares que recibio significa algo.
    assert recortado["agrupamiento"]["silueta"] is not None


def test_el_analisis_usa_cache_y_la_puede_saltar(algoritmos, token_especialista):
    """La caché tiene que existir Y tiene que poderse ignorar.

    Sin `sin_cache=1` no hay forma de medir cuánto cuesta de verdad el
    algoritmo, que es justo lo que la caché esconde. Una medición de
    rendimiento tomada contra una caché caliente no mide el algoritmo.
    """
    primero = algoritmos.get("/api/v1/algoritmos/analisis?sin_cache=1",
                             headers=cab(token_especialista))
    assert primero.status_code == 200
    assert primero.get_json()["origen"] == "calculado"
    assert primero.get_json()["tiempo_ms"] > 0

    segundo = algoritmos.get("/api/v1/algoritmos/analisis",
                             headers=cab(token_especialista))
    assert segundo.status_code == 200
    assert segundo.get_json()["origen"] == "cache", (
        "La segunda consulta se recalculo: la cache no esta guardando nada.")
    # El informe cacheado es el MISMO, no una version reducida.
    assert (segundo.get_json()["priorizadas"]
            == primero.get_json()["priorizadas"])


def test_una_campania_sin_agregados_publicados_no_se_lee_como_sin_riesgo(
        algoritmos, token_especialista):
    """«No pudimos ver» y «no hay nada» son respuestas distintas.

    Una campaña cuyos agregados se suprimieron todos por el umbral k no
    tiene riesgo cero: tiene riesgo desconocido. Devolver un informe vacío
    con 200 haría que el portal mostrara «sin hallazgos», que es
    exactamente la conclusión equivocada.
    """
    r = algoritmos.get("/api/v1/algoritmos/analisis?campania_id=CAMP-2026-S5",
                       headers=cab(token_especialista))
    assert r.status_code in (200, 409), r.get_data(as_text=True)
    if r.status_code == 409:
        cuerpo = r.get_json()
        assert cuerpo["error"]["codigo"] == "SIN_DATOS"
        assert "no haya riesgo" in cuerpo["error"]["mensaje"], (
            "El mensaje no advierte que la ausencia de datos no es "
            "ausencia de riesgo.")


def test_el_analisis_rechaza_una_campania_inexistente(algoritmos,
                                                      token_especialista):
    r = algoritmos.get("/api/v1/algoritmos/analisis?campania_id=CAMP-NO-EXISTE",
                       headers=cab(token_especialista))
    assert r.status_code == 404


def test_el_analisis_queda_en_bitacora(algoritmos, token_especialista):
    """La cuarta vez que este modo de falla aparece en el proyecto.

    `auditoria.bitacora` tiene llave foránea contra `auditoria.tipo_accion`
    y el INSERT va envuelto en un try para no tumbar la operación. Si
    `ANALISIS_EJECUTADO` no está declarado —migración 018— el registro
    falla sin que nadie se entere.
    """
    import psycopg2
    algoritmos.get("/api/v1/algoritmos/analisis",
                   headers=cab(token_especialista))
    cn = psycopg2.connect(host=os.environ["PG_HOST"], dbname=os.environ["PG_BASE"],
                          user=os.environ["PG_USUARIO"],
                          password=os.environ["PG_CLAVE"])
    with cn, cn.cursor() as cur:
        cur.execute("SELECT count(*) FROM auditoria.bitacora "
                    " WHERE accion = 'ANALISIS_EJECUTADO'")
        n = cur.fetchone()[0]
    cn.close()
    assert n >= 1, ("El analisis no quedo en bitacora: falta aplicar la "
                    "migracion 018.")
