"""
algorithms-service — motor de reglas de riesgo organizacional.

Es el microservicio de algoritmos del proyecto. Toma los agregados que ya
se publicaron, evalúa las reglas del catálogo y produce detecciones con su
explicación. Los resultados de cada corrida se guardan en MongoDB, que es
donde el proyecto almacena los resultados de algoritmos.

CUATRO DECISIONES QUE DEFINEN AL SERVICIO
-----------------------------------------
1. **Evalúa sobre lo ya publicado, así que no consume épsilon.** Las reglas
   leen `agregado.resultado_protegido` donde el estado es PUBLICADO. Si el
   motor recalculara agregados para evaluar, cada corrida gastaría
   presupuesto de privacidad y evaluar el riesgo de una organización
   costaría la capacidad de publicar resultados nuevos.

2. **Una detección sin explicación no se emite.** Cada regla produce un
   texto que dice qué valor se observó, contra qué umbral y en qué
   campaña. Nadie aprueba un plan de intervención porque un sistema lo
   diga: el especialista que lo propone tiene que poder defender por qué.

3. **Las unidades que NO se pudieron evaluar se reportan.** Si una unidad
   tiene todos sus agregados suprimidos por el umbral k, el motor no puede
   decir nada de ella. Omitirla en silencio haría creer a la organización
   que ahí no hay riesgo, cuando lo que hay es falta de datos publicables.
   Es la diferencia entre «no detectamos nada» y «no pudimos ver».

4. **La simulación no escribe.** Permite preguntar qué detectaría una regla
   con otro umbral, sin crear detecciones. Es lo que deja a un comité
   ajustar los parámetros con evidencia en lugar de a ciegas, y es de solo
   lectura a propósito: una simulación que dejara detecciones reales
   contaminaría el histórico con escenarios que nunca ocurrieron.

La evaluación en sí vive en `riesgo.fn_evaluar_unidad`, una función
SECURITY DEFINER de PostgreSQL. El servicio no reimplementa las reglas: si
lo hiciera, el portal y el microservicio podrían llegar a conclusiones
distintas sobre los mismos datos.
"""
import datetime as dt
import decimal
import json
import os
import uuid

from flask import g, request

from comun import (ErrorApi, VERSION_API, crear_servicio, cuerpo_peticion,
                   exigir_tiempo, limite_consumo, obtener_redis, pagina,
                   responder, requiere_permiso, sobre_pagina)
from comun.datos import consultar, consultar_uno, cursor, ping as ping_pg
from comun.mongo import (ASCENDING, DESCENDING, asegurar_indices, base,
                         ping as ping_mongo, verificar_sin_identidad)

os.environ.setdefault("NOMBRE_SERVICIO", "algorithms-service")

NIVELES = ("INFORMATIVO", "ATENCION", "PRIORITARIO")

INDICES = {
    "corridas_algoritmo": [
        ([("corrida_id", ASCENDING)], {"unique": True, "name": "ix_corrida_id"}),
        ([("campania_id", ASCENDING), ("fecha", DESCENDING)],
         {"name": "ix_campania_fecha"}),
        ([("unidad_organizacional_id", ASCENDING), ("fecha", DESCENDING)],
         {"name": "ix_unidad_fecha"}),
        ([("detecciones.regla_id", ASCENDING)], {"name": "ix_regla"}),
        # `GET /algoritmos/corridas` SIN campania_id ordena por fecha con
        # el filtro vacio, y ningun indice empezaba por fecha: el orden se
        # hacia en memoria. Y un sort en memoria tiene un limite de 32 MB
        # y **falla** al pasarlo — no se degrada, deja de funcionar — asi
        # que el historial completo se rompia justo cuando tenia historial.
        #
        # Es el caso por omision del endpoint: quien abre el historial sin
        # filtrar por campania recorre todo.
        ([("fecha", DESCENDING)], {"name": "ix_fecha"}),
    ],
}


def _ping_redis():
    obtener_redis().ping()


app = crear_servicio(
    "algorithms-service",
    "Motor de reglas de riesgo organizacional sobre agregados ya publicados",
    # MongoDB es OPCIONAL para este servicio y esencial para los otros que
    # lo usan. El motor evalua leyendo agregados ya publicados de
    # PostgreSQL; MongoDB solo guarda el historial de corridas. Con MongoDB
    # caido, /reglas, /evaluar y /cobertura siguen funcionando, y lo unico
    # que se pierde es /corridas. Declararlo esencial sacaba de servicio a
    # una pieza que funcionaba.
    comprobaciones={"postgresql": ping_pg,
                    "mongodb": (ping_mongo, "opcional"),
                    "redis": _ping_redis})

from contrato import montar as _montar_contrato
_montar_contrato(app)

BASE = f"/api/{VERSION_API}/algoritmos"


def _bitacora(accion, resultado, recurso=None):
    try:
        with cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO auditoria.bitacora (actor_usuario_id, actor_perfil, "
                " accion, tipo_recurso, recurso_id, resultado, correlacion_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                ((g.get("actor") or {}).get("sub"),
                 ((g.get("actor") or {}).get("perfil") or "ANONIMO")[:30],
                 accion, "DETECCION", recurso, resultado,
                 getattr(g, "correlacion_id", "")))
    except Exception:
        app.logger.exception("No se pudo escribir en la bitacora: %s", accion)


