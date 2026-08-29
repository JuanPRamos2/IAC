import assert from "node:assert/strict";
import { test } from "node:test";
import { PERFILES } from "../src/utilidades/catalogos-auditoria.js";

test("RBAC cubre los cuatro perfiles del esquema", () => {
  assert.deepEqual(Object.values(PERFILES).sort(), [
    "ADMIN_SISTEMA",
    "AUDITOR",
    "COLAB",
    "LIDER_TURNO",
  ]);
});
