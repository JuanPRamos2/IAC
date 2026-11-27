import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createHmac } from "node:crypto";

import { entero, numero, booleano, texto, arreglo } from "../src/validacion.js";
import { traducirErrorPg } from "../src/pg-errores.js";
import { aXml } from "../src/xmlizar.js";
import { crearContratoOpenApi } from "../src/openapi.js";
import { ErrorApi } from "../src/errores.js";
import { crearServicio } from "../src/servicio.js";
import { notificarEventoInterno } from "../src/notificador.js";
import { postgres as cfgPostgres } from "../src/entorno.js";
import { cerrarRedis, estrategiaReintentoRedis, obtenerRedis } from "../src/redis.js";

test("validacion.entero parsea enteros y strings de enteros", () => {
  assert.equal(entero(10, "campo"), 10);
  assert.equal(entero("42", "campo"), 42);
  assert.equal(entero(null, "campo", { requerido: false, defecto: 5 }), 5);

  assert.throws(() => entero("no-numero", "campo"), (err) => err instanceof ErrorApi && err.http === 400);
  assert.throws(() => entero(3.14, "campo"), (err) => err instanceof ErrorApi && err.http === 400);
  assert.throws(() => entero(3, "campo", { min: 5 }), (err) => err instanceof ErrorApi && err.http === 400);
});

test("validacion.booleano parsea correctamente booleano y string booleano", () => {
  assert.equal(booleano(true, "campo"), true);
  assert.equal(booleano("true", "campo"), true);
  assert.equal(booleano(false, "campo"), false);
  assert.equal(booleano("false", "campo"), false);
  assert.equal(booleano(null, "campo", { defecto: true }), true);
  assert.throws(() => booleano("invalido", "campo"), (err) => err instanceof ErrorApi && err.http === 400);
});

test("validacion.texto y arreglo validan restricciones", () => {
  assert.equal(texto("  hola  ", "campo"), "hola");
  assert.throws(() => texto("", "campo", { requerido: true }), (err) => err instanceof ErrorApi && err.http === 400);
  assert.throws(() => texto("ab", "campo", { minLong: 3 }), (err) => err instanceof ErrorApi && err.http === 400);

  assert.deepEqual(arreglo(["a", "b"], "items"), ["a", "b"]);
  assert.deepEqual(arreglo("solo-uno", "items"), ["solo-uno"]);
  assert.throws(() => arreglo([], "items", { minElementos: 1 }), (err) => err instanceof ErrorApi && err.http === 400);
});

test("pg-errores mapea codigos de PostgreSQL", () => {
  const errDuplicado = traducirErrorPg({ code: "23505", detail: "llave duplicada" });
  assert.equal(errDuplicado.http, 409);
  assert.equal(errDuplicado.codigo, "RECURSO_DUPLICADO");

  const errFk = traducirErrorPg({ code: "23503", detail: "fk no existe" });
  assert.equal(errFk.http, 422);
  assert.equal(errFk.codigo, "REFERENCIA_INVALIDA");

  const errCheck = traducirErrorPg({ code: "23514", detail: "check fallo" });
  assert.equal(errCheck.http, 422);
  assert.equal(errCheck.codigo, "RESTRICCION_VIOLADA");

  const errPermiso = traducirErrorPg({ code: "42501" });
  assert.equal(errPermiso.http, 403);
  assert.equal(errPermiso.codigo, "PERMISO_DENEGADO");
});

test("xmlizar serializa listas con elementos singulares sincronizados", () => {
  const xml = aXml({ cuestionarios: [{ id: 1 }, { id: 2 }] }, "cuestionarios_respuesta");
  assert.ok(xml.includes("<cuestionarios>"));
  assert.ok(xml.includes("<cuestionario>"));
  assert.ok(xml.includes("</cuestionario>"));
  assert.ok(xml.includes("</cuestionarios>"));
});