def _normalizar(valor):
    if isinstance(valor, (dt.datetime, dt.date)):
        return valor.isoformat()
    if isinstance(valor, decimal.Decimal):
        return float(valor)
    return valor


def _filas(sql, params=None):
    return [{k: _normalizar(v) for k, v in dict(f).items()}
            for f in consultar(sql, params)]


# Orden canónico de una detección. Es EL MISMO que declara el tipo
# Deteccion de contratos/xml/algoritmos.xsd, y existe por una razón
# concreta: una detección se construye en dos lugares distintos — la vista
# riesgo.v_recomendaciones y la función riesgo.fn_evaluar_unidad — y las dos
# devuelven sus columnas en el orden en que están escritas en el SQL, que no
# es el mismo. Un <xs:sequence> impone orden, así que el XML salía válido
# desde un endpoint e inválido desde el otro.
#
# La alternativa era relajar el esquema a <xs:all> para que el orden no
# importara. No se hizo: el orden del contrato es parte de lo que el
# contrato promete, y lo que estaba mal no era el esquema, era que el
# servicio tenía dos formas de la misma entidad. Esta tabla deja una.
CAMPOS_DETECCION = (
    "deteccion_id", "regla_id", "unidad_organizacional_id", "unidad",
    "campania_id", "nivel", "valor_observado", "explicacion",
    "tipo_intervencion", "intervencion_sugerida", "descripcion", "orden",
    "fecha_deteccion",
)


def _deteccion_canonica(fila):
    """Reordena una detección al orden del contrato y descarta lo que no está.

    Se omiten las claves ausentes en lugar de rellenarlas con nulo: en el
    esquema casi todas son minOccurs="0", y un elemento con xsi:nil dice
    «lo consulté y no hay dato», que no es lo mismo que «este endpoint no
    entrega ese campo». La diferencia la lee un cliente.
    """
    return {c: fila[c] for c in CAMPOS_DETECCION if c in fila}


def _limpiar(doc):
    doc = dict(doc)
    doc.pop("_id", None)
    for k, v in list(doc.items()):
        if isinstance(v, dt.datetime):
            doc[k] = v.isoformat()
    return doc


def _unidad_existe(unidad_id):
    return bool(consultar_uno(
        "SELECT 1 AS ok FROM organizacion.unidad_organizacional "
        " WHERE unidad_organizacional_id = %s", (unidad_id,)))


def _campania_existe(campania_id):
    return bool(consultar_uno(
        "SELECT 1 AS ok FROM catalogo.campania WHERE campania_id = %s",
        (campania_id,)))


def _alcance_permite(unidad_id):
    """El alcance sale del perfil asignado, nunca del parámetro.

    Un alcance nulo significa toda la organización, que es lo correcto para
    el especialista de bienestar: su trabajo es transversal. El líder trae
    unidad y entonces solo pasa su propio subárbol.
    """
    permisos = getattr(g, "permisos", set()) or set()
    if "AGREGADO_GLOBAL" in permisos or "PARAMETRO_ADMIN" in permisos:
        return True
    fila = consultar_uno(
        "SELECT unidad_alcance_id FROM usuarios.usuario_perfil "
        " WHERE usuario_id = %s AND perfil_id = %s",
        (g.actor.get("sub"), g.actor.get("perfil_id")))
    alcance = (fila or {}).get("unidad_alcance_id")
    if alcance is None or alcance == unidad_id:
        return True
    return bool(consultar_uno(
        "WITH RECURSIVE arbol AS ("
        "  SELECT unidad_organizacional_id FROM organizacion.unidad_organizacional"
        "   WHERE unidad_organizacional_id = %s"
        "  UNION ALL"
        "  SELECT u.unidad_organizacional_id FROM organizacion.unidad_organizacional u"
        "    JOIN arbol a ON u.unidad_padre_id = a.unidad_organizacional_id)"
        " SELECT 1 AS ok FROM arbol WHERE unidad_organizacional_id = %s",
        (alcance, unidad_id)))


# ===================================================== catálogo de reglas
@app.get(f"{BASE}/reglas")
@requiere_permiso("RECOMENDACION_CONSULTAR", "AGREGADO_UNIDAD",
                  "AGREGADO_GLOBAL", "PARAMETRO_ADMIN")
def reglas():
    """Las reglas del motor, con su condición en texto legible.

    La condición legible no es decoración: es lo que permite que alguien sin
    acceso al código entienda por qué se disparó una detección, y lo que
    hace auditable al motor.
    """
    limite_consumo(maximo=120)
    filas = _filas(
        "SELECT r.regla_id, r.nombre, r.condicion_legible, r.dimension_id, "
        "       COALESCE(d.nombre, 'Indice global') AS dimension, "
        "       r.umbral_valor, r.comparador, r.campanias_consecutivas, "
        "       r.nivel, r.activa, "
        "       (SELECT count(*) FROM riesgo.deteccion x "
        "         WHERE x.regla_id = r.regla_id) AS detecciones_historicas "
        "  FROM riesgo.regla r "
        "  LEFT JOIN catalogo.dimension d USING (dimension_id) "
        " ORDER BY r.regla_id")
    for f in filas:
        f["intervenciones_sugeridas"] = [
            x["tipo_intervencion"] for x in consultar(
                "SELECT tipo_intervencion FROM riesgo.regla_recomendacion "
                " WHERE regla_id = %s ORDER BY orden", (f["regla_id"],))]
    return responder({"reglas": filas, "total": len(filas)},
                     200, raiz="reglas_respuesta")


