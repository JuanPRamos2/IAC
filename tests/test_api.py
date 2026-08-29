from unittest.mock import patch

from web.services.classifier.modelos import ResultadoClasificacion


def test_clasificar_sin_clave(client):
    respuesta = client.post("/api/clasificar", json={"texto": "AWS EC2 servidores virtuales"})
    assert respuesta.status_code == 503
    assert "OPENROUTER_API_KEY" in respuesta.get_json()["error"]


def test_clasificar_texto_invalido(client, app):
    app.config["OPENROUTER_API_KEY"] = "test-key"
    respuesta = client.post("/api/clasificar", json={"texto": "ab"})
    assert respuesta.status_code == 400


def test_clasificar_ok(client, app):
    app.config["OPENROUTER_API_KEY"] = "test-key"
    falso = ResultadoClasificacion(
        modelo="IaaS",
        confianza=0.95,
        puntajes={"IaaS": 1.0, "PaaS": 0.0, "SaaS": 0.0, "FaaS": 0.0},
        texto_original="AWS EC2",
        texto_procesado="aws ec2",
        metodo="deepseek_nlp",
    )
    with patch(
        "web.blueprints.api.ClasificadorModelosNube.clasificar",
        return_value=falso,
    ):
        respuesta = client.post("/api/clasificar", json={"texto": "AWS EC2 servidores virtuales"})
    assert respuesta.status_code == 200
    assert respuesta.get_json()["modelo"] == "IaaS"
