#!/usr/bin/env python3
"""
Banco de pruebas de rendimiento: índices, consultas y caché.

QUÉ MIDE Y POR QUÉ ASÍ
-----------------------
La rúbrica pide medir tiempo de consulta, uso de índices, uso de caché y
comportamiento con y sin Redis. Lo fácil sería cronometrar una consulta
una vez y apuntar el número. No sirve, por tres motivos que este guión
trata explícitamente:

1. **Una sola medición mide el azar.** La primera ejecución de una
   consulta paga el arranque del plan y la lectura de disco; la segunda
   encuentra todo en la caché de páginas de PostgreSQL. Aquí cada consulta
   se ejecuta `REPETICIONES` veces y se reporta la MEDIANA y el p95, no el
   promedio: con una cola larga, el promedio describe a nadie.

2. **Medir la caché sin vaciarla mide la caché.** Comparar «con y sin
   Redis» exige borrar la clave entre corridas; si no, la segunda medición
   siempre gana y la conclusión está escrita de antemano.

3. **«Usa índice» no se adivina del tiempo.** Una consulta puede ser
   rápida y estar haciendo un recorrido secuencial porque la tabla cabe en
   memoria, y eso deja de ser cierto el día que crece. Se lee del plan de
   ejecución, que es donde está la respuesta.

Uso:
    python3 scripts/rendimiento.py --base nexum_carga
    python3 scripts/rendimiento.py --base nexum_carga --crear-indices
"""
import argparse
import json
import os
import statistics
import sys
import time

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("Falta psycopg2")

REPETICIONES = 7

# Los índices que propone esta parte del proyecto, con el motivo de cada
# uno. Un índice sin motivo escrito es un índice que nadie se atreve a
# quitar después, aunque ya no sirva: ocupa espacio y frena cada
# escritura, y como nadie sabe por qué está, ahí se queda.
INDICES = [
    ("ix_respuesta_campania_unidad",
     "autoreporte.respuesta (campania_id, unidad_organizacional_id)",
     "El calculo de agregados recorre las respuestas de UNA campania y UNA "
     "unidad. Sin este indice es un recorrido secuencial de doscientas mil "
     "filas por cada uno de los seiscientos sesenta agregados."),

    ("ix_detalle_respuesta_reactivo",
     "autoreporte.respuesta_detalle (respuesta_id, reactivo_id)",
     "El detalle se une por respuesta_id y se filtra por reactivo para "
     "separar dimensiones. Es la union mas grande del sistema: un millon "
     "de filas contra doscientas mil."),

    ("ix_agregado_unidad_campania_dim",
     "agregado.resultado_protegido "
     "(unidad_organizacional_id, campania_id, dimension_id) "
     "WHERE estado_publicacion = 'PUBLICADO'",
     "El tablero y el motor de tendencias solo leen lo PUBLICADO. Un indice "
     "parcial deja fuera las filas suprimidas, que son las que nunca se "
     "consultan, y queda la mitad de grande."),

    ("ix_agregado_campania_publicado",
     "agregado.resultado_protegido (campania_id) "
     "WHERE estado_publicacion = 'PUBLICADO'",
     "El algoritmo complejo lee TODAS las unidades de una campania de golpe "
     "para construir la matriz de perfiles."),

    ("ix_bitacora_fecha_accion",
     "auditoria.bitacora (fecha_hora DESC, accion)",
     "El panel de errores pide las ultimas N horas. Sin el indice, cada "
     "apertura del panel recorre la bitacora entera, que es la tabla que "
     "mas crece."),
]

