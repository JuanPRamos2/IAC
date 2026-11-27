"""
El algoritmo complejo: detección de anomalías y tendencias por grupos.

LAS TRES PRUEBAS QUE JUSTIFICAN EL ARCHIVO
-------------------------------------------
1. **Que dispare con señal real.** Suena obvio y es la que encontró el
   defecto de diseño más serio: k-medias AÍSLA a la unidad anómala en su
   propio grupo, su centroide pasa a ser ella misma, su desviación es
   cero, y la anomalía se esconde a sí misma. Una unidad con recuperación
   1.9 contra pares en 3.5 salía como INFORMATIVO y sin un solo hallazgo.

2. **Que NO dispare con ruido.** Es la mitad que se olvida. Un detector
   que marca todo pasaría la primera prueba y sería inútil: produciría una
   lista de unidades «en riesgo» perfectamente creíble, se intervendría
   sobre equipos a los que no les pasa nada, y nadie se enteraría.

3. **Que no gaste épsilon.** Si el motor llamara a la función de cálculo,
   analizar consumiría presupuesto de privacidad y al agotarlo dejaría a
   la campaña sin poder publicar.
"""
import math
import os

import pytest

import analitica
from analitica import agrupamiento as ag
from analitica import tendencia as td
from analitica.ruido import cola_laplace, significancia, umbral_para_confianza

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIMENSIONES = ["DIM-CARGA", "DIM-RECUP", "DIM-APOYO", "DIM-AUTON",
               "DIM-CLARID"]


def fila(unidad, dimension, valor, escala=0.12, n=40):
    return {"unidad_organizacional_id": unidad, "dimension_id": dimension,
            "valor_protegido": valor, "escala_ruido": escala,
            "n_observaciones": n}


def organizacion_sana(cuantas=9, base=3.5, escala=0.12):
    """Unidades parecidas entre sí, sin nada que reportar."""
    filas = []
    for i in range(cuantas):
        for d in DIMENSIONES:
            filas.append(fila(f"UO-SANA-{i}", d, base + (i % 3) * 0.05,
                              escala))
    return filas


# =========================================================================
# 1. Dispara con señal real
# =========================================================================

def test_detecta_una_unidad_con_problema_real():
    """Recuperación 1.9 y apoyo 2.0 contra pares en 3.5.

    Es una diferencia enorme y tiene que salir. La primera versión del
    motor NO la detectaba: k-medias la aislaba en su propio grupo y su
    desviación contra su propio centroide era cero.
    """
    filas = organizacion_sana()
    for d, v in zip(DIMENSIONES, [4.6, 1.9, 2.0, 3.4, 3.4]):
        filas.append(fila("UO-PROBLEMA", d, v))

    r = analitica.analizar(filas, {})
    primera = r["priorizadas"][0]
    assert primera["unidad_organizacional_id"] == "UO-PROBLEMA", (
        f"La unidad con el problema quedo en la posicion "
        f"{[f['unidad_organizacional_id'] for f in r['priorizadas']].index('UO-PROBLEMA')}")
    assert primera["nivel"] in ("ATENCION", "PRIORITARIO"), primera
    assert len(primera["dimensiones_anomalas"]) >= 2


def test_una_unidad_aislada_se_compara_contra_el_grupo_vecino():
    """El arreglo del defecto, comprobado por dentro.

    Si se comparara contra su propio grupo, su desviación sería cero por
    construcción.
    """
    filas = organizacion_sana()
    for d, v in zip(DIMENSIONES, [4.8, 1.5, 1.6, 2.0, 2.0]):
        filas.append(fila("UO-SOLA", d, v))

    perfiles, _, dims = analitica.construir_perfiles(filas)
    anomalias, _ = analitica.detectar_anomalias(perfiles, dims)
    sola = anomalias["UO-SOLA"]

    assert sola["aislada"] is True
    assert sola["comparada_contra"] != sola["grupo"], (
        "Se comparo contra su propio grupo: la desviacion sale cero y la "
        "anomalia se esconde a si misma.")
    assert sola["desviacion_peor"] > 1.0
    assert "se esconderia a si misma" in sola["nota_referencia"]