test("crearContratoOpenApi genera estructura OpenAPI 3.0 con 7 respuestas comunes, security, servers y ejemplos JSON/XML", () => {
  const contrato = crearContratoOpenApi({
    nombre: "Test Service",
    puerto: 8199,
    version: "1.0.0",
    descripcion: "Prueba de contrato",
    rutas: {
      "/api/v1/prueba": {
        get: {
          summary: "Endpoint de prueba",
          responses: {
            200: { description: "OK" },
          },
        },
      },
    },
  });
  assert.equal(contrato.openapi, "3.0.3");
  assert.deepEqual(contrato.security, [{ bearerAuth: [] }]);
  assert.deepEqual(contrato.servers, [
    { url: "http://localhost:8199", description: "Desarrollo local" },
    { url: "/", description: "Mismo origen" },
  ]);
  assert.equal(Object.keys(contrato.components.responses).length, 7);
  for (const resp of Object.values(contrato.components.responses)) {
    assert.ok(resp.content["application/json"].example);
    assert.ok(resp.content["application/xml"].example.startsWith('<?xml version="1.0" encoding="UTF-8"?>'));
  }
  const opResponses = contrato.paths["/api/v1/prueba"].get.responses;
  for (const code of ["200", "400", "401", "403", "404", "422", "429", "500"]) {
    assert.ok(opResponses[code], `Falta respuesta ${code}`);
  }
});

test("entorno.postgres expone statementTimeoutMs por defecto en 5000", () => {
  assert.equal(cfgPostgres.statementTimeoutMs, 5000);
});

test("crearServicio homologa /health/live, /health y soporta dependencias opcionales en /health/ready", async () => {
  process.env.VERSION_DESPLIEGUE = "v2.3.4-test";
  const { app, finalizar } = crearServicio("test-node-svc", "Servicio de prueba", {
    pg: async () => true,
    cache: [async () => { throw new Error("redis apagado"); }, "opcional"],
  });
  finalizar();

  const srv = await new Promise((resolve) => {
    const s = app.listen(0, "127.0.0.1", () => resolve(s));
  });
  try {
    const port = srv.address().port;
    const base = `http://127.0.0.1:${port}`;

    const liveRes = await fetch(`${base}/health/live`);
    assert.equal(liveRes.status, 200);
    const live = await liveRes.json();
    assert.equal(live.servicio, "test-node-svc");
    assert.equal(live.estado, "vivo");
    assert.equal(live.version, "v1");
    assert.equal(live.version_desplegada, "v2.3.4-test");
    assert.ok(live.instancia);
    assert.ok(live.arrancado_en);
    assert.equal(typeof live.segundos_arriba, "number");

    const healthRes = await fetch(`${base}/health`);
    const health = await healthRes.json();
    assert.equal(health.version_desplegada, "v2.3.4-test");

    const readyRes = await fetch(`${base}/health/ready`);
    assert.equal(readyRes.status, 200);
    const ready = await readyRes.json();
    assert.equal(ready.estado, "degradado");
    assert.deepEqual(ready.degradado_por, ["cache"]);
    assert.equal(ready.dependencias.pg.ok, true);
    assert.equal(ready.dependencias.pg.esencial, true);
    assert.equal(typeof ready.dependencias.pg.ms, "number");
    assert.equal(ready.dependencias.cache.ok, false);
    assert.equal(ready.dependencias.cache.esencial, false);
  } finally {
    delete process.env.VERSION_DESPLIEGUE;
    await new Promise((resolve) => srv.close(resolve));
  }
});

