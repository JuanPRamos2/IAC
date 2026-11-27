-- =====================================================================
-- 018 — El análisis complejo: su acción de bitácora y sus índices
--
-- DOS COSAS, Y LA PRIMERA ES LA DE SIEMPRE
-- ----------------------------------------
-- `algorithms-service` gana el endpoint `/algoritmos/analisis`, que corre
-- el análisis complejo: agrupamiento por perfil, anomalías medidas contra
-- el grupo de pares, umbral derivado del ruido de privacidad y tendencia
-- por Theil-Sen y Mann-Kendall. Ese endpoint escribe en la bitácora con
-- el código `ANALISIS_EJECUTADO`, que hasta ahora no existía en
-- `auditoria.tipo_accion`.
--
-- Es el **cuarto** caso del mismo modo de falla en este proyecto: la 007
-- por `RECHAZADO_PERMISO`, la 014 por `COMPONENTE_REINICIADO`, la 015 por
-- las dos acciones del ciclo de intervención, y esta. `auditoria.bitacora`
-- tiene llave foránea contra `auditoria.tipo_accion`, el INSERT va
-- envuelto en try para no tumbar la operación principal, y el resultado
-- es que la acción no se registra **y nadie se entera**. La migración se
-- escribe junto con el endpoint y no después de descubrir el hueco.
--
-- LOS ÍNDICES: POR QUÉ ESTOS Y NO «LOS QUE HAGAN FALTA»
-- -----------------------------------------------------
-- Un índice no es gratis: ocupa espacio, frena cada escritura de la tabla
-- y, si nadie escribió para qué sirve, nadie se atreve a quitarlo cuando
-- deja de servir. Cada uno de los cinco lleva aquí el motivo y la
-- consulta que lo justifica, medidos contra 206 mil respuestas, un millón
-- de valores de detalle y 1 320 pares unidad-campaña.
--
-- Tres son índices PARCIALES, con `WHERE estado_publicacion = 'PUBLICADO'`.
-- Eso no es una optimización de adorno: **todo** lo que leen el tablero,
-- el motor de reglas y el análisis complejo son resultados publicados —
-- los suprimidos por el umbral k nunca se consultan, solo se cuentan.
-- Dejarlos fuera del índice lo deja a la mitad del tamaño y no cambia una
-- sola respuesta.
-- =====================================================================
BEGIN;

INSERT INTO auditoria.tipo_accion (codigo, descripcion, sensible) VALUES
  ('ANALISIS_EJECUTADO',
   'Se corrio el analisis complejo sobre una campania: agrupamiento de '
   'unidades por perfil, deteccion de anomalias contra el centroide del '
   'grupo de pares, umbral de significancia derivado de la escala de '
   'ruido aplicada, y estimacion de tendencia por Theil-Sen con prueba '
   'de Mann-Kendall. Se registra aunque no consuma epsilon: lee solo '
   'resultados ya publicados. Queda en bitacora porque produce un '
   'ranking de unidades que se usa para decidir intervenciones sobre '
   'equipos de personas, y quien lo pidio y cuando es parte de poder '
   'explicar esa decision despues.',
   FALSE)
ON CONFLICT (codigo) DO NOTHING;

-- ---------------------------------------------------------------------
-- 1. El cálculo de agregados recorre las respuestas de UNA campaña y UNA
--    unidad, una vez por cada par unidad-campaña. Con 110 unidades y 12
--    campañas son 1 320 recorridos; sin índice, cada uno lee las 206 mil
--    filas de la tabla.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_respuesta_campania_unidad
    ON autoreporte.respuesta (campania_id, unidad_organizacional_id);

-- ---------------------------------------------------------------------
-- 2. El detalle se une por respuesta_id y se separa por reactivo para
--    armar las dimensiones. Es la unión más grande del sistema: un millón
--    de filas de detalle contra doscientas mil de respuesta.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_detalle_respuesta_reactivo
    ON autoreporte.respuesta_detalle (respuesta_id, reactivo_id);