def test_la_carga_alta_es_mala_y_la_carga_baja_no():
    """En carga percibida, MÁS es peor. En las demás, menos.

    Sin esta distinción el motor reportaría como problema a las unidades
    con poca carga y como sanas a las más cargadas, que es el error que
    invierte el sentido del instrumento entero.
    """
    filas = organizacion_sana()
    for d, v in zip(DIMENSIONES, [4.9, 3.5, 3.5, 3.5, 3.5]):   # solo carga alta
        filas.append(fila("UO-CARGADA", d, v))
    for d, v in zip(DIMENSIONES, [1.6, 3.5, 3.5, 3.5, 3.5]):   # solo carga baja
        filas.append(fila("UO-DESCARGADA", d, v))

    r = analitica.analizar(filas, {})
    por_unidad = {f["unidad_organizacional_id"]: f for f in r["priorizadas"]}
    assert "DIM-CARGA" in por_unidad["UO-CARGADA"]["dimensiones_anomalas"]
    assert "DIM-CARGA" not in por_unidad["UO-DESCARGADA"]["dimensiones_anomalas"], (
        "Marco como problema a la unidad con MENOS carga.")


# =========================================================================
# 2. No dispara con ruido
# =========================================================================

def test_no_marca_nada_en_una_organizacion_homogenea():
    """La mitad que se olvida.

    Un detector que marcara todo pasaría la prueba de arriba y sería
    inútil: reportar todo equivale a no reportar nada.
    """
    r = analitica.analizar(organizacion_sana(cuantas=12), {})
    con_hallazgo = [f for f in r["priorizadas"] if f["dimensiones_anomalas"]]
    assert not con_hallazgo, (
        f"Marco {len(con_hallazgo)} unidades en una organizacion donde todas "
        f"valen casi lo mismo: {[f['unidad_organizacional_id'] for f in con_hallazgo]}")


def test_el_umbral_crece_con_el_ruido():
    """Más ruido exige más evidencia. Es la idea central del detector."""
    anterior = 0.0
    for b in (0.05, 0.12, 0.25, 0.5):
        u = umbral_para_confianza(b)
        assert u > anterior, f"con b={b} el umbral no crecio"
        anterior = u
    # Con el ruido de la semilla de demostracion hace falta MUCHA
    # diferencia. No es un defecto: es lo que ese nivel de ruido permite
    # afirmar, y el motor lo dice en lugar de fingir precision.
    assert umbral_para_confianza(0.5) > 2.0


def test_una_diferencia_pequena_con_mucho_ruido_no_es_anomalia():
    """0.3 puntos con b=0.5 cabe de sobra dentro del ruido."""
    p, significativa = significancia(0.3, 0.5)
    assert not significativa
    assert p > 0.5, p


def test_la_misma_diferencia_con_poco_ruido_si_lo_es():
    """La MISMA desviación, con un décimo del ruido, sí se puede afirmar.

    Es lo que distingue a este detector de un umbral fijo: la respuesta
    depende de cuánto ruido se aplicó, no solo del tamaño del cambio.
    """
    p, significativa = significancia(0.3, 0.05)
    assert significativa
    assert p < 0.05, p


# =========================================================================
# 3. No gasta épsilon
# =========================================================================

def test_el_informe_declara_cero_epsilon():
    r = analitica.analizar(organizacion_sana(), {})
    assert r["epsilon_consumido"] == 0.0
    assert "YA PUBLICADOS" in r["nota_epsilon"]


def test_el_paquete_no_puede_gastar_epsilon_ni_queriendo():
    """Se comprueba contra el código, no contra el comportamiento.

    Lo que importa es que nadie agregue después una llamada a la función
    de cálculo «para tener el dato fresco».
    """
    import pathlib
    carpeta = pathlib.Path(RAIZ) / "apps" / "analitica" / "analitica"
    for archivo in carpeta.glob("*.py"):
        fuente = archivo.read_text(encoding="utf-8")
        assert "fn_calcular_agregado_protegido" not in fuente, archivo.name
        # El paquete es puro: no abre conexiones. Si las abriera, podria
        # llamar a cualquier cosa.
        for prohibido in ("psycopg2", "import redis", "pymongo"):
            assert prohibido not in fuente, f"{archivo.name}: {prohibido}"


