import { mongoDb } from "../config/mongo.js";

export function colRespuestas() {
  return mongoDb().collection("respuestas_encuesta");
}

export async function insertarRespuesta(doc) {
  const result = await colRespuestas().insertOne(doc);
  return { ...doc, _id: result.insertedId };
}

export async function existeRespuesta(seudonimoId, campaniaId) {
  const n = await colRespuestas().countDocuments({
    seudonimo_id: seudonimoId,
    campania_id: campaniaId,
  });
  return n > 0;
}

export async function respuestasPorUnidadCampania(unidadId, campaniaId) {
  return colRespuestas()
    .find(
      { unidad_organizacional_id: unidadId, campania_id: campaniaId },
      { projection: { seudonimo_id: 0, _id: 0 } }
    )
    .toArray();
}