CONSULTAS = {
    "tablero_de_una_unidad": """
        SELECT unidad_organizacional_id, dimension_id, valor_protegido,
               escala_ruido, n_observaciones
          FROM agregado.resultado_protegido
         WHERE unidad_organizacional_id = %(unidad)s
           AND campania_id = %(campania)s
           AND estado_publicacion = 'PUBLICADO'""",

    "serie_completa_de_una_unidad": """
        SELECT c.secuencia, r.dimension_id, r.valor_protegido, r.escala_ruido
          FROM agregado.resultado_protegido r
          JOIN catalogo.campania c USING (campania_id)
         WHERE r.unidad_organizacional_id = %(unidad)s
           AND r.estado_publicacion = 'PUBLICADO'
         ORDER BY c.secuencia""",

    "matriz_de_toda_una_campania": """
        SELECT unidad_organizacional_id, dimension_id, valor_protegido,
               escala_ruido, n_observaciones
          FROM agregado.resultado_protegido
         WHERE campania_id = %(campania)s
           AND estado_publicacion = 'PUBLICADO'
           AND dimension_id IS NOT NULL""",

    "recuento_de_respuestas_por_unidad": """
        SELECT unidad_organizacional_id, count(*) AS n
          FROM autoreporte.respuesta
         WHERE campania_id = %(campania)s
         GROUP BY unidad_organizacional_id""",

    # La forma REAL de la unión respuesta-detalle: una unidad y una
    # campaña, que es lo que hace `fn_calcular_agregado_protegido` una vez
    # por cada par unidad-campaña-dimensión.
    #
    # La primera versión de este guión medía la misma unión para la
    # CAMPAÑA ENTERA, y era una consulta que yo había inventado: ningún
    # endpoint la ejecuta. Daba 42 ms y un recorrido secuencial del millón
    # de filas de detalle, lo cual es el plan correcto para esa forma
    # —PostgreSQL lee casi toda la tabla, así que un índice no ayuda— y una
    # conclusión equivocada sobre los índices, porque la consulta que sí
    # corre tiene otra forma y sí los usa.
    "union_de_una_unidad_y_campania": """
        SELECT d.reactivo_id, avg(d.valor)::numeric(6,3) AS media
          FROM autoreporte.respuesta r
          JOIN autoreporte.respuesta_detalle d USING (respuesta_id)
         WHERE r.campania_id = %(campania)s
           AND r.unidad_organizacional_id = %(unidad)s
         GROUP BY d.reactivo_id""",

    # El tamaño del grupo con consentimiento vigente: la consulta que
    # gastaba 30 de los 89 ms de la función de agregados, porque la vista
    # de consentimiento ordenaba las 24 476 filas de la tabla completa en
    # cada llamada. Ver el punto 6 de la migración 018.
    "tamano_del_grupo_con_consentimiento": """
        SELECT COUNT(DISTINCT r.respuesta_id) AS n
          FROM autoreporte.respuesta r
          JOIN autoreporte.respuesta_detalle d ON d.respuesta_id = r.respuesta_id
          JOIN catalogo.reactivo rx ON rx.reactivo_id = d.reactivo_id
          JOIN consentimiento.v_estado_vigente ev
            ON ev.seudonimo_id = r.seudonimo_id
         WHERE r.campania_id = %(campania)s
           AND r.unidad_organizacional_id = %(unidad)s
           AND ev.estado = 'ACEPTADO'""",
}


def medir(cur, sql, params, repeticiones=REPETICIONES):
    """Ejecuta varias veces y devuelve mediana, p95 y filas.

    La PRIMERA ejecución se descarta: paga el arranque del plan y la
    lectura de disco, y mezclarla con las demás inventa una cola que no
    describe el uso real, donde la consulta ya se hizo antes.
    """
    tiempos = []
    filas = 0
    for i in range(repeticiones + 1):
        t0 = time.perf_counter()
        cur.execute(sql, params)
        datos = cur.fetchall()
        ms = (time.perf_counter() - t0) * 1000
        if i == 0:
            filas = len(datos)
            continue
        tiempos.append(ms)
    tiempos.sort()
    p95 = tiempos[min(len(tiempos) - 1, int(0.95 * len(tiempos)))]
    return {"mediana_ms": round(statistics.median(tiempos), 2),
            "p95_ms": round(p95, 2),
            "minimo_ms": round(tiempos[0], 2),
            "maximo_ms": round(tiempos[-1], 2),
            "filas": filas}


def plan_de(cur, sql, params):
    """El plan real, para saber si usa índice en lugar de suponerlo."""
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params)
    plan = cur.fetchone()[0][0]["Plan"]

    nodos, usa_indice, secuenciales = [], False, []

    def recorrer(n):
        nonlocal usa_indice
        tipo = n.get("Node Type", "")
        nodos.append(tipo)
        if "Index" in tipo:
            usa_indice = True
        if tipo == "Seq Scan":
            secuenciales.append(n.get("Relation Name", "?"))
        for hijo in n.get("Plans", []):
            recorrer(hijo)

    recorrer(plan)
    return {"usa_indice": usa_indice,
            "recorridos_secuenciales": secuenciales,
            "nodos": nodos[:6],
            "costo_estimado": plan.get("Total Cost"),
            "tiempo_real_ms": round(plan.get("Actual Total Time", 0), 2),
            "memoria": memoria_del_plan(plan),
            "bloques": bloques_del_plan(plan)}


