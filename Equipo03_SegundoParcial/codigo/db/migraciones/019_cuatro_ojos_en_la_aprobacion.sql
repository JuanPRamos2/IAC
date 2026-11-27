-- =====================================================================
-- 019 — Quién propuso el plan, para que no sea quien lo aprueba
--
-- QUÉ PROMETÍA EL SISTEMA Y QUÉ CUMPLÍA
-- -------------------------------------
-- `interventions-service` dice, en su propio mensaje de error:
--
--     «Proponer y aprobar son permisos distintos: quien detecta la
--      necesidad no es quien autoriza el cambio.»
--
-- El mecanismo existe y es correcto: `INTERVENCION_PROPONER` e
-- `INTERVENCION_APROBAR` son permisos separados, y aprobar comprueba el
-- segundo y no se conforma con el de seguimiento.
--
-- Pero la promesa solo se cumple si los dos permisos están en perfiles
-- distintos, y en la configuración de roles del sistema **los dos son del
-- perfil ESPECIALISTA**. Resultado: el mismo especialista propone un plan
-- de intervención sobre una unidad y lo aprueba él mismo, sin que nadie
-- más lo vea. La separación de funciones que el sistema anuncia no
-- ocurre.
--
-- Lo encontró la prueba del proceso integral 2, que daba por hecho que el
-- administrador aprobaba y descubrió que el administrador **no puede**
-- —no tiene el permiso— y que el especialista sí puede aprobar el suyo.
--
-- POR QUÉ SE ARREGLA AQUÍ Y NO MOVIENDO EL PERMISO DE PERFIL
-- -----------------------------------------------------------
-- Mover `INTERVENCION_APROBAR` al administrador arreglaría este caso y
-- dejaría la garantía dependiendo otra vez de cómo estén repartidos los
-- permisos: la primera organización que decida que sus especialistas
-- senior pueden aprobar vuelve a tener el problema, y nada se lo dirá.
--
-- Y además sería discutible: un administrador del sistema no
-- necesariamente es la persona indicada para autorizar una intervención
-- de bienestar laboral sobre un equipo — eso es una decisión de negocio,
-- no de operación.
--
-- Lo que no es discutible, con cualquier reparto de permisos, es que
-- **una persona no apruebe su propia propuesta**. Eso es el control de
-- cuatro ojos, y para poder exigirlo hay que saber quién propuso: esta
-- columna.
--
-- POR QUÉ UNA COLUMNA Y NO LA BITÁCORA
-- -------------------------------------
-- La bitácora ya guarda quién propuso: `INTERVENCION_PROPUESTA` con su
-- `actor_usuario_id`. Pero el registro en bitácora va envuelto en
-- try/except para que un fallo de auditoría no tumbe la operación
-- principal — y eso es correcto para auditar y **inaceptable para un
-- control de acceso**. Un control que depende de una escritura
-- best-effort se cae en silencio justo cuando la escritura falla, y el
-- modo de falla silencioso ya apareció cuatro veces en este proyecto.
--
-- Esta columna es parte de la misma transacción que crea el plan. Si no
-- se puede escribir, el plan no se crea.
-- =====================================================================
BEGIN;

ALTER TABLE intervencion.plan
    ADD COLUMN IF NOT EXISTS propuesto_por_usuario_id VARCHAR(20)
        REFERENCES usuarios.usuario(usuario_id);

COMMENT ON COLUMN intervencion.plan.propuesto_por_usuario_id IS
    'Quien creo la propuesta. Se usa para impedir que la misma persona '
    'apruebe su propio plan (control de cuatro ojos). Es NULL en los '
    'planes creados antes de esta migracion: ver la nota de abajo.';

-- Un índice porque la comprobación de aprobación lo lee en cada
-- transición, y porque el panel de intervenciones agrupa por quién
-- propone.
CREATE INDEX IF NOT EXISTS ix_plan_propuesto_por
    ON intervencion.plan (propuesto_por_usuario_id);

