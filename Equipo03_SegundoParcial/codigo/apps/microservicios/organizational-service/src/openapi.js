import { crearContratoOpenApi, contenidoDual, PARAM_FORMATO } from "@bienestar/comun/openapi.js";

export const contratoOpenApi = crearContratoOpenApi({
  nombre: "organizational-service",
  puerto: 8117,
  version: "1.0.0",
  descripcion: "Servicio de administracion de jerarquias organizacionales y control de plantilla minima k >= 5 para prevencion de inferencia (Puerto 8117).",
  rutas: {
    "/api/v1/organizacion/unidades": {
      get: {
        summary: "Lista unidades organizacionales disponibles o activas",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "activa", in: "query", required: false, schema: { type: "boolean" } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Listado de unidades",
            content: contenidoDual(
              "ListaUnidadesOrganizacion",
              "unidades_respuesta",
              "  <unidades/>\n  <total>0</total>"
            ),
          },
        },
      },
      post: {
        summary: "Crea una nueva unidad organizacional (exige plantilla declarada >= 5)",
        security: [{ bearerAuth: [] }],
        parameters: [PARAM_FORMATO],
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/SolicitudAltaUnidad" },
            },
          },
        },
        responses: {
          201: {
            description: "Unidad creada exitosamente",
            content: contenidoDual(
              "RespuestaUnidadOrganizacion",
              "unidad_respuesta",
              "  <unidad>\n    <unidad_organizacional_id>UO-OPERACIONES</unidad_organizacional_id>\n    <nombre>Operaciones</nombre>\n    <plantilla_declarada>15</plantilla_declarada>\n    <activa>true</activa>\n  </unidad>"
            ),
          },
          409: { $ref: "#/components/responses/ValidacionFallida" },
        },
      },
    },
    "/api/v1/organizacion/unidades/{id}": {
      get: {
        summary: "Obtiene detalle de una unidad organizacional",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Detalle de la unidad",
            content: contenidoDual(
              "RespuestaUnidadOrganizacion",
              "unidad_respuesta",
              "  <unidad>\n    <unidad_organizacional_id>UO-OPERACIONES</unidad_organizacional_id>\n    <nombre>Operaciones</nombre>\n    <activa>true</activa>\n  </unidad>"
            ),
          },
        },
      },
      put: {
        summary: "Actualiza los atributos de una unidad organizacional",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/SolicitudActualizacionUnidad" },
            },
          },
        },
        responses: {
          200: {
            description: "Unidad actualizada",
            content: contenidoDual(
              "RespuestaUnidadOrganizacion",
              "unidad_respuesta",
              "  <unidad>\n    <unidad_organizacional_id>UO-OPERACIONES</unidad_organizacional_id>\n    <nombre>Operaciones</nombre>\n    <activa>true</activa>\n  </unidad>"
            ),
          },
        },
      },
      delete: {
        summary: "Baja logica de la unidad (valida que no tenga dependencias hijas activas)",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Unidad desactivada",
            content: contenidoDual(
              "RespuestaUnidadOrganizacion",
              "unidad_respuesta",
              "  <unidad>\n    <unidad_organizacional_id>UO-OPERACIONES</unidad_organizacional_id>\n    <activa>false</activa>\n  </unidad>"
            ),
          },
          409: { description: "Tiene dependencias hijas activas" },
        },
      },
    },
    "/api/v1/organizacion/unidades/{id}/arbol": {
      get: {
        summary: "Recupera la jerarquia y arbol subordinado completo usando CTE recursivo",
        security: [{ bearerAuth: [] }],
        parameters: [
          { name: "id", in: "path", required: true, schema: { type: "string" } },
          PARAM_FORMATO,
        ],
        responses: {
          200: {
            description: "Arbol jerarquico de unidades subordinadas",
            content: contenidoDual(
              "ArbolOrganizacional",
              "arbol_organizacional_respuesta",
              "  <unidad_raiz_id>UO-OPERACIONES</unidad_raiz_id>\n  <total_nodos>1</total_nodos>\n  <nodos/>"
            ),
          },
        },
      },
    },
  },
  esquemas: {
    UnidadOrganizacional: {
      type: "object",
      properties: {
        unidad_organizacional_id: { type: "string" },
        nombre: { type: "string" },
        descripcion: { type: "string", nullable: true },
        tipo: { type: "string" },
        unidad_padre_id: { type: "string", nullable: true },
        nivel_jerarquico: { type: "integer" },
        plantilla_declarada: { type: "integer" },
        activa: { type: "boolean" },
        fecha_creacion: { type: "string", format: "date-time" },
        fecha_actualizacion: { type: "string", format: "date-time" },
      },
    },
    SolicitudAltaUnidad: {
      type: "object",
      required: ["nombre", "plantilla_declarada"],
      properties: {
        unidad_id: { type: "string" },
        nombre: { type: "string", minLength: 3, maxLength: 100 },
        descripcion: { type: "string", nullable: true },
        tipo: { type: "string", default: "DEPARTAMENTO" },
        padre_id: { type: "string", nullable: true },
        nivel: { type: "integer", minimum: 1, maximum: 10, default: 1 },
        plantilla_declarada: { type: "integer", minimum: 5 },
        activa: { type: "boolean", default: true },
      },
    },
    SolicitudActualizacionUnidad: {
      type: "object",
      properties: {
        nombre: { type: "string", minLength: 3, maxLength: 100 },
        descripcion: { type: "string", nullable: true },
        tipo: { type: "string" },
        padre_id: { type: "string", nullable: true },
        nivel: { type: "integer", minimum: 1 },
        plantilla_declarada: { type: "integer", minimum: 5 },
        activa: { type: "boolean" },
      },
    },
    RespuestaUnidadOrganizacion: {
      type: "object",
      properties: {
        unidad: { $ref: "#/components/schemas/UnidadOrganizacional" },
      },
    },
    ListaUnidadesOrganizacion: {
      type: "object",
      properties: {
        unidades: {
          type: "array",
          items: { $ref: "#/components/schemas/UnidadOrganizacional" },
        },
        total: { type: "integer" },
      },
    },
    NodoArbolOrganizacional: {
      type: "object",
      properties: {
        unidad_organizacional_id: { type: "string" },
        nombre: { type: "string" },
        descripcion: { type: "string", nullable: true },
        tipo: { type: "string" },
        unidad_padre_id: { type: "string", nullable: true },
        nivel_jerarquico: { type: "integer" },
        plantilla_declarada: { type: "integer" },
        activa: { type: "boolean" },
        fecha_creacion: { type: "string", format: "date-time" },
        fecha_actualizacion: { type: "string", format: "date-time" },
        profundidad: { type: "integer" },
      },
    },
    ArbolOrganizacional: {
      type: "object",
      properties: {
        unidad_raiz_id: { type: "string" },
        total_nodos: { type: "integer" },
        nodos: {
          type: "array",
          items: { $ref: "#/components/schemas/NodoArbolOrganizacional" },
        },
      },
    },
  },
});
