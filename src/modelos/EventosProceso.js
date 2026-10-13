import { mongoDb, conectarMongo } from "../config/mongo.js";

export function colEventosProceso() {
  return mongoDb().collection("eventos_proceso");
}

async function resolverCol(col) {
  if (col) return col;
  await conectarMongo();
  return colEventosProceso();
}

// Sin empleado_id: solo seudónimo + correlación.
export async function registrarEventoProceso(
  { seudonimo_id, correlacion_id, tipo, detalle, timestamp },
  col
) {
  const doc = {
    seudonimo_id,
    correlacion_id,
    tipo,
    ...(detalle ? { detalle } : {}),
    timestamp: timestamp || new Date(),
  };
  const c = await resolverCol(col);
  const r = await c.insertOne(doc);
  return { ...doc, _id: r.insertedId };
}

export async function eventosPorCorrelacion(correlacionId, col) {
  const c = await resolverCol(col);
  return c.find({ correlacion_id: correlacionId }).sort({ timestamp: 1 }).toArray();
}

export async function eventosDeSeudonimo(seudonimoId, { limite = 50 } = {}, col) {
  const c = await resolverCol(col);
  return c
    .find({ seudonimo_id: seudonimoId })
    .sort({ timestamp: -1 })
    .limit(Math.min(Number(limite) || 50, 200))
    .toArray();
}
