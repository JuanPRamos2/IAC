#!/usr/bin/env python3
"""
Generador de volumen para las pruebas de rendimiento del tercer parcial.

QUÉ GENERA Y POR QUÉ ASÍ
-------------------------
La rúbrica pide «un conjunto considerable de datos» y medir inserción,
consulta, índices y caché. Generar ruido aleatorio cumpliría la letra y no
serviría para nada: sobre datos sin estructura, el algoritmo no encuentra
nada y las consultas no se parecen a las reales.

Así que este generador construye una organización **con forma**:

* Dos poblaciones distintas —áreas de oficina y turnos operativos— porque
  es lo que el agrupamiento tiene que separar. Si todas las unidades se
  parecieran, k-medias partiría una nube homogénea por la mitad y el
  resultado no significaría nada.
* Unas pocas unidades con un problema real inyectado, y otras con una
  tendencia a la baja sostenida. Son las que el detector debe encontrar,
  y están anotadas al final para poder comprobar que las encontró.
* El resto, estables. Si todas tuvieran algo, un detector que marcara
  todo pasaría la prueba.

LA JERARQUÍA TIENE QUE CUADRAR
-------------------------------
La plantilla de cada unidad padre se calcula como la suma de sus hijas, no
se inventa. No es pulcritud: el control de inferencia resta la plantilla
del padre menos la de las hijas conocidas para detectar si alguien está
aislando un grupo por debajo del umbral k. Con un árbol que no cuadra ese
resto da cualquier cosa y el control deja de servir. Ya pasó en este
proyecto con la semilla original, y se arregló en la migración 008.

POR QUÉ LAS RESPUESTAS ENTRAN POR COPY Y NO POR LA FUNCIÓN
-----------------------------------------------------------
`autoreporte.fn_registrar_autoreporte` es la única vía de escritura en
operación, y eso no cambia. Pero procesa UNA respuesta por llamada, con
sus validaciones de campaña abierta y consentimiento vigente; para
cientos de miles de filas serían horas.

Este guión carga datos de PRUEBA y corre como superusuario, fuera de la
aplicación, así que usa COPY. Lo que sí respeta es la garantía que
protege la función: `autoreporte.respuesta` recibe seudónimo y nunca
`empleado_id`, porque esa columna no existe y la garantía G2 lo comprueba
contra el catálogo del sistema.

Uso:
    python3 scripts/datos_masivos.py --base nexum_p3 \\
        --unidades 120 --empleados 24000 --campanias 12
"""
import argparse
import io
import math
import os
import random
import sys
import time

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("Falta psycopg2: pip install --break-system-packages psycopg2-binary")

SEMILLA = 20263011

# Perfiles base de las dos poblaciones, en el orden de las dimensiones.
# No son números bonitos: describen lo que de verdad distingue a un turno
# operativo de un área de oficina. El turno tiene más carga y peor
# recuperación SIEMPRE, y eso no es un problema que haya que detectar: es
# lo que el agrupamiento tiene que aprender para no reportarlo cada
# semestre.
PERFILES = {
    "OFICINA": {"DIM-CARGA": 2.9, "DIM-RECUP": 4.0, "DIM-APOYO": 4.0,
                "DIM-AUTON": 4.1, "DIM-CLARID": 4.0},
    "OPERATIVO": {"DIM-CARGA": 3.9, "DIM-RECUP": 2.9, "DIM-APOYO": 3.5,
                  "DIM-AUTON": 2.9, "DIM-CLARID": 3.4},
}

REACTIVO_DE = {"DIM-CARGA": "R-01", "DIM-RECUP": "R-02", "DIM-APOYO": "R-03",
               "DIM-AUTON": "R-04", "DIM-CLARID": "R-05"}


def log(mensaje, t0=None):
    if t0 is None:
        print(f"==> {mensaje}", flush=True)
    else:
        print(f"    {mensaje}: {time.perf_counter() - t0:.2f}s", flush=True)


def conectar(base, usuario):
    return psycopg2.connect(host=os.environ.get("PG_HOST", "/var/run/postgresql"),
                            dbname=base, user=usuario)


