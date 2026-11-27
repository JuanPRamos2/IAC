// Constructores puros de pipelines de agregación (sin acceso a BD; testeables sin Mongo).

function rangoFecha(campo, desde, hasta) {
  const r = {};
  if (desde) r.$gte = new Date(desde);
  if (hasta) r.$lt = new Date(hasta);
  return Object.keys(r).length ? { [campo]: r } : {};
}

export function pipelineRespuestasPorUnidadCampania({ campaniaId, desde, hasta } = {}) {
  const match = { ...rangoFecha("fecha_respuesta", desde, hasta) };
  if (campaniaId !== undefined) match.campania_id = campaniaId;
  return [
    { $match: match },
    {
      $group: {
        _id: { unidad_organizacional_id: "$unidad_organizacional_id", campania_id: "$campania_id" },
        total: { $sum: 1 },
      },
    },
    {
      $project: {
        _id: 0,
        unidad_organizacional_id: "$_id.unidad_organizacional_id",
        campania_id: "$_id.campania_id",
        total: 1,
      },
    },
    { $sort: { campania_id: 1, unidad_organizacional_id: 1 } },
  ];
}

export function pipelineConteoBitacoraPorAccion({ desde, hasta } = {}) {
  return [
    { $match: rangoFecha("timestamp", desde, hasta) },
    { $group: { _id: { accion: "$accion", resultado: "$resultado" }, total: { $sum: 1 } } },
    { $project: { _id: 0, accion: "$_id.accion", resultado: "$_id.resultado", total: 1 } },
    { $sort: { total: -1, accion: 1 } },
  ];
}
