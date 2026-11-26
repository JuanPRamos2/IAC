import { crearContratoOpenApi, contenidoDual, PARAM_FORMATO } from "@bienestar/comun/openapi.js";

export const contratoOpenApi = crearContratoOpenApi({
  nombre: "indicators-service",
  puerto: 8113,
  version: "1.0.0",
  descripcion: "Servicio de calculo y agregacion de indicadores organizacionales de estres, carga y bienestar con garantia k >= 5 (Puerto 8113).",
  rutas: {
    "/api/v1/indicadores": {
      get: {
        summary: "Lista el catalogo de metricas e indicadores de bienestar autorizados",
        security: [{ bearerAuth: [] }],
        parameters: [PARAM_FORMATO],
        responses: {
          200: {
            description: "Catalogo de indicadores",
            content: contenidoDual(
              "ListaIndicadores",
              "indicadores_catalogo",
              "  <indicadores>\n    <indicador>\n      <clave>IND_ESTRES</clave>\n      <nombre>Percepcion de Estres Laboral</nombre>\n      <dimension_id>DIM-01</dimension_id>\n      <unidad_medida>escala_1_5</unidad_medida>\n      <umbral_alerta>3.8</umbral_alerta>\n    </indicador>\n  </indicadores>\n  <total>1</total>"
            ),
          },
        },
      },
    },
    "/api/v1/indicadores/agregados": {
      get: {
        summary: "Consulta indicadores agregados por campania y unidad con umbral k >= 5",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "campania_id", in: "query", required: true, schema: { type: "string" } },
          { name: "unidad_id", in: "query", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Indicadores agregados protegidos",
            content: contenidoDual(
              "RespuestaAgregados",
              "agregados_respuesta",
              "  <campania_id>CAMP-2026-S1</campania_id>\n  <unidad_id>UO-OPERACIONES</unidad_id>\n  <indicadores/>\n  <total>0</total>\n  <fuente>postgresql_protegido</fuente>"
            ),
          },
        },
      },
    },
    "/api/v1/indicadores/historico": {
      get: {
        summary: "Consulta evolucion temporal e historico de indicadores para una unidad",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "unidad_id", in: "query", required: true, schema: { type: "string" } },
          { name: "dimension_id", in: "query", required: false, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Serie historica de indicadores",
            content: contenidoDual(
              "RespuestaHistorico",
              "historico_respuesta",
              "  <unidad_id>UO-OPERACIONES</unidad_id>\n  <dimension_id>TODAS</dimension_id>\n  <puntos/>\n  <total>0</total>"
            ),
          },
        },
      },
    },
    "/api/v1/indicadores/calcular": {
      post: {
        summary: "Dispara procesamiento y consolidacion de indicadores agregados",
        security: [{ bearerAuth: [] }],
        parameters: [PARAM_FORMATO],
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/SolicitudCalculoIndicadores" },
            },
          },
        },
        responses: {
          200: {
            description: "Calculo completado",
            content: contenidoDual(
              "RespuestaCalculoIndicadores",
              "calculo_respuesta",
              "  <resultado>CALCULADO</resultado>\n  <campania_id>CAMP-2026-S1</campania_id>\n  <unidades_consolidadas>5</unidades_consolidadas>\n  <mensaje>Indicadores procesados bajo estricto cumplimiento del umbral k &gt;= 5.</mensaje>"
            ),
          },
        },
      },
    },
  },
  esquemas: {
    Indicador: {
      type: "object",
      properties: {
        clave: { type: "string" },
        nombre: { type: "string" },
        dimension_id: { type: "string", nullable: true },
        unidad_medida: { type: "string" },
        umbral_alerta: { type: "number" },
      },
    },
    ListaIndicadores: {
      type: "object",
      properties: {
        indicadores: {
          type: "array",
          items: { $ref: "#/components/schemas/Indicador" },
        },
        total: { type: "integer" },
      },
    },
    AgregadoIndicador: {
      type: "object",
      properties: {
        clave: { type: "string" },
        nombre: { type: "string" },
        dimension_id: { type: "string", nullable: true },
        valor: { type: "number", nullable: true },
        n_observaciones: { type: "integer" },
        k_umbral: { type: "integer" },
        suprimido_por_umbral: { type: "boolean" },
        nivel_riesgo: { type: "string" },
        precision: { type: "string" },
      },
    },
    RespuestaAgregados: {
      type: "object",
      properties: {
        campania_id: { type: "string" },
        unidad_id: { type: "string" },
        indicadores: {
          type: "array",
          items: { $ref: "#/components/schemas/AgregadoIndicador" },
        },
        total: { type: "integer" },
        fuente: { type: "string" },
      },
    },
    PuntoHistoricoIndicador: {
      type: "object",
      properties: {
        campania_id: { type: "string" },
        campania: { type: "string" },
        fecha: { type: "string", format: "date" },
        dimension_id: { type: "string" },
        valor: { type: "number", nullable: true },
        suprimido_por_umbral: { type: "boolean" },
        n_observaciones: { type: "integer" },
      },
    },
    RespuestaHistorico: {
      type: "object",
      properties: {
        unidad_id: { type: "string" },
        dimension_id: { type: "string" },
        puntos: {
          type: "array",
          items: { $ref: "#/components/schemas/PuntoHistoricoIndicador" },
        },
        total: { type: "integer" },
      },
    },
    SolicitudCalculoIndicadores: {
      type: "object",
      required: ["campania_id"],
      properties: {
        campania_id: { type: "string" },
      },
    },
    RespuestaCalculoIndicadores: {
      type: "object",
      properties: {
        resultado: { type: "string" },
        campania_id: { type: "string" },
        unidades_consolidadas: { type: "integer" },
        mensaje: { type: "string" },
      },
    },
  },
});
