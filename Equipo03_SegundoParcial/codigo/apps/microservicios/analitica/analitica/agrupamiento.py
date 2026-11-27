"""
Agrupamiento de unidades por perfil de bienestar (k-medias con k-means++).

POR QUÉ AGRUPAR ANTES DE BUSCAR ANOMALÍAS
------------------------------------------
Lo intuitivo sería comparar cada unidad contra el promedio de toda la
organización. Está mal, y el motivo es del problema y no del método: un
turno nocturno de centro de contacto y un área de oficina **no son
comparables**. El turno nocturno tendrá peor recuperación siempre, no
porque algo vaya mal sino porque trabaja de noche. Contra el promedio
global aparecería como anomalía todos los semestres, y la lista de
«unidades en riesgo» se llenaría de turnos nocturnos que nadie puede
arreglar.

Agrupando primero, cada unidad se compara contra las que se le parecen, y
lo que sale es lo que de verdad llama la atención: el turno nocturno que
está peor **que los otros turnos nocturnos**.

POR QUÉ K-MEDIAS Y NO ALGO MÁS ELABORADO
-----------------------------------------
El espacio son cinco dimensiones acotadas a 1..5 y las unidades son
decenas o cientos, no millones. En ese tamaño, k-medias con una
inicialización decente converge en pocas iteraciones y el resultado se
puede explicar: cada grupo tiene un centroide que es un perfil de
bienestar legible («carga alta, apoyo bajo»). Un método que produjera
grupos mejores pero inexplicables no serviría aquí, porque el resultado
se discute en un comité y hay que poder decir por qué una unidad quedó
donde quedó.

LA INICIALIZACIÓN IMPORTA MÁS QUE EL ALGORITMO
-----------------------------------------------
K-medias con centroides al azar cae en óptimos locales malos, y con
datos reales eso se ve como grupos que cambian de una corrida a otra. Se
usa k-means++ —cada centroide inicial se elige con probabilidad
proporcional al cuadrado de la distancia al centroide más cercano ya
elegido— que acota el error esperado y, en la práctica, hace que corridas
distintas den el mismo resultado.

COMPLEJIDAD
-----------
    k-means++ inicial   O(n · k · d)
    cada iteración      O(n · k · d)
    total               O(n · k · i · d)

con n unidades, k grupos, i iteraciones (tope `MAXIMO_ITERACIONES`) y
d = 5 dimensiones. La selección de k prueba `K_CANDIDATOS` valores, así
que multiplica por esa constante. Memoria: O(n · d + k · d).
"""
import math
import random

MAXIMO_ITERACIONES = 100
TOLERANCIA = 1e-6
# Semilla fija por omisión. El agrupamiento alimenta decisiones sobre
# equipos de personas, y un resultado que cambia entre corridas sin que
# cambien los datos es indefendible ante quien pregunta por qué su área
# salió en la lista este semestre y no el pasado.
SEMILLA = 20260101


def distancia2(a, b):
    """Distancia euclidiana al cuadrado. Sin raíz: no hace falta.

    Comparar distancias al cuadrado ordena igual que compararlas, y
    ahorra una raíz por cada par en el bucle más caliente del algoritmo.
    """
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _siembra(puntos, k, aleatorio):
    """k-means++: centroides iniciales separados entre sí.

    El primero al azar; cada siguiente con probabilidad proporcional a
    D(x)², la distancia al centroide más cercano ya elegido. Es lo que
    evita que dos centroides nazcan dentro del mismo grupo natural y
    dejen otro grupo sin representante.
    """
    centroides = [list(aleatorio.choice(puntos))]
    while len(centroides) < k:
        pesos = [min(distancia2(p, c) for c in centroides) for p in puntos]
        total = sum(pesos)
        if total <= 0:
            # Todos los puntos restantes coinciden con algún centroide.
            # Repetir uno sería crear un grupo vacío, así que se corta y
            # se devuelven los que hay: pedir más grupos que puntos
            # distintos no tiene respuesta, y fingir que sí la tiene
            # produciría grupos fantasma en el informe.
            break
        objetivo = aleatorio.random() * total
        acumulado = 0.0
        for punto, peso in zip(puntos, pesos):
            acumulado += peso
            if acumulado >= objetivo:
                centroides.append(list(punto))
                break
    return centroides


def _asignar(puntos, centroides):
    return [min(range(len(centroides)),
                key=lambda i: distancia2(p, centroides[i]))
            for p in puntos]


