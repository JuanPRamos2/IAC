import * as Catalogo from "../modelos/Catalogo.js";
import { registrarAsync } from "./auditoria.servicio.js";
import { HttpError } from "../utilidades/errores.js";
import { ACCIONES, RESULTADOS, RECURSOS } from "../utilidades/catalogos-auditoria.js";
import { historialConsentimientoPublico } from "../utilidades/encuesta-documento.js";

export async function historialPorSeudonimo({ actor, seudonimoId, correlacionId }) {
  if (!seudonimoId) {
    throw new HttpError(400, "PAYLOAD_INVALIDO", "seudonimo_id es obligatorio");
  }
  const existe = await Catalogo.existeSeudonimo(seudonimoId);
  if (!existe) {
    throw new HttpError(404, "SEUDONIMO_INVALIDO", "El seudónimo no existe");
  }

  const filas = await Catalogo.historialConsentimiento(seudonimoId);
  await registrarAsync({
    actor_id: actor.usuario_id,
    actor_perfil: actor.perfil,
    accion: ACCIONES.CONSULTA_HISTORIAL_CONSENTIMIENTO,
    recurso: RECURSOS.VERSION_CONSENTIMIENTO,
    resultado: RESULTADOS.EXITO,
    correlacion_id: correlacionId,
  });

  return { seudonimo_id: seudonimoId, data: historialConsentimientoPublico(filas) };
}
