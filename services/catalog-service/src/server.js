import { crearAppCatalogService } from "./app.js";
import { config } from "./config/env.js";

const puerto = Number(config.port || 3002);
const app = crearAppCatalogService();

app.listen(puerto, () => {
  console.log(`[catalog-service] Activo y escuchando en http://0.0.0.0:${puerto}`);
  console.log(`[catalog-service] Sonda de salud en http://0.0.0.0:${puerto}/health`);
  console.log(`[catalog-service] Catálogos v1 en http://0.0.0.0:${puerto}/api/v1/catalogos`);
});
