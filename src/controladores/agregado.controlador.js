import * as Agregado from "../servicios/agregado.servicio.js";
import { asyncHandler } from "../utilidades/errores.js";

export const consultar = asyncHandler(async (req, res) => {
  const out = await Agregado.consultarAgregado({
    actor: req.actor,
    unidadId: req.params.unidadId,
    campaniaId: req.params.campaniaId,
    correlacionId: req.correlacionId,
  });
  res.status(out.visible ? 200 : 200).json(out);
});

export const cambiarK = asyncHandler(async (req, res) => {
  res.json(
    await Agregado.cambiarK({
      actor: req.actor,
      k: req.body?.k,
      correlacionId: req.correlacionId,
    })
  );
});
