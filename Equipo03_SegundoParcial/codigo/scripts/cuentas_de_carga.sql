-- =====================================================================
-- Cuentas para la prueba de carga. SOLO para la base de carga.
--
-- POR QUÉ HACEN FALTA, Y POR QUÉ NO VAN EN UNA MIGRACIÓN
-- ------------------------------------------------------
-- El sistema limita las peticiones por token y minuto
-- (`limite_consumo`), y sin token todavía —en el inicio de sesión— por
-- dirección IP. Los dos límites están bien y protegen de un abuso real.
--
-- Pero convierten una prueba de carga mal preparada en una medición del
-- limitador. Se midió, dos veces:
--
--   * con un inicio de sesión por usuario virtual a 30 nacimientos por
--     segundo: 65 rechazos con 429 en /auth/login —los usuarios
--     virtuales salen de 127.0.0.1 y comparten los 30 inicios por
--     minuto de esa IP— y 899 peticiones con 401 después, porque los
--     usuarios sin token siguieron trabajando sin él. 34.6% de errores.
--
--   * con un token compartido por perfil: 1 012 rechazos con 429, ahora
--     por el límite POR TOKEN de 120 peticiones por minuto, repartido
--     entre cien colaboradores que usaban el mismo. 37.9% de errores.
--
-- Las dos cifras hablan del limitador y no del sistema. En producción
-- 150 usuarios son 150 cuentas, así que el límite por token no se
-- reparte entre ellos. Este guión reproduce eso: un lote de cuentas
-- reales, una por usuario virtual. El ritmo de llegada lo arregla aparte
-- la forma de la carga (`RampaYVuelta` en el locustfile).
--
-- NO va en una migración —ni en db/migraciones/ ni en db/semilla/—
-- porque son cuentas con una contraseña conocida. En una base de
-- producción serían una puerta abierta. Van aparte, se aplican a mano
-- sobre la base de carga, y el nombre del archivo dice para qué son.
--
-- ES IDEMPOTENTE: se puede volver a correr. Lo único que no puede hacer
-- es RENUMERAR una cuenta que ya actuó en el sistema, porque
-- `auditoria.bitacora` tiene llave foránea contra `usuarios.usuario` y se
-- niega. Eso no es un defecto del guión: es la garantía de auditoría
-- funcionando — un usuario que hizo algo no se puede borrar ni renombrar
-- para que lo que hizo quede sin dueño.
--
-- Uso:
--   psql -d nexum_carga -f scripts/cuentas_de_carga.sql
-- =====================================================================
BEGIN;

-- 100 colaboradores, 32 especialistas, 22 administradores, 12 auditores.
--
-- La proporción NO es inventada: sale de los pesos con que la prueba
-- reparte los usuarios virtuales (10 : 3 : 2 : 1), que a su vez imitan la
-- realidad —los colaboradores son la inmensa mayoría de las cuentas de
-- una plataforma así, y repartir por igual entre perfiles mediría una
-- plataforma que no existe—. En el pico de 150 usuarios eso da 94
-- colaboradores, 28 especialistas, 19 administradores y 9 auditores, y
-- cada rango lleva un margen por encima.
--
-- El margen importa: cuando un perfil se queda sin cuentas, los usuarios
-- virtuales de más reutilizan una y vuelven a compartir el límite por
-- token, que es justo lo que este guión existe para evitar. La primera
-- versión tenía 12 especialistas y 8 administradores, y la rampa los
-- agotaba a la mitad.
CREATE TEMPORARY TABLE lote AS
SELECT n,
       -- lpad y no format('%04s'): `%04s` rellena con ESPACIOS porque el
       -- valor es texto, y produce 'USR-C   1' en lugar de 'USR-C0001'.
       -- La primera versión de este guión creó las cuentas así.
       'USR-C' || lpad(n::text, 4, '0')         AS id_deseado,
       format('carga%s@nexum.com.mx', n)        AS correo,
       CASE WHEN n <= 100 THEN 'COLABORADOR'
            WHEN n <= 132 THEN 'ESPECIALISTA'
            WHEN n <= 154 THEN 'ADMINISTRADOR'
            ELSE 'AUDITOR' END                  AS perfil
  FROM generate_series(1, 166) AS n;

-- El correo es la identidad estable aquí: es lo que usa el locustfile, y
-- es lo único que no cambia si una cuenta ya existía con otro
-- identificador. Las cuentas que ya están se reutilizan.
INSERT INTO usuarios.usuario
    (usuario_id, nombre, apellido_paterno, correo, contrasena_hash)
