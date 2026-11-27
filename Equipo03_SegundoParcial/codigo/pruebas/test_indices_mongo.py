"""
Cada consulta a MongoDB tiene que tener un índice detrás.

POR QUÉ ESTA PRUEBA ES ESTÁTICA Y NO UNA MEDICIÓN
--------------------------------------------------
Las consultas a PostgreSQL se midieron con `EXPLAIN ANALYZE` sobre datos
masivos, y de ahí salieron tres defectos reales: un índice inerte por una
columna de más en el `ORDER BY` de una vista, una subconsulta correlacionada
sin índice que recorría una tabla 1 372 veces, y un plan que confirmaba lo
que se suponía.

Con MongoDB no se puede hacer lo mismo aquí: no está instalado en este
ambiente —las pruebas usan `mongomock`, que no implementa `explain()`— y
no se puede instalar. Así que esto NO mide: **lee las consultas del código
y comprueba que cada una tenga un índice declarado que la cubra.**

Es menos que una medición y encuentra la misma clase de defecto: una
consulta sin índice detrás. Y tiene una ventaja sobre la medición: no
depende de que la colección haya crecido lo suficiente para que se note.

QUÉ ENCONTRÓ AL ESCRIBIRLA
---------------------------
Cinco consultas sin índice, de 44:

  1. `documentos.find_one({hash_contenido, tipo})` — la consulta de CADA
     descarga de evidencia. Ningún índice empezaba por hash_contenido.
  2. `documentos.find({campania_id}).sort(fecha_creacion)` — el índice
     tenía campania_id en SEGUNDA posición.
  3. `dispositivos_push.delete_one({token})` — token era la segunda
     columna de su índice.
  4. `/notificaciones/mias` sin `solo_sin_leer` — el índice es
     (destinatario, leida, fecha_creacion) y sin fijar `leida` no se puede
     usar para ORDENAR.
  5. `documentos.find({}).sort(fecha_creacion)` — ningún índice empezaba
     por fecha_creacion.

Las dos últimas son las que más importan, y no por lentas: **un `sort` sin
índice en MongoDB se hace en memoria, tiene un límite de 32 MB y falla al
pasarlo.** No se degrada: deja de funcionar, y justo cuando la colección
creció.

LAS DOS REGLAS QUE SE APLICAN
------------------------------
Son las de MongoDB y no invenciones de esta prueba:

**Prefijo.** Un índice compuesto `(a, b, c)` sirve para consultas que
filtran por `a`, por `(a, b)` o por `(a, b, c)`. NO sirve para una que
filtra solo por `b` o solo por `c`.

**Orden.** Para que un índice sirva para ordenar por `k`, las claves que
van antes de `k` en el índice tienen que estar fijadas por una igualdad en
el filtro. Con `(destinatario, leida, fecha_creacion)` y un filtro que
solo trae `destinatario`, el índice encuentra las filas pero el orden se
hace en memoria.
"""
import ast
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVICIOS = ("algorithms-service", "documents-service",
             "notifications-service", "reports-service")

METODOS_DE_LECTURA = ("find", "find_one", "count_documents", "distinct")
METODOS_DE_ESCRITURA = ("update_one", "update_many", "delete_one",
                        "delete_many", "replace_one")

# Consultas que NO necesitan índice, con el motivo. Una lista de
# excepciones sin motivo escrito es una lista que crece hasta que la
# prueba no comprueba nada.
TOLERADAS = {
    # `estimated_document_count` no lleva filtro: lee los metadatos de la
    # colección y no recorre nada.
    "estimated_document_count",
}


def archivo_de(servicio):
    return os.path.join(RAIZ, "apps", "microservicios", servicio, "app.py")