# ========================================================== evaluación
@app.post(f"{BASE}/evaluar")
@requiere_permiso("RECOMENDACION_CONSULTAR", "AGREGADO_GLOBAL",
                  "PARAMETRO_ADMIN")
def evaluar():
    """Corre el motor sobre una campaña, para una unidad o para todas.

    La corrida completa queda guardada en MongoDB: qué reglas se evaluaron,
    qué se detectó y qué unidades no se pudieron evaluar. Sin ese registro,
    una detección de hace tres meses no se puede explicar, porque los
    umbrales pudieron cambiar desde entonces.
    """
    limite_consumo(maximo=20)
    cuerpo = cuerpo_peticion()
    campania_id = (cuerpo.get("campania_id") or "").strip()
    unidad_id = (cuerpo.get("unidad_organizacional_id") or "").strip() or None

    problemas = []
    if not campania_id:
        problemas.append({"campo": "campania_id", "problema": "es obligatorio"})
    elif not _campania_existe(campania_id):
        problemas.append({"campo": "campania_id", "problema": "no existe"})
    if unidad_id and not _unidad_existe(unidad_id):
        problemas.append({"campo": "unidad_organizacional_id",
                          "problema": "no existe"})
    if problemas:
        raise ErrorApi("VALIDACION", "La solicitud tiene campos invalidos.",
                       422, problemas)

    if unidad_id and not _alcance_permite(unidad_id):
        _bitacora("ACCESO_DENEGADO", "RECHAZADO_PERMISO", unidad_id)
        raise ErrorApi("FUERA_DE_ALCANCE",
                       "Tu perfil no tiene alcance sobre esa unidad.", 403)

    if unidad_id:
        unidades = [unidad_id]
    else:
        # Solo las unidades con algún agregado PUBLICADO en esa campaña: las
        # demás se reportan como no evaluables más abajo.
        unidades = [f["unidad_organizacional_id"] for f in consultar(
            "SELECT DISTINCT unidad_organizacional_id "
            "  FROM agregado.resultado_protegido "
            " WHERE campania_id = %s AND estado_publicacion = 'PUBLICADO' "
            " ORDER BY unidad_organizacional_id", (campania_id,))]
        unidades = [u for u in unidades if _alcance_permite(u)]

    detecciones = []
    for u in unidades:
        for f in _filas("SELECT * FROM riesgo.fn_evaluar_unidad(%s, %s)",
                        (u, campania_id)):
            f["unidad_organizacional_id"] = u
            detecciones.append(_deteccion_canonica(f))

    no_evaluables = _no_evaluables(campania_id, unidad_id)

    documento = {
        "corrida_id": f"ALG-{uuid.uuid4().hex[:12].upper()}",
        "campania_id": campania_id,
        "unidad_organizacional_id": unidad_id,
        "unidades_evaluadas": len(unidades),
        "detecciones": detecciones,
        "total_detecciones": len(detecciones),
        "por_nivel": {n: sum(1 for d in detecciones if d["nivel"] == n)
                      for n in NIVELES},
        "no_evaluables": no_evaluables,
        "total_no_evaluables": len(no_evaluables),
        "epsilon_consumido": 0.0,
        "ejecutado_por": (g.get("actor") or {}).get("sub"),
        "perfil_ejecutor": (g.get("actor") or {}).get("perfil"),
        "fecha": dt.datetime.now(dt.timezone.utc),
        "correlacion_id": getattr(g, "correlacion_id", ""),
    }
    # El motor trabaja con unidades y agregados: nada de lo que produce
    # identifica a una persona. Se verifica antes de escribir, igual que en
    # los demas servicios que tocan MongoDB.
    verificar_sin_identidad({k: v for k, v in documento.items()
                             if k != "ejecutado_por"})
    # Si MongoDB no responde, la EVALUACION NO SE PIERDE: se devuelve igual
    # y se avisa que no quedo guardada. Lo contrario -- fallar con 500 --
    # tiraria a la basura un calculo correcto por no poder archivarlo, y
    # quien pidio la evaluacion se quedaria sin el resultado y sin saber
    # por que. La bitacora de PostgreSQL si queda en los dos casos, asi que
    # el hecho de que la corrida ocurrio no se pierde nunca.
    persistida = True
    try:
        base()["corridas_algoritmo"].insert_one(dict(documento))
    except Exception as e:
        persistida = False
        app.logger.warning("La corrida %s no se pudo guardar en MongoDB: %s",
                           documento["corrida_id"], e)
    _bitacora("DETECCION_EVALUADA", "EXITO" if persistida else "PARCIAL",
              documento["corrida_id"])

    salida = _limpiar(documento)
    if not persistida:
        salida["advertencia_persistencia"] = (
            "La evaluacion se hizo y este es su resultado, pero no quedo "
            "guardada en el historial porque MongoDB no responde. No "
            "aparecera en /corridas.")
    return responder(salida, 201, raiz="corrida_respuesta")


