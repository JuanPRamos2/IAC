"""
El motor: de valores publicados a una lista priorizada de unidades.

QUÉ RESUELVE
------------
La organización tiene decenas o cientos de unidades y cinco dimensiones
de bienestar medidas cada campaña. Nadie puede mirar esa matriz y decidir
dónde intervenir. El motor contesta una pregunta concreta:

    ¿Qué unidades merecen atención, por qué, y qué tan seguros estamos?

Y la contesta sin ver a una sola persona: trabaja únicamente sobre
agregados ya publicados, que pasaron el umbral k y ya llevan su ruido.

LAS CINCO DECISIONES
--------------------
1. **Cero epsilon adicional.** El motor lee `agregado.v_tablero_unidad`,
   que son resultados publicados. No llama a la función de cálculo. Si lo
   hiciera, analizar gastaría presupuesto de privacidad y, al agotarlo,
   dejaría a la campaña sin poder publicar. Hay una prueba que lo
   comprueba contra el código.

2. **Cada unidad se compara con sus pares, no con el promedio global.**
   Ver `agrupamiento.py`: contra el promedio global, los turnos nocturnos
   salen como anomalía todos los semestres y la lista se vuelve inútil.

3. **El umbral de anomalía sale del ruido, no de una constante.** Ver
   `ruido.py`: el sistema guarda la escala que aplicó, así que la
   pregunta «¿puede el ruido explicar esto?» tiene respuesta exacta.

4. **Anomalía y tendencia son cosas distintas y se reportan por
   separado.** Una unidad puede estar mal y estable —ya tocó fondo— o
   bien y cayendo. Mezclarlas en un solo número esconde justo la
   diferencia que decide qué intervención toca.

5. **La prioridad se explica renglón por renglón.** Cada unidad priorizada
   trae de dónde salió su puntaje. Un ranking sin desglose no se puede
   discutir, y este se discute en un comité que puede —y debe— no estar
   de acuerdo.

LO QUE EL MOTOR NO HACE
------------------------
No dice la causa. Detecta que una unidad está lejos de sus pares o que
viene cayendo; por qué, lo averigua una persona hablando con el área. Un
sistema que afirmara la causa estaría inventando, y sobre eso se tomarían
decisiones que afectan a equipos de gente.

COMPLEJIDAD TOTAL
-----------------
    perfiles            O(n · d)
    agrupamiento        O(n · k · i · d) por cada k candidato
    anomalías           O(n · d)
    tendencias          O(n · d · m²)
    priorización        O(n log n)

con n unidades, d = 5 dimensiones, m campañas, k grupos, i iteraciones.
Domina el agrupamiento para n grande y las tendencias para m grande; con
los tamaños reales del proyecto (n en cientos, m en decenas) las dos
partes son de milisegundos.
"""
import time

from . import agrupamiento as ag
from . import tendencia as td
from .ruido import (FACTOR_CONTRA_CENTROIDE, escala_combinada, significancia,
                    umbral_para_confianza)

# Dimensiones en las que un valor MÁS ALTO es peor. En este instrumento
# todas las demás son "más alto es mejor": más apoyo, más autonomía, más
# recuperación. La carga es la excepción, y tratarla como las demás haría
# que el motor reportara como logro justamente a las unidades más
# cargadas.
DIMENSIONES_INVERTIDAS = {"DIM-CARGA"}

PESOS = {
    "anomalia": 0.30,      # qué tan lejos está de sus pares
    "tendencia": 0.30,     # hacia dónde va
    "contexto": 0.20,      # qué tan desplazado está su grupo entero
    "persistencia": 0.12,  # cuántas dimensiones a la vez
    "confianza": 0.08,     # qué tan fiable es la lectura
}

