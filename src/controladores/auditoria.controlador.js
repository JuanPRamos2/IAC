import * as Bitacora from "../modelos/Bitacora.js";
import { asyncHandler } from "../utilidades/errores.js";

export const listar = asyncHandler(async (req, res) => {
  const data = await Bitacora.listarBitacora({ limite: req.query.limite });
  res.json({
    data: data.map((row) => ({
      actor_id: row.actor_id,
      actor_perfil: row.actor_perfil,
      accion: row.accion,
      recurso: row.recurso,
      resultado: row.resultado,
      correlacion_id: row.correlacion_id,
      timestamp: row.timestamp,
    })),
  });
});