def _no_evaluables(campania_id, unidad_id=None):
    """Unidades convocadas que el motor no pudo evaluar, y por qué.

    Es la parte que una implementación descuidada omite. Una unidad cuyos
    agregados se suprimieron todos no aparece en las detecciones, y si no se
    reporta aquí, la organización concluye que ahí no hay problema.
    """
    sql = (
        "SELECT cu.unidad_organizacional_id, uo.nombre AS unidad, "
        "       uo.plantilla_declarada, "
        "       count(rp.resultado_id) FILTER "
        "            (WHERE rp.estado_publicacion = 'PUBLICADO') AS publicados, "
        "       count(rp.resultado_id) FILTER "
        "            (WHERE rp.estado_publicacion <> 'PUBLICADO') AS suprimidos, "
        "       CASE "
        "         WHEN count(rp.resultado_id) = 0 "
        "           THEN 'Sin agregados calculados para esta campania.' "
        "         WHEN count(rp.resultado_id) FILTER "
        "              (WHERE rp.estado_publicacion = 'PUBLICADO') = 0 "
        "           THEN 'Todos sus agregados quedaron suprimidos: el grupo no "
        "alcanza el umbral k o la campania agoto su presupuesto de epsilon. "
        "El motor no puede concluir nada, y eso NO significa que no haya "
        "riesgo.' "
        "         ELSE NULL END AS motivo "
        "  FROM catalogo.campania_unidad cu "
        "  JOIN organizacion.unidad_organizacional uo USING (unidad_organizacional_id) "
        "  LEFT JOIN agregado.resultado_protegido rp "
        "         ON rp.unidad_organizacional_id = cu.unidad_organizacional_id "
        "        AND rp.campania_id = cu.campania_id "
        " WHERE cu.campania_id = %s "
        + ("   AND cu.unidad_organizacional_id = %s " if unidad_id else "") +
        " GROUP BY cu.unidad_organizacional_id, uo.nombre, uo.plantilla_declarada "
        " HAVING count(rp.resultado_id) FILTER "
        "        (WHERE rp.estado_publicacion = 'PUBLICADO') = 0 "
        " ORDER BY uo.nombre")
    params = (campania_id, unidad_id) if unidad_id else (campania_id,)
    return _filas(sql, params)


@app.get(f"{BASE}/cobertura")
@requiere_permiso("RECOMENDACION_CONSULTAR", "AGREGADO_GLOBAL",
                  "PARAMETRO_ADMIN", "BITACORA_CONSULTAR")
def cobertura():
    """Qué pudo ver el motor y qué no, en una campaña."""
    limite_consumo(maximo=120)
    campania_id = (request.args.get("campania_id") or "").strip()
    if not campania_id:
        raise ErrorApi("PARAMETRO_FALTANTE", "Falta 'campania_id'.", 400)
    if not _campania_existe(campania_id):
        raise ErrorApi("NO_ENCONTRADO", "No existe esa campania.", 404)

    convocadas = consultar_uno(
        "SELECT count(*) AS n FROM catalogo.campania_unidad WHERE campania_id = %s",
        (campania_id,))
    no_evaluables = _no_evaluables(campania_id)
    total = (convocadas or {}).get("n", 0)
    return responder({
        "campania_id": campania_id,
        "unidades_convocadas": total,
        "unidades_evaluables": total - len(no_evaluables),
        "unidades_no_evaluables": len(no_evaluables),
        "cobertura_porcentaje": (round(100.0 * (total - len(no_evaluables)) / total, 1)
                                 if total else None),
        "no_evaluables": no_evaluables,
        "nota": "Una unidad no evaluable no es una unidad sin riesgo: es una "
                "unidad sobre la que el mecanismo de privacidad no permite "
                "concluir nada.",
    }, 200, raiz="cobertura_respuesta")


# ========================================================= detecciones
@app.get(f"{BASE}/detecciones")
@requiere_permiso("RECOMENDACION_CONSULTAR", "AGREGADO_UNIDAD",
                  "AGREGADO_GLOBAL")