# EL UMBRAL MATERIAL, Y POR QUÉ HACEN FALTA DOS UMBRALES
# ------------------------------------------------------
# `ruido.py` contesta «¿puede el ruido de privacidad explicar esta
# diferencia?». Es una pregunta necesaria y no es suficiente, y con datos
# masivos se vuelve engañosa: con 400 personas en una unidad la escala de
# Laplace baja a 0.04, y entonces una diferencia de 0.12 puntos entre dos
# áreas es estadísticamente certísima. Sobre una escala de 1 a 5, 0.12
# puntos no es nada que un comité pueda accionar.
#
# Se midió: con los datos masivos, el detector marcaba 36 dimensiones con
# desviación mediana de 0.12 puntos. Treinta y seis hallazgos ciertos e
# inservibles. El tamaño de muestra había vuelto significativo todo, que
# es lo que siempre pasa, y la lista perdía su único propósito: decir por
# dónde empezar.
#
# Así que una dimensión se señala solo si pasa LAS DOS pruebas:
#   1. es mayor que lo que el ruido explica  (ruido.py)
#   2. es materialmente grande               (esto)
#
# El umbral material NO es una constante inventada: es una fracción de la
# dispersión real entre unidades de la propia organización. Media
# desviación estándar es el «efecto medio» de Cohen, el punto en que una
# diferencia deja de ser ruido de la población y empieza a describir algo
# distinto. Dicho sin estadística: una diferencia menor que la mitad de lo
# que normalmente varían las áreas entre sí no es un hallazgo, es esta
# área dentro de la variación normal.
#
# El piso existe para el caso degenerado: en una organización muy
# homogénea la dispersión tiende a cero y media desviación estándar
# también, y entonces el umbral material desaparecería justo cuando más
# hace falta.
FRACCION_DESVIACION = 0.5
PISO_MATERIAL = 0.25

# Cuántas unidades hacen falta para hablar de un «segmento». Por debajo
# de tres, un grupo desplazado es una unidad que no se parece a ninguna
# otra, y de eso ya se encarga el camino de la unidad: se la mide contra
# el centroide del grupo más cercano. Ver `hallazgos_de_segmento`.
MINIMO_PARA_SEGMENTO = 3


def _peor_direccion(dimension_id, desviacion):
    """¿Esta desviación es hacia peor?

    En carga percibida, estar POR ENCIMA de los pares es peor. En las
    demás, estar por debajo.
    """
    if dimension_id in DIMENSIONES_INVERTIDAS:
        return desviacion > 0
    return desviacion < 0


def _mediana(valores):
    v = sorted(valores)
    n = len(v)
    if not n:
        return 0.0
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def _dispersion(valores):
    """Desviación estándar muestral. Base del umbral material."""
    n = len(valores)
    if n < 2:
        return 0.0
    media = sum(valores) / n
    return (sum((x - media) ** 2 for x in valores) / (n - 1)) ** 0.5


def _umbrales_materiales(perfiles, dimensiones):
    """Cuánta diferencia hace falta, por dimensión, para que importe.

    Se calcula de los datos de la propia organización y no de una tabla:
    media desviación estándar de lo que varían sus unidades entre sí, con
    un piso para que una organización muy homogénea no se quede sin
    umbral.
    """
    salida = {}
    for dim in dimensiones:
        valores = [p[dim]["valor"] for p in perfiles.values()]
        salida[dim] = max(PISO_MATERIAL,
                          FRACCION_DESVIACION * _dispersion(valores))
    return salida


def _referencia_de_la_organizacion(perfiles, dimensiones):
    """La mediana de cada dimensión entre TODAS las unidades.

    Mediana y no media, y el motivo es el defecto que esta función existe
    para arreglar: si un puñado de unidades está muy mal, arrastran la
    media hacia abajo y el punto de referencia se contamina justamente con
    lo que se quiere detectar. La mediana no se mueve.
    """
    return {dim: _mediana([p[dim]["valor"] for p in perfiles.values()])
            for dim in dimensiones}