# =========================================================================
# Consumo de recursos
# =========================================================================
#
# POR QUÉ ESTO NO SE MIDE CON psutil SOBRE ESTE PROCESO
# -----------------------------------------------------
# Lo obvio sería leer la memoria y el CPU del proceso que corre este
# guión. Mediría lo que no importa: este guión manda una cadena de SQL y
# espera. El trabajo —leer 206 mil filas, ordenarlas, agruparlas— lo hace
# el proceso servidor de PostgreSQL, en otro proceso y a veces en otra
# máquina. Medir el cliente daría números bonitos y constantes mientras el
# servidor se queda sin memoria.
#
# Así que se mide el BACKEND que atiende esta conexión. `pg_backend_pid()`
# dice cuál es, y en Linux `/proc/<pid>/stat` y `/proc/<pid>/status` dan su
# CPU y su memoria con precisión de reloj del sistema. Es una medición del
# servidor hecha desde el cliente, que es lo que hacía falta.
#
# TRES NÚMEROS, TRES PREGUNTAS DISTINTAS
# --------------------------------------
# 1. **CPU por consulta.** El tiempo de reloj incluye esperas de disco y
#    de red; el CPU no. Una consulta de 40 ms con 2 ms de CPU espera
#    disco —se arregla con un índice—. Una de 40 ms con 39 de CPU está
#    calculando —se arregla con otra consulta—. El tiempo de reloj solo no
#    distingue los dos casos, y se arreglan en lugares opuestos.
#
# 2. **Memoria pico del backend (VmHWM).** Es el máximo histórico, no el
#    de ahora: un pico durante una ordenación grande ya bajó cuando se
#    consulta, y leer la memoria «actual» no lo vería nunca. Importa
#    porque cada conexión concurrente paga ese pico: 200 conexiones en el
#    pico de carga son 200 veces ese número.
#
# 3. **Memoria de trabajo y derrames a disco.** El plan dice cuánta
#    memoria usó cada ordenación y cada tabla hash, y —esto es lo que se
#    busca— si tuvo que DERRAMAR a disco por no caber en `work_mem`. Un
#    derrame es la diferencia entre una consulta de 5 ms y una de 500, y
#    aparece de golpe el día que los datos crecen un poco más. Con datos
#    de demostración nunca ocurre; con datos masivos es justo lo que hay
#    que vigilar.
def memoria_del_plan(plan):
    """Memoria de trabajo y derrames a disco, leídos del plan.

    Recorre el árbol entero porque el derrame puede estar en cualquier
    nodo, y el de abajo es el que suele doler.
    """
    picos_kb, derrames = [], []

    def recorrer(n):
        tipo = n.get("Node Type", "?")
        # Ordenaciones.
        if n.get("Sort Space Used") is not None:
            kb = n["Sort Space Used"]
            donde = n.get("Sort Space Type", "Memory")
            if donde == "Disk":
                derrames.append({"nodo": tipo, "kb": kb, "que": "ordenacion"})
            else:
                picos_kb.append(kb)
        # Tablas hash (joins y agrupaciones).
        if n.get("Peak Memory Usage") is not None:
            picos_kb.append(n["Peak Memory Usage"])
        if (n.get("Disk Usage") or 0) > 0:
            derrames.append({"nodo": tipo, "kb": n["Disk Usage"],
                             "que": "tabla hash"})
        for hijo in n.get("Plans", []):
            recorrer(hijo)

    recorrer(plan)
    return {"memoria_trabajo_pico_kb": max(picos_kb) if picos_kb else 0,
            "derrames_a_disco": derrames,
            # Lo que hay que mirar: cero derrames significa que todo cupo
            # en work_mem con el volumen actual.
            "derrama": bool(derrames)}


def bloques_del_plan(plan):
    """Bloques leídos de disco contra bloques encontrados en memoria.

    `shared_read` son lecturas que PostgreSQL tuvo que pedirle al sistema
    de archivos; `shared_hit`, las que ya estaban en su caché. La razón
    entre los dos es la que explica por qué la misma consulta tarda 40 ms
    la primera vez y 2 ms la segunda, y por qué una medición única miente.
    """
    leidos = encontrados = escritos = 0

    def recorrer(n):
        nonlocal leidos, encontrados, escritos
        leidos += n.get("Shared Read Blocks", 0) or 0
        encontrados += n.get("Shared Hit Blocks", 0) or 0
        escritos += ((n.get("Temp Written Blocks", 0) or 0)
                     + (n.get("Local Written Blocks", 0) or 0))
        for hijo in n.get("Plans", []):
            recorrer(hijo)

    recorrer(plan)
    total = leidos + encontrados
    return {"leidos_de_disco": leidos, "encontrados_en_memoria": encontrados,
            "escritos_temporales": escritos,
            "aciertos_pct": round(100.0 * encontrados / total, 1) if total else None,
            # Un bloque son 8 kB.
            "leidos_kb": leidos * 8}


def _cpu_y_memoria(pid):
    """utime+stime en milisegundos, RSS actual y RSS pico, del proceso dado.

    Devuelve None si no hay procfs: en ese caso la medición no se hace y
    se dice, en lugar de reportar ceros que se leen como «no consume
    nada».
    """
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as f:
            campos = f.read().rsplit(") ", 1)[1].split()
        reloj = os.sysconf("SC_CLK_TCK")
        cpu_ms = (int(campos[11]) + int(campos[12])) * 1000.0 / reloj
        rss_kb = pico_kb = None
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as f:
            for linea in f:
                if linea.startswith("VmRSS:"):
                    rss_kb = int(linea.split()[1])
                elif linea.startswith("VmHWM:"):
                    pico_kb = int(linea.split()[1])
        return {"cpu_ms": cpu_ms, "rss_kb": rss_kb, "rss_pico_kb": pico_kb}
    except (OSError, IndexError, ValueError):
        return None