-- LOS PLANES VIEJOS QUEDAN EN NULL, Y SE RELLENAN DESDE LA BITÁCORA
-- ------------------------------------------------------------------
-- Para los planes que ya existen sí se usa la bitácora, porque es la
-- única fuente que hay y porque aquí no es un control de acceso: es un
-- relleno histórico que se hace una vez y se puede revisar.
--
-- Los que queden en NULL —porque su registro de propuesta se perdió— no
-- bloquean nada: la comprobación de cuatro ojos solo puede aplicarse
-- cuando se sabe quién propuso, y bloquear la aprobación de un plan por
-- no saberlo dejaría planes vivos que nadie puede mover. El servicio lo
-- dice en la respuesta cuando pasa.
UPDATE intervencion.plan p
   SET propuesto_por_usuario_id = b.actor_usuario_id
  FROM (
      SELECT DISTINCT ON (recurso_id)
             recurso_id, actor_usuario_id
        FROM auditoria.bitacora
       WHERE accion = 'INTERVENCION_PROPUESTA'
         AND actor_usuario_id IS NOT NULL
       ORDER BY recurso_id, fecha_hora ASC
  ) b
 WHERE p.propuesto_por_usuario_id IS NULL
   AND b.recurso_id = p.intervencion_id::TEXT;

-- ---------------------------------------------------------------------
-- Y UN SEGUNDO APROBADOR, PORQUE SI NO EL CONTROL ES UN BLOQUEO
--
-- Esto no es un extra: sin esto, la migración rompe el sistema.
--
-- `INTERVENCION_APROBAR` es un permiso del perfil ESPECIALISTA, y la
-- configuración de usuarios del sistema trae **un solo especialista**.
-- Con el control de cuatro ojos activado y una sola persona capaz de
-- aprobar, esa persona solo puede aprobar planes que no propuso —es
-- decir, ninguno— y **ningún plan de intervención podría aprobarse
-- jamás**.
--
-- Un control de seguridad que deja inservible la configuración por
-- omisión no está terminado. Así que la migración que lo introduce trae
-- también lo que hace falta para que el sistema siga funcionando: una
-- segunda cuenta con el permiso de aprobar.
--
-- POR QUÉ UN SEGUNDO ESPECIALISTA Y NO DARLE EL PERMISO AL ADMINISTRADOR
-- ----------------------------------------------------------------------
-- Dar `INTERVENCION_APROBAR` al administrador del sistema arreglaría el
-- bloqueo y sería la decisión equivocada: quien opera la plataforma no es
-- necesariamente quien debe autorizar una intervención de bienestar
-- laboral sobre un equipo de personas. Eso es una decisión de negocio, y
-- el administrador tiene el permiso de administrar usuarios y parámetros,
-- no de decidir sobre las condiciones de trabajo de nadie.
--
-- Dos especialistas es el reparto correcto: la autorización se queda en
-- el área que entiende lo que se está autorizando, y deja de ser una
-- sola persona.
--
-- La contraseña es la misma de las demás cuentas de demostración. En una
-- instalación real, la cuenta la crea quien administre el sistema y esta
-- parte de la migración no aplica; queda aquí para que el sistema de
-- demostración siga siendo demostrable.
-- ---------------------------------------------------------------------
INSERT INTO usuarios.usuario
    (usuario_id, nombre, apellido_paterno, apellido_materno, correo,
     contrasena_hash)
VALUES
    ('USR-00006', 'Teresa', 'Villalobos', 'Quintero',
     'teresa.villalobos@nexum.com.mx', crypt('demo123', gen_salt('bf')))
ON CONFLICT (usuario_id) DO NOTHING;

INSERT INTO usuarios.usuario_perfil (usuario_id, perfil_id, unidad_alcance_id)
SELECT 'USR-00006', p.perfil_id, NULL
  FROM usuarios.perfil p
 WHERE p.codigo = 'ESPECIALISTA'
ON CONFLICT DO NOTHING;

COMMIT;

-- Verificación:
--
--   -- Que hay al menos DOS cuentas capaces de aprobar. Con una sola, el
--   -- control de cuatro ojos bloquea el sistema en lugar de protegerlo.
--   SELECT count(DISTINCT u.usuario_id) AS aprobadores
--     FROM usuarios.usuario u
--     JOIN usuarios.usuario_perfil up USING (usuario_id)
--     JOIN usuarios.perfil_permiso pp USING (perfil_id)
--     JOIN usuarios.permiso pm USING (permiso_id)
--    WHERE pm.codigo = 'INTERVENCION_APROBAR' AND u.activo;
--
--
--   SELECT count(*) FILTER (WHERE propuesto_por_usuario_id IS NOT NULL) AS con_autor,
--          count(*) FILTER (WHERE propuesto_por_usuario_id IS NULL)     AS sin_autor
--     FROM intervencion.plan;
--
--   -- Y que el control funciona: crear un plan como especialista e
--   -- intentar aprobarlo con la MISMA cuenta tiene que dar 409.
--   -- Lo comprueba pruebas/test_procesos_integrales.py.
