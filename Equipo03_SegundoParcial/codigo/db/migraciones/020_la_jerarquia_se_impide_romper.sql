-- =====================================================================
-- 020 — La invariante de la jerarquía deja de ser una comprobación y
--       pasa a ser una restricción
--
-- QUÉ PROTEGE LA INVARIANTE
-- -------------------------
-- El control de inferencia por diferencia descansa en que la plantilla
-- declarada de un padre sea al menos la suma de las de sus hijas. Si no,
-- el residuo
--
--     residuo = plantilla del padre − suma de las hijas ya consultadas
--
-- sale negativo o absurdo, y con él se puede acotar —o aislar— un grupo
-- por debajo del umbral k sin consultarlo nunca. Es el ataque que la
-- migración 008 describe y cierra.
--
-- QUÉ HACÍA LA 008 Y QUÉ NO
-- --------------------------
-- La 008 hizo dos cosas, las dos correctas y ninguna suficiente:
--
--   1. **Arregló los datos que ya estaban mal**, con un UPDATE que subió
--      la plantilla de los padres que no cuadraban.
--   2. **Creó una función para detectarlo**,
--      `gobernanza.fn_jerarquia_consistente()`, que devuelve las unidades
--      que violan la invariante y que debe devolver cero filas. La 012
--      agregó además `integracion.fn_validar_arbol_propuesto(JSONB)`, que
--      el importador corporativo usa ANTES de aplicar un árbol.
--
-- Lo que no hizo fue **impedir** que se vuelva a romper por los otros
-- caminos. El importador sí valida —la 012 lo dejó hecho— pero crear una
-- unidad hija desde el portal web o desde organizational-service no
-- consulta nada: inserta y ya. Así que la invariante quedó dependiendo de
-- que cada camino de escritura se acordara de comprobarla, y de una
-- prueba que la verifica **después del hecho**.
--
-- CÓMO SE DESCUBRIÓ
-- -----------------
-- Por el peor camino posible: `test_inferencia` empezó a fallar sin que
-- nadie hubiera tocado nada de la jerarquía.
--
--     UO-OPERACIONES: declarada 1186, suma de hijas 1206
--
-- Los 20 de diferencia eran tres unidades creadas por OTRAS pruebas
-- —UO-PRUEBA-JSON (4), UO-PRUEBA-XML (9), UO-PRUEBA-BAJA (7)— que se
-- colgaron de UO-OPERACIONES sin subirle la plantilla. El sistema las
-- aceptó sin una palabra.
--
-- Eso deja dos conclusiones. La primera es que el resultado de la prueba
-- dependía del orden de ejecución y de lo que hubieran dejado las
-- corridas anteriores, que es lo peor que le puede pasar a una prueba de
-- una garantía. La segunda, y la que importa: si tres pruebas pudieron
-- romper la invariante sin querer, cualquier pantalla de administración
-- puede romperla igual, y el control de inferencia se queda sin efecto en
-- producción sin que nada avise.
--
-- POR QUÉ UN DISPARADOR Y NO UNA COMPROBACIÓN EN CADA SERVICIO
-- -------------------------------------------------------------
-- Comprobarlo en el servicio de organización, en el portal, en el
-- importador y en cualquier camino futuro es cuatro lugares donde hay que
-- acordarse, y el que se olvide no fallará: insertará. Aquí es un lugar y
-- no se puede olvidar, porque no es un camino sino la tabla.
--
-- POR QUÉ ES `DEFERRABLE`
-- -----------------------
-- Una carga masiva construye el árbol por partes y la invariante no se
-- cumple a mitad de la transacción, aunque sí al final. Con un disparador
-- estricto habría que insertar en un orden exacto o la carga fallaría por
-- un estado intermedio perfectamente correcto.
--
-- `DEFERRABLE INITIALLY IMMEDIATE` deja las dos cosas: comprueba en cada
-- sentencia por omisión —que es lo que hace falta contra un error
-- humano— y permite a una carga masiva pedir
--
--     SET CONSTRAINTS organizacion.ctr_jerarquia_consistente DEFERRED;
--
-- para que se compruebe al COMMIT. Diferido sigue comprobando: lo que no
-- se puede es terminar la transacción con el árbol roto.
-- =====================================================================
BEGIN;

-- Primero se limpia lo que ya está mal, porque un disparador nuevo no
-- arregla el pasado y la restricción no se puede dar por cumplida
-- mientras haya filas que la violan.
--
-- Se sube la plantilla del padre a la suma de sus hijas, igual que hizo
-- la 008, y por el mismo motivo: bajar la de las hijas sería inventar que
-- esas áreas tienen menos gente de la que declararon.
UPDATE organizacion.unidad_organizacional padre
   SET plantilla_declarada = (
         SELECT coalesce(sum(hija.plantilla_declarada), 0)
           FROM organizacion.unidad_organizacional hija
          WHERE hija.unidad_padre_id = padre.unidad_organizacional_id)
 WHERE EXISTS (SELECT 1 FROM organizacion.unidad_organizacional h
                WHERE h.unidad_padre_id = padre.unidad_organizacional_id)
   AND padre.plantilla_declarada < (
         SELECT coalesce(sum(hija.plantilla_declarada), 0)
           FROM organizacion.unidad_organizacional hija
          WHERE hija.unidad_padre_id = padre.unidad_organizacional_id);


