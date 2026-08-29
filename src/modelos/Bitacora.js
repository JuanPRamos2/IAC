import { mongoDb } from "../config/mongo.js";

export function colBitacora() {
  return mongoDb().collection("bitacora_auditoria");
}

export async function registrarBitacora(doc) {
  await colBitacora().insertOne({
    actor_id: doc.actor_id,
    actor_perfil: doc.actor_perfil,
    accion: doc.accion,
    recurso: doc.recurso,
    resultado: doc.resultado,
    correlacion_id: doc.correlacion_id,
    timestamp: doc.timestamp || new Date(),
  });
}

export async function listarBitacora({ limite = 50 } = {}) {
  return colBitacora()
    .find({}, { projection: {} })
    .sort({ timestamp: -1 })
    .limit(Math.min(Number(limite) || 50, 200))
    .toArray();
}