def detecciones():
    """Detecciones con su explicación y las intervenciones sugeridas."""
    limite_consumo(maximo=120)
    p, t = pagina()
    condiciones, params = ["1=1"], []
    if request.args.get("campania_id"):
        condiciones.append("v.campania_id = %s")
        params.append(request.args["campania_id"])
    if request.args.get("nivel"):
        nivel = request.args["nivel"].strip().upper()
        if nivel not in NIVELES:
            raise ErrorApi("PARAMETRO_INVALIDO",
                           f"Nivel invalido. Validos: {', '.join(NIVELES)}.", 400)
        condiciones.append("v.nivel = %s")
        params.append(nivel)
    unidad = request.args.get("unidad_organizacional_id")
    if unidad:
        if not _alcance_permite(unidad):
            raise ErrorApi("FUERA_DE_ALCANCE",
                           "Tu perfil no tiene alcance sobre esa unidad.", 403)
        condiciones.append("v.unidad_organizacional_id = %s")
        params.append(unidad)

    donde = " AND ".join(condiciones)
    total = (consultar_uno(
        f"SELECT count(*) AS n FROM riesgo.v_recomendaciones v WHERE {donde}",
        tuple(params)) or {}).get("n", 0)
    filas = _filas(
        f"SELECT v.* FROM riesgo.v_recomendaciones v WHERE {donde} "
        " ORDER BY v.campania_id DESC, v.unidad, v.orden "
        " LIMIT %s OFFSET %s", tuple(params) + (t, (p - 1) * t))

    # El alcance se vuelve a aplicar sobre el resultado: sin el filtro de
    # unidad, un lider veria el arbol completo.
    filas = [_deteccion_canonica(f) for f in filas
             if _alcance_permite(f["unidad_organizacional_id"])]
    # El sobre pasa por responder() y no se devuelve tal cual: devolver el
    # diccionario hace que Flask lo serialice como JSON SIEMPRE, y entonces
    # `?formato=xml` se ignora en silencio. La aplicacion de escritorio, que
    # solo habla XML, recibia JSON y fallaba al parsear con un mensaje que
    # no apuntaba a la causa.
    return responder(sobre_pagina(filas, total, p, t, clave="detecciones"),
                     200, raiz="detecciones_respuesta")


def _historial():
    """Colección de corridas, o 503 explicativo si MongoDB no responde.

    POR QUÉ NO SE DEJA QUE FALLE SOLO
    ---------------------------------
    MongoDB es una dependencia OPCIONAL de este servicio: el motor evalúa
    leyendo agregados ya publicados de PostgreSQL, y MongoDB solo guarda el
    historial de corridas. La sonda /health/ready lo refleja y responde
    «degradado» con 200 en lugar de sacar el servicio de rotación.

    Pero declararlo opcional solo es honesto si los endpoints que SÍ lo
    necesitan lo dicen. Sin esto, una caída de MongoDB daba 500
    ERROR_INTERNO: el cliente no podía distinguir «el historial no está
    disponible ahora» de «el motor está roto», y la diferencia decide si
    conviene reintentar o avisar.
    """
    try:
        coleccion = base()["corridas_algoritmo"]
        coleccion.estimated_document_count()
        return coleccion
    except Exception as e:
        raise ErrorApi(
            "HISTORIAL_NO_DISPONIBLE",
            "El historial de corridas vive en MongoDB y MongoDB no responde. "
            "La evaluacion de riesgo sigue funcionando (lee de PostgreSQL): "
            "lo unico que no se puede consultar ahora es el registro de "
            "corridas anteriores.", 503,
            [{"campo": "mongodb", "problema": str(e)[:160]}])


# ========================================================== simulación
@app.post(f"{BASE}/simular")
@requiere_permiso("PARAMETRO_ADMIN", "AGREGADO_GLOBAL")
def simular():
    """Qué detectaría una regla con otro umbral. NO escribe nada.

    Permite a un comité mover un umbral con evidencia: cuántas unidades
    más entrarían en atención, y cuáles. La alternativa es cambiar el
    parámetro en producción y ver qué pasa, que con datos de bienestar
    laboral no es aceptable.
    """
    limite_consumo(maximo=30)
    cuerpo = cuerpo_peticion()
    regla_id = (cuerpo.get("regla_id") or "").strip()
    campania_id = (cuerpo.get("campania_id") or "").strip()
    umbral = cuerpo.get("umbral_valor")

    regla = consultar_uno(
        "SELECT regla_id, nombre, dimension_id, umbral_valor, comparador, nivel "
        "  FROM riesgo.regla WHERE regla_id = %s", (regla_id,))
    if not regla:
        raise ErrorApi("NO_ENCONTRADO", "No existe esa regla.", 404)
    if not _campania_existe(campania_id):
        raise ErrorApi("NO_ENCONTRADO", "No existe esa campania.", 404)
    if regla["umbral_valor"] is None:
        raise ErrorApi("OPERACION_NO_PERMITIDA",
                       "Esa regla no evalua un umbral sino una tendencia "
                       "sostenida: no hay un valor que simular.", 400)
    try:
        umbral = float(regla["umbral_valor"]) if umbral is None else float(umbral)
    except (TypeError, ValueError):
        raise ErrorApi("VALIDACION", "La solicitud tiene campos invalidos.", 422,
                       [{"campo": "umbral_valor", "problema": "debe ser numerico"}])

    comparador = regla["comparador"]
    if comparador not in ("<", "<=", ">", ">="):
        raise ErrorApi("OPERACION_NO_PERMITIDA",
                       f"Comparador no soportado: {comparador}.", 400)

    filas = _filas(
        "SELECT rp.unidad_organizacional_id, uo.nombre AS unidad, "
        "       rp.valor_protegido, rp.precision_advertencia "
        "  FROM agregado.resultado_protegido rp "
        "  JOIN organizacion.unidad_organizacional uo USING (unidad_organizacional_id) "
        " WHERE rp.campania_id = %s AND rp.estado_publicacion = 'PUBLICADO' "
        "   AND (%s IS NULL OR rp.dimension_id = %s) "
        "   AND (%s IS NOT NULL OR rp.dimension_id IS NULL) "
        " ORDER BY uo.nombre",
        (campania_id, regla["dimension_id"], regla["dimension_id"],
         regla["dimension_id"]))

    def dispara(v, u):
        if v is None:
            return False
        return {"<": v < u, "<=": v <= u, ">": v > u, ">=": v >= u}[comparador]

    con_umbral_actual = [f for f in filas
                         if dispara(f["valor_protegido"],
                                    float(regla["umbral_valor"]))]
    con_umbral_nuevo = [f for f in filas
                        if dispara(f["valor_protegido"], umbral)]
    nuevas = [f for f in con_umbral_nuevo if f not in con_umbral_actual]
    dejarian = [f for f in con_umbral_actual if f not in con_umbral_nuevo]

    # Advertencia honesta: una unidad cuyo valor trae advertencia de
    # precision esta cerca del ruido, y mover el umbral unas decimas la
    # mete o la saca por azar y no por su situacion real.
    cerca_del_ruido = [f for f in con_umbral_nuevo if f["precision_advertencia"]]

    return responder({
        "regla_id": regla["regla_id"],
        "nombre": regla["nombre"],
        "campania_id": campania_id,
        "comparador": comparador,
        "umbral_actual": float(regla["umbral_valor"]),
        "umbral_simulado": umbral,
        "unidades_con_valor_publicado": len(filas),
        "detectadas_con_umbral_actual": len(con_umbral_actual),
        "detectadas_con_umbral_simulado": len(con_umbral_nuevo),
        "entrarian": nuevas,
        "saldrian": dejarian,
        "con_advertencia_de_precision": len(cerca_del_ruido),
        "nota": "Simulacion de solo lectura: no se creo ninguna deteccion. "
                "Las unidades con advertencia de precision estan cerca del "
                "ruido, de modo que mover el umbral unas decimas las mete o "
                "las saca por azar y no por su situacion.",
        "epsilon_consumido": 0.0,
    }, 200, raiz="simulacion_respuesta")


