import { crearContratoOpenApi, contenidoDual, PARAM_FORMATO } from "@bienestar/comun/openapi.js";

export const contratoOpenApi = crearContratoOpenApi({
  nombre: "support-service",
  puerto: 8116,
  version: "1.0.0",
  descripcion: "Servicio de gestion confidencial de solicitudes de apoyo emocional asignadas exclusivamente a especialistas (Puerto 8116).",
  rutas: {
    "/api/v1/apoyo/solicitudes": {
      post: {
        summary: "Crea una solicitud voluntaria de apoyo confidencial mediante seudonimo",
        security: [{ bearerAuth: [] }],
        parameters: [PARAM_FORMATO],
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/SolicitudApoyoCreacion" },
            },
          },
        },
        responses: {
          201: {
            description: "Solicitud de apoyo creada exitosamente",
            content: contenidoDual(
              "SolicitudApoyo",
              "solicitud_apoyo",
              "  <id>SOL-ABC123DEF456</id>\n  <seudonimo_id>SEUD-00042</seudonimo_id>\n  <estado>ABIERTA</estado>"
            ),
          },
        },
      },
      get: {
        summary: "Lista solicitudes de apoyo para atencion por parte de especialistas autorizados",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "estado", in: "query", required: false, schema: { type: "string", enum: ["ABIERTA", "EN_PROCESO", "CERRADA"] } },
          { name: "pagina", in: "query", required: false, schema: { type: "integer", minimum: 1, default: 1 } },
          { name: "tamano", in: "query", required: false, schema: { type: "integer", minimum: 1, maximum: 100, default: 50 } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Listado de solicitudes de apoyo",
            content: contenidoDual(
              "ListaSolicitudesApoyo",
              "solicitudes_apoyo",
              "  <solicitudes/>\n  <total>0</total>"
            ),
          },
        },
      },
    },
    "/api/v1/apoyo/solicitudes/{id}": {
      get: {
        summary: "Consulta el detalle y bitacora de atencion de una solicitud",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Detalle de la solicitud de apoyo",
            content: contenidoDual(
              "SolicitudApoyo",
              "solicitud_apoyo",
              "  <id>SOL-ABC123DEF456</id>\n  <seudonimo_id>SEUD-00042</seudonimo_id>\n  <estado>ABIERTA</estado>"
            ),
          },
        },
      },
    },
    "/api/v1/apoyo/solicitudes/{id}/estado": {
      put: {
        summary: "Actualiza el estado de atencion de la solicitud con notas confidenciales",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/SolicitudCambioEstadoApoyo" },
            },
          },
        },
        responses: {
          200: {
            description: "Estado actualizado",
            content: contenidoDual(
              "SolicitudApoyo",
              "solicitud_apoyo",
              "  <id>SOL-ABC123DEF456</id>\n  <estado>EN_PROCESO</estado>"
            ),
          },
          409: { description: "Transicion de estado no permitida" },
        },
      },
    },
    "/api/v1/apoyo/solicitudes/{id}/mensajes": {
      post: {
        summary: "Registra comunicacion o nota protegida entre especialista y solicitante",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/SolicitudMensajeApoyo" },
            },
          },
        },
        responses: {
          201: {
            description: "Mensaje agregado",
            content: contenidoDual(
              "RespuestaMensajeApoyo",
              "mensaje_apoyo_respuesta",
              "  <resultado>ENVIADO</resultado>\n  <solicitud_id>SOL-ABC123DEF456</solicitud_id>\n  <mensaje>Mensaje agregado al expediente confidencial de apoyo.</mensaje>"
            ),
          },
        },
      },
    },
  },
  esquemas: {
    SolicitudApoyoCreacion: {
      type: "object",
      required: ["mensaje"],
      properties: {
        mensaje: { type: "string", minLength: 8, maxLength: 1000 },
      },
    },
    SolicitudCambioEstadoApoyo: {
      type: "object",
      required: ["estado"],
      properties: {
        estado: { type: "string", enum: ["ABIERTA", "EN_PROCESO", "CERRADA"] },
        nota: { type: "string" },
      },
    },
    SolicitudMensajeApoyo: {
      type: "object",
      required: ["mensaje"],
      properties: {
        mensaje: { type: "string", minLength: 3, maxLength: 1000 },
      },
    },
    RespuestaMensajeApoyo: {
      type: "object",
      properties: {
        resultado: { type: "string" },
        solicitud_id: { type: "string" },
        mensaje: { type: "string" },
        fecha: { type: "string", format: "date-time" },
      },
    },
    SolicitudApoyo: {
      type: "object",
      properties: {
        id: { type: "string" },
        seudonimo_id: { type: "string" },
        mensaje: { type: "string" },
        fecha: { type: "string", format: "date-time" },
        estado: { type: "string", enum: ["ABIERTA", "EN_PROCESO", "CERRADA"] },
        fecha_actualizacion: { type: "string", format: "date-time", nullable: true },
        historial: { type: "array", items: { type: "object" } },
      },
    },
    ListaSolicitudesApoyo: {
      type: "object",
      properties: {
        solicitudes: {
          type: "array",
          items: { $ref: "#/components/schemas/SolicitudApoyo" },
        },
        total: { type: "integer" },
        paginacion: {
          type: "object",
          properties: {
            pagina: { type: "integer" },
            tamano: { type: "integer" },
            total: { type: "integer" },
            total_paginas: { type: "integer" },
          },
        },
      },
    },
  },
});