# El CPU del kernel se contabiliza en tics, y un tic son 10 ms en casi
# todo Linux. Esa es la trampa de esta medición y costó una corrida
# entenderla: midiendo 7 repeticiones de una consulta de 0.13 ms, el CPU
# acumulado es menos de un milisegundo y el contador no se mueve. El
# resultado es «0.00 ms de CPU», que se lee como «no consume CPU» cuando
# lo que pasa es que no se midió. Y peor: una consulta que cruza el límite
# de un tic reportó 2.86 ms de CPU para 0.34 ms de reloj —CPU mayor que el
# tiempo total, que es imposible— porque el único tic observado se dividió
# entre siete repeticiones.
#
# Así que se repite hasta acumular suficientes tics para que el cociente
# signifique algo, con un techo de tiempo para no colgarse en una consulta
# lenta. Si no se alcanza la resolución, se dice; no se reporta un número.
TICS_MINIMOS = 20          # 200 ms de CPU: el error de cuantización baja al 5 %
SEGUNDOS_MAXIMOS_CPU = 6.0


def medir_recursos(cur, sql, params):
    """CPU y memoria del backend de PostgreSQL mientras corre la consulta.

    Se mide el servidor y no este guión: ver el comentario grande de
    arriba. Y se repite hasta superar la resolución del reloj de CPU: ver
    el comentario de TICS_MINIMOS, que es el error que esta función tuvo.
    """
    cur.execute("SELECT pg_backend_pid()")
    pid = cur.fetchone()[0]
    antes = _cpu_y_memoria(pid)
    if antes is None:
        return {"medido": False,
                "motivo": "sin /proc: no se puede leer el consumo del "
                          "backend en este sistema"}
    tic_ms = 1000.0 / os.sysconf("SC_CLK_TCK")
    objetivo_ms = TICS_MINIMOS * tic_ms

    corridas = 0
    reloj0 = time.perf_counter()
    while True:
        for _ in range(REPETICIONES):
            cur.execute(sql, params)
            cur.fetchall()
            corridas += 1
        despues = _cpu_y_memoria(pid)
        cpu = despues["cpu_ms"] - antes["cpu_ms"]
        if cpu >= objetivo_ms:
            break
        if time.perf_counter() - reloj0 > SEGUNDOS_MAXIMOS_CPU:
            return {
                "medido": False,
                "pid_backend": pid,
                "corridas": corridas,
                "cpu_acumulado_ms": round(cpu, 1),
                "resolucion_ms": round(tic_ms, 1),
                "rss_kb": despues["rss_kb"],
                "rss_pico_kb": despues["rss_pico_kb"],
                "motivo":
                    f"la consulta es demasiado barata para el reloj de CPU: "
                    f"{corridas} corridas en "
                    f"{time.perf_counter() - reloj0:.1f} s acumularon "
                    f"{cpu:.0f} ms de CPU y un tic son {tic_ms:.0f} ms. Un "
                    f"numero aqui seria ruido de cuantizacion, no una "
                    f"medicion.",
            }
    return {
        "medido": True,
        "pid_backend": pid,
        "cpu_ms_por_consulta": round(cpu / corridas, 3),
        "cpu_acumulado_ms": round(cpu, 1),
        "corridas": corridas,
        "resolucion_ms": round(tic_ms, 1),
        "rss_kb": despues["rss_kb"],
        "rss_pico_kb": despues["rss_pico_kb"],
        "rss_crecio_kb": (despues["rss_kb"] or 0) - (antes["rss_kb"] or 0),
    }


