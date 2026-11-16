import express from "express";
import cors from "cors";
import helmet from "helmet";

import { cuerpoXml } from "@bienestar/comun/cuerpoXml.js";
import { registrarManejadores } from "@bienestar/comun/errores.js";
import { montarSwagger } from "@bienestar/comun/openapi.js";
import { limiteConsumo } from "@bienestar/comun/servicio.js";
import { estadoPostgres } from "@bienestar/comun/postgres.js";
import { estadoRedis } from "@bienestar/comun/redis.js";
import { estadoMongo } from "@bienestar/comun/mongo.js";

import { router } from "./rutas.js";
import { contratoOpenApi } from "./openapi.js";

export const app = express();

app.use(cors());
app.use(helmet({ contentSecurityPolicy: false }));
app.use(cuerpoXml());
app.use(express.json({ limit: "1mb" }));
app.use(limiteConsumo(240, 60));

// Sondas de salud
app.get("/health/live", (req, res) => res.json({ estado: "VIVO" }));
app.get("/health/ready", async (req, res) => {
  const [pg, red, mg] = await Promise.all([
    estadoPostgres().catch(() => false),
    estadoRedis().catch(() => false),
    estadoMongo().catch(() => false),
  ]);
  const ok = pg && red && mg;
  res.status(ok ? 200 : 503).json({
    estado: ok ? "LISTO" : "DEGRADADO",
    dependencias: { postgresql: pg, redis: red, mongodb: mg },
  });
});

// Documentacion OpenAPI y Swagger UI
montarSwagger(app, "organizational-service", contratoOpenApi);

// Rutas versionadas
app.use("/api/v1", router);

// Manejo centralizado de errores
registrarManejadores(app);