def desplazamiento_de_grupos(perfiles, dimensiones, asignacion, centroides,
                             unidades, umbrales):
    """Cuánto se aparta cada GRUPO de la organización, y hacia dónde.

    EL DEFECTO QUE ESTO ARREGLA
    ---------------------------
    Comparar cada unidad con su grupo de pares es correcto y resuelve un
    problema real: contra el promedio global, los turnos nocturnos salen
    como anomalía todos los semestres y la lista se vuelve inútil.

    Pero tiene un punto ciego que lo anula, y no se ve hasta probarlo con
    señal inyectada: **el grupo puede ser él mismo la anomalía.** Se midió
    con 110 unidades y cinco unidades deterioradas a propósito: k-medias
    las puso a las cinco en el MISMO grupo —para eso sirve, agrupa lo
    parecido— con un centroide de recuperación 1.86 y apoyo 2.60 contra
    3.97 y 3.98 del grupo sano. Dos puntos de diferencia en una escala de
    1 a 5, y dentro de su grupo las cinco parecían normales. El motor las
    reportó INFORMATIVO. Las cinco unidades que había que encontrar.

    LO QUE ESTA FUNCIÓN **NO** PUEDE DECIR
    --------------------------------------
    Que un grupo esté desplazado no significa que esté en problemas. Un
    turno nocturno tiene peor recuperación porque trabaja de noche; eso es
    un desplazamiento legítimo y estructural. Un grupo de áreas en crisis
    también está desplazado. **Desde los datos las dos cosas son
    idénticas**, y ningún estadístico las separa.

    Así que esto no decide: mide el desplazamiento, lo reporta por
    separado del desvío intra-grupo, y dice explícitamente que distinguir
    «este segmento es así» de «este segmento está mal» es un juicio de una
    persona que conoce la organización. Colapsar las dos cosas en un solo
    número —en cualquier dirección— sería el motor afirmando algo que no
    puede saber.
    """
    referencia = _referencia_de_la_organizacion(perfiles, dimensiones)
    salida = {}
    for g, centro in enumerate(centroides):
        miembros = [i for i, a in enumerate(asignacion) if a == g]
        detalle = []
        for j, dim in enumerate(dimensiones):
            desplazamiento = centro[j] - referencia[dim]
            material = abs(desplazamiento) >= umbrales[dim]
            hacia_peor = _peor_direccion(dim, desplazamiento)
            detalle.append({
                "dimension_id": dim,
                "centroide_del_grupo": round(centro[j], 3),
                "mediana_de_la_organizacion": round(referencia[dim], 3),
                "desplazamiento": round(desplazamiento, 3),
                "umbral_material": round(umbrales[dim], 3),
                "material": material,
                "hacia_peor": hacia_peor,
                "desplazado_hacia_peor": material and hacia_peor,
            })
        peores = [d for d in detalle if d["desplazado_hacia_peor"]]
        salida[g] = {
            "grupo": g,
            "unidades": len(miembros),
            "dimensiones": detalle,
            "dimensiones_desplazadas_hacia_peor": [d["dimension_id"]
                                                   for d in peores],
            "desplazamiento_peor": round(
                max((abs(d["desplazamiento"]) for d in peores), default=0.0), 3),
            "lectura": (
                f"Este grupo esta por debajo de la mediana de la organizacion "
                f"en {len(peores)} dimension(es); la peor por "
                f"{max((abs(d['desplazamiento']) for d in peores), default=0.0):.2f} "
                f"puntos. Eso puede ser la naturaleza del segmento (un turno "
                f"nocturno descansa peor porque trabaja de noche) o un "
                f"problema sistemico del segmento completo. Los datos NO "
                f"distinguen las dos cosas: lo decide quien conoce la "
                f"organizacion."
                if peores else
                "Este grupo no esta materialmente por debajo de la mediana de "
                "la organizacion en ninguna dimension."),
        }
    return salida, referencia


def construir_perfiles(filas):
    """Matriz unidad × dimensión de la campaña más reciente de cada una.

    `filas` son diccionarios con unidad_organizacional_id, dimension_id,
    valor_protegido, escala_ruido, n_observaciones.

    Una unidad entra solo si tiene valor publicado en TODAS las
    dimensiones. Rellenar los huecos con la media del grupo sería lo
    cómodo y falsearía justo lo que se quiere medir: una unidad a la que
    le suprimieron una dimensión por grupo pequeño quedaría descrita por
    un número que nadie midió.
    """
    por_unidad = {}
    for f in filas:
        if f.get("valor_protegido") is None:
            continue
        u = f["unidad_organizacional_id"]
        por_unidad.setdefault(u, {})[f["dimension_id"]] = {
            "valor": float(f["valor_protegido"]),
            "escala": float(f.get("escala_ruido") or 0.0),
            "n": int(f.get("n_observaciones") or 0),
        }

    dimensiones = sorted({f["dimension_id"] for f in filas
                          if f.get("dimension_id")})
    completas, incompletas = {}, {}
    for unidad, dims in por_unidad.items():
        faltan = [d for d in dimensiones if d not in dims]
        if faltan:
            incompletas[unidad] = faltan
        else:
            completas[unidad] = dims
    return completas, incompletas, dimensiones


