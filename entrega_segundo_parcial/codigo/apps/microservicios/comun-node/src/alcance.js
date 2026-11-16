/**
 * Control de alcance organizacional jerarquico para roles LIDER y COLABORADOR.
 *
 * Utiliza un CTE recursivo sobre catalogo.unidad_organizacional para determinar
 * de forma dinamica si una unidad destino se encuentra dentro del arbol de mando
 * del actor.
 */
import { ErrorApi } from "./errores.js";
import { consultar } from "./postgres.js";

export async function obtenerUnidadesSubordinadas(unidadRaizId) {
  if (!unidadRaizId) return [];
  const filas = await consultar(
    `WITH RECURSIVE jerarquia AS (
       SELECT unidad_id
         FROM catalogo.unidad_organizacional
        WHERE unidad_id = $1 AND activa = true
       UNION ALL
       SELECT u.unidad_id
         FROM catalogo.unidad_organizacional u
         JOIN jerarquia j ON u.padre_id = j.unidad_id
        WHERE u.activa = true
     )
     SELECT unidad_id FROM jerarquia`,
    [unidadRaizId]
  );
  return filas.map((f) => f.unidad_id);
}

export async function validarAlcanceUnidad(actor, unidadDestinoId) {
  if (!actor) {
    throw new ErrorApi("TOKEN_AUSENTE", "Se requiere identidad de actor para verificar alcance.", 401);
  }

  const perfil = actor.perfil || "";
  // Perfiles con alcance global
  if (perfil === "ADMINISTRADOR" || perfil === "AUDITOR" || perfil === "ESPECIALISTA") {
    return true;
  }

  const unidadActor = actor.unidad_id || actor.unidad;
  if (!unidadActor) {
    throw new ErrorApi("SIN_UNIDAD_ASIGNADA", "El usuario no tiene una unidad organizacional asignada.", 403);
  }

  if (unidadDestinoId === unidadActor) {
    return true;
  }

  if (perfil === "LIDER") {
    const permitidas = await obtenerUnidadesSubordinadas(unidadActor);
    if (!permitidas.includes(unidadDestinoId)) {
      throw new ErrorApi(
        "FUERA_DE_ALCANCE",
        "El lider solo puede acceder a su propia unidad organizacional y dependencias subordinadas.",
        403,
        [{ unidad_solicitada: unidadDestinoId, unidad_actor: unidadActor }]
      );
    }
    return true;
  }

  // COLABORADOR solo puede ver su propia unidad
  if (unidadDestinoId !== unidadActor) {
    throw new ErrorApi(
      "FUERA_DE_ALCANCE",
      "El colaborador solo tiene permitido el acceso a su propia unidad organizacional.",
      403,
      [{ unidad_solicitada: unidadDestinoId, unidad_actor: unidadActor }]
    );
  }

  return true;
}
