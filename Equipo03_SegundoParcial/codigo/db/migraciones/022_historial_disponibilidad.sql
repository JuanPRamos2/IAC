-- Historial de las sondas que muestra el panel Servicios.
--
-- Cada apertura de Administración → Servicios inserta una fila por
-- microservicio. Con eso la pantalla puede decir, en las últimas 24 horas,
-- cuántas veces estuvo disponible, degradado, sin una dependencia esencial
-- o caído. La bitácora sigue siendo la fuente de los errores de negocio;
-- esta tabla es solo la disponibilidad del proceso.
--
-- Idempotente: se puede correr sobre una base que ya existe.

BEGIN;

CREATE TABLE IF NOT EXISTS auditoria.sonda_disponibilidad (
    sonda_id    BIGSERIAL    PRIMARY KEY,
    servicio    VARCHAR(60)  NOT NULL,
    estado      VARCHAR(20)  NOT NULL,
    latencia_ms NUMERIC(10,1),
    detalle     VARCHAR(200),
    momento     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_sonda_momento
    ON auditoria.sonda_disponibilidad (momento DESC);
CREATE INDEX IF NOT EXISTS ix_sonda_servicio
    ON auditoria.sonda_disponibilidad (servicio, momento DESC);

COMMENT ON TABLE auditoria.sonda_disponibilidad IS
  'Muestras del panel de servicios. No guarda datos de personas: solo el nombre del contenedor, su estado y la latencia del sondeo.';

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bienestar_app') THEN
    GRANT SELECT, INSERT ON auditoria.sonda_disponibilidad TO bienestar_app;
    GRANT USAGE, SELECT ON SEQUENCE auditoria.sonda_disponibilidad_sonda_id_seq TO bienestar_app;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS auditoria.migracion_aplicada (
    nombre      TEXT PRIMARY KEY,
    aplicada_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
