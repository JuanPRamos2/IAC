import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const html = readFileSync(new URL("../web/index.html", import.meta.url), "utf8");
const css = readFileSync(new URL("../web/css/estilos.css", import.meta.url), "utf8");
const js = readFileSync(new URL("../web/js/app.js", import.meta.url), "utf8");
const consentimiento = readFileSync(
  new URL("../src/servicios/consentimiento.servicio.js", import.meta.url),
  "utf8"
);
const encuestaRutas = readFileSync(new URL("../src/rutas/encuesta.rutas.js", import.meta.url), "utf8");
const catalogoRutas = readFileSync(new URL("../src/rutas/catalogo.rutas.js", import.meta.url), "utf8");

test("el login no expone motores, JWT ni cuentas de prueba", () => {
  const prohibido = /PostgreSQL|MongoDB|Redis|pgcrypto|JWT|TTL|seudónimo|ana\.perez|demo123|EQUIPO 03/i;
  assert.equal(prohibido.test(html), false);
  assert.match(html, /Plataforma de Bienestar Laboral/);
  assert.match(html, /cuenta corporativa/i);
  assert.match(html, /Cerrar sesión/);
});

test("la paleta corporativa usa verde bosque", () => {
  assert.match(css, /--forest-900:\s*#1b4d3e/i);
});

test("las secciones de cada perfil cargan catálogos y no dependen solo del portal", () => {
  assert.match(js, /\/catalogos\/campanias/);
  assert.match(js, /\/catalogos\/unidades/);
  assert.match(js, /\/catalogos\/instrumentos/);
  assert.match(js, /\/agregados\/parametros\/k/);
  assert.match(js, /async function cargarCampanias/);
  assert.match(js, /async function cargarUnidades/);
  assert.match(js, /async function cargarK/);
  assert.match(js, /function apiOpcional/);
});

test("el consentimiento propio y el historial de Ana no quedan en un helper inexistente", () => {
  assert.match(consentimiento, /historialConsentimientoPublico/);
  assert.match(consentimiento, /from "\.\.\/utilidades\/encuesta-documento\.js"/);
  assert.match(encuestaRutas, /\/consentimiento/);
  assert.match(encuestaRutas, /\/mias/);
  assert.match(catalogoRutas, /\/cuentas/);
  assert.match(catalogoRutas, /\/versiones-consentimiento/);
});
