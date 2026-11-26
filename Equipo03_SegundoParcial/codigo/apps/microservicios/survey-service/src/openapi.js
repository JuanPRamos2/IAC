import { crearContratoOpenApi, contenidoDual, PARAM_FORMATO } from "@bienestar/comun/openapi.js";

export const contratoOpenApi = crearContratoOpenApi({
  nombre: "survey-service",
  puerto: 8112,
  version: "1.0.0",
  descripcion: "Servicio de administracion de cuestionarios, escalas, borradores y captura de respuestas de bienestar (Puerto 8112).",
  rutas: {
    "/api/v1/cuestionarios": {
      get: {
        summary: "Lista cuestionarios de evaluacion activos o disponibles",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "activo", in: "query", required: false, schema: { type: "boolean" } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Listado de cuestionarios",
            content: contenidoDual(
              "ListaCuestionarios",
              "cuestionarios_respuesta",
              "  <cuestionarios>\n    <cuestionario>\n      <cuestionario_id>INST-BIENESTAR</cuestionario_id>\n      <nombre>Encuesta de Bienestar</nombre>\n      <activo>true</activo>\n    </cuestionario>\n  </cuestionarios>\n  <total>1</total>"
            ),
          },
        },
      },
    },
    "/api/v1/cuestionarios/{id}": {
      get: {
        summary: "Obtiene detalle completo de un cuestionario con sus preguntas y escalas",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Detalle del cuestionario",
            content: contenidoDual(
              "DetalleCuestionario",
              "cuestionario_detalle",
              "  <cuestionario_id>INST-BIENESTAR</cuestionario_id>\n  <nombre>Encuesta de Bienestar</nombre>\n  <reactivos/>\n  <total_reactivos>0</total_reactivos>"
            ),
          },
        },
      },
    },
    "/api/v1/cuestionarios/{id}/borrador": {
      get: {
        summary: "Recupera el borrador temporal de respuestas del colaborador",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Borrador de encuesta",
            content: contenidoDual(
              "Borrador",
              "borrador_encuesta",
              "  <cuestionario_id>INST-BIENESTAR</cuestionario_id>\n  <seudonimo_id>SEUD-00042</seudonimo_id>\n  <respuestas/>"
            ),
          },
        },
      },
      put: {
        summary: "Guarda o actualiza borrador temporal de respuestas (con expiracion TTL)",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/SolicitudBorrador" },
            },
          },
        },
        responses: {
          200: {
            description: "Borrador guardado exitosamente",
            content: contenidoDual(
              "BorradorGuardado",
              "borrador_guardado",
              "  <mensaje>Borrador guardado exitosamente.</mensaje>\n  <cuestionario_id>INST-BIENESTAR</cuestionario_id>\n  <seudonimo_id>SEUD-00042</seudonimo_id>"
            ),
          },
        },
      },
    },
    "/api/v1/cuestionarios/{id}/respuestas": {
      post: {
        summary: "Registra respuestas definitivas de la encuesta (valida completitud y evita duplicados)",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/SolicitudRespuestasCuestionario" },
            },
          },
        },
        responses: {
          201: {
            description: "Respuestas registradas exitosamente",
            content: contenidoDual(
              "RegistroRespuestaCuestionario",
              "registro_respuesta",
              "  <estado>REGISTRADA</estado>\n  <mensaje>Respuesta registrada.</mensaje>\n  <campania_id>CAMP-2026-S1</campania_id>\n  <cuestionario_id>INST-BIENESTAR</cuestionario_id>\n  <total_respuestas>2</total_respuestas>\n  <documento_pendiente>false</documento_pendiente>"
            ),
          },
          409: { description: "Encuesta ya respondida previamente o campania no abierta" },
        },
      },
    },
  },
  esquemas: {
    Cuestionario: {
      type: "object",
      properties: {
        cuestionario_id: { type: "string" },
        nombre: { type: "string" },
        descripcion: { type: "string", nullable: true },
        tipo: { type: "string" },
        version: { type: "integer", nullable: true },
        escala_min: { type: "integer", nullable: true },
        escala_max: { type: "integer", nullable: true },
        activo: { type: "boolean" },
      },
    },
    ListaCuestionarios: {
      type: "object",
      properties: {
        cuestionarios: {
          type: "array",
          items: { $ref: "#/components/schemas/Cuestionario" },
        },
        total: { type: "integer" },
      },
    },
    ReactivoCuestionario: {
      type: "object",
      properties: {
        reactivo_id: { type: "string" },
        texto: { type: "string" },
        dimension_id: { type: "string", nullable: true },
        invertido: { type: "boolean" },
        orden: { type: "integer" },
        obligatorio: { type: "boolean" },
        escala_min: { type: "integer" },
        escala_max: { type: "integer" },
      },
    },
    DetalleCuestionario: {
      type: "object",
      properties: {
        cuestionario_id: { type: "string" },
        nombre: { type: "string" },
        descripcion: { type: "string", nullable: true },
        tipo: { type: "string" },
        version: { type: "integer", nullable: true },
        escala_min: { type: "integer", nullable: true },
        escala_max: { type: "integer", nullable: true },
        activo: { type: "boolean" },
        reactivos: {
          type: "array",
          items: { $ref: "#/components/schemas/ReactivoCuestionario" },
        },
        total_reactivos: { type: "integer" },
      },
    },
    Borrador: {
      type: "object",
      properties: {
        cuestionario_id: { type: "string" },
        seudonimo_id: { type: "string" },
        campania_id: { type: "string", nullable: true },
        respuestas: { type: "array", items: { type: "object" } },
        fecha_actualizacion: { type: "string", format: "date-time" },
      },
    },
    SolicitudBorrador: {
      type: "object",
      required: ["respuestas"],
      properties: {
        campania_id: { type: "string", nullable: true },
        respuestas: { type: "array", items: { type: "object" } },
      },
    },
    BorradorGuardado: {
      type: "object",
      properties: {
        mensaje: { type: "string" },
        cuestionario_id: { type: "string" },
        seudonimo_id: { type: "string" },
        campania_id: { type: "string", nullable: true },
        respuestas: { type: "array", items: { type: "object" } },
        fecha_actualizacion: { type: "string", format: "date-time" },
      },
    },
    SolicitudRespuestasCuestionario: {
      type: "object",
      required: ["campania_id", "respuestas"],
      properties: {
        campania_id: { type: "string" },
        respuestas: {
          type: "array",
          minItems: 1,
          items: {
            type: "object",
            required: ["reactivo_id", "valor"],
            properties: {
              reactivo_id: { type: "string" },
              valor: { type: "integer", minimum: 1, maximum: 5 },
            },
          },
        },
        comentario: { type: "string" },
        metadatos: { type: "object" },
      },
    },
    RegistroRespuestaCuestionario: {
      type: "object",
      properties: {
        estado: { type: "string" },
        mensaje: { type: "string" },
        campania_id: { type: "string" },
        cuestionario_id: { type: "string" },
        total_respuestas: { type: "integer" },
        documento_pendiente: { type: "boolean" },
      },
    },
  },
});