-- ---------------------------------------------------------------------
-- 3. La consulta del tablero: una unidad, una campaña, lo publicado.
--    Índice parcial —los suprimidos nunca se consultan— con las tres
--    columnas en el orden en que el WHERE las filtra.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_agregado_unidad_campania_dim
    ON agregado.resultado_protegido
       (unidad_organizacional_id, campania_id, dimension_id)
    WHERE estado_publicacion = 'PUBLICADO';

-- ---------------------------------------------------------------------
-- 4. El análisis complejo lee TODAS las unidades de una campaña de golpe
--    para construir la matriz unidad × dimensión. Es un patrón distinto
--    del anterior —barre por campaña en lugar de buscar por unidad— y por
--    eso necesita su propio índice: el del punto 3 tiene
--    unidad_organizacional_id como primera columna y no sirve para esto.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_agregado_campania_publicado
    ON agregado.resultado_protegido (campania_id)
    WHERE estado_publicacion = 'PUBLICADO';

-- ---------------------------------------------------------------------
-- 5. El panel de monitoreo pide los errores de las últimas N horas.
--    `auditoria.bitacora` es la tabla que más crece del sistema —una fila
--    por operación auditada— así que sin índice cada apertura del panel
--    la recorre entera, y el costo crece con el uso del sistema.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_bitacora_fecha_accion
    ON auditoria.bitacora (fecha_hora DESC, accion);

-- ---------------------------------------------------------------------
-- 6. EL HALLAZGO QUE MÁS VALE DE TODA ESTA MIGRACIÓN
--
-- `agregado.fn_calcular_agregado_protegido` es el camino más caliente del
-- sistema: se llama una vez por cada par unidad-campaña-dimensión, 7 920
-- veces para calcular una organización de 110 unidades y 12 campañas. Se
-- midió: **89 ms por llamada**, de los cuales 30 ms los gastaba una sola
-- consulta, la que cuenta el tamaño del grupo.
--
-- La causa, en el plan de ejecución: la vista
-- `consentimiento.v_estado_vigente` ordenaba **las 24 476 filas de la
-- tabla de consentimientos completa** en cada llamada, para después
-- resolver los 198 seudónimos que la consulta necesitaba.
--
-- Y ya había un índice para eso, `idx_consent_seud`, sobre
-- `(seudonimo_id, fecha_evento DESC)`. No se usaba. El `ORDER BY` de la
-- vista es
--
--     ORDER BY seudonimo_id, fecha_evento DESC, consentimiento_id DESC
--
-- con una TERCERA clave que el índice no cubre, así que PostgreSQL no
-- podía resolver el `DISTINCT ON` con él y caía al ordenamiento completo.
-- Un desajuste de una columna al final, y el índice queda inerte sin que
-- nada lo diga: la consulta sigue dando el resultado correcto y nadie
-- mira el plan hasta que algo tarda.
--
-- Este índice cubre las tres claves en el mismo orden. Medido en la base
-- de carga (26 526 empleados, 206 231 respuestas):
--
--     consulta del tamaño del grupo:  30.5 ms  ->  11.3 ms
--     la función completa:            89 ms    ->  21 ms   (4.2x)
--
-- y de paso `respuesta_detalle` pasa a Index Only Scan.
--
-- NOTA sobre `idx_consent_seud`: ahora es un prefijo de este índice, así
-- que es redundante y podría quitarse. No se quita aquí a propósito —lo
-- creó otra migración y no es de esta parte del proyecto decidir
-- eliminarlo—, y el costo de dejarlo es despreciable: los consentimientos
-- se escriben una vez por persona y aviso, no es una tabla de alta
-- escritura. Queda anotado para quien le corresponda.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_consent_vigente
    ON consentimiento.consentimiento
       (seudonimo_id, fecha_evento DESC, consentimiento_id DESC);

