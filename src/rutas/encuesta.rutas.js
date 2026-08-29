import { Router } from "express";
import * as Encuesta from "../controladores/encuesta.controlador.js";
import { autenticar } from "../middlewares/autenticacion.js";
import { autorizar } from "../middlewares/autorizacion.js";
import { PERFILES } from "../utilidades/catalogos-auditoria.js";

export const encuestaRouter = Router();
encuestaRouter.post(
  "/respuestas",
  autenticar,
  autorizar(PERFILES.COLAB),
  Encuesta.crear
);