# =========================================================== corridas
@app.get(f"{BASE}/corridas")
@requiere_permiso("RECOMENDACION_CONSULTAR", "AGREGADO_GLOBAL",
                  "PARAMETRO_ADMIN", "BITACORA_CONSULTAR")
def corridas():
    """Historial de corridas del motor, desde MongoDB."""
    limite_consumo(maximo=120)
    p, t = pagina()
    filtro = {}
    if request.args.get("campania_id"):
        filtro["campania_id"] = request.args["campania_id"]
    coleccion = _historial()
    total = coleccion.count_documents(filtro)
    cursor_mongo = (coleccion.find(filtro, {"detecciones": 0, "no_evaluables": 0})
                    .sort("fecha", DESCENDING).skip((p - 1) * t).limit(t))
    return responder(sobre_pagina([_limpiar(d) for d in cursor_mongo],
                                  total, p, t, clave="corridas"),
                     200, raiz="corridas_respuesta")


@app.get(f"{BASE}/corridas/<corrida_id>")
@requiere_permiso("RECOMENDACION_CONSULTAR", "AGREGADO_GLOBAL",
                  "PARAMETRO_ADMIN", "BITACORA_CONSULTAR")
def corrida(corrida_id):
    doc = _historial().find_one({"corrida_id": corrida_id})
    if not doc:
        raise ErrorApi("NO_ENCONTRADO", "No existe esa corrida.", 404)
    return responder(_limpiar(doc), 200, raiz="corrida_respuesta")


# ===================================================== análisis complejo
#
# El motor de reglas de más arriba evalúa UMBRALES: «si la dimensión X
# está por debajo de Y, detecta». Es correcto y es lo que pide el
# catálogo de reglas, pero tiene dos límites que no se arreglan ajustando
# los umbrales:
#
#   - Compara cada unidad contra una constante, no contra sus pares. Los
#     turnos nocturnos salen como anomalía todos los semestres, porque un
#     turno nocturno tiene peor descanso que una oficina y eso no es un
#     hallazgo.
#   - No distingue estar mal de estar empeorando. Una unidad en 2.8 y
#     estable ya tocó fondo; otra en 3.4 cayendo 0.2 por campaña llegará
#     más abajo en un año. La primera dispara la regla y la segunda no,
#     y es la segunda donde una intervención todavía sirve.
#
# El análisis complejo (paquete `analitica`) contesta eso: agrupa las
# unidades por perfil con k-medias, mide la desviación de cada una contra
# el centroide de SU grupo, decide si el ruido de privacidad puede
# explicar esa desviación, estima la tendencia con Theil-Sen y
# Mann-Kendall, y prioriza con un puntaje desglosado.
#
# Igual que el motor de reglas: lee solo lo PUBLICADO y consume cero
# épsilon.
from analitica import motor as motor_analitico

PREFIJO_CACHE = "analisis:"

# Diez minutos. El análisis depende solo de agregados PUBLICADOS, y
# publicar es una operación deliberada que nadie hace cada minuto: un TTL
# corto gastaría CPU recalculando lo mismo. Y no es como el presupuesto de
# épsilon, donde un dato viejo lleva a creer que queda presupuesto cuando
# ya se agotó; aquí un informe de hace diez minutos describe los mismos
# datos publicados.
TTL_ANALISIS = 600