def _recalcular(puntos, asignacion, k, centroides_previos):
    nuevos = []
    for grupo in range(k):
        miembros = [p for p, g in zip(puntos, asignacion) if g == grupo]
        if not miembros:
            # Un grupo que se queda sin miembros conserva su centroide en
            # lugar de desaparecer. Quitarlo renumeraría los grupos a
            # media corrida y las etiquetas dejarían de significar lo
            # mismo entre iteraciones.
            nuevos.append(list(centroides_previos[grupo]))
            continue
        nuevos.append([sum(valores) / len(miembros)
                       for valores in zip(*miembros)])
    return nuevos


def kmedias(puntos, k, semilla=SEMILLA):
    """Agrupa los puntos en k grupos. Devuelve (asignacion, centroides).

    Para por convergencia —ningún centroide se mueve más que TOLERANCIA—
    y no por agotar las iteraciones. El tope existe solo para que un caso
    patológico no deje el proceso girando.
    """
    if not puntos:
        return [], []
    k = max(1, min(int(k), len(puntos)))
    aleatorio = random.Random(semilla)

    centroides = _siembra(puntos, k, aleatorio)
    k = len(centroides)
    asignacion = _asignar(puntos, centroides)

    for _ in range(MAXIMO_ITERACIONES):
        nuevos = _recalcular(puntos, asignacion, k, centroides)
        movimiento = max(distancia2(a, b) for a, b in zip(centroides, nuevos))
        centroides = nuevos
        asignacion = _asignar(puntos, centroides)
        if movimiento < TOLERANCIA:
            break
    return asignacion, centroides


def silueta(puntos, asignacion, centroides):
    """Qué tan bien separados quedaron los grupos, entre -1 y 1.

    Para cada punto: a = distancia media a los de su grupo, b = distancia
    media al grupo vecino más cercano, y su silueta es (b - a) /
    max(a, b). Cerca de 1 el punto está cómodo donde está; cerca de 0 está
    en la frontera; negativo, estaría mejor en otro grupo.

    Se usa para ELEGIR k, que es la decisión que k-medias no toma por sí
    solo. Sin esto habría que fijar el número de grupos a mano, y ese
    número cambia con la organización: una empresa con tres áreas y otra
    con cuarenta no se describen con el mismo k.
    """
    if len(set(asignacion)) < 2:
        return 0.0
    total = 0.0
    for i, punto in enumerate(puntos):
        propio = asignacion[i]
        companeros = [p for j, p in enumerate(puntos)
                      if asignacion[j] == propio and j != i]
        if not companeros:
            continue                     # un grupo de uno no tiene silueta
        a = sum(math.sqrt(distancia2(punto, c)) for c in companeros) / len(companeros)

        bs = []
        for grupo in set(asignacion):
            if grupo == propio:
                continue
            otros = [p for j, p in enumerate(puntos) if asignacion[j] == grupo]
            if otros:
                bs.append(sum(math.sqrt(distancia2(punto, o)) for o in otros)
                          / len(otros))
        if not bs:
            continue
        b = min(bs)
        total += (b - a) / max(a, b) if max(a, b) > 0 else 0.0
    return total / len(puntos)


def elegir_k(puntos, candidatos=(2, 3, 4, 5, 6), semilla=SEMILLA):
    """El k con mejor silueta. Devuelve (k, asignacion, centroides, silueta).

    Se prueban varios y gana el de grupos más separados. No se usa el
    método del codo porque exige que una persona mire una gráfica y
    decida; esto corre sin nadie delante, en un servicio.
    """
    if len(puntos) < 3:
        # Con uno o dos puntos no hay agrupamiento que valga: todos a un
        # grupo. Forzar k=2 con dos puntos daría dos grupos de uno y una
        # silueta sin sentido.
        return 1, [0] * len(puntos), ([list(puntos[0])] if puntos else []), 0.0

    mejor = None
    for k in candidatos:
        if k >= len(puntos):
            break
        asignacion, centroides = kmedias(puntos, k, semilla)
        if len(set(asignacion)) < 2:
            continue
        s = silueta(puntos, asignacion, centroides)
        if mejor is None or s > mejor[3]:
            mejor = (k, asignacion, centroides, s)

    if mejor is None:
        return 1, [0] * len(puntos), [list(puntos[0])], 0.0
    return mejor
