from setuptools import setup, find_packages

setup(
    name="analitica",
    version="1.0.0",
    description="Deteccion de anomalias y tendencias de bienestar sobre "
                "agregados protegidos",
    packages=find_packages(),
    python_requires=">=3.9",
    # Sin dependencias a proposito: numpy y scipy harian el codigo mas
    # corto y lo volverian imposible de defender renglon por renglon, que
    # es justo lo que pide la rubrica. Todo lo que hace falta —mediana,
    # erfc, exp— esta en la biblioteca estandar.
    install_requires=[],
)