def detectar_anomalias(perfiles, dimensiones, semilla=ag.SEMILLA):
    """Agrupa y mide cuánto se aparta cada unidad de su grupo.

    Devuelve (resultado_por_unidad, info_agrupamiento).
    """
    unidades = sorted(perfiles)
    if not unidades:
        return {}, {"grupos": 0, "motivo": "no hay unidades con perfil completo"}

    puntos = [[perfiles[u][d]["valor"] for d in dimensiones] for u in unidades]
    k, asignacion, centroides, s = ag.elegir_k(puntos, semilla=semilla)

    # Los dos umbrales que gobiernan todo lo que sigue: el del ruido se
    # calcula por valor (lo hace `ruido.py`), y el material se calcula una
    # vez para toda la organización.
    umbrales = _umbrales_materiales(perfiles, dimensiones)
    grupos_desplazados, referencia_org = desplazamiento_de_grupos(
        perfiles, dimensiones, asignacion, centroides, unidades, umbrales)

    salida = {}
    for i, unidad in enumerate(unidades):
        grupo = asignacion[i]
        companeros = [j for j, g in enumerate(asignacion) if g == grupo]

        # UNA UNIDAD SOLA EN SU GRUPO SE COMPARA CON EL GRUPO VECINO
        # -----------------------------------------------------------
        # Esto arregla un fallo que vuelve inútil al detector entero, y
        # que no se ve hasta que se prueba con una anomalía de verdad:
        # k-medias AÍSLA a la unidad anómala en su propio grupo, porque
        # para eso sirve. Y entonces su centroide es ella misma, su
        # desviación es cero, y la anomalía se esconde a sí misma.
        #
        # Se comprobó: una unidad con recuperación 1.9 y apoyo 2.0 contra
        # pares en 3.5 —una diferencia enorme— salía como INFORMATIVO y
        # sin un solo hallazgo.
        #
        # Cuando el grupo propio tiene uno o dos miembros, la referencia
        # pasa a ser el centroide del grupo MÁS CERCANO. Que una unidad no
        # encaje en ningún grupo no es motivo para dejar de medirla: es
        # exactamente lo que había que detectar.
        aislada = len(companeros) <= 2
        referencia = grupo
        if aislada and len(centroides) > 1:
            referencia = min((g for g in range(len(centroides)) if g != grupo),
                             key=lambda g: ag.distancia2(puntos[i], centroides[g]))
        centro = centroides[referencia]

        detalle = []
        for j, dim in enumerate(dimensiones):
            valor = perfiles[unidad][dim]["valor"]
            desviacion = valor - centro[j]

            # La escala que gobierna la comparación es la del valor suelto
            # (el del centroide se promedia entre los miembros del grupo y
            # casi desaparece), salvo que el grupo sea de dos, donde no
            # hay promedio que valga.
            escalas = [perfiles[unidad][dim]["escala"]]
            if aislada and len(centroides) <= 1:
                # Sin grupo vecino contra el que comparar, la referencia
                # son sus propios compañeros y su ruido también cuenta.
                escalas += [perfiles[unidades[j2]][dim]["escala"]
                            for j2 in companeros]
            escala = escala_combinada(escalas)

            p, significativa = significancia(desviacion, escala,
                                             FACTOR_CONTRA_CENTROIDE)
            umbral_por_ruido = umbral_para_confianza(
                escala, 0.95, FACTOR_CONTRA_CENTROIDE)
            hacia_peor = _peor_direccion(dim, desviacion)
            # LAS DOS PRUEBAS. Significativa dice «el ruido no explica
            # esto»; material dice «y además es una diferencia que
            # importa». Con datos masivos la primera la pasa casi todo
            # —el ruido baja a 0.04— y sin la segunda el detector devuelve
            # treinta y seis hallazgos ciertos e inservibles.
            material = abs(desviacion) >= umbrales[dim]
            detalle.append({
                "dimension_id": dim,
                "valor": round(valor, 3),
                "centroide_del_grupo": round(centro[j], 3),
                "desviacion": round(desviacion, 3),
                "escala_ruido": round(escala, 4),
                "umbral_por_ruido": round(umbral_por_ruido, 4),
                "umbral_material": round(umbrales[dim], 3),
                "p_valor": round(p, 5),
                "significativa": significativa,
                "material": material,
                "hacia_peor": hacia_peor,
                "anomala": significativa and material and hacia_peor,
            })

        anomalas = [d for d in detalle if d["anomala"]]
        salida[unidad] = {
            "grupo": grupo,
            "companeros_de_grupo": len(companeros),
            "comparada_contra": referencia,
            "aislada": aislada,
            "nota_referencia": (
                f"Su grupo tiene {len(companeros)} miembro(s), asi que se "
                f"compara contra el grupo vecino mas cercano ({referencia}). "
                f"Contra su propio centroide la desviacion seria cero: "
                f"k-medias aisla a la unidad anomala, y entonces la anomalia "
                f"se esconderia a si misma."
                if aislada else
                f"Comparada contra su propio grupo ({grupo}), que tiene "
                f"{len(companeros)} miembros."),
            "dimensiones": detalle,
            "dimensiones_anomalas": len(anomalas),
            "desviacion_peor": round(
                max((abs(d["desviacion"]) for d in anomalas), default=0.0), 3),
            "n_minimo": min(perfiles[unidad][d]["n"] for d in dimensiones),
            # El contexto del grupo va en CADA unidad y no solo en el
            # resumen del agrupamiento. Una unidad que se lee sola —y así
            # se lee, una por una, en la lista priorizada— tiene que traer
            # consigo que su segmento entero esta desplazado: es la
            # diferencia entre «esta unidad esta como sus pares» y «esta
            # unidad esta como sus pares, y sus pares estan dos puntos por
            # debajo de la organizacion».
            "contexto_de_grupo": grupos_desplazados[referencia],
        }

    info = {
        "grupos": k,
        "silueta": round(s, 4),
        "umbrales_materiales": {d: round(u, 3) for d, u in umbrales.items()},
        "mediana_de_la_organizacion": {d: round(v, 3)
                                       for d, v in referencia_org.items()},
        "centroides": [
            {"grupo": g,
             "perfil": {d: round(c[j], 3) for j, d in enumerate(dimensiones)},
             "unidades": sum(1 for a in asignacion if a == g),
             "desplazamiento": grupos_desplazados[g][
                 "dimensiones_desplazadas_hacia_peor"],
             "desplazamiento_peor": grupos_desplazados[g]["desplazamiento_peor"],
             "lectura": grupos_desplazados[g]["lectura"]}
            for g, c in enumerate(centroides)],
        "grupos_desplazados_hacia_peor": sorted(
            g for g, d in grupos_desplazados.items()
            if d["dimensiones_desplazadas_hacia_peor"]),
        "nota": "Cada unidad se compara con su grupo y no con el promedio "
                "global. Contra el promedio global, un turno nocturno "
                "apareceria como anomalia todos los semestres: tiene peor "
                "recuperacion porque trabaja de noche, no porque algo vaya "
                "mal, y la lista se llenaria de unidades que nadie puede "
                "arreglar.",
        "nota_desplazamiento":
            "Comparar dentro del grupo tiene un punto ciego: el grupo puede "
            "ser el mismo la anomalia. Se midio con cinco unidades "
            "deterioradas a proposito y k-medias las puso a las cinco en el "
            "mismo grupo, cuyo centroide estaba dos puntos por debajo del "
            "grupo sano; dentro de su grupo las cinco parecian normales. Por "
            "eso cada grupo se mide ademas contra la MEDIANA de la "
            "organizacion, y el desplazamiento se reporta aparte del desvio "
            "intra-grupo. Aparte y no sumado, porque un grupo desplazado "
            "puede ser un segmento que es asi (un turno nocturno descansa "
            "peor) o un segmento en problemas, y desde los datos las dos "
            "cosas son identicas.",
    }
    return salida, info


