import { mongoDb, conectarMongo } from "../config/mongo.js";

export async function crearSolicitud({ seudonimo_id, mensaje }) {
  await conectarMongo();
  const doc = {
    seudonimo_id,
    mensaje,
    fecha: new Date(),
    estado: "ABIERTA",
  };
  const r = await mongoDb().collection("solicitudes_apoyo").insertOne(doc);
  return { id: String(r.insertedId), fecha: doc.fecha };
}

export async function listarSolicitudes({ limite = 50 } = {}) {
  await conectarMongo();
  return mongoDb()
    .collection("solicitudes_apoyo")
    .find({}, { projection: { seudonimo_id: 0 } })
    .sort({ fecha: -1 })
    .limit(Math.min(Number(limite) || 50, 200))
    .toArray();
}

export const ESTADOS_SOLICITUD = ["ABIERTA", "EN_PROCESO", "CERRADA"];

// Actualiza estado y agrega entrada a historial[] atómicamente. `col` opcional (tests).
export async function actualizarEstadoSolicitud({ id, estado, actor_id, nota }, col) {
  if (!ESTADOS_SOLICITUD.includes(estado)) {
    throw new Error(`Estado de solicitud inválido: ${estado}`);
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

// Recuperación por seudónimo (solo para uso del propio titular / proceso interno).
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
