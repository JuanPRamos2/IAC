import { redis } from "../config/redis.js";
import * as Catalogo from "../modelos/Catalogo.js";
import * as Encuesta from "../modelos/Encuesta.js";
import * as Usuario from "../modelos/Usuario.js";
import { registrarAsync } from "./auditoria.servicio.js";
import { publicarAgregado } from "../utilidades/privacidad.js";
import { HttpError } from "../utilidades/errores.js";
import { ACCIONES, RESULTADOS, RECURSOS, PERFILES } from "../utilidades/catalogos-auditoria.js";

function claveCache(unidad, campania) {
  return `cache:agregado:${unidad}:${campania}`;
}
function claveLock(unidad) {
  return `lock:calculo_agregado:${unidad}`;
}

function promedio(docs) {
  let suma = 0;
  let n = 0;
  const porReactivo = {};
  for (const doc of docs) {
    for (const r of doc.respuestas || []) {
      suma += r.valor;
      n += 1;
      if (!porReactivo[r.reactivo_id]) porReactivo[r.reactivo_id] = { suma: 0, n: 0 };
      porReactivo[r.reactivo_id].suma += r.valor;
      porReactivo[r.reactivo_id].n += 1;
    }
  }
  const detalle = Object.fromEntries(
    Object.entries(porReactivo).map(([id, v]) => [id, Number((v.suma / v.n).toFixed(2))])
  );
  return {
    promedioGlobal: n ? Number((suma / n).toFixed(2)) : null,
    detalle,
  };
}

export async function consultarAgregado({ actor, unidadId, campaniaId, correlacionId }) {
  if (actor.perfil === PERFILES.COLAB) {
    throw new HttpError(403, "RBAC", "El colaborador no consulta agregados");
  }
  if (actor.perfil === PERFILES.LIDER_TURNO) {
    const ctx = await Usuario.contextoOperativo(actor.usuario_id);
    if (ctx?.unidad_organizacional_id !== unidadId) {
      throw new HttpError(403, "RBAC", "Solo puedes ver agregados de tu unidad");
    }
  }

  const cacheKey = claveCache(unidadId, campaniaId);
  const cached = await redis.get(cacheKey);
  if (cached) {
    const parsed = JSON.parse(cached);
    await registrarAsync({
      actor_id: actor.usuario_id,
      actor_perfil: actor.perfil,
      accion: ACCIONES.CONSULTA_AGREGADO,
      recurso: RECURSOS.UNIDAD_ORGANIZACIONAL,
      resultado: parsed.visible ? RESULTADOS.EXITO : RESULTADOS.GRUPO_INSUFICIENTE,
      correlacion_id: correlacionId,
    });
    return parsed;
  }

  const lock = await redis.set(claveLock(unidadId), actor.usuario_id, "EX", 10, "NX");
  if (!lock) {
    await new Promise((r) => setTimeout(r, 200));
    const again = await redis.get(cacheKey);
    if (again) return JSON.parse(again);
  }

  try {
    const campania = await Catalogo.obtenerCampania(campaniaId);
    if (!campania) throw new HttpError(404, "CAMPANIA_INVALIDA", "Campaña no encontrada");

    const docs = await Encuesta.respuestasPorUnidadCampania(unidadId, campaniaId);
    const k = await Catalogo.leerUmbralK();
    const { promedioGlobal, detalle } = promedio(docs);
    const publico = publicarAgregado({
      total: docs.length,
      k,
      promedioGlobal,
      detalle,
    });

    await Catalogo.guardarAgregadoCalculado({
      campania_id: campaniaId,
      unidad_organizacional_id: unidadId,
      instrumento_id: campania.instrumento_id,
      version_instrumento: campania.version_instrumento,
      total_respuestas: docs.length,
      supera_umbral_k: docs.length >= k,
      k_umbral: k,
      promedio_global: publico.visible ? promedioGlobal : null,
      detalle_json: publico.visible ? detalle : {},
    });

    await redis.set(cacheKey, JSON.stringify(publico), "EX", 300);
    await registrarAsync({
      actor_id: actor.usuario_id,
      actor_perfil: actor.perfil,
      accion: ACCIONES.CONSULTA_AGREGADO,
      recurso: RECURSOS.UNIDAD_ORGANIZACIONAL,
      resultado: publico.visible ? RESULTADOS.EXITO : RESULTADOS.GRUPO_INSUFICIENTE,
      correlacion_id: correlacionId,
    });
    return publico;
  } finally {
    if (lock) await redis.del(claveLock(unidadId));
  }
}

export async function cambiarK({ actor, k, correlacionId }) {
  const valor = Number(k);
  if (!Number.isInteger(valor) || valor < 2 || valor > 50) {
    throw new HttpError(400, "K_INVALIDO", "k debe ser un entero entre 2 y 50");
  }
  await Catalogo.actualizarUmbralK(valor, actor.usuario_id);
  await registrarAsync({
    actor_id: actor.usuario_id,
    actor_perfil: actor.perfil,
    accion: ACCIONES.CAMBIO_UMBRAL_K,
    recurso: RECURSOS.PARAMETRO_GLOBAL,
    resultado: RESULTADOS.EXITO,
    correlacion_id: correlacionId,
  });
  return { k: valor };
}
