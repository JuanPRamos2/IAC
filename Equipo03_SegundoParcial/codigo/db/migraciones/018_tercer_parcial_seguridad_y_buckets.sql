-- =====================================================================
-- Migracion 018 — Seguridad, recuperacion de acceso y control de buckets
--
-- DECISIONES DE SEGURIDAD Y MENOR PRIVILEGIO
-- ----------------------------------------
-- 1. Restablecimiento de contrasena via SECURITY DEFINER:
--    En 09_permisos.sh, el rol `bienestar_app` tiene INSERT y UPDATE sobre
--    `usuarios.usuario` porque `users-service` da de alta usuarios y
--    actualiza el campo `activo`. Sin embargo, `auth-service` no necesita
--    permiso directo de escritura sobre la tabla `usuarios.usuario` para
--    restablecer contrasenas.
--
--    Encapsular el cambio de `contrasena_hash` en la funcion
--    `usuarios.fn_restablecer_contrasena` (propiedad de `bienestar_motor`,
--    SECURITY DEFINER y con `search_path` fijo) garantiza que:
--      - El hash bcrypt (`crypt` + `gen_salt('bf')`) se calcula siempre
--        dentro de PostgreSQL y nunca sale ni se recibe ya digerido por
--        fuera.
--      - La longitud minima de 8 caracteres se valida tambien en el motor,
--        no solo en Python.
--      - Solo se actualizan usuarios activos (`activo = TRUE`), impidiendo
--        reactivar o alterar cuentas dadas de baja mediante recuperacion.
--      - `users-service` conserva su capacidad de actualizar `activo`.
--
-- 2. Catalogo de acciones de auditoria:
--    `auditoria.bitacora` tiene llave foranea contra `auditoria.tipo_accion`.
--    Si un microservicio intenta registrar una accion inexistente, el INSERT
--    falla por FK (y al ir envuelto en try/except, la evidencia se perderia
--    en silencio). Se registran de forma idempotente todas las acciones de
--    seguridad del tercer parcial.
-- =====================================================================

BEGIN;

CREATE OR REPLACE FUNCTION usuarios.fn_restablecer_contrasena(
    p_usuario_id       VARCHAR,
    p_nueva_contrasena TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = usuarios, public, pg_temp
AS $$
BEGIN
    IF p_usuario_id IS NULL OR btrim(p_usuario_id) = '' THEN
        RAISE EXCEPTION 'USUARIO_REQUERIDO: falta p_usuario_id'
              USING ERRCODE = 'check_violation';
    END IF;

    IF length(coalesce(p_nueva_contrasena, '')) < 8 THEN
        RAISE EXCEPTION 'CONTRASENA_DEBIL: la contrasena debe tener al menos 8 caracteres'
              USING ERRCODE = 'check_violation';
    END IF;

    UPDATE usuarios.usuario
       SET contrasena_hash     = public.crypt(p_nueva_contrasena, public.gen_salt('bf')),
           fecha_actualizacion = NOW()
     WHERE usuario_id = p_usuario_id
       AND activo = TRUE;

    RETURN FOUND;
END;
$$;

COMMENT ON FUNCTION usuarios.fn_restablecer_contrasena(VARCHAR, TEXT) IS
    'Actualiza contrasena_hash con bcrypt dentro de PostgreSQL solo para usuarios activos. '
    'SECURITY DEFINER con search_path fijo para mantener el principio de menor privilegio.';

REVOKE ALL ON FUNCTION usuarios.fn_restablecer_contrasena(VARCHAR, TEXT) FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bienestar_motor') THEN
        GRANT USAGE ON SCHEMA usuarios TO bienestar_motor;
        GRANT SELECT, UPDATE (contrasena_hash, fecha_actualizacion)
              ON usuarios.usuario TO bienestar_motor;
        ALTER FUNCTION usuarios.fn_restablecer_contrasena(VARCHAR, TEXT)
            OWNER TO bienestar_motor;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bienestar_app') THEN
        GRANT USAGE ON SCHEMA usuarios TO bienestar_app;
        GRANT EXECUTE ON FUNCTION usuarios.fn_restablecer_contrasena(VARCHAR, TEXT)
              TO bienestar_app;
    END IF;
END $$;

INSERT INTO auditoria.tipo_accion (codigo, descripcion, sensible) VALUES
 ('RECUPERACION_SOLICITADA',
  'Solicitud de codigo OTP para recuperacion de acceso.',
  TRUE),
 ('RECUPERACION_CONFIRMADA',
  'Restablecimiento de contrasena confirmado mediante codigo OTP.',
  TRUE),
 ('RATE_LIMIT_EXCEDIDO',
  'Peticion rechazada por exceder el limite de consumo permitido.',
  TRUE),
 ('URL_FIRMADA_GENERADA',
  'Generacion de URL prefirmada temporal para descarga o carga controlada en almacenamiento.',
  TRUE),
 ('ARCHIVO_RECHAZADO',
  'Archivo rechazado por validacion de tamano, tipo MIME, extension o magic bytes.',
  TRUE),
 ('ACCESO_DENEGADO',
  'Intento de alcanzar una operacion sin el permiso necesario.',
  TRUE)
ON CONFLICT (codigo) DO NOTHING;

COMMIT;