def _normalizar(valor, tope):
    """Lleva un valor a 0..1 recortando en el tope."""
    if tope <= 0:
        return 0.0
    return max(0.0, min(1.0, valor / tope))


def priorizar(anomalias, tendencias, dimensiones, umbrales=None):
    """Ordena las unidades por atención que merecen, con el desglose.

    El puntaje combina cuatro cosas y cada una se explica en la salida.
    Un ranking sin desglose no se puede discutir, y este se discute.
    """
    filas = []
    for unidad, datos in anomalias.items():
        anomalas = [d for d in datos["dimensiones"] if d["anomala"]]

        # 1. Magnitud: la peor desviación hacia peor, acotada a 1.5 puntos
        #    de la escala 1..5, que ya es una diferencia enorme.
        magnitud = _normalizar(datos["desviacion_peor"], 1.5)

        # 2. Tendencia: solo cuentan las que empeoran de verdad
        #    —significativas y por encima del ruido—. Una pendiente que no
        #    supera el ruido no sostiene una decisión.
        #
        #    «Empeorar» NO es «bajar»: en carga percibida, subir es
        #    empeorar y bajar es mejorar. La primera versión de esto
        #    contaba A_LA_BAJA en todas las dimensiones y además sumaba
        #    aparte las cargas al alza, así que una unidad cuya carga
        #    estaba bajando —una mejora— se contaba como si estuviera
        #    empeorando, y una que empeoraba en carga se contaba dos
        #    veces. `_peor_direccion` ya sabe qué lado es el malo de cada
        #    dimensión; se usa esa y no una lista aparte.
        #    Y además el cambio acumulado tiene que ser MATERIAL, con el
        #    mismo umbral que gobierna las anomalías. Sin esta condición
        #    el detector marcaba 19 unidades de 110 como deteriorándose
        #    cuando solo 5 lo estaban: con 110 unidades por 5 dimensiones
        #    hay 550 series, y a p<0.05 el azar solo ya produce unas 27
        #    detecciones. El filtro de ruido no las frena porque con datos
        #    masivos la escala de Laplace baja a 0.04 y cualquier deriva
        #    real la supera. La pregunta que falta es la misma de siempre:
        #    no «¿es real?», sino «¿es lo bastante grande para actuar?».
        tend = tendencias.get(unidad, {})
        dimensiones_empeorando = sorted(
            dim for dim, t in tend.items()
            if t.get("supera_el_ruido")
            and t.get("pendiente_por_campania") is not None
            and t.get("direccion") in ("A_LA_BAJA", "AL_ALZA")
            and _peor_direccion(dim, t["pendiente_por_campania"])
            and abs(t.get("recorrido_total") or 0.0) >= (umbrales or {}).get(
                dim, PISO_MATERIAL))
        empeorando = len(dimensiones_empeorando)
        puntaje_tendencia = _normalizar(empeorando, max(1, len(dimensiones)))

        # 3. Persistencia: un problema en cuatro dimensiones a la vez no es
        #    lo mismo que uno en una sola.
        persistencia = _normalizar(len(anomalas), max(1, len(dimensiones)))

        # 4. Confianza: con más respuestas detrás, la lectura es más firme.
        #    Se satura en 30: por encima de eso el ruido ya no es el
        #    problema.
        confianza = _normalizar(datos["n_minimo"], 30)

        # 5. Contexto: cuánto está desplazado su GRUPO ENTERO respecto de
        #    la organización. Sin este componente las cinco unidades
        #    deterioradas del ensayo salían INFORMATIVO, porque k-medias
        #    las había agrupado y dentro de su grupo parecían normales.
        #    Ver `desplazamiento_de_grupos`.
        contexto = datos.get("contexto_de_grupo") or {}
        desplazadas = contexto.get("dimensiones_desplazadas_hacia_peor") or []
        puntaje_contexto = _normalizar(contexto.get("desplazamiento_peor", 0.0),
                                       1.5)

        puntaje = (PESOS["anomalia"] * magnitud
                   + PESOS["tendencia"] * puntaje_tendencia
                   + PESOS["contexto"] * puntaje_contexto
                   + PESOS["persistencia"] * persistencia
                   + PESOS["confianza"] * confianza)

        # EL NIVEL SALE DE REGLAS SOBRE LOS HALLAZGOS, NO DEL PUNTAJE
        # ------------------------------------------------------------
        # El puntaje sirve para ORDENAR; para decidir el nivel es malo, y
        # se midió por qué: al ser un promedio ponderado, diluye una
        # señal fuerte y aislada. Una unidad con tres de cinco dimensiones
        # deteriorándose de forma sostenida (p≈0.000, casi un punto de
        # caída en doce campañas) y sin nada más que señalar salía con
        # 0.316, por debajo del corte de ATENCION. Es exactamente la
        # unidad donde una intervención todavía sirve.
        #
        # Subir los pesos no lo arregla: desplaza el problema a otra
        # combinación. Lo que estaba mal era usar un promedio para una
        # decisión que es una disyunción: basta UNA de varias condiciones.
        #
        # Y un nivel por reglas se puede explicar en una frase —«ATENCION
        # porque tres dimensiones vienen cayendo por encima del ruido»—
        # mientras «ATENCION porque 0.407 > 0.35» no explica nada y no se
        # puede discutir en un comité.
        if len(anomalas) >= 2 or empeorando >= 3 or (anomalas and empeorando >= 2):
            nivel = "PRIORITARIO"
        elif anomalas or empeorando >= 2 or (desplazadas and empeorando >= 1):
            nivel = "ATENCION"
        else:
            nivel = "INFORMATIVO"

        motivos = []
        if anomalas:
            peor = max(anomalas, key=lambda d: abs(d["desviacion"]))
            motivos.append(
                f"{len(anomalas)} dimension(es) fuera de lo que explica el "
                f"ruido; la peor es {peor['dimension_id']} a "
                f"{abs(peor['desviacion']):.2f} de su grupo (p={peor['p_valor']:.4f})")
        if empeorando:
            motivos.append(
                f"{empeorando} dimension(es) empeorando por encima del ruido: "
                f"{', '.join(dimensiones_empeorando)}")
        if desplazadas:
            motivos.append(
                f"su grupo completo ({contexto.get('unidades')} unidades) esta "
                f"por debajo de la mediana de la organizacion en "
                f"{len(desplazadas)} dimension(es), la peor por "
                f"{contexto.get('desplazamiento_peor')} puntos. Puede ser la "
                f"naturaleza del segmento o un problema del segmento entero: "
                f"los datos no lo distinguen")
        if not motivos:
            motivos.append("Sin anomalias ni tendencias distinguibles del azar")

        filas.append({
            "unidad_organizacional_id": unidad,
            "puntaje": round(puntaje, 4),
            "nivel": nivel,
            "grupo": datos["grupo"],
            "comparada_contra": datos.get("comparada_contra"),
            "dimensiones_anomalas": [d["dimension_id"] for d in anomalas],
            "dimensiones_empeorando": dimensiones_empeorando,
            "grupo_desplazado_en": desplazadas,
            "desplazamiento_del_grupo": contexto.get("desplazamiento_peor", 0.0),
            "n_minimo": datos["n_minimo"],
            "desglose": {
                "magnitud": round(magnitud, 4),
                "tendencia": round(puntaje_tendencia, 4),
                "contexto": round(puntaje_contexto, 4),
                "persistencia": round(persistencia, 4),
                "confianza": round(confianza, 4),
                "pesos": PESOS,
            },
            "motivos": motivos,
        })

    # El orden es por NIVEL primero y por puntaje dentro de cada nivel.
    # Ordenar solo por puntaje dejaba por encima a unidades INFORMATIVO
    # con muchas respuestas detrás —la confianza empuja el puntaje— que a
    # unidades ATENCION con un hallazgo claro, y la lista existe para
    # decir por dónde empezar.
    rango = {"PRIORITARIO": 0, "ATENCION": 1, "INFORMATIVO": 2}
    filas.sort(key=lambda f: (rango[f["nivel"]], -f["puntaje"],
                              f["unidad_organizacional_id"]))
    return filas