# =========================================================================
# Valores suprimidos
# =========================================================================

def test_una_unidad_sin_todas_las_dimensiones_queda_fuera_y_se_reporta():
    """Rellenar el hueco con la media la describiría con un número que
    nadie midió. Quitarla en silencio la haría desaparecer del informe."""
    filas = organizacion_sana()
    for d, v in zip(DIMENSIONES[:3], [3.5, 3.4, 3.6]):   # le faltan dos
        filas.append(fila("UO-PARCIAL", d, v))

    r = analitica.analizar(filas, {})
    fuera = {f["unidad_organizacional_id"]
             for f in r["unidades_sin_perfil_completo"]}
    assert "UO-PARCIAL" in fuera
    detalle = next(f for f in r["unidades_sin_perfil_completo"]
                   if f["unidad_organizacional_id"] == "UO-PARCIAL")
    assert set(detalle["dimensiones_suprimidas"]) == {"DIM-AUTON", "DIM-CLARID"}
    assert "UO-PARCIAL" not in {f["unidad_organizacional_id"]
                                for f in r["priorizadas"]}


def test_un_valor_nulo_no_se_toma_como_cero():
    """Un cero en escala 1..5 sería el peor valor posible.

    Tomar una supresión como cero convertiría a toda unidad con un grupo
    pequeño en la más urgente de la lista.
    """
    filas = organizacion_sana()
    filas.append(fila("UO-NULA", "DIM-CARGA", None))
    perfiles, incompletas, _ = analitica.construir_perfiles(filas)
    assert "UO-NULA" not in perfiles
    valores = [v["valor"] for dims in perfiles.values() for v in dims.values()]
    assert all(v > 0 for v in valores)


# =========================================================================
# Tendencia
# =========================================================================

def test_theil_sen_aguanta_un_valor_atipico():
    """Es la razón de usarlo en lugar de mínimos cuadrados.

    El ruido de Laplace tiene colas pesadas: produce valores lejanos con
    una frecuencia que no es despreciable. Mínimos cuadrados pesa cada
    punto por su distancia AL CUADRADO, así que es el peor método posible
    para exactamente estos datos.
    """
    x = [1, 2, 3, 4, 5, 6]
    limpia = [3.0, 2.9, 2.8, 2.7, 2.6, 2.5]      # baja 0.1 por paso
    pendiente, _ = td.theil_sen(x, limpia)
    assert pendiente == pytest.approx(-0.1, abs=0.02)

    con_atipico = list(limpia)
    con_atipico[2] = 9.0                          # un disparate
    robusta, _ = td.theil_sen(x, con_atipico)

    # Mínimos cuadrados, para comparar.
    n = len(x)
    mx, my = sum(x) / n, sum(con_atipico) / n
    mc = (sum((a - mx) * (b - my) for a, b in zip(x, con_atipico))
          / sum((a - mx) ** 2 for a in x))

    assert abs(robusta - (-0.1)) < abs(mc - (-0.1)), (
        f"Theil-Sen ({robusta:.3f}) no aguanto mejor que minimos cuadrados "
        f"({mc:.3f}) frente a la pendiente real de -0.1")
    assert robusta < 0, "perdio hasta el signo"


def test_mann_kendall_distingue_tendencia_de_azar():
    bajando = [4.0, 3.8, 3.6, 3.4, 3.2, 3.0]
    _, _, p, direccion = td.mann_kendall(bajando)
    assert direccion == "A_LA_BAJA" and p < 0.05

    plana = [3.5, 3.4, 3.6, 3.5, 3.4, 3.6]
    _, _, p2, direccion2 = td.mann_kendall(plana)
    assert direccion2 == "ESTABLE", (direccion2, p2)


def test_una_serie_corta_no_produce_tendencia():
    """Con dos puntos, cualquier par define una recta perfecta."""
    r = td.analizar([(1, 3.5, 0.1), (2, 3.0, 0.1)])
    assert r["direccion"] == "INDETERMINADA"
    assert r["pendiente_por_campania"] is None


