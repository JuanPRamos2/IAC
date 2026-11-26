/**
 * Notificador resiliente servicio-a-servicio para notificaciones internas.
 *
 * Firma el cuerpo JSON con HMAC-SHA256 usando JWT_SECRETO y envia los
 * encabezados X-Servicio-Timestamp, X-Servicio-Firma y X-Correlacion-Id
 * hacia {NOTIFICATIONS_SERVICE_URL}/api/v1/notificaciones/evento-interno.
 *
 * Nunca lanza excepciones: si notifications-service no responde o falla la
 * entrega, devuelve false para no interrumpir la operacion principal.
 */
import { createHmac } from "node:crypto";
import { jwt as cfgJwt, esDeveloper } from "./entorno.js";

function obtenerSecreto() {
  return process.env.JWT_SECRETO || cfgJwt.secreto || (esDeveloper ? "secreto-solo-para-developer" : "");
}

export async function notificarEventoInterno({
  tipo,
  destinatarios = [],
  unidad_organizacional_id = null,
  titulo,
  mensaje,
  metadata = {},
  correlacionId = "",
  timeoutMs = 1500,
} = {}) {
  const secreto = obtenerSecreto();
  if (!secreto) {
    console.warn("[NOTIFICADOR] Falta JWT_SECRETO para firmar evento interno");
    return false;
  }

  const baseUrl = (process.env.NOTIFICATIONS_SERVICE_URL || "http://notifications-service:8000").replace(/\/+$/, "");
  const url = `${baseUrl}/api/v1/notificaciones/evento-interno`;

  const payload = {
    tipo,
    destinatarios: Array.isArray(destinatarios) ? destinatarios : [],
    titulo,
    mensaje,
    metadata: metadata && typeof metadata === "object" && !Array.isArray(metadata) ? metadata : {},
  };
  if (unidad_organizacional_id) {
    payload.unidad_organizacional_id = unidad_organizacional_id;
  }

  try {
    const cuerpo = JSON.stringify(payload);
    const ts = String(Math.floor(Date.now() / 1000));
    const firma = createHmac("sha256", secreto)
      .update(`${ts}.${cuerpo}`, "utf8")
      .digest("hex");

    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "X-Servicio-Timestamp": ts,
        "X-Servicio-Firma": firma,
        "X-Correlacion-Id": String(correlacionId || ""),
      },
      body: cuerpo,
      signal: AbortSignal.timeout(timeoutMs),
    });

    return resp.ok;
  } catch (err) {
    console.warn(`[NOTIFICADOR] Fallo evento interno (${tipo}) hacia ${url}: ${err?.message || err}`);
    return false;
  }
}