def hallazgos_de_segmento(info_grupos, anomalias):
    """Los hallazgos que son del GRUPO y no de ninguna unidad en concreto.

    POR QUÉ APARTE Y NO COMO NIVEL DE CADA UNIDAD
    ---------------------------------------------
    Cuando un grupo entero está desplazado, marcar a sus seis unidades
    como PRIORITARIO cada una por separado dice algo falso: que cada una
    tiene un problema propio. Lo que hay es UN hallazgo —este segmento de
    seis unidades está un punto por debajo de la organización— y seis
    unidades que lo comparten. Esa diferencia decide qué se hace: no son
    seis intervenciones de equipo, es una revisión del segmento.

    Y el hallazgo tampoco afirma que el segmento esté mal. Un turno
    nocturno descansa peor porque trabaja de noche; un segmento en crisis
    también sale desplazado. Desde los datos son indistinguibles, así que
    esto entrega la medición y nombra la pregunta que una persona tiene
    que contestar.
    """
    salida = []
    for centroide in info_grupos.get("centroides", []):
        g = centroide["grupo"]
        if not centroide.get("desplazamiento"):
            continue

        # UN SEGMENTO NECESITA UN TAMAÑO MÍNIMO
        # -------------------------------------
        # Un grupo de una o dos unidades no es un segmento de la
        # organización: es una unidad que no se parece a ninguna otra, y
        # de eso ya se encarga el camino de la unidad, que la mide contra
        # el centroide del grupo más cercano. Emitir además un «hallazgo
        # de segmento» de dos unidades diría dos veces lo mismo y
        # sugeriría revisar un segmento que no existe.
        if centroide["unidades"] < MINIMO_PARA_SEGMENTO:
            continue

        # Miembros del grupo, y PERTENECER no es lo mismo que COMPARARSE
        # CONTRA. Una unidad aislada se compara contra el centroide
        # vecino, y la primera versión de esto la contaba como miembro de
        # ese grupo vecino: un hallazgo declaraba dos unidades y listaba
        # seis. Un informe que se contradice a sí mismo no se puede usar
        # para nada.
        miembros = sorted(u for u, d in anomalias.items()
                          if d.get("grupo") == g)
        salida.append({
            "grupo": g,
            "unidades": centroide["unidades"],
            "unidades_del_grupo": miembros,
            "perfil_del_grupo": centroide["perfil"],
            "dimensiones_desplazadas": centroide["desplazamiento"],
            "desplazamiento_peor": centroide["desplazamiento_peor"],
            "lectura": centroide["lectura"],
            "accion_sugerida":
                "Revisar el segmento completo antes que sus unidades una por "
                "una. Si el desplazamiento es la naturaleza del segmento "
                "—trabajo nocturno, operacion de campo— lo que corresponde es "
                "ajustar con que se le compara, no intervenirlo. Si no lo es, "
                "es un hallazgo sistemico y la intervencion es del segmento.",
            "pregunta_para_la_persona":
                f"¿Las {centroide['unidades']} unidades de este grupo "
                f"comparten una condicion de trabajo que explique estar por "
                f"debajo en {', '.join(centroide['desplazamiento'])}?",
        })
    salida.sort(key=lambda h: -h["desplazamiento_peor"])
    return salida


