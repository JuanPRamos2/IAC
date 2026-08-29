import { pgQuery } from "../config/postgres.js";

export async function listarUnidades() {
  const r = await pgQuery(
    `SELECT unidad_organizacional_id, nombre, unidad_padre_id, nivel_jerarquico
     FROM organizacion.v_unidades_activas
     ORDER BY nombre`
  );
  return r.rows;
}

export async function listarCampaniasDeUnidad(unidadId) {
  const r = await pgQuery(
    `SELECT c.campania_id, c.nombre, c.fecha_inicio, c.fecha_fin,
            c.instrumento_id, c.version_instrumento, c.activa
     FROM catalogo.campania c
     JOIN catalogo.campania_unidad cu ON cu.campania_id = c.campania_id
     WHERE c.activa = TRUE AND cu.unidad_organizacional_id = $1
     ORDER BY c.fecha_inicio DESC`,
    [unidadId]
  );
  return r.rows;
}

export async function obtenerCampania(campaniaId) {
  const r = await pgQuery(
    `SELECT campania_id, nombre, fecha_inicio, fecha_fin,
            instrumento_id, version_instrumento, activa
     FROM catalogo.campania
     WHERE campania_id = $1`,
    [campaniaId]
  );
  return r.rows[0] || null;
}

export async function campaniaAsignadaAUnidad(campaniaId, unidadId) {
  const r = await pgQuery(
    `SELECT 1 FROM catalogo.campania_unidad
     WHERE campania_id = $1 AND unidad_organizacional_id = $2`,
    [campaniaId, unidadId]
  );
  return r.rowCount === 1;
}

export async function reactivosDeVersion(instrumentoId, version) {
  const r = await pgQuery(
    `SELECT r.reactivo_id, r.texto, r.dimension, r.escala_min, r.escala_max,
            r.invertido, riv.orden, riv.obligatorio
     FROM catalogo.reactivo_instrumento_version riv
     JOIN catalogo.reactivo r ON r.reactivo_id = riv.reactivo_id AND r.activo = TRUE
     WHERE riv.instrumento_id = $1 AND riv.version = $2
     ORDER BY riv.orden`,
    [instrumentoId, version]
  );
  return r.rows;
}

export async function obtenerSeudonimo(seudonimoId) {
  const r = await pgQuery(
    `SELECT s.seudonimo_id, s.empleado_id, s.activo,
            e.unidad_organizacional_id, e.usuario_id
     FROM consentimiento.seudonimo s
     JOIN usuarios.empleado e ON e.empleado_id = s.empleado_id
     WHERE s.seudonimo_id = $1`,
    [seudonimoId]
  );
  return r.rows[0] || null;
}

export async function consentimientoVigente(seudonimoId) {
  const r = await pgQuery(
    `SELECT seudonimo_id, version_consentimiento_id
     FROM consentimiento.v_consentimiento_vigente
     WHERE seudonimo_id = $1`,
    [seudonimoId]
  );
  return r.rows[0] || null;
}

export async function leerUmbralK() {
  const r = await pgQuery(
    `SELECT valor FROM agregado.parametro_global WHERE clave = 'k'`
  );
  return Number(r.rows[0]?.valor || 5);
}

export async function actualizarUmbralK(valor, usuarioId) {
  await pgQuery(
    `UPDATE agregado.parametro_global
     SET valor = $1, fecha_actualizacion = NOW(), actualizado_por = $2
     WHERE clave = 'k'`,
    [String(valor), usuarioId]
  );
}

export async function guardarAgregadoCalculado(row) {
  await pgQuery(
    `INSERT INTO agregado.agregado_calculado (
        campania_id, unidad_organizacional_id, instrumento_id, version_instrumento,
        total_respuestas, supera_umbral_k, k_umbral, promedio_global, detalle_json
     ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
     ON CONFLICT (campania_id, unidad_organizacional_id, instrumento_id, version_instrumento)
     DO UPDATE SET
        total_respuestas = EXCLUDED.total_respuestas,
        supera_umbral_k = EXCLUDED.supera_umbral_k,
        k_umbral = EXCLUDED.k_umbral,
        promedio_global = EXCLUDED.promedio_global,
        detalle_json = EXCLUDED.detalle_json,
        fecha_calculo = NOW()`,
    [
      row.campania_id,
      row.unidad_organizacional_id,
      row.instrumento_id,
      row.version_instrumento,
      row.total_respuestas,
      row.supera_umbral_k,
      row.k_umbral,
      row.promedio_global,
      JSON.stringify(row.detalle_json),
    ]
  );
}
