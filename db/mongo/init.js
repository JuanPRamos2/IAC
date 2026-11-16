// =====================================================================
// Inicialización de la base documental — Bienestar Nexum
//
// Lo ejecuta el contenedor de MongoDB la primera vez que arranca, desde
// /docker-entrypoint-initdb.d/. Es idempotente: createIndex con el mismo
// nombre y la misma especificación no falla, y los validadores se aplican
// con collMod cuando la colección ya existe.
//
// ORIGEN Y CORRECCIONES
// =====================
// Parte del archivo que entregó el Integrante 2 y lo corrige en dos
// puntos que lo volvían inofensivo:
//
//   1. Escribía en la base "bienestar_nexum". El resto del proyecto usa
//      la que indique MONGO_BASE (por omisión "bienestar"), de modo que
//      los índices se creaban en una base que ningún servicio abría.
//      Ahora se toma del ambiente.
//
//   2. Declaraba los índices de las colecciones de los servicios de Node
//      y no los de las de Python (documentos, notificaciones, reportes).
//      Los servicios en Python los crean solos con POST /indices, pero
//      dejarlos fuera de aquí significa que una base recién levantada
//      atiende sin índices hasta que alguien se acuerde de llamar a esa
//      ruta.
//
// POR QUÉ HAY VALIDADORES Y NO SOLO ÍNDICES
// =========================================
// El validador de eventos_proceso y el de respuestas_encuesta prohíben
// propiedades adicionales en el nivel donde viven los identificadores.
// Es la última línea de la regla D-01: si una versión futura de un
// servicio mandara empleado_id por error, la base rechaza el documento en
// lugar de guardarlo. Las dos barreras anteriores (la verificación en el
// código y la ausencia del campo en el XSD) se pueden evadir con un
// cliente escrito a mano; esta no.
// =====================================================================

const nombreBase = process.env.MONGO_BASE || "bienestar";
db = db.getSiblingDB(nombreBase);
print(`[init] base documental: ${nombreBase}`);

// ---------------------------------------------------------------------
// 1. Respuestas de encuesta (espejo documental) — main-process-service
// ---------------------------------------------------------------------
// La unicidad por (seudonimo_id, campania_id) hace cumplir RN-01 también
// aquí: una respuesta por persona y campaña. La regla ya la impone
// PostgreSQL, pero el espejo documental no debe poder contradecirla.
db.respuestas_encuesta.createIndex(
  { seudonimo_id: 1, campania_id: 1 },
  { unique: true, name: "ux_seudonimo_campania" }
);
db.respuestas_encuesta.createIndex(
  { unidad_organizacional_id: 1, campania_id: 1 },
  { name: "ix_unidad_campania" }
);
db.respuestas_encuesta.createIndex({ fecha: -1 }, { name: "ix_fecha" });

const validadorRespuestas = {
  $jsonSchema: {
    bsonType: "object",
    required: ["seudonimo_id", "campania_id", "fecha"],
    properties: {
      seudonimo_id: { bsonType: "string", pattern: "^SEUD-" },
      campania_id: { bsonType: "string" },
      instrumento_id: { bsonType: ["string", "null"] },
      version_instrumento: { bsonType: ["int", "long", "null"] },
      unidad_organizacional_id: { bsonType: "string" },
      fecha: { bsonType: "date" },
      valores: { bsonType: "object" },
      comentario: { bsonType: ["string", "null"] },
      metadatos: { bsonType: ["object", "null"] },
      fecha_actualizacion: { bsonType: ["date", "null"] },
      correlacion_id: { bsonType: "string" },
    },
    // Cerrado a propósito: es lo que impide que empleado_id entre por una
    // via que el codigo no haya previsto (regla D-01).
    additionalProperties: false,
  },
};
if (!db.getCollectionNames().includes("respuestas_encuesta")) {
  db.createCollection("respuestas_encuesta",
    { validator: validadorRespuestas, validationAction: "error" });
} else {
  db.runCommand({ collMod: "respuestas_encuesta", validator: validadorRespuestas });
}