test("crearServicio /health/ready responde 503 no_listo si falla dependencia esencial", async () => {
  const { app, finalizar } = crearServicio("test-node-fail", "Prueba fallo esencial", {
    db: async () => { throw new Error("pg caido"); },
  });
  finalizar();

  const srv = await new Promise((resolve) => {
    const s = app.listen(0, "127.0.0.1", () => resolve(s));
  });
  try {
    const port = srv.address().port;
    const readyRes = await fetch(`http://127.0.0.1:${port}/health/ready`);
    assert.equal(readyRes.status, 503);
    const ready = await readyRes.json();
    assert.equal(ready.estado, "no_listo");
    assert.deepEqual(ready.falta, ["db"]);
  } finally {
    await new Promise((resolve) => srv.close(resolve));
  }
});

test("notificarEventoInterno firma HMAC-SHA256 y no lanza si falla", async () => {
  const secreto = "secreto-de-prueba-hmac";
  process.env.JWT_SECRETO = secreto;

  let recibido = null;
  const srv = http.createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => { raw += c; });
    req.on("end", () => {
      recibido = {
        url: req.url,
        ts: req.headers["x-servicio-timestamp"],
        firma: req.headers["x-servicio-firma"],
        corr: req.headers["x-correlacion-id"],
        raw,
      };
      res.writeHead(201, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ enviadas: 1 }));
    });
  });

  await new Promise((resolve) => srv.listen(0, "127.0.0.1", resolve));
  try {
    const port = srv.address().port;
    process.env.NOTIFICATIONS_SERVICE_URL = `http://127.0.0.1:${port}`;
    const ok = await notificarEventoInterno({
      tipo: "CONFIRMACION_RECIBIDA",
      destinatarios: ["USR-00001"],
      titulo: "Confirmacion de encuesta",
      mensaje: "Se registro tu respuesta en la campania CAMP-01.",
      metadata: { campania_id: "CAMP-01" },
      correlacionId: "corr-xyz-123",
    });
    assert.equal(ok, true);
    assert.equal(recibido.url, "/api/v1/notificaciones/evento-interno");
    assert.equal(recibido.corr, "corr-xyz-123");
    const esperada = createHmac("sha256", secreto)
      .update(`${recibido.ts}.${recibido.raw}`, "utf8")
      .digest("hex");
    assert.equal(recibido.firma, esperada);

    // Resiliencia ante URL inalcanzable: nunca lanza excepcion
    process.env.NOTIFICATIONS_SERVICE_URL = "http://127.0.0.1:1";
    const fallo = await notificarEventoInterno({
      tipo: "CONFIRMACION_RECIBIDA",
      destinatarios: ["USR-00001"],
      titulo: "Confirmacion",
      mensaje: "No debe lanzar excepcion al fallar.",
      timeoutMs: 300,
    });
    assert.equal(fallo, false);
  } finally {
    delete process.env.NOTIFICATIONS_SERVICE_URL;
    delete process.env.JWT_SECRETO;
    await new Promise((resolve) => srv.close(resolve));
  }
});

test("redis.estrategiaReintentoRedis nunca corta tras 10 intentos y obtenerRedis se recupera tras estado end", async () => {
  try {
    assert.equal(estrategiaReintentoRedis(1), 250);
    assert.equal(estrategiaReintentoRedis(10), 2500);
    assert.equal(estrategiaReintentoRedis(11), 2750);
    assert.equal(estrategiaReintentoRedis(12), 3000);
    assert.equal(estrategiaReintentoRedis(50), 3000);
    assert.notEqual(estrategiaReintentoRedis(100), null);

    const primero = obtenerRedis();
    assert.equal(typeof primero.options.retryStrategy, "function");
    assert.equal(primero.options.retryStrategy(11), 2750);
    assert.equal(primero.options.retryStrategy(50), 3000);
    assert.equal(primero.options.commandTimeout, 2000);
    assert.equal(primero.options.connectTimeout, 2000);
    assert.equal(primero.options.maxRetriesPerRequest, 1);
    assert.equal(obtenerRedis(), primero);

    primero.status = "end";
    const segundo = obtenerRedis();
    assert.notEqual(segundo, primero);
  } finally {
    await cerrarRedis();
  }
});
