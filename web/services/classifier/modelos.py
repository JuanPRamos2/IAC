"""Modelo de resultado del clasificador."""

from dataclasses import dataclass
from typing import Dict


@dataclass
class ResultadoClasificacion:
    modelo: str
    confianza: float
    puntajes: Dict[str, float]
    texto_original: str
    texto_procesado: str
    metodo: str