// ---------------------------------------------------------------------
// 1b. Borradores de encuestas incompletas — survey-service (8112)
// ---------------------------------------------------------------------
db.borradores_encuesta.createIndex(
  { seudonimo_id: 1, campania_id: 1 },
  { unique: true, name: "ux_borrador_seudonimo_campania" }
);
db.borradores_encuesta.createIndex(
  { fecha_expiracion: 1 },
  { expireAfterSeconds: 0, name: "ix_borrador_ttl" }
);

const validadorBorradores = {
  $jsonSchema: {
    bsonType: "object",
    required: ["seudonimo_id", "campania_id", "valores"],
    properties: {
      seudonimo_id: { bsonType: "string", pattern: "^SEUD-" },
      campania_id: { bsonType: "string" },
      instrumento_id: { bsonType: ["string", "null"] },
      version_instrumento: { bsonType: ["int", "long", "null"] },
      valores: { bsonType: "object" },
      faltantes: { bsonType: ["array", "null"] },
      fecha_guardado: { bsonType: ["date", "null"] },
      fecha_expiracion: { bsonType: ["date", "null"] },
      correlacion_id: { bsonType: ["string", "null"] },
    },
    additionalProperties: false,
  },
};
if (!db.getCollectionNames().includes("borradores_encuesta")) {
  db.createCollection("borradores_encuesta",
    { validator: validadorBorradores, validationAction: "error" });
} else {
  db.runCommand({ collMod: "borradores_encuesta", validator: validadorBorradores });
}

// ---------------------------------------------------------------------
// 2. Solicitudes de apoyo — main-process-service (8104) y support-service (8116)
// ---------------------------------------------------------------------
db.solicitudes_apoyo.createIndex({ id_publico: 1 },
  { unique: true, name: "ux_sol_id_publico" });
db.solicitudes_apoyo.createIndex({ seudonimo_id: 1, fecha: -1 },
  { name: "ix_sol_seudonimo_fecha" });
db.solicitudes_apoyo.createIndex({ estado: 1, fecha: -1 },
  { name: "ix_sol_estado_fecha" });
db.solicitudes_apoyo.createIndex({ especialista_asignado_id: 1, estado: 1, fecha: -1 },
  { sparse: true, name: "ix_sol_especialista_estado" });
db.solicitudes_apoyo.createIndex({ prioridad: 1, estado: 1, fecha: -1 },
  { sparse: true, name: "ix_sol_prioridad_estado" });

// Hilos confidenciales de comunicación protegida — support-service (8116)
db.comunicaciones_apoyo.createIndex({ solicitud_id: 1, fecha: 1 },
  { name: "ix_com_solicitud_fecha" });
db.comunicaciones_apoyo.createIndex({ seudonimo_id: 1 },
  { sparse: true, name: "ix_com_seudonimo" });

// ---------------------------------------------------------------------
// 2b. Indicadores organizacionales colectivos — indicators-service (8113)
// ---------------------------------------------------------------------
db.indicadores_organizacionales.createIndex(
  { unidad_organizacional_id: 1, campania_id: 1 },
  { name: "ix_ind_org_unidad_campania" }
);
db.indicadores_organizacionales.createIndex(
  { tipo_metrica: 1, fecha_registro: -1 },
  { name: "ix_ind_org_tipo_fecha" }
);

const validadorIndicadores = {
  $jsonSchema: {
    bsonType: "object",
    required: ["unidad_organizacional_id", "campania_id", "fuente_id", "tipo_metrica", "valor", "n_observados"],
    properties: {
      unidad_organizacional_id: { bsonType: "string" },
      campania_id: { bsonType: "string" },
      fuente_id: { bsonType: "string" },
      tipo_metrica: { bsonType: "string" },
      valor: { bsonType: ["double", "int", "long", "decimal"] },
      n_observados: { bsonType: ["int", "long"] },
      publicable: { bsonType: "bool" },
      fecha_registro: { bsonType: "date" },
      correlacion_id: { bsonType: ["string", "null"] },
    },
    // Garantía G3 y G6: sin empleado_id ni seudonimo_id en métricas colectivas
    additionalProperties: false,
  },
};
if (!db.getCollectionNames().includes("indicadores_organizacionales")) {
  db.createCollection("indicadores_organizacionales",
    { validator: validadorIndicadores, validationAction: "error" });
} else {
  db.runCommand({ collMod: "indicadores_organizacionales", validator: validadorIndicadores });
}