def indices_declarados(servicio):
    """Lee el diccionario INDICES del servicio, ejecutándolo.

    Se evalúa el literal en lugar de analizarlo a mano porque usa las
    constantes ASCENDING y DESCENDING de pymongo, y reimplementar aquí
    cómo se resuelven sería una segunda copia de algo que ya está escrito.
    """
    texto = open(archivo_de(servicio), encoding="utf-8").read()
    m = re.search(r"^INDICES = (\{.*?^\})", texto, re.S | re.M)
    if not m:
        return {}
    from pymongo import ASCENDING, DESCENDING
    return eval(m.group(1), {"ASCENDING": ASCENDING,          # noqa: S307
                             "DESCENDING": DESCENDING})


def claves_de(nodo):
    """Las claves literales de un dict pasado como filtro, o None."""
    if isinstance(nodo, ast.Dict):
        claves = []
        for k in nodo.keys:
            if not isinstance(k, ast.Constant):
                return None                   # clave calculada
            claves.append(k.value)
        return claves
    return None


def coleccion_de(nodo):
    """`base()["coleccion"].find(...)` -> "coleccion", o None.

    Resuelve también la forma en dos pasos, muy común en estos servicios:

        col = base()["documentos"]
        col.find(...)
    """
    objetivo = nodo.func.value
    # base()["x"].metodo(...)
    if (isinstance(objetivo, ast.Subscript)
            and isinstance(objetivo.slice, ast.Constant)):
        return objetivo.slice.value
    # col.metodo(...)  — se resuelve con el mapa de asignaciones
    if isinstance(objetivo, ast.Name):
        return ("variable", objetivo.id)
    # cursor.sort(...) y demás encadenados
    return None


def mapa_de_variables(arbol):
    """{nombre_de_variable: coleccion} para `x = base()["coleccion"]`."""
    mapa = {}
    for n in ast.walk(arbol):
        if not isinstance(n, ast.Assign) or len(n.targets) != 1:
            continue
        if not isinstance(n.targets[0], ast.Name):
            continue
        valor = n.value
        if (isinstance(valor, ast.Subscript)
                and isinstance(valor.slice, ast.Constant)
                and isinstance(valor.value, ast.Call)):
            mapa[n.targets[0].id] = valor.slice.value
    return mapa


def claves_garantizadas_de_variable(arbol, nombre, antes_de):
    """Las claves que un filtro armado en una variable SIEMPRE lleva.

    POR QUÉ HACE FALTA RESOLVER ESTO
    --------------------------------
    La primera versión de esta prueba trataba todo filtro armado en una
    variable como «podría estar vacío», y produjo tres falsos positivos:
    el listado de notificaciones y el de reportes **siempre** llevan una
    clave —`destinatario_usuario_id` el uno, `tipo` el otro— porque se
    asigna en el literal inicial o con un `setdefault` incondicional.

    Una prueba que grita en falso se acaba desactivando, y entonces deja
    de encontrar los casos de verdad. Así que se resuelve lo que se puede
    resolver: las claves del literal de la asignación y las que se agregan
    con `setdefault`, que son incondicionales. Las que se agregan dentro
    de un `if` NO cuentan: son justamente las que pueden faltar.
    """
    claves = set()
    for n in ast.walk(arbol):
        # filtro = {"a": ...}
        if (isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id == nombre
                and n.lineno < antes_de):
            literales = claves_de(n.value)
            if literales:
                claves |= set(literales)
        # filtro.setdefault("a", ...)  -> incondicional
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "setdefault"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == nombre
                and n.lineno < antes_de
                and n.args and isinstance(n.args[0], ast.Constant)):
            claves.add(n.args[0].value)
    return claves


def orden_de(nodo, fuente):
    """El campo por el que ordena una consulta, si la línea trae `.sort(`.

    Se busca en el TEXTO de las líneas siguientes en lugar de recorrer el
    árbol hacia arriba porque `find(...).sort(...)` encadena, y en el
    árbol el `sort` es el padre del `find`: desde el `find` no se llega.
    """
    lineas = fuente.splitlines()
    desde = nodo.lineno - 1
    hasta = min(len(lineas), desde + 4)
    bloque = "\n".join(lineas[desde:hasta])
    m = re.search(r'\.sort\(\s*"([a-z_.]+)"', bloque)
    return m.group(1) if m else None


