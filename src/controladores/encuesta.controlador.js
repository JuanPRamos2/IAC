import * as Encuesta from "../servicios/encuesta.servicio.js";
import { asyncHandler } from "../utilidades/errores.js";

export const crear = asyncHandler(async (req, res) => {
  const out = await Encuesta.guardarAutoreporte({
    actor: req.actor,
    body: req.body,
    correlacionId: req.correlacionId,
  });
  res.status(201).json(out);
});

export const estado = asyncHandler(async (req, res) => {
  res.json(
    await Encuesta.estadoRespuesta({
      actor: req.actor,
      campaniaId: req.query.campania_id,
    })
  );
});
