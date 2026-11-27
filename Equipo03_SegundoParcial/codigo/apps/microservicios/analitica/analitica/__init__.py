"""Analítica de bienestar organizacional de Bienestar Nexum.

Paquete PURO: sin Flask, sin conexión a base de datos, sin estado global.
Recibe listas de diccionarios y devuelve diccionarios.

Esa separación no es estética. El algoritmo es lo que hay que documentar
con pseudocódigo, medir con datos masivos y defender ante el profesor; si
viviera dentro de un endpoint, probarlo exigiría levantar el servicio
entero y medirlo sería medir también Flask, la red y PostgreSQL. Aquí se
mide el algoritmo y nada más.
"""
from .motor import analizar, construir_perfiles, detectar_anomalias, priorizar
from .ruido import cola_laplace, significancia, umbral_para_confianza
from .tendencia import mann_kendall, theil_sen
from .agrupamiento import elegir_k, kmedias, silueta

__all__ = ["analizar", "construir_perfiles", "detectar_anomalias",
           "priorizar", "cola_laplace", "significancia",
           "umbral_para_confianza", "mann_kendall", "theil_sen",
           "elegir_k", "kmedias", "silueta"]