def _unidades_en_alcance():
    """El conjunto de unidades que el solicitante puede ver, o None = todas.

    Se resuelve UNA vez y no por unidad. `_alcance_permite` hace una
    consulta recursiva cada vez que se le llama, y el análisis trabaja con
    cientos de unidades: llamarla en un bucle convertía una respuesta de
    milisegundos en cientos de consultas.
    """
    permisos = getattr(g, "permisos", set()) or set()
    if "AGREGADO_GLOBAL" in permisos or "PARAMETRO_ADMIN" in permisos:
        return None
    fila = consultar_uno(
        "SELECT unidad_alcance_id FROM usuarios.usuario_perfil "
        " WHERE usuario_id = %s AND perfil_id = %s",
        (g.actor.get("sub"), g.actor.get("perfil_id")))
    alcance = (fila or {}).get("unidad_alcance_id")
    if alcance is None:
        return None
    return {f["unidad_organizacional_id"] for f in consultar(
        "WITH RECURSIVE arbol AS ("
        "  SELECT unidad_organizacional_id FROM organizacion.unidad_organizacional"
        "   WHERE unidad_organizacional_id = %s"
        "  UNION ALL"
        "  SELECT u.unidad_organizacional_id FROM organizacion.unidad_organizacional u"
        "    JOIN arbol a ON u.unidad_padre_id = a.unidad_organizacional_id)"
        " SELECT unidad_organizacional_id FROM arbol", (alcance,))}


def _ultima_campania():
    fila = consultar_uno(
        "SELECT campania_id FROM catalogo.campania "
        " WHERE campania_id IN (SELECT DISTINCT campania_id "
        "                         FROM agregado.resultado_protegido "
        "                        WHERE estado_publicacion = 'PUBLICADO') "
        " ORDER BY secuencia DESC LIMIT 1")
    return (fila or {}).get("campania_id")


def _datos_para_analisis(campania_id):
    """Las dos entradas del motor: la matriz de la campaña y las series.

    POR QUÉ LAS SERIES SE ARMAN EN PYTHON Y NO EN SQL
    -------------------------------------------------
    La serie de una unidad tiene que incluir las campañas en que NO
    publicó, con valor nulo, porque el análisis de tendencia cuenta los
    puntos suprimidos y los reporta. Una serie que solo trae lo publicado
    hace creer que la unidad tiene seis lecturas seguidas cuando tiene
    seis de doce, y la pendiente sale calculada sobre campañas que no son
    consecutivas.

    Traer eso en SQL exige cruzar las unidades convocadas por las
    dimensiones y hacer un LEFT JOIN contra los resultados: un producto
    cartesiano de tres tablas para rellenar huecos. Armarlo aquí son dos
    consultas con índice y un bucle.
    """
    secuencia = (consultar_uno(
        "SELECT secuencia FROM catalogo.campania WHERE campania_id = %s",
        (campania_id,)) or {}).get("secuencia")

    filas_campania = _filas(
        "SELECT unidad_organizacional_id, dimension_id, valor_protegido, "
        "       escala_ruido, n_observaciones "
        "  FROM agregado.resultado_protegido "
        " WHERE campania_id = %s AND estado_publicacion = 'PUBLICADO' "
        "   AND dimension_id IS NOT NULL", (campania_id,))

    publicados = _filas(
        "SELECT rp.unidad_organizacional_id, rp.dimension_id, c.secuencia, "
        "       rp.valor_protegido, rp.escala_ruido "
        "  FROM agregado.resultado_protegido rp "
        "  JOIN catalogo.campania c USING (campania_id) "
        " WHERE rp.estado_publicacion = 'PUBLICADO' "
        "   AND rp.dimension_id IS NOT NULL AND c.secuencia <= %s",
        (secuencia,))

    convocadas = {}
    for f in consultar(
            "SELECT cu.unidad_organizacional_id, c.secuencia "
            "  FROM catalogo.campania_unidad cu "
            "  JOIN catalogo.campania c USING (campania_id) "
            " WHERE c.secuencia <= %s", (secuencia,)):
        convocadas.setdefault(f["unidad_organizacional_id"], set()).add(
            f["secuencia"])

    dimensiones = sorted({f["dimension_id"] for f in filas_campania})
    valores = {}
    for f in publicados:
        valores[(f["unidad_organizacional_id"], f["dimension_id"],
                 f["secuencia"])] = (f["valor_protegido"], f["escala_ruido"])

    series = {}
    for unidad, secuencias in convocadas.items():
        # El plazo de la peticion se consulta aqui, entre unidades, que es
        # donde es seguro rendirse: nada a medias y ninguna transaccion
        # abierta. Ver `exigir_tiempo` en comun/servicio.py — este bucle es
        # Python puro y `statement_timeout` no lo puede cancelar.
        exigir_tiempo("las series por unidad")
        por_dimension = {}
        for dim in dimensiones:
            puntos = []
            for s in sorted(secuencias):
                valor, escala = valores.get((unidad, dim, s), (None, None))
                puntos.append((s, valor, escala))
            por_dimension[dim] = puntos
        series[unidad] = por_dimension
    return filas_campania, series