// ---------------------------------------------------------------------
// 3. Eventos de proceso — main-process-service
// ---------------------------------------------------------------------
const validadorEventos = {
  $jsonSchema: {
    bsonType: "object",
    required: ["seudonimo_id", "correlacion_id", "tipo", "timestamp"],
    properties: {
      seudonimo_id: { bsonType: "string" },
      correlacion_id: { bsonType: "string" },
      tipo: { bsonType: "string" },
      timestamp: { bsonType: "date" },
      detalle: { bsonType: "object" },
    },
    additionalProperties: false,
  },
};
if (!db.getCollectionNames().includes("eventos_proceso")) {
  db.createCollection("eventos_proceso",
    { validator: validadorEventos, validationAction: "error" });
} else {
  db.runCommand({ collMod: "eventos_proceso", validator: validadorEventos });
}
db.eventos_proceso.createIndex({ seudonimo_id: 1, timestamp: -1 },
  { name: "ix_evt_seudonimo_ts" });
db.eventos_proceso.createIndex({ correlacion_id: 1 }, { name: "ix_evt_correlacion" });
db.eventos_proceso.createIndex({ tipo: 1, timestamp: -1 }, { name: "ix_evt_tipo_ts" });

// ---------------------------------------------------------------------
// 4. Documentos — documents-service
// ---------------------------------------------------------------------
// Los mismos índices que declara el servicio en POST /documentos/indices.
// Estar en los dos lados no es duplicación inútil: aquí sirven para que
// una base recién levantada atienda con índices desde la primera consulta,
// y allá para poder reconstruirlos sin recrear el contenedor.
db.documentos.createIndex({ documento_id: 1 },
  { unique: true, name: "ix_documento_id" });
db.documentos.createIndex({ tipo: 1, fecha_creacion: -1 }, { name: "ix_tipo_fecha" });
db.documentos.createIndex({ seudonimo_id: 1 }, { sparse: true, name: "ix_seudonimo" });
db.documentos.createIndex({ unidad_organizacional_id: 1, campania_id: 1 },
  { sparse: true, name: "ix_unidad_campania" });

// ---------------------------------------------------------------------
// 5. Notificaciones — notifications-service
// ---------------------------------------------------------------------
db.notificaciones.createIndex({ notificacion_id: 1 },
  { unique: true, name: "ix_notif_id" });
db.notificaciones.createIndex(
  { destinatario_usuario_id: 1, leida: 1, fecha_creacion: -1 },
  { name: "ix_destinatario" });
db.notificaciones.createIndex({ tipo: 1, fecha_creacion: -1 }, { name: "ix_tipo" });
// Índice TTL: las notificaciones se borran solas cuando pasa su fecha de
// expiración (90 días). Es minimización de datos hecha por la base y no
// por un proceso que alguien tenga que acordarse de correr.
db.notificaciones.createIndex({ fecha_expiracion: 1 },
  { expireAfterSeconds: 0, name: "ix_ttl" });

// ---------------------------------------------------------------------
// 6. Reportes — reports-service
// ---------------------------------------------------------------------
db.reportes.createIndex({ reporte_id: 1 }, { unique: true, name: "ix_reporte_id" });
db.reportes.createIndex({ tipo: 1, fecha_generacion: -1 }, { name: "ix_tipo_fecha" });
db.reportes.createIndex({ sello_sha256: 1 }, { name: "ix_sello" });
db.reportes.createIndex({ generado_por: 1, fecha_generacion: -1 },
  { name: "ix_actor_fecha" });

// ---------------------------------------------------------------------
// 7. Bitácora espejo — solo lectura para análisis
// ---------------------------------------------------------------------
// La bitácora de verdad vive en PostgreSQL, con llave foránea contra
// auditoria.tipo_accion. Esta es una copia para consultas analíticas que
// serían caras en la base transaccional.
db.bitacora_auditoria.createIndex({ timestamp: -1 }, { name: "ix_bit_ts" });
db.bitacora_auditoria.createIndex({ correlacion_id: 1 }, { name: "ix_bit_correlacion" });
db.bitacora_auditoria.createIndex({ actor_id: 1, timestamp: -1 },
  { name: "ix_bit_actor_ts" });

print("[init] indices y validadores aplicados en 7 colecciones");
