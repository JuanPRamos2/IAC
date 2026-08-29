import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(dir, "classify.js"), "utf8");
const sandbox = { console, globalThis: {} };
sandbox.globalThis = sandbox;
vm.runInNewContext(src, sandbox);
const { IacClassifier } = sandbox;

const cases = [
  ["Máquinas virtuales, almacenamiento y redes para instalar mi propio SO.", "IaaS"],
  ["Desplegar una aplicación web sin administrar servidores ni sistemas operativos.", "PaaS"],
  ["Correo electrónico en el navegador con suscripción mensual.", "SaaS"],
  ["Ejecutar una función cada vez que un usuario suba una imagen.", "FaaS"],
  ["Instancias EC2, discos persistentes y red privada para instalar Linux.", "IaaS"],
];

let failed = 0;
for (const [texto, esperado] of cases) {
  const out = IacClassifier.classify(texto);
  const ok = out.regex.modelo === esperado && out.nlp.modelo === esperado;
  if (!ok) {
    failed += 1;
    console.error(`FALLA: "${texto}" regex=${out.regex.modelo} nlp=${out.nlp.modelo} esperado=${esperado}`);
  }
}

const err = IacClassifier.validate("", "Ramos", "texto de prueba largo");
if (err !== "El nombre es obligatorio.") {
  failed += 1;
  console.error("FALLA validación de nombre");
}

if (failed) {
  process.exit(1);
}
console.log(`OK ${cases.length} casos del simulador`);
