"""API JSON del monolito."""

from flask import Blueprint, current_app, jsonify, request

from web.services.classifier import ClasificadorModelosNube

api_bp = Blueprint("api", __name__)


@api_bp.get("/salud")
def salud():
    tiene_clave = bool(current_app.config.get("OPENROUTER_API_KEY"))
    return jsonify(
        {
            "ok": True,
            "servicio": "iac-web",
            "clasificador_configurado": tiene_clave,
        }
    )


@api_bp.post("/clasificar")
def clasificar():
    payload = request.get_json(silent=True) or {}
    texto = payload.get("texto", "")
    if not isinstance(texto, str):
        return jsonify({"error": "El campo 'texto' debe ser una cadena."}), 400

    if not current_app.config.get("OPENROUTER_API_KEY"):
        return jsonify(
            {
                "error": "Falta OPENROUTER_API_KEY. Copia .env.example a .env y añade tu clave.",
            }
        ), 503

    clasificador = ClasificadorModelosNube()
    try:
        resultado = clasificador.clasificar(texto)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if resultado.modelo == "Error":
        return jsonify(
            {
                "error": "No se pudo clasificar el texto. Inténtalo de nuevo más tarde.",
            }
        ), 502

    return jsonify(
        {
            "modelo": resultado.modelo,
            "confianza": resultado.confianza,
            "puntajes": resultado.puntajes,
            "texto_original": resultado.texto_original,
            "texto_procesado": resultado.texto_procesado,
            "metodo": resultado.metodo,
        }
    )