def cubre(indice, campos_filtro, campo_orden):
    """¿Este índice cubre un filtro por `campos_filtro` y un orden por
    `campo_orden`? Aplica las reglas de prefijo y de orden de MongoDB.
    """
    claves = [c for c, _ in indice]
    filtro = set(campos_filtro)

    # Regla del prefijo: la primera clave del índice tiene que estar en el
    # filtro, o el índice no se usa para buscar.
    if claves and claves[0] not in filtro:
        # Salvo que no haya filtro y el índice sirva para el orden: una
        # consulta sin filtro que ordena por la primera clave sí lo usa.
        if filtro or claves[0] != campo_orden:
            return False

    if campo_orden is None:
        return True

    # Regla del orden: las claves anteriores a la de orden tienen que
    # estar fijadas por igualdad en el filtro.
    if campo_orden not in claves:
        return False
    for clave in claves[:claves.index(campo_orden)]:
        if clave not in filtro:
            return False
    return True


def consultas_de(servicio):
    """Todas las consultas con filtro literal, con su colección y orden."""
    fuente = open(archivo_de(servicio), encoding="utf-8").read()
    arbol = ast.parse(fuente)
    variables = mapa_de_variables(arbol)
    salida = []
    for n in ast.walk(arbol):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        metodo = n.func.attr
        if metodo not in METODOS_DE_LECTURA + METODOS_DE_ESCRITURA:
            continue
        if metodo in TOLERADAS:
            continue
        col = coleccion_de(n)
        if isinstance(col, tuple):
            col = variables.get(col[1])
        if not col:
            continue
        claves = claves_de(n.args[0]) if n.args else []
        if claves is None:
            # Filtro armado en una variable: se resuelven las claves que
            # lleva SIEMPRE —el literal de la asignación y los
            # `setdefault`— y se marcan como parciales, porque puede
            # llevar más.
            nombre = (n.args[0].id if isinstance(n.args[0], ast.Name)
                      else None)
            seguras = (claves_garantizadas_de_variable(arbol, nombre, n.lineno)
                       if nombre else set())
            salida.append({"linea": n.lineno, "metodo": metodo,
                           "coleccion": col, "filtro": None,
                           "filtro_minimo": sorted(seguras),
                           "orden": orden_de(n, fuente)})
            continue
        salida.append({"linea": n.lineno, "metodo": metodo, "coleccion": col,
                       "filtro": claves, "filtro_minimo": claves,
                       "orden": orden_de(n, fuente)})
    return salida


@pytest.mark.parametrize("servicio", SERVICIOS)
def test_cada_consulta_con_filtro_literal_tiene_un_indice(servicio):
    """La prueba que encontró los cinco huecos.

    Solo mira las consultas cuyo filtro está escrito literalmente: las que
    lo arman en una variable se comprueban en la prueba de abajo, que es
    más débil a propósito y lo dice.
    """
    declarados = indices_declarados(servicio)
    sin_indice = []
    for c in consultas_de(servicio):
        if c["filtro"] is None:
            continue
        if not c["filtro"] and not c["orden"]:
            continue                          # sin filtro ni orden
        indices = declarados.get(c["coleccion"], [])
        if not any(cubre(i[0], c["filtro"], c["orden"]) for i in indices):
            sin_indice.append(
                f"L{c['linea']} {c['coleccion']}.{c['metodo']}"
                f"(filtro={c['filtro']}"
                + (f", orden={c['orden']}" if c["orden"] else "") + ")")

    assert not sin_indice, (
        f"{servicio}: estas consultas no tienen un indice que las cubra:\n  "
        + "\n  ".join(sin_indice)
        + "\n\nRecuerda las dos reglas de MongoDB:\n"
          "  * PREFIJO: un indice (a,b,c) no sirve para un filtro solo por b.\n"
          "  * ORDEN: para ordenar por k, las claves anteriores a k en el\n"
          "    indice tienen que estar fijadas por igualdad en el filtro.\n"
          "Y un sort sin indice se hace en memoria, tiene un limite de\n"
          "32 MB y FALLA al pasarlo: no se degrada, deja de funcionar.")