def construir_arbol(cur, n_unidades, rnd):
    """Un árbol de dos niveles con la plantilla cuadrada.

    Las hojas llevan la plantilla real; cada padre recibe la SUMA de sus
    hijas. Hacerlo al revés —repartir la del padre— deja restos por el
    redondeo y rompe la invariante.
    """
    log(f"arbol organizacional: {n_unidades} unidades")
    t0 = time.perf_counter()

    direcciones, hojas = [], []
    n_direcciones = max(2, n_unidades // 12)

    for d in range(n_direcciones):
        tipo = "OFICINA" if d % 3 == 0 else "OPERATIVO"
        did = f"UO-MX-D{d:03d}"
        direcciones.append((did, tipo))

    por_direccion = max(2, (n_unidades - n_direcciones) // n_direcciones)
    for did, tipo in direcciones:
        for h in range(por_direccion):
            if len(hojas) + len(direcciones) >= n_unidades:
                break
            # Plantillas grandes a propósito: la escala del ruido es
            # (hi-lo)/n/epsilon, así que con 8 respuestas sale 0.5 y nada
            # es detectable. Con 60 a 400 personas por unidad baja a
            # 0.01–0.07 y el algoritmo puede afirmar cosas.
            plantilla = rnd.randint(60, 400)
            hojas.append((f"{did}-U{h:03d}", did, tipo, plantilla))

    filas = []
    for did, tipo in direcciones:
        suma = sum(p for _, padre, _, p in hojas if padre == did)
        filas.append((did, f"Direccion {did[-4:]}", "DIRECCION", None, 0, suma))
    for uid, padre, tipo, plantilla in hojas:
        nombre = f"{'Area' if tipo == 'OFICINA' else 'Turno'} {uid[-4:]}"
        filas.append((uid, nombre, "AREA" if tipo == "OFICINA" else "TURNO",
                      padre, 1, plantilla))

    psycopg2.extras.execute_values(cur, """
        INSERT INTO organizacion.unidad_organizacional
          (unidad_organizacional_id, nombre, tipo, unidad_padre_id,
           nivel_jerarquico, plantilla_declarada)
        VALUES %s ON CONFLICT (unidad_organizacional_id) DO NOTHING""", filas)
    log(f"{len(filas)} unidades insertadas", t0)
    return hojas


def crear_empleados(cur, hojas, rnd):
    """Empleados, seudónimos y consentimiento, en bloque.

    El seudónimo es lo único que viaja a `autoreporte`. El vínculo
    seudónimo→empleado vive aquí y el rol de la aplicación no lo puede
    leer: es la garantía G2 del proyecto.
    """
    total = sum(p for _, _, _, p in hojas)
    log(f"empleados: {total:,} con seudonimo y consentimiento")
    t0 = time.perf_counter()

    cur.execute("SELECT aviso_id FROM consentimiento.aviso_privacidad "
                " WHERE vigente ORDER BY aviso_id LIMIT 1")
    fila = cur.fetchone()
    aviso = fila[0] if fila else None
    if aviso is None:
        cur.execute("SELECT aviso_id FROM consentimiento.aviso_privacidad "
                    " ORDER BY aviso_id LIMIT 1")
        aviso = cur.fetchone()[0]

    empleados, seudonimos, consentimientos = [], [], []
    n = 0
    por_unidad = {}
    for uid, _, tipo, plantilla in hojas:
        ids = []
        for _ in range(plantilla):
            n += 1
            eid = f"EMP-M{n:07d}"
            sid = f"SD-M{n:07d}"
            empleados.append((eid, f"Nombre{n}", f"Apellido{n}",
                              "2024-01-15", uid))
            seudonimos.append((sid, eid))
            # Un 8% no consiente: sin eso, toda unidad tendría
            # participación perfecta y el umbral k nunca se activaría.
            if rnd.random() > 0.08:
                consentimientos.append((sid, aviso, "ACEPTADO"))
                ids.append(sid)
        por_unidad[uid] = (ids, tipo)

    def copiar(tabla, columnas, filas):
        """COPY por copy_expert y no por copy_from.

        `copy_from` cita el nombre de tabla como un solo identificador,
        así que "usuarios.empleado" se vuelve una tabla llamada
        literalmente «usuarios.empleado» y falla con «relation does not
        exist». Con copy_expert el SQL se escribe completo y el esquema
        se respeta.
        """
        buf = io.StringIO()
        for f in filas:
            buf.write("\t".join("\\N" if v is None else str(v) for v in f) + "\n")
        buf.seek(0)
        cur.copy_expert(f"COPY {tabla} ({', '.join(columnas)}) FROM STDIN", buf)

    copiar("usuarios.empleado",
           ("empleado_id", "nombre", "apellido_paterno", "fecha_ingreso",
            "unidad_organizacional_id"), empleados)
    copiar("consentimiento.seudonimo", ("seudonimo_id", "empleado_id"),
           seudonimos)
    copiar("consentimiento.consentimiento",
           ("seudonimo_id", "aviso_id", "estado"), consentimientos)

    log(f"{len(empleados):,} empleados, {len(consentimientos):,} consentidos",
        t0)
    return por_unidad, aviso


def crear_campanias(cur, n_campanias):
    """Campañas cerradas para tener serie de tiempo larga."""
    log(f"campanias: {n_campanias}")
    # La columna se llama `version`, no `version_instrumento`: ese es el
    # nombre de la TABLA, y pedirlo asi devolvia la fila entera como
    # compuesto. La llave foranea de campania si se llama
    # version_instrumento, y ahi estuvo la confusion.
    cur.execute("SELECT instrumento_id, version "
                "  FROM catalogo.version_instrumento "
                " WHERE publicada AND activa ORDER BY version DESC LIMIT 1")
    instrumento, version = cur.fetchone()
    cur.execute("SELECT coalesce(max(secuencia),0) FROM catalogo.campania")
    base_sec = cur.fetchone()[0]

    campanias = []
    for i in range(n_campanias):
        sec = base_sec + i + 1
        anio = 2024 + (i // 4)
        trimestre = (i % 4) + 1
        campanias.append((f"CAMP-M{sec:03d}", f"Campania masiva {sec}",
                          instrumento, version,
                          f"{anio}-{trimestre * 3 - 2:02d}-01",
                          f"{anio}-{trimestre * 3:02d}-28", "CERRADA", sec))
    psycopg2.extras.execute_values(cur, """
        INSERT INTO catalogo.campania
          (campania_id, nombre, instrumento_id, version_instrumento,
           fecha_inicio, fecha_fin, estado, secuencia)
        VALUES %s ON CONFLICT (campania_id) DO NOTHING""", campanias)
    return [c[0] for c in campanias]


def inyectar_senal(hojas, rnd):
    """Decide qué unidades tendrán un problema y de qué tipo.

    Se devuelve la lista para poder COMPROBAR después que el algoritmo las
    encontró. Un generador que no anotara la verdad dejaría las pruebas de
    rendimiento sin forma de validar la calidad del detector.
    """
    unidades = [u for u, _, _, _ in hojas]
    rnd.shuffle(unidades)
    corte = max(1, len(unidades) // 20)        # 5% anómalas
    anomalas = unidades[:corte]
    decayendo = unidades[corte:corte * 2]      # otro 5% en caída
    return {"anomalas": set(anomalas), "decayendo": set(decayendo)}


def generar_respuestas(cur, por_unidad, campanias, aviso, senal, rnd):
    """Las respuestas, con su perfil, su tendencia y su anomalía."""
    total_esperado = sum(len(ids) for ids, _ in por_unidad.values()) * len(campanias)
    log(f"respuestas: hasta {total_esperado:,} con detalle por reactivo")
    t0 = time.perf_counter()

    cur.execute("SELECT coalesce(max(respuesta_id),0) FROM autoreporte.respuesta")
    siguiente = cur.fetchone()[0] + 1

    dimensiones = list(PERFILES["OFICINA"])
    insertadas = 0

    for indice, campania in enumerate(campanias):
        buf_r, buf_d = io.StringIO(), io.StringIO()
        for uid, (ids, tipo) in por_unidad.items():
            base = dict(PERFILES[tipo])

            # Tendencia: una caída sostenida de 0.08 por campaña en
            # recuperación y apoyo. Es pequeña a propósito: una caída
            # enorme la detectaría cualquier cosa.
            if uid in senal["decayendo"]:
                caida = 0.08 * indice
                base["DIM-RECUP"] -= caida
                base["DIM-APOYO"] -= caida
                base["DIM-CARGA"] += caida * 0.6

            # Anomalía: constante y grande, en todas las campañas.
            if uid in senal["anomalas"]:
                base["DIM-RECUP"] -= 1.1
                base["DIM-APOYO"] -= 0.9
                base["DIM-CARGA"] += 1.0

            # No todos contestan cada campaña: la participación real anda
            # entre el 55% y el 90%, y de ahí sale que algunas unidades
            # chicas caigan por debajo del umbral k.
            participacion = rnd.uniform(0.55, 0.90)
            quienes = rnd.sample(ids, max(0, int(len(ids) * participacion)))

            for sid in quienes:
                rid = siguiente
                siguiente += 1
                buf_r.write(f"{rid}\t{sid}\t{campania}\t{uid}\t{aviso}\n")
                for dim in dimensiones:
                    # Variación individual alrededor del perfil de la
                    # unidad. Sin ella todos contestarían lo mismo y la
                    # media no tendría dispersión.
                    v = base[dim] + rnd.gauss(0, 0.75)
                    v = max(1, min(5, int(round(v))))
                    buf_d.write(f"{rid}\t{REACTIVO_DE[dim]}\t{v}\n")
                insertadas += 1

        buf_r.seek(0); buf_d.seek(0)
        cur.copy_expert(
            "COPY autoreporte.respuesta (respuesta_id, seudonimo_id, "
            " campania_id, unidad_organizacional_id, aviso_id) FROM STDIN",
            buf_r)
        cur.copy_expert(
            "COPY autoreporte.respuesta_detalle (respuesta_id, reactivo_id, "
            " valor) FROM STDIN", buf_d)
        print(f"    campania {indice + 1}/{len(campanias)}: "
              f"{insertadas:,} acumuladas", flush=True)

    cur.execute("SELECT setval(pg_get_serial_sequence('autoreporte.respuesta',"
                " 'respuesta_id'), %s, true)", (siguiente,))
    segundos = time.perf_counter() - t0
    log(f"{insertadas:,} respuestas ({insertadas * 5:,} valores)", t0)
    return insertadas, segundos


def ligar_campanias(cur, por_unidad, campanias):
    filas = [(c, u) for c in campanias for u in por_unidad]
    psycopg2.extras.execute_values(cur, """
        INSERT INTO catalogo.campania_unidad
          (campania_id, unidad_organizacional_id)
        VALUES %s ON CONFLICT DO NOTHING""", filas, page_size=5000)


def calcular_agregados(cur, por_unidad, campanias):
    """Los agregados se calculan con la función oficial, sin atajos.

    Es la que aplica el umbral k, el recorte y el ruido de Laplace, y la
    que descuenta el épsilon. Insertar los agregados a mano sería más
    rápido y produciría valores que nunca pasaron por la tubería de
    privacidad: exactamente lo que el proyecto entero existe para evitar.
    """
    log(f"agregados protegidos: {len(por_unidad)} unidades x "
        f"{len(campanias)} campanias x 6")
    t0 = time.perf_counter()
    cur.execute("SELECT usuario_id FROM usuarios.usuario LIMIT 1")
    actor = cur.fetchone()[0]

    cur.execute("SELECT dimension_id FROM catalogo.dimension ORDER BY orden")
    dimensiones = [d[0] for d in cur.fetchall()]

    hecho = 0
    for campania in campanias:
        for uid in por_unidad:
            cur.execute("SELECT agregado.fn_calcular_agregado_protegido(%s,%s,NULL,%s)",
                        (campania, uid, actor))
            for dim in dimensiones:
                cur.execute(
                    "SELECT agregado.fn_calcular_agregado_protegido(%s,%s,%s,%s)",
                    (campania, uid, dim, actor))
            hecho += 1
        print(f"    {campania}: {hecho} unidades procesadas", flush=True)
    segundos = time.perf_counter() - t0
    log(f"{hecho * (len(dimensiones) + 1):,} agregados", t0)
    return hecho * (len(dimensiones) + 1), segundos


# =========================================================================
# Consumo de recursos durante la generación
# =========================================================================
#
# POR QUÉ SE MIDE AQUÍ Y NO SOLO EN EL BANCO DE CONSULTAS
# -------------------------------------------------------
# Generar un millón de valores es la operación de escritura más grande que
# el sistema va a ver, y es donde se rompe primero. Dos fallas concretas
# que esta medición hace visibles y el reloj no:
#
# 1. **El generador cargando todo en memoria.** Armar un millón de tuplas
#    en una lista para después insertarlas de golpe funciona en un portátil
#    con 32 GB y muere en un contenedor con 512 MB. El tiempo total no
#    cambia hasta el momento en que el proceso se cae, así que el reloj no
#    avisa: el pico de memoria sí.
#
# 2. **El servidor penando en CPU por una carga que debería ser de disco.**
#    Una carga masiva que consume CPU del servidor en lugar de ancho de
#    banda de disco está pagando parseo e índices fila por fila —es lo que
#    distingue un INSERT por fila de un COPY—, y eso no se ve en el total
#    cuando la base es pequeña.
#
# Se mide el pico (`ru_maxrss` del generador, `VmHWM` del backend) y no la
# memoria del momento: el pico de una carga ya bajó cuando la carga
# terminó, y leer la memoria «actual» al final no lo vería nunca.
def _rss_pico_kb_de(pid):
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as f:
            for linea in f:
                if linea.startswith("VmHWM:"):
                    return int(linea.split()[1])
    except OSError:
        return None
    return None


def _cpu_ms_de(pid):
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as f:
            campos = f.read().rsplit(") ", 1)[1].split()
        return ((int(campos[11]) + int(campos[12])) * 1000.0
                / os.sysconf("SC_CLK_TCK"))
    except (OSError, IndexError, ValueError):
        return None


def consumo_de_recursos(cur, cpu_backend_inicial):
    """Pico de memoria y CPU, del generador y del backend que carga.

    Devuelve lo que se pudo medir. En un sistema sin procfs la parte del
    servidor sale nula y dicha, en lugar de salir en cero: un cero se lee
    como «no consumió nada».
    """
    salida = {}
    try:
        import resource
        salida["generador_rss_pico_mb"] = round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)
    except Exception:                                     # noqa: BLE001
        salida["generador_rss_pico_mb"] = None

    cur.execute("SELECT pg_backend_pid()")
    pid = cur.fetchone()[0]
    pico = _rss_pico_kb_de(pid)
    cpu = _cpu_ms_de(pid)
    salida["backend_pid"] = pid
    salida["backend_rss_pico_mb"] = round(pico / 1024.0, 1) if pico else None
    salida["backend_cpu_s"] = (
        round((cpu - cpu_backend_inicial) / 1000.0, 2)
        if (cpu is not None and cpu_backend_inicial is not None) else None)

    cur.execute("SHOW shared_buffers")
    salida["shared_buffers"] = cur.fetchone()[0]
    cur.execute("SHOW maintenance_work_mem")
    salida["maintenance_work_mem"] = cur.fetchone()[0]
    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    salida["tamano_de_la_base"] = cur.fetchone()[0]
    return salida


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default=os.environ.get("PG_BASE", "nexum_p3"))
    p.add_argument("--usuario", default="postgres")
    p.add_argument("--unidades", type=int, default=120)
    p.add_argument("--campanias", type=int, default=12)
    p.add_argument("--semilla", type=int, default=SEMILLA)
    p.add_argument("--solo-agregados", action="store_true",
                   help="recalcula agregados sin regenerar respuestas")
    args = p.parse_args()

    rnd = random.Random(args.semilla)
    inicio = time.perf_counter()
    cn = conectar(args.base, args.usuario)
    cn.autocommit = False
    cur = cn.cursor()
    # El CPU del backend ANTES de empezar: la diferencia al final es lo
    # que costó la carga, y no el acumulado de la conexión.
    cur.execute("SELECT pg_backend_pid()")
    cpu_backend_inicial = _cpu_ms_de(cur.fetchone()[0])

    hojas = construir_arbol(cur, args.unidades, rnd)
    por_unidad, aviso = crear_empleados(cur, hojas, rnd)
    campanias = crear_campanias(cur, args.campanias)
    ligar_campanias(cur, por_unidad, campanias)
    senal = inyectar_senal(hojas, rnd)
    cn.commit()

    insercion_s = agregados_s = None
    if not args.solo_agregados:
        _filas, insercion_s = generar_respuestas(
            cur, por_unidad, campanias, aviso, senal, rnd)
        cn.commit()

    _n_agregados, agregados_s = calcular_agregados(cur, por_unidad, campanias)
    cn.commit()

    # La verdad inyectada se guarda para poder comprobar despues que el
    # detector la encontro. Sin esto, medir el rendimiento del algoritmo
    # no diria nada de su calidad.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.verdad_inyectada (
            unidad_organizacional_id VARCHAR(40) PRIMARY KEY,
            tipo VARCHAR(20) NOT NULL)""")
    cur.execute("TRUNCATE public.verdad_inyectada")
    psycopg2.extras.execute_values(cur,
        "INSERT INTO public.verdad_inyectada VALUES %s",
        [(u, "ANOMALA") for u in senal["anomalas"]]
        + [(u, "DECAYENDO") for u in senal["decayendo"]])
    cn.commit()

    cur.execute("SELECT count(*) FROM autoreporte.respuesta")
    respuestas = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM autoreporte.respuesta_detalle")
    detalles = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM agregado.resultado_protegido")
    agregados = cur.fetchone()[0]
    cur.execute("SELECT round(avg(escala_ruido),4), round(min(escala_ruido),4) "
                "  FROM agregado.resultado_protegido "
                " WHERE estado_publicacion='PUBLICADO'")
    escala_media, escala_min = cur.fetchone()

    print()
    log("RESUMEN")
    print(f"    respuestas:        {respuestas:,}")
    print(f"    valores:           {detalles:,}")
    print(f"    agregados:         {agregados:,}")
    print(f"    escala de ruido:   media {escala_media}  minima {escala_min}")
    print(f"    unidades anomalas inyectadas:  {len(senal['anomalas'])}")
    print(f"    unidades decayendo inyectadas: {len(senal['decayendo'])}")
    print(f"    tiempo total:      {time.perf_counter() - inicio:.1f}s")

    # CONSUMO DE RECURSOS. Ver el comentario de `consumo_de_recursos`: con
    # un volumen asi, el pico de memoria es lo que decide si el proceso
    # termina o se cae, y el reloj no lo dice.
    r = consumo_de_recursos(cur, cpu_backend_inicial)
    transcurrido = time.perf_counter() - inicio
    print()
    log("CONSUMO DE RECURSOS")
    if r["generador_rss_pico_mb"] is not None:
        print(f"    generador, memoria pico:  "
              f"{r['generador_rss_pico_mb']:.1f} MB")
    if r["backend_rss_pico_mb"] is not None:
        print(f"    backend, memoria pico:    "
              f"{r['backend_rss_pico_mb']:.1f} MB "
              f"(shared_buffers {r['shared_buffers']}, "
              f"maintenance_work_mem {r['maintenance_work_mem']})")
    else:
        print("    backend: sin /proc, no se pudo medir su consumo")
    if r["backend_cpu_s"] is not None:
        print(f"    backend, cpu:             {r['backend_cpu_s']:.2f} s de "
              f"{transcurrido:.1f} s de reloj "
              f"({100.0 * r['backend_cpu_s'] / transcurrido:.0f}%)")
    print(f"    tamano de la base:        {r['tamano_de_la_base']}")
    # EL RENDIMIENTO SE REPORTA POR FASE, no dividido entre el tiempo
    # total. Las dos fases hacen cosas opuestas y se dimensionan distinto,
    # y la medicion de arriba lo demuestra: la insercion es un COPY —entra
    # a decenas de miles de filas por segundo y el limite es el disco— y el
    # calculo de agregados es la tuberia de privacidad, que resulta estar
    # al 99 % de CPU. Una sola cifra «filas por segundo» sobre el total
    # dice 2 168 y no describe ninguna de las dos: haria creer que la carga
    # es lenta cuando la carga es rapida y lo que cuesta es el calculo.
    if insercion_s:
        print(f"    insercion (COPY):         "
              f"{(respuestas + detalles) / insercion_s:,.0f} filas/s "
              f"en {insercion_s:.2f} s")
    if agregados_s:
        print(f"    calculo de agregados:     "
              f"{agregados:,} en {agregados_s:.1f} s "
              f"({1000.0 * agregados_s / agregados:.1f} ms cada uno, "
              f"limitado por CPU)")
    cn.close()


if __name__ == "__main__":
    main()
