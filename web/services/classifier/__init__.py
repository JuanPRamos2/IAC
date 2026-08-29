"""Clasificador de modelos de servicio en la nube (IaaS, PaaS, SaaS, FaaS)."""

from web.services.classifier.clasificador import ClasificadorModelosNube
from web.services.classifier.modelos import ResultadoClasificacion

__all__ = ["ClasificadorModelosNube", "ResultadoClasificacion"]