def test_los_puntos_suprimidos_se_cuentan_y_no_se_rellenan():
    """Si falta la campaña 3, las campañas 2 y 4 no son consecutivas.

    La pendiente se calcula contra la secuencia real, así que el salto
    entre ellas vale dos pasos y no uno.
    """
    r = td.analizar([(1, 4.0, 0.1), (2, 3.8, 0.1), (3, None, None),
                     (4, 3.4, 0.1), (5, 3.2, 0.1)])
    assert r["puntos_suprimidos"] == 1
    assert r["puntos_publicados"] == 4
    assert r["pendiente_por_campania"] == pytest.approx(-0.2, abs=0.05)


# =========================================================================
# Agrupamiento
# =========================================================================

def test_el_agrupamiento_es_repetible():
    """Un resultado que cambia entre corridas sin que cambien los datos es
    indefendible ante quien pregunta por qué su área salió en la lista."""
    filas = organizacion_sana(cuantas=15)
    a = analitica.analizar(filas, {})
    b = analitica.analizar(filas, {})
    assert ([f["unidad_organizacional_id"] for f in a["priorizadas"]]
            == [f["unidad_organizacional_id"] for f in b["priorizadas"]])
    assert a["agrupamiento"]["grupos"] == b["agrupamiento"]["grupos"]


def test_separa_dos_poblaciones_claramente_distintas():
    """Turnos nocturnos contra oficina: el caso que motiva agrupar."""
    filas = []
    for i in range(6):      # oficina: todo bien
        for d, v in zip(DIMENSIONES, [2.8, 4.2, 4.1, 4.0, 4.1]):
            filas.append(fila(f"UO-OFI-{i}", d, v + (i % 2) * 0.05))
    for i in range(6):      # turno nocturno: recuperacion baja SIEMPRE
        for d, v in zip(DIMENSIONES, [4.0, 2.4, 3.6, 3.0, 3.5]):
            filas.append(fila(f"UO-NOC-{i}", d, v + (i % 2) * 0.05))

    perfiles, _, dims = analitica.construir_perfiles(filas)
    anomalias, info = analitica.detectar_anomalias(perfiles, dims)
    assert info["grupos"] >= 2
    grupos_ofi = {anomalias[f"UO-OFI-{i}"]["grupo"] for i in range(6)}
    grupos_noc = {anomalias[f"UO-NOC-{i}"]["grupo"] for i in range(6)}
    assert not (grupos_ofi & grupos_noc), (
        "Mezclo oficina con turno nocturno. Contra un centroide comun, los "
        "turnos nocturnos saldrian como anomalia todos los semestres: tienen "
        "peor recuperacion porque trabajan de noche, no porque algo vaya mal.")

    # Y ningún turno nocturno sale marcado por ser nocturno.
    r = analitica.analizar(filas, {})
    marcadas = {f["unidad_organizacional_id"] for f in r["priorizadas"]
                if f["dimensiones_anomalas"]}
    assert not marcadas, marcadas


def test_la_silueta_prefiere_grupos_separados():
    juntos = [[3.5, 3.5], [3.5, 3.6], [3.6, 3.5], [3.5, 3.5]]
    separados = [[1.0, 1.0], [1.1, 1.0], [5.0, 5.0], [4.9, 5.0]]
    aj, cj = ag.kmedias(juntos, 2)
    as_, cs = ag.kmedias(separados, 2)
    assert ag.silueta(separados, as_, cs) > ag.silueta(juntos, aj, cj)


# =========================================================================
# El ruido, por dentro
# =========================================================================

def test_la_cola_de_laplace_es_la_formula_conocida():
    assert cola_laplace(0.5, 0.5) == pytest.approx(math.exp(-1.0))
    assert cola_laplace(0, 0.5) == 1.0
    assert cola_laplace(1.0, 0) == 0.0          # sin ruido, nada es azar


def test_sin_ruido_declarado_no_se_inventa_un_umbral():
    assert umbral_para_confianza(0) == 0.0
    assert umbral_para_confianza(None) == 0.0


@pytest.mark.parametrize("confianza", [0.0, 1.0, -0.1, 1.5])
def test_una_confianza_imposible_se_rechaza(confianza):
    with pytest.raises(ValueError):
        umbral_para_confianza(0.5, confianza)


