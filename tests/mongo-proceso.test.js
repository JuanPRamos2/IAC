import { test } from "node:test";
import assert from "node:assert/strict";
import { pipelineRespuestasPorUnidadCampania, pipelineConteoBitacoraPorAccion } from "../src/modelos/pipelinesMongo.js";
import { actualizarEstadoSolicitud } from "../src/modelos/Soporte.js";
import { agregarRespuestasPorUnidadCampania } from "../src/modelos/Encuesta.js";
import { conteoBitacoraPorAccion } from "../src/modelos/Bitacora.js";
import { registrarEventoProceso, eventosPorCorrelacion } from "../src/modelos/EventosProceso.js";

test("pipeline respuestas: filtra campaña y rango, agrupa por unidad", () => {
  const p = pipelineRespuestasPorUnidadCampania({ campaniaId: 3, desde: "2026-01-01", hasta: "2026-02-01" });
  assert.equal(p[0].$match.campania_id, 3);
  assert.ok(p[0].$match.fecha_respuesta.$gte instanceof Date);
  assert.ok(p[0].$match.fecha_respuesta.$lt instanceof Date);
  assert.ok(p[1].$group);
  assert.ok(!JSON.stringify(p).includes("seudonimo"));
});

test("pipeline bitácora: sin filtros -> $match vacío", () => {
  const p = pipelineConteoBitacoraPorAccion();
  assert.deepEqual(p[0].$match, {});
  assert.equal(p[1].$group._id.accion, "$accion");
});

test("agregar respuestas usa aggregate de la colección inyectada", async () => {
  let recibido;
  const col = { aggregate: (p) => ((recibido = p), { toArray: async () => [{ total: 2 }] }) };
  assert.deepEqual(await agregarRespuestasPorUnidadCampania({ campaniaId: 1 }, col), [{ total: 2 }]);
  assert.equal(recibido[0].$match.campania_id, 1);
});

test("conteo bitácora por acción", async () => {
  const col = { aggregate: () => ({ toArray: async () => [{ accion: "X", total: 1 }] }) };
  assert.equal((await conteoBitacoraPorAccion({}, col))[0].accion, "X");
});

test("actualizarEstadoSolicitud: $set estado + $push historial", async () => {
  let args;
  const col = { findOneAndUpdate: async (...a) => ((args = a), { value: { estado: "CERRADA" } }) };
  const r = await actualizarEstadoSolicitud({ id: "abc", estado: "CERRADA", actor_id: "u1", nota: "ok" }, col);
  assert.equal(r.estado, "CERRADA");
  assert.equal(args[1].$set.estado, "CERRADA");
  assert.equal(args[1].$push.historial.actor_id, "u1");
  assert.equal(args[1].$push.historial.nota, "ok");
});

test("actualizarEstadoSolicitud rechaza estado inválido", async () => {
  await assert.rejects(() => actualizarEstadoSolicitud({ id: "a", estado: "X", actor_id: "u" }, {}));
});

test("eventos_proceso: no persiste empleado_id y consulta por correlación", async () => {
  let doc;
  const col = {
    insertOne: async (d) => ((doc = d), { insertedId: "i1" }),
    find: (q) => ({ sort: () => ({ toArray: async () => [q] }) }),
  };
  const e = await registrarEventoProceso({ seudonimo_id: "s", correlacion_id: "c", tipo: "T" }, col);
  assert.equal(e._id, "i1");
  assert.ok(!("empleado_id" in doc));
  assert.deepEqual(await eventosPorCorrelacion("c", col), [{ correlacion_id: "c" }]);
});