CREATE OR REPLACE FUNCTION organizacion.fn_exigir_jerarquia_consistente()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_padre      VARCHAR(40);
    v_declarada  INTEGER;
    v_suma       INTEGER;
    v_nombre     TEXT;
BEGIN
    -- Se comprueban los padres AFECTADOS por esta fila, que pueden ser
    -- dos: una unidad que cambia de padre deja uno y entra en otro, y
    -- solo el nuevo puede quedar mal. El viejo solo pierde una hija, así
    -- que su suma baja y sigue cumpliendo; se revisa igual porque cuesta
    -- nada y porque razonar «solo baja» es como se cuelan los errores.
    FOR v_padre IN
        SELECT DISTINCT p FROM (VALUES
            (CASE WHEN TG_OP <> 'DELETE' THEN NEW.unidad_padre_id END),
            (CASE WHEN TG_OP <> 'INSERT' THEN OLD.unidad_padre_id END),
            -- Y la propia fila, porque subirle la plantilla a una hija no
            -- es lo unico que rompe: BAJARSELA a un padre tambien.
            (CASE WHEN TG_OP <> 'DELETE' THEN NEW.unidad_organizacional_id END)
        ) AS t(p) WHERE p IS NOT NULL
    LOOP
        SELECT u.plantilla_declarada, u.nombre
          INTO v_declarada, v_nombre
          FROM organizacion.unidad_organizacional u
         WHERE u.unidad_organizacional_id = v_padre;

        IF v_declarada IS NULL THEN
            CONTINUE;                         -- el padre ya no existe
        END IF;

        SELECT coalesce(sum(h.plantilla_declarada), 0) INTO v_suma
          FROM organizacion.unidad_organizacional h
         WHERE h.unidad_padre_id = v_padre;

        IF v_suma > 0 AND v_declarada < v_suma THEN
            RAISE EXCEPTION
                'La unidad % (%) declara % de plantilla y sus hijas suman %. '
                'Un padre mas chico que sus hijas deja sin efecto el control '
                'de inferencia: el residuo «plantilla del padre menos las '
                'hijas ya consultadas» permite acotar un grupo por debajo del '
                'umbral k sin consultarlo. Sube la plantilla del padre o baja '
                'la de la hija.',
                v_padre, coalesce(v_nombre, '?'), v_declarada, v_suma
                USING ERRCODE = 'check_violation',
                      HINT = 'Si estas cargando un arbol por partes, usa '
                             'SET CONSTRAINTS organizacion.ctr_jerarquia_'
                             'consistente DEFERRED y se comprobara al COMMIT.';
        END IF;
    END LOOP;

    RETURN NULL;                              -- disparador AFTER
END;
$$;

COMMENT ON FUNCTION organizacion.fn_exigir_jerarquia_consistente() IS
    'Impide dejar un padre con menos plantilla que la suma de sus hijas. '
    'La migracion 008 arreglo los datos y creo la funcion que lo DETECTA; '
    'esto lo IMPIDE, que es distinto: antes cualquier camino de escritura '
    'podia romperlo y solo se notaba al correr la prueba.';

DROP TRIGGER IF EXISTS ctr_jerarquia_consistente
    ON organizacion.unidad_organizacional;

CREATE CONSTRAINT TRIGGER ctr_jerarquia_consistente
    AFTER INSERT OR UPDATE OR DELETE ON organizacion.unidad_organizacional
    DEFERRABLE INITIALLY IMMEDIATE
    FOR EACH ROW
    EXECUTE FUNCTION organizacion.fn_exigir_jerarquia_consistente();

COMMIT;

-- Verificación:
--
--   -- Cero filas, y ahora porque no se puede llegar a tenerlas:
--   SELECT * FROM gobernanza.fn_jerarquia_consistente();
--
--   -- Y que de verdad impide. Esto tiene que fallar:
--   BEGIN;
--     INSERT INTO organizacion.unidad_organizacional
--       (unidad_organizacional_id, nombre, tipo, unidad_padre_id,
--        nivel_jerarquico, plantilla_declarada)
--     VALUES ('UO-ROMPE', 'Rompe la invariante', 'AREA', 'UO-OPERACIONES',
--             3, 99999);
--   ROLLBACK;
--
--   -- Y que una carga por partes puede diferirlo:
--   BEGIN;
--     SET CONSTRAINTS organizacion.ctr_jerarquia_consistente DEFERRED;
--     -- ... insertar el arbol en cualquier orden ...
--   COMMIT;   -- aqui se comprueba