# =========================================================================
# 4. Significativo no es lo mismo que importante
#
# Las pruebas de esta sección y de la siguiente existen por dos defectos
# que solo aparecieron al validar el detector contra señal inyectada en
# 110 unidades con 26 mil empleados. Ninguno se veía con los datos de
# demostración, y los dos volvían inútil al detector por lados opuestos.
# =========================================================================

def test_una_diferencia_cierta_pero_minuscula_no_es_un_hallazgo():
    """El defecto que trae el tamaño de muestra.

    Con 400 personas en una unidad la escala de Laplace baja a 0.04, y
    entonces una diferencia de 0.12 puntos entre dos áreas es
    estadísticamente certísima. Sobre una escala de 1 a 5, 0.12 puntos no
    es nada sobre lo que un comité pueda actuar.

    Se midió con los datos masivos: el detector marcaba 36 dimensiones con
    desviación mediana de 0.12 puntos. Treinta y seis hallazgos ciertos e
    inservibles, y la lista perdía su único propósito, que es decir por
    dónde empezar.
    """
    escala_diminuta = 0.01
    filas = organizacion_sana(cuantas=12, base=3.5, escala=escala_diminuta)
    # 0.12 puntos por debajo: doce veces la escala de ruido, así que el
    # ruido no lo explica ni de lejos. Y materialmente, nada.
    for d in DIMENSIONES:
        filas.append(fila("UO-APENAS", d, 3.38, escala=escala_diminuta, n=400))

    r = analitica.analizar(filas, {})
    apenas = next(p for p in r["priorizadas"]
                  if p["unidad_organizacional_id"] == "UO-APENAS")
    assert apenas["dimensiones_anomalas"] == [], (
        f"Se senalaron {apenas['dimensiones_anomalas']} con una desviacion de "
        f"0.12 puntos. Es cierta y es irrelevante: con datos masivos el ruido "
        f"baja tanto que todo pasa la prueba de significancia, y sin umbral "
        f"material el detector devuelve decenas de hallazgos inservibles.")
    assert apenas["nivel"] == "INFORMATIVO"

    # Y la prueba de que el filtro no es que no detecte NADA: la misma
    # organizacion con una desviacion material si dispara.
    filas_grandes = organizacion_sana(cuantas=12, base=3.5,
                                      escala=escala_diminuta)
    for d in DIMENSIONES:
        filas_grandes.append(fila("UO-GRANDE", d, 2.6, escala=escala_diminuta,
                                  n=400))
    r2 = analitica.analizar(filas_grandes, {})
    grande = next(p for p in r2["priorizadas"]
                  if p["unidad_organizacional_id"] == "UO-GRANDE")
    assert grande["dimensiones_anomalas"], (
        "Con 0.9 puntos de diferencia no detecto nada: el umbral material "
        "quedo tan alto que ahora el detector no sirve para lo contrario.")


def test_el_umbral_material_sale_de_los_datos_y_no_de_una_constante():
    """Media desviación estándar de lo que varían las unidades entre sí.

    Un umbral fijo sería arbitrario: 0.3 puntos es mucho en una
    organización muy homogénea y poco en una muy dispar. Lo que importa es
    si esta área se sale de la variación normal de SU organización.
    """
    homogenea = organizacion_sana(cuantas=20, base=3.5, escala=0.02)
    r1 = analitica.analizar(homogenea, {})
    umbrales_h = r1["agrupamiento"]["umbrales_materiales"]

    dispar = []
    for i in range(20):
        for d in DIMENSIONES:
            dispar.append(fila(f"UO-D-{i}", d, 2.0 + (i % 10) * 0.3,
                               escala=0.02))
    r2 = analitica.analizar(dispar, {})
    umbrales_d = r2["agrupamiento"]["umbrales_materiales"]

    assert all(umbrales_d[d] > umbrales_h[d] for d in DIMENSIONES), (
        f"El umbral material no reacciono a la dispersion de la "
        f"organizacion.\nhomogenea: {umbrales_h}\ndispar: {umbrales_d}")
    # El piso existe para el caso degenerado: en una organizacion donde
    # todas las unidades son identicas, media desviacion estandar es cero
    # y el umbral desapareceria justo cuando mas hace falta.
    assert all(v >= 0.25 for v in umbrales_h.values()), umbrales_h


