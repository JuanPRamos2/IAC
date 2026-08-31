import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const html = readFileSync(new URL("../web/index.html", import.meta.url), "utf8");
const css = readFileSync(new URL("../web/css/estilos.css", import.meta.url), "utf8");

test("el login no expone motores, JWT ni cuentas de prueba", () => {
  const prohibido = /PostgreSQL|MongoDB|Redis|pgcrypto|JWT|TTL|seudónimo|ana\.perez|demo123/i;
  assert.equal(prohibido.test(html), false);
  assert.match(html, /Plataforma de Bienestar Laboral/);
  assert.match(html, /cuenta corporativa/i);
  assert.match(html, /Cerrar sesión/);
});

test("la paleta corporativa usa verde bosque", () => {
  assert.match(css, /--forest-900:\s*#1b4d3e/i);
});