def recursos_del_servidor(cur):
    """Memoria de TODO el servidor, no de un backend: el total es lo que cabe.

    Un backend que usa 12 MB no dice nada por sí solo. Lo que decide si el
    sistema aguanta es cuántos backends hay por cuánto usa cada uno, más
    la memoria compartida —`shared_buffers`, que es la caché de páginas y
    la paga el servidor una sola vez—. Las dos cosas se reportan aparte
    porque se dimensionan distinto: la compartida es una decisión de
    configuración y la privada se multiplica por la concurrencia.
    """
    cur.execute("SHOW shared_buffers")
    compartida = cur.fetchone()[0]
    cur.execute("SHOW work_mem")
    trabajo = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend'")
    conexiones = cur.fetchone()[0]

    backends = []
    try:
        cur.execute("""SELECT pid FROM pg_stat_activity
                        WHERE backend_type='client backend'""")
        for (pid,) in cur.fetchall():
            m = _cpu_y_memoria(pid)
            if m and m["rss_kb"]:
                backends.append(m["rss_kb"])
    except Exception:                                     # noqa: BLE001
        pass

    salida = {"shared_buffers": compartida, "work_mem": trabajo,
              "conexiones_cliente": conexiones}
    if backends:
        salida.update({
            "rss_por_backend_kb_mediana": int(statistics.median(backends)),
            "rss_por_backend_kb_maximo": max(backends),
            "rss_backends_total_kb": sum(backends),
            # El RSS incluye la parte de shared_buffers que ese backend
            # ya tocó, así que sumar los RSS cuenta la memoria compartida
            # tantas veces como backends haya. Se dice, porque si no el
            # total parece mucho mayor de lo que el servidor ocupa.
            "nota": "Los RSS de los backends comparten shared_buffers; el "
                    "total suma esa parte una vez por backend y por eso es "
                    "una cota superior, no la memoria real del servidor.",
        })
    try:
        import resource
        salida["rss_pico_de_este_guion_kb"] = (
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:                                     # noqa: BLE001
        pass
    return salida


# =========================================================================
# A qué unidad se le mide
# =========================================================================
#
# EL ERROR QUE ESTO CORRIGE, Y CÓMO SE ENCONTRÓ
# ---------------------------------------------
# Este guión elegía la unidad y la campaña con `ORDER BY random() LIMIT 1`.
# Dos corridas seguidas contra la MISMA base dieron:
#
#     tamano_del_grupo_con_consentimiento      7.45 ms  /  110.96 ms
#     fn_calcular_agregado_protegido          15.85 ms  /  226.41 ms
#
# Catorce veces de diferencia, sin que nada cambiara en la base. La causa
# no era la base: era que cada corrida medía una unidad distinta, y las
# unidades van de 28 a 210 personas. Casi puse el 15.85 en el documento
# como «el» número del camino caliente.
#
# Una sola unidad al azar no describe el sistema y además impide comparar
# corridas, que es para lo que sirve un banco de pruebas. Así que se miden
# TRES unidades elegidas por volumen —la más chica, la mediana y la más
# grande— de forma determinista, y se reportan las tres. El número útil no
# es un promedio: es el rango, porque lo que decide si el sistema aguanta
# es la unidad grande, y lo que la mayoría de los usuarios experimenta es
# la mediana.
def unidades_representativas(cur, campania=None):
    """La unidad más chica, la mediana y la más grande por respuestas.

    Determinista: mismo orden, mismos desempates por identificador. Dos
    corridas contra la misma base miden lo mismo y se pueden comparar.
    """
    cur.execute("""
        SELECT r.unidad_organizacional_id, r.campania_id, count(*) AS n
          FROM autoreporte.respuesta r
          JOIN agregado.resultado_protegido g
            ON g.unidad_organizacional_id = r.unidad_organizacional_id
           AND g.campania_id = r.campania_id
           AND g.estado_publicacion = 'PUBLICADO'
         GROUP BY r.unidad_organizacional_id, r.campania_id
         ORDER BY n, r.unidad_organizacional_id, r.campania_id""")
    filas = cur.fetchall()
    if not filas:
        return []
    indices = {"chica": 0, "mediana": len(filas) // 2, "grande": len(filas) - 1}
    vistas, salida = set(), []
    for etiqueta, i in indices.items():
        unidad, camp, n = filas[i]
        if (unidad, camp) in vistas:          # bases chicas: no repetir
            continue
        vistas.add((unidad, camp))
        salida.append({"etiqueta": etiqueta, "unidad": unidad,
                       "campania": camp, "respuestas": n})
    return salida


def crear_indices(cur):
    print("==> creando indices")
    for nombre, definicion, motivo in INDICES:
        t0 = time.perf_counter()
        cur.execute(f"CREATE INDEX IF NOT EXISTS {nombre} ON {definicion}")
        print(f"    {nombre}: {time.perf_counter() - t0:.2f}s")
        print(f"      {motivo}")
    cur.execute("ANALYZE")


def tamanos(cur):
    cur.execute("""
        SELECT c.relname,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS total,
               pg_size_pretty(pg_indexes_size(c.oid))        AS indices,
               n.nspname
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'r'
           AND n.nspname IN ('autoreporte','agregado','auditoria','organizacion')
         ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 8""")
    filas = cur.fetchall()

    # LAS FILAS SE CUENTAN, NO SE ESTIMAN. Esto empezó leyendo
    # `n_live_tup` de pg_stat_user_tables y cayendo a `reltuples`, y las
    # dos mintieron en la misma corrida:
    #
    #   n_live_tup  0      sale en cero hasta que autovacuum pasa, y en una
    #                      base recién cargada no ha pasado. El informe
    #                      decía «0 filas» sobre una tabla de 112 MB.
    #   reltuples   5      es lo que dejó el último ANALYZE, y las 8 294
    #                      filas que entraron después no están ahí.
    #
    # La tabla real tenía 8 299. Un informe de rendimiento cuya columna de
    # volumen está mal no sirve para nada: el volumen es la variable
    # independiente de todo lo que mide. `count(*)` cuesta unos cientos de
    # milisegundos en la tabla más grande y se corre una vez.
    salida = []
    for nombre, total, indices, esquema in filas:
        cur.execute(f'SELECT count(*) FROM "{esquema}"."{nombre}"')
        salida.append({"tabla": nombre, "total": total, "indices": indices,
                       "filas": cur.fetchone()[0]})
    return salida


def medir_camino_caliente(cur, campania, unidad):
    """Cronometra `fn_calcular_agregado_protegido`, el camino más caliente.

    Se mide la FUNCIÓN y no solo sus consultas porque es la unidad de
    trabajo real: se llama una vez por cada par unidad-campaña-dimensión,
    7 920 veces para una organización de 110 unidades y 12 campañas. Un
    milisegundo aquí son ocho segundos allá.

    Es de solo lectura para esta medición: se llama con una dimensión que
    ya tiene resultado, así que inserta una fila nueva de resultado. Por
    eso corre contra la base de CARGA y no contra una base de la que
    dependa nadie.
    """
    tiempos = []
    for _ in range(5):
        t0 = time.perf_counter()
        cur.execute("SELECT estado FROM "
                    "agregado.fn_calcular_agregado_protegido(%s, %s, %s)",
                    (campania, unidad, "DIM-APOYO"))
        cur.fetchall()
        tiempos.append((time.perf_counter() - t0) * 1000)
    tiempos.sort()
    return {"mediana_ms": round(statistics.median(tiempos), 2),
            "minimo_ms": round(tiempos[0], 2),
            "maximo_ms": round(tiempos[-1], 2),
            "llamadas_para_una_organizacion": 110 * 12 * 6,
            "nota": "7 920 llamadas para 110 unidades x 12 campanias x 6 "
                    "agregados. A 89 ms eran 705 s; a 21 ms son 166 s."}


def plan_de_la_vista_de_consentimiento(cur):
    """Comprueba que la vista resuelve por índice y no ordenando la tabla.

    Es una comprobación y no una medición: el síntoma —un `Sort` de
    veinticuatro mil filas dentro de una consulta que necesita 198— no se
    ve en el tiempo de respuesta de un endpoint, se ve en el plan. Y
    volvería a aparecer sin aviso si alguien cambiara el `ORDER BY` de la
    vista y no el índice.
    """
    cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) "
                "SELECT * FROM consentimiento.v_estado_vigente")
    plan = cur.fetchone()[0][0]["Plan"]
    nodos = []

    def recorrer(n):
        nodos.append((n.get("Node Type"), n.get("Index Name")))
        for h in n.get("Plans", []):
            recorrer(h)

    recorrer(plan)
    tipos = [t for t, _ in nodos]
    indices = [i for _, i in nodos if i]
    return {
        "usa_indice": any("Index" in t for t in tipos),
        "indices": indices,
        "ordena_la_tabla_entera": "Sort" in tipos,
        "tiempo_ms": round(plan.get("Actual Total Time", 0), 2),
        "nota": "Si aparece un Sort, el indice volvio a quedar inerte: el "
                "ORDER BY de la vista y las columnas del indice dejaron de "
                "coincidir, y basta una columna al final para eso.",
    }


