import * as Catalogo from "../modelos/Catalogo.js";
import * as Usuario from "../modelos/Usuario.js";
import * as Encuesta from "../modelos/Encuesta.js";
import * as Soporte from "../modelos/Soporte.js";
import * as Catalogos from "./catalogo.servicio.js";
import { registrarAsync } from "./auditoria.servicio.js";
import { HttpError } from "../utilidades/errores.js";
import { ACCIONES, RESULTADOS, RECURSOS, PERFILES } from "../utilidades/catalogos-auditoria.js";
import { invalidarTodosLosCachesAgregado } from "./cache-agregado.js";

async function seguro(fn, fallback) {
  try {
    return await fn();
  } catch (err) {
    console.error(err.message);
    return fallback;
  }
}

export async function escritorio(actor) {
  const ctx = await seguro(() => Usuario.contextoOperativo(actor.usuario_id), null);
  const out = {
    perfil: actor.perfil,
    unidad_organizacional_id: ctx?.unidad_organizacional_id || null,
    unidades: await seguro(() => Catalogos.unidades(actor), []),
    campanias: await seguro(() => Catalogos.campanias(actor), []),
    instrumentos: [],
    k: 5,
    parametros: {},
  };
  if (actor.perfil === PERFILES.ADMIN_SISTEMA || actor.perfil === PERFILES.AUDITOR) {
    out.instrumentos = await seguro(() => Catalogos.instrumentos(), []);
  }
  if (actor.perfil !== PERFILES.COLAB) {
    out.k = await seguro(() => Catalogo.leerUmbralK(), 5);
    out.parametros = await seguro(() => Catalogo.leerParametros(), {});
  }
  return out;
}

export async function miConsentimiento(actor) {
  const ctx = await Usuario.contextoOperativo(actor.usuario_id);
  if (!ctx?.seudonimo_id) {
    throw new HttpError(403, "SIN_SEUDONIMO", "Su cuenta no tiene participación operativa");
  }
  const vigente = await Catalogo.consentimientoVigente(ctx.seudonimo_id);
  const historial = historialConsentimientoPublico(
    await Catalogo.historialConsentimiento(ctx.seudonimo_id)
  );
  const versionActiva = (await Catalogo.leerParametros()).version_activa_consentimiento || null;
  return {
    participando: Boolean(vigente),
    version_vigente: vigente?.version_consentimiento_id || null,
    version_activa: versionActiva,
    historial,
  };
}

export async function cambiarMiConsentimiento({ actor, aceptar, correlacionId }) {
  const ctx = await Usuario.contextoOperativo(actor.usuario_id);
  if (!ctx?.seudonimo_id) {
    throw new HttpError(403, "SIN_SEUDONIMO", "Su cuenta no tiene participación operativa");
  }
  if (aceptar) {
    const version =
      (await Catalogo.leerParametros()).version_activa_consentimiento ||
      (await Catalogo.listarVersionesConsentimiento())[0]?.version_consentimiento_id;
    if (!version) throw new HttpError(400, "PAYLOAD_INVALIDO", "No hay aviso de privacidad activo");
    await Catalogo.aceptarConsentimiento(ctx.seudonimo_id, version);
  } else {
    await Catalogo.revocarConsentimientosVigentes(ctx.seudonimo_id);
  }
  await registrarAsync({
    actor_id: actor.usuario_id,
    actor_perfil: actor.perfil,
    accion: ACCIONES.CAMBIO_CONSENTIMIENTO,
    recurso: RECURSOS.VERSION_CONSENTIMIENTO,
    resultado: RESULTADOS.EXITO,
    correlacion_id: correlacionId,
  });
  return miConsentimiento(actor);
}

export async function misEvaluaciones(actor) {
  const ctx = await Usuario.contextoOperativo(actor.usuario_id);
  if (!ctx?.seudonimo_id) {
    throw new HttpError(403, "SIN_SEUDONIMO", "Su cuenta no tiene participación operativa");
  }
  const docs = await Encuesta.respuestasDeSeudonimo(ctx.seudonimo_id);
  return {
    data: docs.map((d) => {
      const valores = (d.respuestas || []).map((x) => x.valor);
      const n = valores.length;
      return {
        campania_id: d.campania_id,
        fecha_respuesta: d.fecha_respuesta,
        promedio: n ? Number((valores.reduce((a, b) => a + b, 0) / n).toFixed(2)) : null,
      };
    }),
  };
}

export async function solicitarApoyo({ actor, mensaje, correlacionId }) {
  const texto = String(mensaje || "").trim();
  if (texto.length < 8) {
    throw new HttpError(400, "PAYLOAD_INVALIDO", "Escriba una solicitud con más detalle");
  }
  const ctx = await Usuario.contextoOperativo(actor.usuario_id);
  if (!ctx?.seudonimo_id) {
    throw new HttpError(403, "SIN_SEUDONIMO", "Su cuenta no tiene participación operativa");
  }
  const out = await Soporte.crearSolicitud({ seudonimo_id: ctx.seudonimo_id, mensaje: texto.slice(0, 1000) });
  return { ok: true, fecha: out.fecha };
}

export async function listarApoyo() {
  const rows = await Soporte.listarSolicitudes();
  return {
    data: rows.map((r) => ({
      fecha: r.fecha,
      mensaje: r.mensaje,
      estado: r.estado || "ABIERTA",
    })),
  };
}

export async function cuentas() {
  return {
    usuarios: await Usuario.listarCuentas(),
    perfiles: await Usuario.listarPerfiles(),
  };
}

export async function configuracion() {
  const parametros = await Catalogo.leerParametros();
  return {
    k: Number(parametros.k || 5),
    version_activa_consentimiento: parametros.version_activa_consentimiento || null,
    versiones: await Catalogo.listarVersionesConsentimiento(),
  };
}

export async function guardarConfiguracion({ actor, k, version_activa_consentimiento, correlacionId }) {
  if (k !== undefined && k !== null && k !== "") {
    const valor = Number(k);
    if (!Number.isInteger(valor) || valor < 2 || valor > 50) {
      throw new HttpError(400, "K_INVALIDO", "k debe ser un entero entre 2 y 50");
    }
    await Catalogo.actualizarUmbralK(valor, actor.usuario_id);
    await invalidarTodosLosCachesAgregado();
    await registrarAsync({
      actor_id: actor.usuario_id,
      actor_perfil: actor.perfil,
      accion: ACCIONES.CAMBIO_UMBRAL_K,
      recurso: RECURSOS.PARAMETRO_GLOBAL,
      resultado: RESULTADOS.EXITO,
      correlacion_id: correlacionId,
    });
  }
  if (version_activa_consentimiento) {
    await Catalogo.actualizarParametro(
      "version_activa_consentimiento",
      version_activa_consentimiento,
      actor.usuario_id
    );
    await registrarAsync({
      actor_id: actor.usuario_id,
      actor_perfil: actor.perfil,
      accion: ACCIONES.CAMBIO_CONSENTIMIENTO,
      recurso: RECURSOS.VERSION_CONSENTIMIENTO,
      resultado: RESULTADOS.EXITO,
      correlacion_id: correlacionId,
    });
  }
  return configuracion();
}
