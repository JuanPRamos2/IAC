def test_inicio(client):
    respuesta = client.get("/")
    assert respuesta.status_code == 200
    assert "Una sola aplicación".encode("utf-8") in respuesta.data


def test_clasificador(client):
    respuesta = client.get("/clasificador")
    assert respuesta.status_code == 200
    assert b"form-clasificar" in respuesta.data


def test_acerca(client):
    respuesta = client.get("/acerca")
    assert respuesta.status_code == 200
    assert b"web/" in respuesta.data


def test_salud(client):
    respuesta = client.get("/api/salud")
    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo["ok"] is True
    assert cuerpo["clasificador_configurado"] is False
