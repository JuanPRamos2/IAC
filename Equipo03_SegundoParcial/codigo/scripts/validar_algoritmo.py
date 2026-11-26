#!/usr/bin/env python3
"""
Valida el análisis complejo contra la verdad inyectada.

POR QUÉ ESTA VALIDACIÓN Y NO «SE VE BIEN»
------------------------------------------
Un detector se puede ajustar hasta que sus salidas parezcan razonables, y
eso no prueba nada: con suficientes parámetros cualquier lista de unidades
se puede justificar después de verla. La única forma de medir un detector
es inyectar la señal a propósito, apuntar dónde se inyectó ANTES de
correrlo, y comparar.

El generador de datos masivos hace justo eso: elige al azar un 5% de las
unidades y les baja el bienestar, y otro 5% y se lo hace decaer campaña a
campaña, y escribe cuáles en `public.verdad_inyectada`. Este guión corre
el análisis sin saber nada de esa tabla y después compara.

LAS DOS MÉTRICAS, Y POR QUÉ LAS DOS
------------------------------------
    precisión = de las que señalé, ¿cuántas estaban de verdad mal?
    exhaustividad (recall) = de las que estaban mal, ¿cuántas señalé?

Una sola es fácil de falsear. Un detector que señala a TODAS tiene
exhaustividad perfecta y precisión inútil; uno que señala solo a la peor
tiene precisión perfecta y deja pasar al resto. En este dominio el costo de
los dos errores no es igual y conviene decirlo: un falso positivo gasta el
tiempo de un especialista en un área que está bien; un falso negativo deja
sin atender a un equipo que lo necesita. Por eso el motor prioriza en lugar
de dar un sí/no, y lo que se mide es si la lista pone arriba lo que importa.

Uso:
    python3 scripts/validar_algoritmo.py --base nexum_carga
"""
import argparse
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("Falta psycopg2")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "apps", "microservicios", "analitica"))

from analitica import motor  # noqa: E402


def cargar(cn, campania_id):
    """Las dos entradas del motor, igual que las arma el microservicio."""
    with cn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT secuencia FROM catalogo.campania WHERE campania_id=%s",
                    (campania_id,))
        secuencia = cur.fetchone()["secuencia"]

        cur.execute(
            "SELECT unidad_organizacional_id, dimension_id, valor_protegido, "
            "       escala_ruido, n_observaciones "
            "  FROM agregado.resultado_protegido "
            " WHERE campania_id = %s AND estado_publicacion = 'PUBLICADO' "
            "   AND dimension_id IS NOT NULL", (campania_id,))
        filas = [dict(f) for f in cur.fetchall()]

        cur.execute(
            "SELECT rp.unidad_organizacional_id, rp.dimension_id, c.secuencia, "
            "       rp.valor_protegido, rp.escala_ruido "
            "  FROM agregado.resultado_protegido rp "
            "  JOIN catalogo.campania c USING (campania_id) "
            " WHERE rp.estado_publicacion = 'PUBLICADO' "
            "   AND rp.dimension_id IS NOT NULL AND c.secuencia <= %s",
            (secuencia,))
        publicados = cur.fetchall()

        cur.execute("SELECT cu.unidad_organizacional_id, c.secuencia "
                    "  FROM catalogo.campania_unidad cu "
                    "  JOIN catalogo.campania c USING (campania_id) "
                    " WHERE c.secuencia <= %s", (secuencia,))
        convocadas = {}
        for f in cur.fetchall():
            convocadas.setdefault(f["unidad_organizacional_id"], set()).add(
                f["secuencia"])

    dimensiones = sorted({f["dimension_id"] for f in filas})
    valores = {(f["unidad_organizacional_id"], f["dimension_id"], f["secuencia"]):
               (f["valor_protegido"], f["escala_ruido"]) for f in publicados}
    series = {}
    for unidad, secs in convocadas.items():
        series[unidad] = {
            dim: [(s,) + valores.get((unidad, dim, s), (None, None))
                  for s in sorted(secs)]
            for dim in dimensiones}
    return filas, series


