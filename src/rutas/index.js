import { Router } from "express";
import { authRouter } from "./auth.rutas.js";
import { catalogoRouter } from "./catalogo.rutas.js";
import { encuestaRouter } from "./encuesta.rutas.js";
import { agregadoRouter } from "./agregado.rutas.js";
import { auditoriaRouter } from "./auditoria.rutas.js";
import { portalRouter } from "./portal.rutas.js";
import { catalogoV1Router } from "../../services/catalog-service/src/rutas/catalogo.rutas.js";
import { procesoV1Router } from "../../services/main-process-service/src/rutas/proceso.rutas.js";

export const api = Router();
api.use("/auth", authRouter);
api.use("/catalogos", catalogoRouter);
api.use("/encuestas", encuestaRouter);
api.use("/agregados", agregadoRouter);
api.use("/auditoria", auditoriaRouter);
api.use("/portal", portalRouter);

// Rutas versionadas v1 del segundo parcial (Integrante 2)
api.use("/v1/catalogos", catalogoV1Router);
api.use("/v1", procesoV1Router);

