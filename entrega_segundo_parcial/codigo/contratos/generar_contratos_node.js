import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const RAIZ = path.dirname(AQUI);
const MICROSERVICIOS = path.join(RAIZ, "apps", "microservicios");

const SERVICIOS = [
  "survey-service",
  "indicators-service",
  "support-service",
  "organizational-service",
];

function aYaml(obj, sangria = 0) {
  const esp = "  ".repeat(sangria);
  if (obj === null || obj === undefined) return "null";
  if (typeof obj === "boolean") return String(obj);
  if (typeof obj === "number") return String(obj);
  if (typeof obj === "string") {
    if (obj.includes("\n") || obj.includes(":") || obj.includes("#") || obj.includes("'") || obj.includes('"')) {
      return JSON.stringify(obj);
    }
    return obj || '""';
  }
  if (Array.isArray(obj)) {
    if (obj.length === 0) return "[]";
    return "\n" + obj.map((x) => `${esp}- ${typeof x === "object" && x !== null ? aYaml(x, sangria + 1).trimStart() : aYaml(x, sangria + 1)}`).join("\n");
  }
  if (typeof obj === "object") {
    const keys = Object.keys(obj);
    if (keys.length === 0) return "{}";
    const lineas = [];
    for (const k of keys) {
      const v = obj[k];
      if (typeof v === "object" && v !== null && (Array.isArray(v) ? v.length > 0 : Object.keys(v).length > 0)) {
        lineas.push(`${esp}${k}:${aYaml(v, sangria + 1)}`);
      } else {
        lineas.push(`${esp}${k}: ${aYaml(v, sangria + 1)}`);
      }
    }
    return (sangria > 0 ? "\n" : "") + lineas.join("\n");
  }
  return String(obj);
}

for (const svc of SERVICIOS) {
  const rutaOpenApiJs = path.join(MICROSERVICIOS, svc, "src", "openapi.js");
  if (!fs.existsSync(rutaOpenApiJs)) continue;

  const modulo = await import(`file:///${rutaOpenApiJs.replace(/\\/g, "/")}`);
  const contrato = modulo.contratoOpenApi;

  // 1. Guardar openapi.json
  const rutaJson = path.join(MICROSERVICIOS, svc, "openapi.json");
  fs.writeFileSync(rutaJson, JSON.stringify(contrato, null, 2), "utf8");

  // 2. Guardar openapi.yaml
  const rutaYaml = path.join(MICROSERVICIOS, svc, "openapi.yaml");
  fs.writeFileSync(rutaYaml, aYaml(contrato), "utf8");

  console.log(`[CONTRATOS] Generado openapi.json y openapi.yaml para ${svc}`);
}