def _recortar_a_alcance(informe, permitidas):
    """Deja en el informe solo lo que el solicitante puede ver.

    El análisis se calcula SIEMPRE sobre la organización completa, y eso
    no es negociable: el sentido del método es comparar cada unidad con
    sus pares, y un líder que solo viera su subárbol compararía sus tres
    equipos entre sí y el resultado no significaría nada.

    Lo que se recorta es la SALIDA. Los centroides y la silueta describen
    a toda la organización, así que se reemplazan por una nota: no son un
    riesgo de privacidad —salen de valores ya publicados— pero sí son
    información de áreas que no le corresponden.
    """
    if permitidas is None:
        return informe
    salida = dict(informe)
    salida["priorizadas"] = [p for p in informe["priorizadas"]
                             if p["unidad_organizacional_id"] in permitidas]
    salida["tendencias"] = {u: t for u, t in informe["tendencias"].items()
                            if u in permitidas}
    salida["unidades_sin_perfil_completo"] = [
        x for x in informe["unidades_sin_perfil_completo"]
        if x["unidad_organizacional_id"] in permitidas]
    salida["agrupamiento"] = {
        "nota": "El agrupamiento se calculo sobre la organizacion completa "
                "—es lo que hace significativa la comparacion con pares— "
                "pero sus centroides describen areas fuera de tu alcance, "
                "asi que no se incluyen.",
        "grupos": informe["agrupamiento"].get("grupos"),
        "silueta": informe["agrupamiento"].get("silueta"),
    }
    salida["alcance_aplicado"] = {
        "unidades_visibles": len(permitidas),
        "unidades_analizadas_en_total": informe["unidades_analizadas"],
    }
    return salida


@app.get(f"{BASE}/analisis")
@requiere_permiso("RECOMENDACION_CONSULTAR", "AGREGADO_UNIDAD",
                  "AGREGADO_GLOBAL", "PARAMETRO_ADMIN")
def analisis():
    """Análisis complejo: agrupamiento, anomalías contra pares y tendencia.

    Parámetros:
      campania_id  — la campaña a analizar. Por omisión, la última con
                     resultados publicados.
      sin_cache=1  — recalcula ignorando la caché. Existe para poder medir
                     el costo real del algoritmo, que es justo lo que la
                     caché esconde.

    La caché guarda el informe GLOBAL y el recorte por alcance se aplica
    después de leerla. Al revés —cachear lo ya recortado— la clave tendría
    que incluir el alcance de quien pregunta, y un fallo al construir esa
    clave serviría a un líder el informe completo de la organización.
    """
    limite_consumo(maximo=30)
    campania_id = (request.args.get("campania_id") or "").strip() or _ultima_campania()
    if not campania_id:
        raise ErrorApi("SIN_DATOS",
                       "Ninguna campania tiene resultados publicados todavia: "
                       "no hay nada que analizar.", 409)
    if not _campania_existe(campania_id):
        raise ErrorApi("NO_ENCONTRADO", "No existe esa campania.", 404)

    sin_cache = (request.args.get("sin_cache") or "").lower() in ("1", "true", "si")
    # La semilla va en la clave. El agrupamiento es determinista para una
    # semilla dada, así que si alguien la cambia los informes guardados
    # dejan de corresponder al código que los produciría hoy: con la
    # semilla en la clave, caducan solos en lugar de servirse como si
    # fueran del algoritmo actual.
    clave = f"{PREFIJO_CACHE}{campania_id}:{motor_analitico.ag.SEMILLA}"
    r, informe, desde_cache = None, None, False

    try:
        r = obtener_redis()
        if not sin_cache:
            crudo = r.get(clave)
            if crudo:
                informe = json.loads(crudo)
                desde_cache = True
                r.incr(f"{PREFIJO_CACHE}_metricas:aciertos")
    except Exception as e:                               # noqa: BLE001
        # Una caida de Redis no puede tumbar el analisis: solo lo hace
        # mas lento. Se registra y se sigue contra PostgreSQL.
        r = None
        app.logger.warning("Redis no disponible para %s: %s", clave, e)

    if informe is None:
        filas_campania, series = _datos_para_analisis(campania_id)
        if not filas_campania:
            raise ErrorApi(
                "SIN_DATOS",
                "Esa campania no tiene ningun agregado publicado. No es que "
                "no haya riesgo: es que el umbral k no permitio publicar "
                "nada, y sobre eso el analisis no puede concluir.", 409)
        informe = motor_analitico.analizar(filas_campania, series)
        informe["campania_id"] = campania_id
        if r is not None:
            try:
                r.set(clave, json.dumps(informe, default=str), ex=TTL_ANALISIS)
                r.incr(f"{PREFIJO_CACHE}_metricas:fallos")
            except Exception as e:                       # noqa: BLE001
                app.logger.warning("No se pudo cachear %s: %s", clave, e)

    informe["origen"] = "cache" if desde_cache else "calculado"
    informe["cache_ttl_segundos"] = TTL_ANALISIS
    _bitacora("ANALISIS_EJECUTADO", "EXITO", campania_id)
    return responder(_recortar_a_alcance(informe, _unidades_en_alcance()),
                     200, raiz="analisis_respuesta")


@app.post(f"{BASE}/indices")
@requiere_permiso("PARAMETRO_ADMIN")
def crear_indices():
    creados = asegurar_indices(INDICES)
    return responder({"indices": creados, "total": len(creados)},
                     200, raiz="indices_respuesta")