# =========================================================================
# 5. El grupo de pares puede ser él mismo la anomalía
# =========================================================================

def test_un_grupo_entero_desplazado_se_reporta_como_hallazgo_de_segmento():
    """El defecto más grave que encontró la validación con señal inyectada.

    Comparar cada unidad con su grupo de pares resuelve un problema real
    —contra el promedio global los turnos nocturnos salen como anomalía
    todos los semestres— y tiene un punto ciego que lo anula: **el grupo
    puede ser él mismo la anomalía.**

    Se midió con 110 unidades y cinco deterioradas a propósito: k-medias
    puso a las cinco en el MISMO grupo, porque para eso sirve, con un
    centroide de recuperación 1.86 contra 3.97 del grupo sano. Dos puntos
    de diferencia en una escala de 1 a 5, y dentro de su grupo las cinco
    parecían normales. El motor las reportó INFORMATIVO. Eran las cinco
    unidades que había que encontrar.
    """
    # Variación CONTINUA y no tres valores repetidos: con `i % 3` solo hay
    # tres puntos distintos, k-medias los separa en grupos de puntos
    # idénticos con silueta 1.0, y el caso de prueba deja de parecerse a
    # una organización real.
    filas = []
    for i in range(20):
        for d in DIMENSIONES:
            filas.append(fila(f"UO-SANA-{i}", d, 3.6 + i * 0.015, escala=0.03))
    # Seis unidades parecidas entre sí y muy por debajo del resto. Dentro
    # de su propio grupo ninguna destaca, que es justo el problema.
    for i in range(6):
        for d, v in zip(DIMENSIONES, [4.6, 2.0, 2.1, 2.6, 2.5]):
            filas.append(fila(f"UO-MAL-{i}", d, v + i * 0.02, escala=0.03))

    r = analitica.analizar(filas, {})

    hallazgos = r["hallazgos_de_segmento"]
    assert hallazgos, (
        "Seis unidades un punto y medio por debajo de la organizacion y "
        "ningun hallazgo de segmento. Dentro de su grupo no destacan: si el "
        "grupo no se mide contra la organizacion, las seis desaparecen.")

    grupo_malo = max(hallazgos, key=lambda h: h["desplazamiento_peor"])
    assert grupo_malo["desplazamiento_peor"] > 0.8, grupo_malo
    assert len(grupo_malo["dimensiones_desplazadas"]) >= 2, grupo_malo
    dentro = set(grupo_malo["unidades_del_grupo"])
    assert all(f"UO-MAL-{i}" in dentro for i in range(6)), (
        f"El hallazgo de segmento no cubre a las seis: {sorted(dentro)}")
    assert not any(u.startswith("UO-SANA") for u in dentro), (
        f"El hallazgo de segmento arrastro unidades sanas: {sorted(dentro)}")

    # Y cada unidad del segmento trae el contexto consigo: la lista
    # priorizada se lee una unidad a la vez, y «esta como sus pares» sin
    # «y sus pares estan un punto y medio por debajo» es engañoso.
    for p in r["priorizadas"]:
        if p["unidad_organizacional_id"].startswith("UO-MAL"):
            assert p["grupo_desplazado_en"], p
            assert p["desplazamiento_del_grupo"] > 0.8, p
            assert any("grupo completo" in m for m in p["motivos"]), p["motivos"]