-- ---------------------------------------------------------------------
-- 7. LA SUBCONSULTA CORRELACIONADA SIN ÍNDICE
--
-- Lo encontró la prueba de carga, no una revisión de código:
-- `/consultas/presupuesto` tenía mediana de 16 ms y p95 de **2 700 ms**.
-- Esa distancia entre la mediana y el p95 es la firma de una caché que
-- tapa un problema: los aciertos van a 16 ms y el fallo paga la consulta
-- real. Y el TTL de ese recurso es de diez segundos a propósito —un dato
-- viejo de presupuesto de privacidad lleva a creer que queda épsilon
-- cuando ya se agotó— así que los fallos son frecuentes.
--
-- En el plan: `agregado.v_estado_presupuesto` cuenta las consultas de
-- cada presupuesto con una subconsulta correlacionada,
--
--     (SELECT count(*) FROM agregado.consulta_privada cp
--       WHERE cp.presupuesto_id = p.presupuesto_id)
--
-- y `consulta_privada` no tenía índice por `presupuesto_id`. Resultado:
-- un recorrido secuencial de la tabla **por cada una de las 1 372 filas**
-- de presupuesto. 1 372 × 0.31 ms = 425 de los 458 ms de la consulta.
--
-- Con el índice la subconsulta pasa a Index Only Scan:
--
--     la vista completa:  458 ms  ->  4.6 ms   (100x)
--
-- Y queda dicho por qué lo encontró la carga y no la revisión: con los
-- datos de demostración hay 40 filas de presupuesto en lugar de 1 372, y
-- cuarenta recorridos de una tabla de seis filas no se notan. El costo de
-- una subconsulta correlacionada crece con las filas de FUERA, que es
-- justo lo que unos datos de demostración no tienen.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_consulta_privada_presupuesto
    ON agregado.consulta_privada (presupuesto_id);

COMMIT;

-- El planificador no usa un índice nuevo hasta tener estadísticas de él.
-- Fuera de la transacción porque ANALYZE no corre dentro de un bloque.
ANALYZE autoreporte.respuesta;
ANALYZE autoreporte.respuesta_detalle;
ANALYZE agregado.resultado_protegido;
ANALYZE auditoria.bitacora;
ANALYZE consentimiento.consentimiento;
ANALYZE agregado.consulta_privada;

-- Verificación:
--
--   SELECT codigo FROM auditoria.tipo_accion WHERE codigo = 'ANALISIS_EJECUTADO';
--
--   -- Que los cinco índices existen y cuánto ocupan:
--   SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) AS tamano,
--          idx_scan AS veces_usado
--     FROM pg_stat_user_indexes
--    WHERE indexrelname IN ('ix_respuesta_campania_unidad',
--                           'ix_detalle_respuesta_reactivo',
--                           'ix_agregado_unidad_campania_dim',
--                           'ix_agregado_campania_publicado',
--                           'ix_bitacora_fecha_accion',
--                           'ix_consent_vigente',
--                           'ix_consulta_privada_presupuesto')
--    ORDER BY pg_relation_size(indexrelid) DESC;
--
--   -- Y que el planificador de verdad los elige, que es lo que importa y
--   -- no se deduce del tiempo de respuesta:
--   EXPLAIN (ANALYZE) SELECT * FROM agregado.resultado_protegido
--    WHERE campania_id = 'CAMP-M017' AND estado_publicacion = 'PUBLICADO';
--
--   -- Y el hallazgo del punto 6: que la vista de consentimiento resuelve
--   -- por indice y NO ordenando la tabla entera. En el plan tiene que
--   -- aparecer «Index Scan using ix_consent_vigente» y NO un «Sort» de
--   -- veinticuatro mil filas:
--   EXPLAIN (ANALYZE) SELECT * FROM consentimiento.v_estado_vigente LIMIT 10;
--
--   -- Y que el registro de verdad entra, que es lo que el try esconde:
--   SELECT accion, resultado, recurso_id FROM auditoria.bitacora
--    WHERE accion = 'ANALISIS_EJECUTADO' ORDER BY fecha_hora DESC LIMIT 5;
