/**
 * Logica de dominio para survey-service (Puerto 8112).
 *
 * Administra cuestionarios, escalas, borradores con TTL en MongoDB y registro
 * de respuestas garantizando la regla de privacidad D-01 (prohibido empleado_id).
 */
import { ErrorApi } from "@bienestar/comun/errores.js";
import { base, verificarSinIdentidad } from "@bienestar/comun/mongo.js";
import { consultar, ejecutar } from "@bienestar/comun/postgres.js";
import { entero, texto, arreglo, booleano } from "@bienestar/comun/validacion.js";
import { registrarBitacora } from "@bienestar/comun/auditoria.js";

export async function listarCuestionarios({ activo = null } = {}) {
  let sql = `
    SELECT i.instrumento_id AS cuestionario_id,
           i.nombre,
           i.descripcion,
           i.tipo,
           v.version,
           v.escala_min,
           v.escala_max,
           i.activo
      FROM catalogo.instrumento i
      LEFT JOIN catalogo.version_instrumento v
        ON v.instrumento_id = i.instrumento_id AND v.activa = true
  `;
  const params = [];
  if (activo !== null) {
    sql += ` WHERE i.activo = $1`;
    params.push(booleano(activo, "activo"));
  }
  sql += ` ORDER BY i.nombre`;
  const filas = await consultar(sql, params);
  return filas;
}

export async function obtenerCuestionario(cuestionarioId) {
  const id = texto(cuestionarioId, "id");
  const filas = await consultar(
    `SELECT i.instrumento_id AS cuestionario_id,
            i.nombre,
            i.descripcion,
            i.tipo,
            v.version,
            v.escala_min,
            v.escala_max,
            i.activo
       FROM catalogo.instrumento i
       LEFT JOIN catalogo.version_instrumento v
         ON v.instrumento_id = i.instrumento_id AND v.activa = true
      WHERE i.instrumento_id = $1`,
    [id]
  );
  if (!filas.length) {
    throw new ErrorApi("CUESTIONARIO_NO_ENCONTRADO", `No existe el cuestionario '${id}'.`, 404);
  }

  const cuestionario = filas[0];
  const reactivos = await consultar(
    `SELECT r.reactivo_id,
            r.texto,
            r.dimension_id,
            r.invertido,
            vr.orden,
            vr.obligatorio,
            COALESCE(vr.escala_min, v.escala_min, 1) AS escala_min,
            COALESCE(vr.escala_max, v.escala_max, 5) AS escala_max
       FROM catalogo.version_reactivo vr
       JOIN catalogo.reactivo r ON r.reactivo_id = vr.reactivo_id
       LEFT JOIN catalogo.version_instrumento v
         ON v.instrumento_id = vr.instrumento_id AND v.version = vr.version
      WHERE vr.instrumento_id = $1 AND vr.version = $2
      ORDER BY vr.orden`,
    [id, cuestionario.version || 1]
  );

  return {
    ...cuestionario,
    reactivos,
    total_reactivos: reactivos.length,
  };
}

export async function obtenerBorrador({ cuestionario_id, seudonimo_id, dbMongo }) {
  const cId = texto(cuestionario_id, "cuestionario_id");
  const sId = texto(seudonimo_id, "seudonimo_id");
  const col = (dbMongo || base()).collection("borradores_encuesta");

  const borrador = await col.findOne(
    { cuestionario_id: cId, seudonimo_id: sId },
    { projection: { _id: 0 } }
  );

  if (!borrador) {
    throw new ErrorApi("BORRADOR_NO_ENCONTRADO", "No hay borrador pendiente para este cuestionario.", 404);
  }
  return borrador;
}

export async function guardarBorrador({ cuestionario_id, seudonimo_id, campania_id, respuestas, dbMongo }) {
  const cId = texto(cuestionario_id, "cuestionario_id");
  const sId = texto(seudonimo_id, "seudonimo_id");
  const resp = arreglo(respuestas, "respuestas");

  const doc = {
    cuestionario_id: cId,
    seudonimo_id: sId,
    campania_id: campania_id || null,
    respuestas: resp,
    fecha_actualizacion: new Date(),
  };

  verificarSinIdentidad(doc);
  const col = (dbMongo || base()).collection("borradores_encuesta");
  await col.updateOne(
    { cuestionario_id: cId, seudonimo_id: sId },
    { $set: doc },
    { upsert: true }
  );

  return { mensaje: "Borrador guardado exitosamente.", ...doc };
}

export async function registrarRespuestas({
  cuestionario_id,
  campania_id,
  seudonimo_id,
  respuestas,
  metadatos = {},
  comentario = "",
  correlacionId = "",
  req = null,
  dbMongo = null,
}) {
  const cId = texto(cuestionario_id, "cuestionario_id");
  const sId = texto(seudonimo_id, "seudonimo_id");
  const campId = texto(campania_id, "campania_id");
  const items = arreglo(respuestas, "respuestas", { minElementos: 1 });

  // Regla D-01 estricta: validar ausencia total de empleado_id
  verificarSinIdentidad({ seudonimo_id: sId, respuestas: items, metadatos });

  const mdb = dbMongo || base();
  const colRespuestas = mdb.collection("respuestas_encuesta");

  // Validar prevencion de respuestas duplicadas
  const previa = await colRespuestas.findOne({
    campania_id: campId,
    seudonimo_id: sId,
    instrumento_id: cId,
  });

  if (previa) {
    throw new ErrorApi(
      "ENCUESTA_YA_RESPONDIDA",
      `El colaborador con seudonimo '${sId}' ya registro respuestas para este cuestionario en la campania '${campId}'.`,
      409
    );
  }

  const ahora = new Date();
  const doc = {
    campania_id: campId,
    seudonimo_id: sId,
    instrumento_id: cId,
    respuestas: items.map((r, i) => ({
      reactivo_id: texto(r.reactivo_id || r.id, `respuestas[${i}].reactivo_id`),
      valor: entero(r.valor, `respuestas[${i}].valor`, { min: 1, max: 7 }),
      comentario: r.comentario ? String(r.comentario).trim().slice(0, 300) : null,
    })),
    metadatos: {
      fuente: metadatos.fuente || "web",
      tiempo_segundos: entero(metadatos.tiempo_segundos, "tiempo_segundos", { requerido: false, defecto: 0 }),
    },
    comentario: String(comentario || "").trim().slice(0, 500) || null,
    fecha_registro: ahora,
    fecha_actualizacion: ahora,
  };

  verificarSinIdentidad(doc);
  await colRespuestas.insertOne(doc);

  // Limpiar borrador temporal si existia
  try {
    const colBorradores = mdb.collection("borradores_encuesta");
    await colBorradores.deleteOne({ cuestionario_id: cId, seudonimo_id: sId });
  } catch { /* borrador ya limpio */ }

  // Registro en bitacora de auditoria
  if (req) {
    await registrarBitacora(req, "AUTOREPORTE_ENVIADO", "EXITO", {
      tipo_recurso: "cuestionario",
      recurso_id: cId,
    });
  }

  return {
    resultado: "COMPLETADO",
    mensaje: "Respuestas capturadas y almacenadas de forma confidencial.",
    campania_id: campId,
    cuestionario_id: cId,
    total_respuestas: doc.respuestas.length,
    fecha_registro: ahora,
  };
}