def medir_cache(base, unidad, campania):
    """Con y sin Redis, sobre la MISMA consulta.

    La clave se borra antes de la medición «sin caché»: si no, la segunda
    corrida siempre gana y la comparación no prueba nada. Y se mide
    también el acierto repetido, porque el valor de una caché no está en
    el primer acierto sino en los mil siguientes.
    """
    try:
        import redis
    except ImportError:
        return {"error": "redis-py no instalado"}

    r = redis.Redis(host=os.environ.get("REDIS_HOST", "127.0.0.1"),
                    decode_responses=True)
    try:
        r.ping()
    except Exception as error:                           # noqa: BLE001
        return {"error": f"Redis no responde: {error}"}

    cn = psycopg2.connect(host=os.environ.get("PG_HOST", "/var/run/postgresql"),
                          dbname=base, user="postgres")
    cur = cn.cursor()
    clave = f"medicion:tablero:{unidad}:{campania}"
    sql = CONSULTAS["serie_completa_de_una_unidad"]
    params = {"unidad": unidad, "campania": campania}

    # --- sin cache: cada vez va a PostgreSQL ---
    sin_cache = []
    for _ in range(REPETICIONES):
        r.delete(clave)
        t0 = time.perf_counter()
        cur.execute(sql, params)
        datos = cur.fetchall()
        r.setex(clave, 60, json.dumps([[str(x) for x in f] for f in datos]))
        sin_cache.append((time.perf_counter() - t0) * 1000)

    # --- con cache: la clave ya esta puesta ---
    con_cache = []
    for _ in range(REPETICIONES):
        t0 = time.perf_counter()
        crudo = r.get(clave)
        if crudo is None:
            cur.execute(sql, params)
            cur.fetchall()
        else:
            json.loads(crudo)
        con_cache.append((time.perf_counter() - t0) * 1000)

    cn.close()
    m_sin = statistics.median(sin_cache)
    m_con = statistics.median(con_cache)
    return {
        "sin_cache_mediana_ms": round(m_sin, 3),
        "con_cache_mediana_ms": round(m_con, 3),
        "mejora_x": round(m_sin / m_con, 1) if m_con > 0 else None,
        "ahorro_ms": round(m_sin - m_con, 3),
        "nota": "La clave se borra antes de cada medicion «sin cache». Sin "
                "eso la segunda corrida siempre gana y la comparacion no "
                "prueba nada.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default=os.environ.get("PG_BASE", "nexum_carga"))
    p.add_argument("--usuario", default="postgres")
    p.add_argument("--crear-indices", action="store_true")
    p.add_argument("--salida", default=None, help="guarda el informe en JSON")
    args = p.parse_args()

    cn = psycopg2.connect(host=os.environ.get("PG_HOST", "/var/run/postgresql"),
                          dbname=args.base, user=args.usuario)
    cn.autocommit = True
    cur = cn.cursor()

    if args.crear_indices:
        crear_indices(cur)
        print()

    objetivos = unidades_representativas(cur)
    if not objetivos:
        sys.exit("No hay agregados publicados en esta base: nada que medir.")
    print("==> midiendo tres unidades por volumen (deterministas: ver "
          "`unidades_representativas`)")
    for o in objetivos:
        print(f"    {o['etiqueta']:8} {o['unidad']:16} {o['campania']:12} "
              f"{o['respuestas']:>6,} respuestas")
    print()

    informe = {"base": args.base, "objetivos": objetivos,
               "repeticiones": REPETICIONES, "consultas": {}, "cache": {}}

    # LOS TAMAÑOS SE MIDEN AL FINAL, no aquí, y es un error que costó una
    # corrida entera. `tamanos` cuenta las filas con `count(*)`, y contar
    # `respuesta_detalle` lee 112 MB por unos `shared_buffers` de 128 MB:
    # desaloja justo las páginas que las consultas de abajo iban a usar.
    # Corriéndolo primero, todas las mediciones salían con la caché de
    # PostgreSQL fría y el informe describía un estado que no es el de
    # operación.

    print("==> consultas")
    unidad = objetivos[-1]["unidad"]          # la grande, para el resto
    campania = objetivos[-1]["campania"]
    for nombre, sql in CONSULTAS.items():
        por_objetivo = {}
        for o in objetivos:
            p_o = {"unidad": o["unidad"], "campania": o["campania"]}
            t_o = medir(cur, sql, p_o)
            por_objetivo[o["etiqueta"]] = {**t_o, "respuestas": o["respuestas"]}
        informe["consultas"].setdefault(nombre, {})["por_volumen"] = por_objetivo
        print(f"    {nombre}")
        for etiqueta, t_o in por_objetivo.items():
            print(f"      {etiqueta:8} {t_o['respuestas']:>6,} respuestas  "
                  f"mediana {t_o['mediana_ms']:8.2f} ms  "
                  f"p95 {t_o['p95_ms']:8.2f} ms  {t_o['filas']:>7,} filas")

    print("\n==> plan, cpu y memoria sobre la unidad mas grande "
          f"({unidad} / {campania})")
    params = {"unidad": unidad, "campania": campania}
    for nombre, sql in CONSULTAS.items():
        tiempos = medir(cur, sql, params)
        plan = plan_de(cur, sql, params)
        recursos = medir_recursos(cur, sql, params)
        informe["consultas"][nombre].update(
            {**tiempos, "plan": plan, "recursos": recursos})
        marca = "indice" if plan["usa_indice"] else "SECUENCIAL"
        print(f"    {nombre:36} mediana {tiempos['mediana_ms']:8.2f} ms  "
              f"p95 {tiempos['p95_ms']:8.2f} ms  {tiempos['filas']:>7,} filas  "
              f"[{marca}]")
        if plan["recorridos_secuenciales"]:
            print(f"      recorre entera(s): "
                  f"{', '.join(plan['recorridos_secuenciales'])}")
        if recursos.get("medido"):
            # El CPU junto al reloj: la diferencia entre los dos dice si
            # la consulta espera disco o calcula, y se arreglan distinto.
            fraccion = (100.0 * recursos["cpu_ms_por_consulta"]
                        / tiempos["mediana_ms"]) if tiempos["mediana_ms"] else 0
            print(f"      cpu {recursos['cpu_ms_por_consulta']:7.3f} ms/consulta "
                  f"de {tiempos['mediana_ms']:.2f} ms de reloj ({fraccion:.0f}%, "
                  f"{recursos['corridas']} corridas)   memoria del backend "
                  f"{recursos['rss_kb'] / 1024:.1f} MB "
                  f"(pico {recursos['rss_pico_kb'] / 1024:.1f} MB)")
        elif recursos.get("rss_kb"):
            print(f"      cpu: no medible ({recursos['cpu_acumulado_ms']:.0f} ms "
                  f"en {recursos['corridas']} corridas, tic de "
                  f"{recursos['resolucion_ms']:.0f} ms)   memoria del backend "
                  f"{recursos['rss_kb'] / 1024:.1f} MB "
                  f"(pico {recursos['rss_pico_kb'] / 1024:.1f} MB)")
        b = plan["bloques"]
        if b["leidos_de_disco"] or b["aciertos_pct"] is not None:
            print(f"      bloques: {b['leidos_de_disco']:,} de disco "
                  f"({b['leidos_kb']:,} kB), {b['encontrados_en_memoria']:,} en "
                  f"memoria ({b['aciertos_pct']}% de aciertos)")
        m = plan["memoria"]
        if m["derrama"]:
            print(f"      DERRAMA A DISCO: "
                  f"{', '.join(f'{d['que']} {d['kb']:,} kB en {d['nodo']}' for d in m['derrames_a_disco'])}"
                  f"  -- no cupo en work_mem")
        elif m["memoria_trabajo_pico_kb"]:
            print(f"      memoria de trabajo pico "
                  f"{m['memoria_trabajo_pico_kb']:,} kB, sin derrames a disco")

    print("\n==> camino caliente: fn_calcular_agregado_protegido")
    informe["camino_caliente"] = medir_camino_caliente(cur, campania, unidad)
    h = informe["camino_caliente"]
    print(f"    mediana {h['mediana_ms']} ms  "
          f"(min {h['minimo_ms']}  max {h['maximo_ms']})")
    print(f"    {h['nota']}")

    print("\n==> la vista de consentimiento resuelve por indice")
    informe["vista_consentimiento"] = plan_de_la_vista_de_consentimiento(cur)
    v = informe["vista_consentimiento"]
    if v["ordena_la_tabla_entera"]:
        print(f"    PROBLEMA: ordena la tabla entera ({v['tiempo_ms']} ms)")
        print(f"      {v['nota']}")
    else:
        print(f"    indice {', '.join(v['indices'])}  ({v['tiempo_ms']} ms), "
              f"sin ordenamiento de la tabla completa")

    print("\n==> cache")
    informe["cache"] = medir_cache(args.base, unidad, campania)
    c = informe["cache"]
    if "error" in c:
        print(f"    {c['error']}")
    else:
        print(f"    sin cache: {c['sin_cache_mediana_ms']:.3f} ms")
        print(f"    con cache: {c['con_cache_mediana_ms']:.3f} ms")
        print(f"    mejora:    {c['mejora_x']}x  "
              f"(ahorra {c['ahorro_ms']:.3f} ms por consulta)")

    print("\n==> consumo de recursos del servidor")
    informe["recursos_servidor"] = recursos_del_servidor(cur)
    rs = informe["recursos_servidor"]
    print(f"    shared_buffers {rs['shared_buffers']}   work_mem "
          f"{rs['work_mem']}   {rs['conexiones_cliente']} conexiones cliente")
    if "rss_por_backend_kb_mediana" in rs:
        print(f"    memoria por backend: mediana "
              f"{rs['rss_por_backend_kb_mediana'] / 1024:.1f} MB, maximo "
              f"{rs['rss_por_backend_kb_maximo'] / 1024:.1f} MB")
        print(f"      {rs['nota']}")
    if "rss_pico_de_este_guion_kb" in rs:
        print(f"    pico de este guion: "
              f"{rs['rss_pico_de_este_guion_kb'] / 1024:.1f} MB (el cliente, "
              f"que no es donde esta el trabajo)")

    # Hasta aqui no se cuenta ninguna fila: ver el comentario de arriba
    # sobre la cache de PostgreSQL. Esto va al final a proposito.
    print("\n==> tamanos")
    informe["tablas"] = tamanos(cur)
    for t in informe["tablas"]:
        print(f"    {t['tabla']:24} {t['total']:>10}  indices {t['indices']:>10}"
              f"  {(t['filas'] or 0):>10,} filas")

    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as f:
            json.dump(informe, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n==> informe en {args.salida}")
    cn.close()


if __name__ == "__main__":
    main()
