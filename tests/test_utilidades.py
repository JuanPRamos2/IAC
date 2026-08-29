from web.services.classifier.utilidades import (
    calcular_confianza_de_respuesta,
    extraer_modelo_de_respuesta,
    preprocesar_texto,
    validar_entrada,
)


def test_preprocesar_texto_normaliza():
    assert preprocesar_texto("  AWS EC2!!  ") == "aws ec2"


def test_validar_entrada_vacia():
    ok, mensaje = validar_entrada("  ")
    assert ok is False
    assert "vacío" in mensaje


def test_validar_entrada_corta():
    ok, mensaje = validar_entrada("ab")
    assert ok is False
    assert "al menos" in mensaje


def test_validar_entrada_ok():
    ok, mensaje = validar_entrada("AWS Lambda")
    assert ok is True
    assert mensaje == ""


def test_extraer_modelo_unico():
    assert extraer_modelo_de_respuesta("La respuesta es PaaS") == "PaaS"


def test_extraer_modelo_sin_coincidencia():
    assert extraer_modelo_de_respuesta("no lo sé") == "No determinado"


def test_confianza_respuesta_corta_y_clara():
    assert calcular_confianza_de_respuesta("IaaS") >= 0.9
