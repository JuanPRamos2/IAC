"""Preprocesamiento y validación de texto para el clasificador."""

from __future__ import annotations

import re
from typing import Tuple

MODELOS = ("IaaS", "PaaS", "SaaS", "FaaS")


def preprocesar_texto(texto: str) -> str:
    texto = texto.lower()
    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def validar_entrada(
    texto: str,
    longitud_minima: int = 3,
    longitud_maxima: int = 1000,
) -> Tuple[bool, str]:
    if not isinstance(texto, str):
        return False, "El texto debe ser una cadena de caracteres"
    if not texto.strip():
        return False, "El texto no puede estar vacío"
    if len(texto) < longitud_minima:
        return False, f"El texto debe tener al menos {longitud_minima} caracteres"
    if len(texto) > longitud_maxima:
        return False, f"El texto no puede tener más de {longitud_maxima} caracteres"
    return True, ""


def extraer_modelo_de_respuesta(respuesta: str) -> str:
    respuesta = respuesta.strip().lower()
    encontrados = [modelo for modelo in MODELOS if modelo.lower() in respuesta]
    if len(encontrados) == 1:
        return encontrados[0]
    if not encontrados:
        return "No determinado"
    return encontrados[0]


def calcular_confianza_de_respuesta(respuesta: str) -> float:
    respuesta = respuesta.strip().lower()
    positivos = 0
    negativos = 0

    coincidencias = sum(respuesta.count(modelo.lower()) for modelo in MODELOS)
    if len(respuesta) < 20 and coincidencias == 1:
        positivos += 2
    if len(respuesta) > 20:
        positivos += 1
    if coincidencias > 1:
        negativos += 1

    incertidumbre = ("quizás", "tal vez", "posiblemente", "probablemente", "no estoy seguro")
    if any(palabra in respuesta for palabra in incertidumbre):
        negativos += 1

    confianza = 0.8 + (positivos * 0.1) - (negativos * 0.2)
    return max(0.0, min(1.0, confianza))
