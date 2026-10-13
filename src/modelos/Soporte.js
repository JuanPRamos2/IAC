import { mongoDb, conectarMongo } from "../config/mongo.js";

export const ESTADOS_SOLICITUD = ["ABIERTA", "EN_PROCESO", "CERRADA"];

export async function crearSolicitud({ seudonimo_id, mensaje }, col) {
  let c = col;
  if (!c) {
    await conectarMongo();
    c = mongoDb().collection("solicitudes_apoyo");
  }
  const doc = {
    seudonimo_id,
    mensaje,
    fecha: new Date(),
    estado: "ABIERTA",
    historial: [],
  };
  const r = await c.insertOne(doc);
  return { id: String(r.insertedId), fecha: doc.fecha, estado: doc.estado, historial: doc.historial };
}

export async function listarSolicitudes({ estado, limite = 50, pagina = 1 } = {}, col) {
  let c = col;
  if (!c) {
    await conectarMongo();
    c = mongoDb().collection("solicitudes_apoyo");
  }
  const filtro = {};
  if (estado && ESTADOS_SOLICITUD.includes(estado)) {
    filtro.estado = estado;
  }
  const limitNum = Math.min(Math.max(Number(limite) || 50, 1), 200);
  const skipNum = Math.max((Number(pagina) || 1) - 1, 0) * limitNum;
  return c
    .find(filtro, { projection: { seudonimo_id: 0 } })
    .sort({ fecha: -1 })
    .skip(skipNum)
    .limit(limitNum)
    .toArray();
}

// Actualiza estado y agrega entrada a historial[] atomicamente. col opcional (tests).
export async function actualizarEstadoSolicitud({ id, estado, actor_id, nota }, col) {
  if (!ESTADOS_SOLICITUD.includes(estado)) {
    throw new Error(`Estado de solicitud invalido: ${estado}`);
  }
  let c = col;
  let _id = id;
  if (!c) {
    await conectarMongo();
    c = mongoDb().collection("solicitudes_apoyo");
    const { ObjectId } = await import("mongodb");
    _id = new ObjectId(String(id));
  }
  const entrada = { estado, actor_id, ...(nota ? { nota } : {}), fecha: new Date() };
  const r = await c.findOneAndUpdate(
    { _id },
    { $set: { estado, fecha_actualizacion: entrada.fecha }, $push: { historial: entrada } },
    { returnDocument: "after", projection: { seudonimo_id: 0 } }
  );
  return r?.value !== undefined ? r.value : r;
}

// Recuperacion por seudonimo (solo para uso del propio titular / proceso interno).
export async function solicitudesDeSeudonimo(seudonimoId, { limite = 50 } = {}, col) {
  let c = col;
  if (!c) {
    await conectarMongo();
    c = mongoDb().collection("solicitudes_apoyo");
  }
  return c
    .find({ seudonimo_id: seudonimoId })
    .sort({ fecha: -1 })
    .limit(Math.min(Number(limite) || 50, 200))
    .toArray();
}