@pytest.mark.parametrize("servicio", SERVICIOS)
def test_las_consultas_con_filtro_armado_ordenan_por_algo_indexado(servicio):
    """Las que arman el filtro en una variable: al menos el orden.

    El filtro no se puede resolver leyendo el código —se construye con los
    parámetros de la petición— así que de estas no se puede afirmar que
    usen índice para buscar. Lo que sí se puede exigir es que el campo por
    el que ORDENAN sea la primera clave de algún índice: eso es lo que
    salva al `sort` de hacerse en memoria en el caso en que el filtro
    quede vacío, que es justo el que más filas trae.

    Es una comprobación más débil que la de arriba y conviene saber que lo
    es. La alternativa —no comprobar nada de estas trece consultas— era
    peor.
    """
    declarados = indices_declarados(servicio)
    malas = []
    for c in consultas_de(servicio):
        if c["filtro"] is not None or not c["orden"]:
            continue
        indices = declarados.get(c["coleccion"], [])
        # Con las claves que el filtro lleva SIEMPRE: si con esas ya hay
        # un indice que cubre el orden, la consulta esta a salvo aunque el
        # filtro traiga mas cosas segun los parametros.
        if any(cubre(i[0], c["filtro_minimo"], c["orden"]) for i in indices):
            continue
        primeras = {i[0][0][0] for i in indices if i[0]}
        malas.append(
            f"L{c['linea']} {c['coleccion']}.{c['metodo']} ordena por "
            f"'{c['orden']}' con un filtro que solo garantiza "
            f"{c['filtro_minimo'] or 'nada'}, y ningun indice lo cubre "
            f"(empiezan por: {sorted(primeras)})")

    assert not malas, (
        f"{servicio}: en el peor caso de su filtro, estas consultas "
        f"ordenan en memoria:\n  " + "\n  ".join(malas))


def test_la_prueba_de_verdad_encuentra_consultas():
    """Que esta prueba no esté comprobando el vacío.

    Si alguien cambia la forma de hacer las consultas —otro ayudante, otra
    biblioteca— el analizador dejaría de encontrarlas y las dos pruebas de
    arriba pasarían sin mirar nada. Eso es lo que hay que detectar.
    """
    total = sum(len(consultas_de(s)) for s in SERVICIOS)
    assert total >= 30, (
        f"El analizador solo encontro {total} consultas a MongoDB en los "
        f"cuatro servicios. Habia 44 cuando se escribio esta prueba: si "
        f"bajo tanto, es que dejo de reconocer la forma de las consultas y "
        f"las otras dos pruebas estan pasando sin comprobar nada.")


def test_cada_coleccion_que_se_usa_declara_sus_indices():
    """Una colección sin índices declarados no aparece en ningún lado.

    `asegurar_indices` crea los que estén en el diccionario INDICES. Una
    colección que se consulta y no está ahí no tiene ni el índice de su
    identificador, y nada lo dice.
    """
    faltan = []
    for servicio in SERVICIOS:
        declarados = set(indices_declarados(servicio))
        usadas = {c["coleccion"] for c in consultas_de(servicio)}
        for col in sorted(usadas - declarados):
            faltan.append(f"{servicio}: '{col}'")
    assert not faltan, (
        f"Estas colecciones se consultan y no declaran indices en "
        f"INDICES:\n  " + "\n  ".join(faltan))