def test_el_hallazgo_de_segmento_no_afirma_que_el_segmento_este_mal():
    """Lo que el algoritmo NO puede saber, dicho por el algoritmo.

    Un turno nocturno tiene peor recuperación porque trabaja de noche: es
    un desplazamiento legítimo y estructural. Un segmento en crisis
    también está desplazado. **Desde los datos las dos cosas son
    idénticas** y ningún estadístico las separa.

    Un motor que afirmara cuál de las dos es estaría inventando, y sobre
    eso se decidirían intervenciones sobre equipos de gente. Esta prueba
    comprueba que la salida nombra la pregunta en lugar de contestarla.
    """
    filas = []
    for i in range(16):
        for d in DIMENSIONES:
            filas.append(fila(f"UO-SANA-{i}", d, 3.6 + i * 0.015, escala=0.03))
    for i in range(5):
        for d, v in zip(DIMENSIONES, [4.4, 2.2, 3.5, 3.5, 2.3]):
            filas.append(fila(f"UO-NOCTURNO-{i}", d, v + i * 0.02, escala=0.03))

    r = analitica.analizar(filas, {})
    hallazgo = max(r["hallazgos_de_segmento"],
                   key=lambda h: h["desplazamiento_peor"])

    texto = (hallazgo["lectura"] + hallazgo["accion_sugerida"]
             + hallazgo["pregunta_para_la_persona"]).lower()
    assert "no distinguen" in texto or "no lo distinguen" in texto, (
        "El hallazgo de segmento no advierte que los datos no distinguen un "
        "segmento que ES asi de un segmento que ESTA mal.")
    assert "?" in hallazgo["pregunta_para_la_persona"], (
        "El hallazgo no deja una pregunta para la persona: entonces esta "
        "afirmando, y no puede.")
    assert hallazgo["unidades_del_grupo"], (
        "El hallazgo no dice de que unidades habla, asi que nadie puede ir a "
        "revisar el segmento.")


# =========================================================================
# 6. El nivel y la dirección
# =========================================================================

def test_el_nivel_sale_de_los_hallazgos_y_no_del_promedio():
    """Un promedio ponderado diluye una señal fuerte y aislada.

    Se midió: una unidad con tres de cinco dimensiones deteriorándose de
    forma sostenida —p≈0.000, casi un punto de caída en doce campañas— y
    sin nada más que señalar salía con puntaje 0.316, por debajo del corte
    de ATENCION. Es exactamente la unidad donde una intervención todavía
    sirve.

    El nivel es una disyunción —basta UNA de varias condiciones— y usar un
    promedio para eso estaba mal. Además, «ATENCION porque tres
    dimensiones vienen cayendo» se puede discutir en un comité y
    «ATENCION porque 0.407 > 0.35» no.
    """
    filas = organizacion_sana(cuantas=12, base=3.5, escala=0.03)
    for d in DIMENSIONES:
        filas.append(fila("UO-CAYENDO", d, 3.5, escala=0.03))

    # Doce campañas bajando 0.08 por campaña en tres dimensiones: casi un
    # punto de recorrido, inequivoco.
    series = {"UO-CAYENDO": {}}
    for d in DIMENSIONES:
        if d in ("DIM-RECUP", "DIM-APOYO"):
            series["UO-CAYENDO"][d] = [(s, 4.3 - 0.08 * s, 0.03)
                                       for s in range(1, 13)]
        elif d == "DIM-CARGA":
            series["UO-CAYENDO"][d] = [(s, 2.9 + 0.08 * s, 0.03)
                                       for s in range(1, 13)]
        else:
            series["UO-CAYENDO"][d] = [(s, 3.5, 0.03) for s in range(1, 13)]

    r = analitica.analizar(filas, series)
    cayendo = next(p for p in r["priorizadas"]
                   if p["unidad_organizacional_id"] == "UO-CAYENDO")

    assert len(cayendo["dimensiones_empeorando"]) == 3, cayendo
    assert cayendo["nivel"] == "PRIORITARIO", (
        f"Tres dimensiones en deterioro sostenido y el nivel es "
        f"{cayendo['nivel']} con puntaje {cayendo['puntaje']}. El promedio "
        f"ponderado volvio a diluir la senal.")
    assert cayendo["puntaje"] < 0.60, (
        "Esta prueba ya no comprueba nada: el puntaje por si solo alcanza el "
        "corte viejo, asi que no distingue el nivel por reglas del nivel por "
        "promedio.")
    assert any("empeorando" in m for m in cayendo["motivos"]), cayendo["motivos"]
    assert r["priorizadas"][0]["unidad_organizacional_id"] == "UO-CAYENDO", (
        "La unidad en deterioro no quedo primera: el orden tiene que ser por "
        "nivel y no solo por puntaje.")


