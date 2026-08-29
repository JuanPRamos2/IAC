"""Clasificador de servicios en la nube usando un modelo de lenguaje."""

from __future__ import annotations

import logging
from typing import Optional

import requests

from web.config import Config
from web.services.classifier.modelos import ResultadoClasificacion
from web.services.classifier.utilidades import (
    calcular_confianza_de_respuesta,
    extraer_modelo_de_respuesta,
    preprocesar_texto,
    validar_entrada,
)

logger = logging.getLogger(__name__)

_PUNTAJES_VACIOS = {"IaaS": 0.0, "PaaS": 0.0, "SaaS": 0.0, "FaaS": 0.0}


class ClasificadorModelosNube:
    def __init__(self, usar_nlp: bool = True, clave_api: Optional[str] = None):
        self.usar_nlp = usar_nlp
        self.clave_api = clave_api if clave_api is not None else Config.OPENROUTER_API_KEY
        self.url_api = Config.OPENROUTER_API_URL
        self.modelo = Config.DEEPSEEK_MODEL
        self.max_tokens = Config.MAX_TOKENS
        self.temperature = Config.TEMPERATURE
        self.longitud_minima = Config.MIN_TEXT_LENGTH
        self.longitud_maxima = Config.MAX_TEXT_LENGTH
        self.timeout = Config.API_TIMEOUT_SECONDS

    def clasificar(self, texto: str) -> ResultadoClasificacion:
        es_valido, mensaje = validar_entrada(
            texto,
            self.longitud_minima,
            self.longitud_maxima,
        )
        if not es_valido:
            raise ValueError(mensaje)
        if not self.usar_nlp:
            raise NotImplementedError("El modo sin NLP no está implementado")
        return self._clasificar_con_nlp(texto)

    def _clasificar_con_nlp(self, texto: str) -> ResultadoClasificacion:
        texto_procesado = preprocesar_texto(texto)
        if not self.clave_api:
            logger.warning("OPENROUTER_API_KEY no está configurada")
            return self._error(texto, texto_procesado)

        instruccion = (
            "Analiza el siguiente texto y determina a qué modelo de servicio "
            "en la nube corresponde:\n\n"
            f'Texto: "{texto}"\n\n'
            "Los modelos posibles son:\n"
            "- IaaS (Infrastructure as a Service): infraestructura, servidores, "
            "almacenamiento, redes\n"
            "- PaaS (Platform as a Service): plataformas de desarrollo y despliegue\n"
            "- SaaS (Software as a Service): aplicaciones accesibles desde el navegador\n"
            "- FaaS (Function as a Service): funciones sin servidor\n\n"
            "Responde únicamente con el modelo correspondiente (IaaS, PaaS, SaaS o FaaS)."
        )

        try:
            respuesta = requests.post(
                self.url_api,
                json={
                    "model": self.modelo,
                    "messages": [{"role": "user", "content": instruccion}],
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                },
                headers={
                    "Authorization": f"Bearer {self.clave_api}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            respuesta.raise_for_status()
            contenido = respuesta.json()["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            logger.exception("Fallo al clasificar con el proveedor NLP")
            return self._error(texto, texto_procesado)

        modelo_extraido = extraer_modelo_de_respuesta(contenido)
        puntajes = {nombre: 1.0 if nombre == modelo_extraido else 0.0 for nombre in _PUNTAJES_VACIOS}
        return ResultadoClasificacion(
            modelo=modelo_extraido,
            confianza=calcular_confianza_de_respuesta(contenido),
            puntajes=puntajes,
            texto_original=texto,
            texto_procesado=texto_procesado,
            metodo="deepseek_nlp",
        )

    @staticmethod
    def _error(texto: str, texto_procesado: str) -> ResultadoClasificacion:
        return ResultadoClasificacion(
            modelo="Error",
            confianza=0.0,
            puntajes=dict(_PUNTAJES_VACIOS),
            texto_original=texto,
            texto_procesado=texto_procesado,
            metodo="error",
        )