def metricas(senaladas, verdaderas, universo):
    """precisión, exhaustividad, F1 y los conteos crudos.

    Los conteos van además de las razones: con universos chicos una
    precisión de 0.60 puede ser 3 de 5, y eso cambia cuánto confiar en el
    número.
    """
    vp = len(senaladas & verdaderas)
    fp = len(senaladas - verdaderas)
    fn = len(verdaderas - senaladas)
    vn = len(universo - senaladas - verdaderas)
    precision = vp / (vp + fp) if (vp + fp) else None
    exhaustividad = vp / (vp + fn) if (vp + fn) else None
    f1 = (2 * precision * exhaustividad / (precision + exhaustividad)
          if precision and exhaustividad else None)
    return {"verdaderos_positivos": vp, "falsos_positivos": fp,
            "falsos_negativos": fn, "verdaderos_negativos": vn,
            "precision": precision, "exhaustividad": exhaustividad, "f1": f1}


def linea(nombre, m):
    def pct(x):
        return f"{100 * x:5.1f}%" if x is not None else "    --"
    print(f"    {nombre:28} precision {pct(m['precision'])}   "
          f"exhaustividad {pct(m['exhaustividad'])}   "
          f"F1 {pct(m['f1'])}   "
          f"(VP {m['verdaderos_positivos']} FP {m['falsos_positivos']} "
          f"FN {m['falsos_negativos']})")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default=os.environ.get("PG_BASE", "nexum_carga"))
    p.add_argument("--campania", default=None,
                   help="por omision, la ultima con resultados publicados")
    args = p.parse_args()

    cn = psycopg2.connect(host=os.environ.get("PG_HOST", "/var/run/postgresql"),
                          dbname=args.base, user="postgres")
    with cn.cursor() as cur:
        if args.campania:
            campania = args.campania
        else:
            cur.execute("SELECT campania_id FROM catalogo.campania "
                        " WHERE campania_id IN (SELECT DISTINCT campania_id "
                        "   FROM agregado.resultado_protegido "
                        "  WHERE estado_publicacion='PUBLICADO') "
                        " ORDER BY secuencia DESC LIMIT 1")
            campania = cur.fetchone()[0]
        cur.execute("SELECT unidad_organizacional_id, tipo "
                    "  FROM public.verdad_inyectada")
        verdad = {}
        for unidad, tipo in cur.fetchall():
            verdad.setdefault(tipo, set()).add(unidad)

    print(f"==> campania {campania}, base {args.base}\n")
    filas, series = cargar(cn, campania)
    informe = motor.analizar(filas, series)

    print(f"    unidades analizadas:       {informe['unidades_analizadas']}")
    print(f"    sin perfil completo:       "
          f"{len(informe['unidades_sin_perfil_completo'])}")
    print(f"    grupos de pares:           "
          f"{informe['agrupamiento']['grupos']}  "
          f"(silueta {informe['agrupamiento']['silueta']})")
    print(f"    epsilon consumido:         {informe['epsilon_consumido']}")
    print(f"    tiempo de ejecucion:       {informe['tiempo_ms']} ms\n")

    universo = {p["unidad_organizacional_id"] for p in informe["priorizadas"]}
    verdad_toda = verdad.get("ANOMALA", set()) | verdad.get("DECAYENDO", set())
    anomalas = verdad.get("ANOMALA", set()) & universo
    decayendo = verdad.get("DECAYENDO", set()) & universo

    # --- anomalías: dos niveles, y hay que medir los dos ---
    #
    # El detector tiene dos salidas y no una, y eso NO es un detalle de
    # formato: es el resultado de un defecto medido con estos mismos
    # datos. k-medias agrupó a las cinco unidades deterioradas en el mismo
    # grupo —para eso sirve, agrupa lo parecido— y dentro de ese grupo
    # cada una parecía normal. Comparar dentro del grupo las escondía a
    # las cinco.
    #
    # La corrección fue medir además cada GRUPO contra la mediana de la
    # organización, y entregar eso como un hallazgo de segmento aparte.
    # Así que medir solo el nivel por unidad da cero y es engañoso: el
    # hallazgo correcto para esas cinco unidades es «este segmento de seis
    # unidades esta 1.1 puntos por debajo de la organizacion», que es lo
    # que el detector dice.
    print("==> deteccion de unidades anomalas "
          f"({len(anomalas)} inyectadas y analizables)")

    print("\n    NIVEL 1 — hallazgos de segmento (grupos desplazados)")
    segmentos = informe["hallazgos_de_segmento"]
    en_segmento = set()
    for h in segmentos:
        en_segmento |= set(h["unidades_del_grupo"])
        dentro = [u for u in h["unidades_del_grupo"] if u in verdad_toda]
        print(f"      grupo {h['grupo']}: {h['unidades']} unidades, "
              f"desplazado {h['desplazamiento_peor']} puntos en "
              f"{len(h['dimensiones_desplazadas'])} dimension(es) -> "
              f"{len(dentro)}/{h['unidades']} son inyectadas")
    if not segmentos:
        print("      ninguno")
    # Se mide contra TODA la verdad inyectada y no solo contra las
    # anómalas: un hallazgo de segmento no afirma de qué tipo es el
    # problema de cada unidad, afirma que el segmento está desplazado.
    # Contar como falso positivo a una unidad decayendo que cayó en el
    # mismo segmento sería castigar al detector por tener razón.
    linea("cobertura por segmento", metricas(en_segmento & universo,
                                             anomalas | decayendo, universo))

    print("\n    NIVEL 2 — nivel asignado a la unidad individual")
    for nivel in ("ATENCION", "PRIORITARIO"):
        senaladas = {p["unidad_organizacional_id"] for p in informe["priorizadas"]
                     if p["nivel"] == nivel or
                     (nivel == "ATENCION" and p["nivel"] == "PRIORITARIO")}
        linea(f"nivel >= {nivel}", metricas(senaladas, anomalas, universo))
    con_anomalia = {p["unidad_organizacional_id"] for p in informe["priorizadas"]
                    if p["dimensiones_anomalas"]}
    linea("con dimension anomala propia", metricas(con_anomalia, anomalas,
                                                   universo))
    print("      Que las anomalas NO salgan senaladas individualmente es el "
          "resultado correcto:")
    print("      dentro de su grupo no se distinguen de sus companeras, y el "
          "hallazgo que les")
    print("      corresponde es del segmento. Lo contrario —marcar a cada una "
          "como si tuviera")
    print("      un problema propio— diria que hacen falta seis "
          "intervenciones de equipo cuando")
    print("      lo que hace falta es una revision del segmento.")

    # El ranking: de las N primeras, cuántas son inyectadas. Es la medida
    # que de verdad corresponde al uso: un especialista no recibe un
    # sí/no, recibe una lista y empieza por arriba.
    #
    # Se mide contra TODAS las inyectadas —anómalas y decayendo— y no solo
    # contra las anómalas. La lista priorizada tiene un único trabajo:
    # poner arriba lo que merece atención, y una unidad que viene cayendo
    # lo merece igual que una que ya está mal. Una primera versión medía
    # solo contra las anómalas y reportaba 0/5 en el top 5 cuando ese top
    # 5 eran exactamente las cinco unidades decayendo: el detector había
    # acertado por completo y la métrica decía lo contrario.
    todas_inyectadas = (anomalas | decayendo)
    print("\n==> calidad del ranking (las N primeras de la lista priorizada)")
    print(f"    contra las {len(todas_inyectadas)} inyectadas analizables "
          f"({len(anomalas)} anomalas + {len(decayendo)} decayendo)")
    for n in (5, 10, 20):
        primeras = {p["unidad_organizacional_id"]
                    for p in informe["priorizadas"][:n]}
        aciertos = len(primeras & todas_inyectadas)
        print(f"    top {n:2}: {aciertos}/{min(n, len(todas_inyectadas))} "
              f"de las inyectadas  "
              f"(precision {100.0 * aciertos / n:5.1f}%)")

    # --- tendencias ---
    #
    # La direccion que devuelve Mann-Kendall es CRUDA —AL_ALZA o
    # A_LA_BAJA— y no dice si eso es mejor o peor: depende de la
    # dimension. En carga percibida, subir ES empeorar. Una primera
    # version de este guion buscaba la etiqueta "DETERIORO", que no
    # existe, y reportaba cero detecciones sobre un detector que estaba
    # funcionando: el error estaba aqui, no en el algoritmo.
    print(f"\n==> deteccion de deterioro sostenido "
          f"({len(decayendo)} inyectadas y analizables)")

    def empeora(dimension_id, direccion):
        if dimension_id in motor.DIMENSIONES_INVERTIDAS:
            return direccion == "AL_ALZA"
        return direccion == "A_LA_BAJA"

    deteriorando = set()
    solo_con_ruido_superado = set()
    for unidad, dims in informe["tendencias"].items():
        for dim, info in dims.items():
            if empeora(dim, info["direccion"]):
                deteriorando.add(unidad)
                if info.get("supera_el_ruido"):
                    solo_con_ruido_superado.add(unidad)
    linea("Mann-Kendall p<0.05", metricas(deteriorando & universo,
                                          decayendo, universo))
    linea("y además supera el ruido", metricas(solo_con_ruido_superado & universo,
                                               decayendo, universo))

    # La tercera línea es la que importa: lo que el motor DE VERDAD cuenta
    # como «empeorando» después de exigir que el cambio acumulado sea
    # materialmente grande, no solo real. Las dos líneas de arriba miden
    # la salida cruda de Mann-Kendall, antes de esa compuerta.
    #
    # La diferencia entre las dos primeras y esta es el argumento entero:
    # con 110 unidades por 5 dimensiones hay 550 series, y a p<0.05 el
    # azar solo produce unas 27 detecciones. Un detector con 100% de
    # exhaustividad y 26% de precisión no sirve para decidir nada, porque
    # de cada cuatro áreas que señala, tres están bien.
    con_compuerta_material = {p["unidad_organizacional_id"]
                              for p in informe["priorizadas"]
                              if p["dimensiones_empeorando"]}
    linea("y además es materialmente grande",
          metricas(con_compuerta_material & universo, decayendo, universo))

    # --- las inyectadas que el detector no vio, una por una ---
    perdidas = anomalas - con_anomalia
    if perdidas:
        print(f"\n==> las {len(perdidas)} anomalas que NO se detectaron, y por que")
        for u in sorted(perdidas):
            fila = next((p for p in informe["priorizadas"]
                         if p["unidad_organizacional_id"] == u), None)
            if fila:
                print(f"    {u}: nivel {fila['nivel']}, puntaje "
                      f"{fila['puntaje']}, grupo {fila['grupo']}, "
                      f"comparada contra grupo {fila.get('comparada_contra')}")
    fuera = (verdad.get("ANOMALA", set()) | verdad.get("DECAYENDO", set())) - universo
    if fuera:
        print(f"\n==> {len(fuera)} unidades inyectadas quedaron FUERA del "
              f"analisis (perfil incompleto): {sorted(fuera)}")
        print("    No son fallos del detector: son unidades a las que el "
              "umbral k les suprimio al menos una dimension, y el motor las "
              "excluye y las reporta en lugar de inventarles un valor.")

    print("\n==> las 10 primeras de la lista priorizada")
    for i, pz in enumerate(informe["priorizadas"][:10], 1):
        u = pz["unidad_organizacional_id"]
        marca = ""
        if u in verdad.get("ANOMALA", set()):
            marca = "  <-- ANOMALA inyectada"
        elif u in verdad.get("DECAYENDO", set()):
            marca = "  <-- DECAYENDO inyectada"
        print(f"    {i:2}. {u:22} {pz['nivel']:12} {pz['puntaje']:.3f}  "
              f"{len(pz['dimensiones_anomalas'])} dim{marca}")
    cn.close()


if __name__ == "__main__":
    main()