def test_en_carga_percibida_bajar_es_mejorar():
    """«Empeorar» no es «bajar», y confundirlos invierte el resultado.

    La primera versión contaba A_LA_BAJA en TODAS las dimensiones y además
    sumaba aparte las cargas al alza. Efecto doble: una unidad cuya carga
    estaba bajando —una mejora clara— se contaba como si estuviera
    empeorando, y una que de verdad empeoraba en carga se contaba dos
    veces.
    """
    filas = organizacion_sana(cuantas=10, base=3.5, escala=0.03)
    for d in DIMENSIONES:
        filas.append(fila("UO-ALIVIADA", d, 3.5, escala=0.03))

    # Carga bajando mucho y nada más cambiando: es una MEJORA.
    series = {"UO-ALIVIADA": {d: [(s, 3.5, 0.03) for s in range(1, 13)]
                              for d in DIMENSIONES}}
    series["UO-ALIVIADA"]["DIM-CARGA"] = [(s, 4.4 - 0.1 * s, 0.03)
                                          for s in range(1, 13)]

    r = analitica.analizar(filas, series)
    aliviada = next(p for p in r["priorizadas"]
                    if p["unidad_organizacional_id"] == "UO-ALIVIADA")
    assert aliviada["dimensiones_empeorando"] == [], (
        f"La carga percibida BAJANDO se conto como deterioro: "
        f"{aliviada['dimensiones_empeorando']}. En carga, menos es mejor.")

    # Y al revés, para que la prueba no pase por no contar nunca nada.
    series["UO-ALIVIADA"]["DIM-CARGA"] = [(s, 2.6 + 0.1 * s, 0.03)
                                          for s in range(1, 13)]
    r2 = analitica.analizar(filas, series)
    cargada = next(p for p in r2["priorizadas"]
                   if p["unidad_organizacional_id"] == "UO-ALIVIADA")
    assert cargada["dimensiones_empeorando"] == ["DIM-CARGA"], (
        f"La carga percibida SUBIENDO no se conto como deterioro: "
        f"{cargada['dimensiones_empeorando']}")


def test_una_tendencia_real_pero_minuscula_no_cuenta_como_deterioro():
    """La misma compuerta material, en el camino de las tendencias.

    Con 110 unidades por 5 dimensiones hay 550 series, y a p<0.05 el azar
    solo produce unas 27 detecciones. El filtro de ruido no las frena
    porque con datos masivos la escala de Laplace baja a 0.04 y cualquier
    deriva real la supera. Medido: 19 unidades señaladas como
    deteriorándose cuando solo 5 lo estaban —precisión 26%—, y con la
    compuerta material, 6 señaladas y precisión 83% sin perder ninguna.
    """
    filas = organizacion_sana(cuantas=12, base=3.5, escala=0.01)
    for d in DIMENSIONES:
        filas.append(fila("UO-DERIVA", d, 3.5, escala=0.01))

    # Doce campañas bajando 0.01 por campaña: 0.11 de recorrido total.
    # Monotono, asi que Mann-Kendall lo declara real, y lo es. Y no
    # significa nada.
    series = {"UO-DERIVA": {d: [(s, 3.5, 0.01) for s in range(1, 13)]
                            for d in DIMENSIONES}}
    series["UO-DERIVA"]["DIM-RECUP"] = [(s, 3.56 - 0.01 * s, 0.01)
                                        for s in range(1, 13)]

    r = analitica.analizar(filas, series)
    tendencia = r["tendencias"]["UO-DERIVA"]["DIM-RECUP"]
    assert tendencia["direccion"] == "A_LA_BAJA", (
        "Esta prueba ya no comprueba nada: Mann-Kendall tendria que ver la "
        "bajada monotona. Si no la ve, el caso de prueba dejo de ser el que "
        "interesa.")
    assert tendencia["supera_el_ruido"] is True, (
        "Esta prueba ya no comprueba nada: el recorrido tendria que superar "
        "el ruido para que la unica razon de descartarlo sea la material.")

    deriva = next(p for p in r["priorizadas"]
                  if p["unidad_organizacional_id"] == "UO-DERIVA")
    assert deriva["dimensiones_empeorando"] == [], (
        f"Una caida de 0.11 puntos en doce campanias se conto como "
        f"deterioro: {deriva['dimensiones_empeorando']}. Es real y es "
        f"irrelevante, y contarla llena la lista de areas que no tienen nada.")