def analizar(filas_campania, series_por_unidad, semilla=ag.SEMILLA):
    """Punto de entrada. Devuelve el informe completo.

    `filas_campania`: valores publicados de la campaña a analizar.
    `series_por_unidad`: {unidad: {dimension: [(secuencia, valor, escala)]}}
    """
    inicio = time.perf_counter()

    perfiles, incompletas, dimensiones = construir_perfiles(filas_campania)
    anomalias, info_grupos = detectar_anomalias(perfiles, dimensiones, semilla)

    tendencias = {}
    for unidad, series in series_por_unidad.items():
        tendencias[unidad] = {dim: td.analizar(puntos)
                              for dim, puntos in series.items()}

    priorizadas = priorizar(anomalias, tendencias, dimensiones,
                            info_grupos.get("umbrales_materiales"))
    segmentos = hallazgos_de_segmento(info_grupos, anomalias)
    ms = (time.perf_counter() - inicio) * 1000

    return {
        "unidades_analizadas": len(perfiles),
        "unidades_sin_perfil_completo": [
            {"unidad_organizacional_id": u, "dimensiones_suprimidas": d}
            for u, d in sorted(incompletas.items())],
        "dimensiones": dimensiones,
        "agrupamiento": info_grupos,
        "priorizadas": priorizadas,
        "hallazgos_de_segmento": segmentos,
        "tendencias": tendencias,
        "epsilon_consumido": 0.0,
        "tiempo_ms": round(ms, 2),
        "nota_epsilon":
            "Cero. Todo lo que se analiza son resultados YA PUBLICADOS, que "
            "ya descontaron su epsilon al calcularse. Si el motor llamara a "
            "la funcion de calculo, analizar gastaria privacidad y al "
            "agotarla dejaria a la campania sin poder publicar.",
        "nota_causa":
            "El motor detecta que una unidad esta lejos de sus pares o que "
            "viene cayendo. NO dice por que. La causa la averigua una "
            "persona hablando con el area: un sistema que la afirmara "
            "estaria inventando, y sobre eso se decidirian intervenciones "
            "sobre equipos de gente.",
        "unidades_excluidas_nota":
            "Las unidades sin perfil completo quedan fuera del agrupamiento "
            "y se listan aparte. Rellenar sus huecos con la media del grupo "
            "las describiria con numeros que nadie midio.",
    }