SELECT l.id_deseado, 'Carga', format('Numero%s', l.n), l.correo,
       -- La MISMA contraseña para todas y a propósito: lo que se mide es
       -- la capacidad de los endpoints, no la variedad de credenciales.
       crypt('carga123', gen_salt('bf'))
  FROM lote l
 WHERE NOT EXISTS (SELECT 1 FROM usuarios.usuario u WHERE u.correo = l.correo);

-- El perfil SÍ se corrige en las que ya existían: la proporción cambió
-- entre la primera versión y esta, y una cuenta con el perfil viejo
-- mandaría al usuario virtual a endpoints que su perfil no puede usar —y
-- esos 403 se leerían como errores del sistema.
WITH existentes AS (
    SELECT u.usuario_id, p.perfil_id
      FROM lote l
      JOIN usuarios.usuario u ON u.correo = l.correo
      JOIN usuarios.perfil p  ON p.codigo = l.perfil
)
INSERT INTO usuarios.usuario_perfil (usuario_id, perfil_id, unidad_alcance_id)
SELECT usuario_id, perfil_id, NULL FROM existentes
    ON CONFLICT (usuario_id, perfil_id) DO NOTHING;

DELETE FROM usuarios.usuario_perfil up
 USING lote l, usuarios.usuario u, usuarios.perfil p
 WHERE u.correo = l.correo
   AND up.usuario_id = u.usuario_id
   AND p.perfil_id = up.perfil_id
   AND p.codigo <> l.perfil;

-- ---------------------------------------------------------------------
-- Y cada cuenta ligada a un EMPLEADO que ya tenga seudónimo.
--
-- POR QUÉ: sin esto, los endpoints del colaborador devuelven 403
-- `SIN_SEUDONIMO`, y con razón. La cadena es
--
--     usuarios.empleado.usuario_id          ->  empleado
--     consentimiento.seudonimo.empleado_id  ->  seudonimo
--
-- y una cuenta sin empleado no tiene seudónimo, así que no tiene
-- consentimiento ni autorreporte que consultar. Se midió lo que pasa sin
-- el enlace: 2 340 peticiones con 403 en `/consentimiento/mio`, el
-- endpoint de más volumen de la prueba. El servicio estaba contestando
-- correctamente —con un código claro y un mensaje que explica la causa—
-- a una prueba que preguntaba por una cuenta que no podía tener
-- respuesta.
--
-- Se eligen empleados que ya tienen seudónimo y todavía no tienen
-- usuario, ordenados por empleado_id para que el enlace sea el mismo en
-- dos corridas: una prueba de carga que mide cuentas distintas cada vez
-- no se puede comparar consigo misma.
-- ---------------------------------------------------------------------
WITH pendientes AS (
    SELECT u.usuario_id,
           row_number() OVER (ORDER BY u.correo) AS orden
      FROM lote l
      JOIN usuarios.usuario u ON u.correo = l.correo
     WHERE NOT EXISTS (SELECT 1 FROM usuarios.empleado e
                        WHERE e.usuario_id = u.usuario_id)
), libres AS (
    SELECT e.empleado_id,
           row_number() OVER (ORDER BY e.empleado_id) AS orden
      FROM usuarios.empleado e
      JOIN consentimiento.seudonimo s ON s.empleado_id = e.empleado_id
     WHERE e.usuario_id IS NULL
)
UPDATE usuarios.empleado e
   SET usuario_id = p.usuario_id
  FROM pendientes p
  JOIN libres li ON li.orden = p.orden
 WHERE e.empleado_id = li.empleado_id;

COMMIT;

-- Verificación:
--   SELECT p.codigo, count(*)
--     FROM usuarios.usuario u
--     JOIN usuarios.usuario_perfil up USING (usuario_id)
--     JOIN usuarios.perfil p USING (perfil_id)
--    WHERE u.correo LIKE 'carga%@nexum.com.mx'
--    GROUP BY p.codigo ORDER BY p.codigo;
--
--   -- Y que todas tienen seudónimo, que es lo que evita los 403:
--   SELECT count(*) FROM portal.v_participacion_propia v
--     JOIN usuarios.usuario u USING (usuario_id)
--    WHERE u.correo LIKE 'carga%@nexum.com.mx';
--
-- Para quitarlas cuando se acabe de medir. El orden importa, y el DELETE
-- de usuarios falla si alguna ya actuó: la bitácora la referencia, y eso
-- es la garantía de auditoría, no un estorbo. En ese caso basta
-- desactivarlas.
--   UPDATE usuarios.empleado SET usuario_id = NULL
--    WHERE usuario_id IN (SELECT usuario_id FROM usuarios.usuario
--                          WHERE correo LIKE 'carga%@nexum.com.mx');
--   UPDATE usuarios.usuario SET activo = false
--    WHERE correo LIKE 'carga%@nexum.com.mx';
