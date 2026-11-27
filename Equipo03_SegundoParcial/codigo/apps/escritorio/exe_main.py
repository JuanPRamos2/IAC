"""Punto de entrada cuando el programa va empaquetado como un solo .exe.

`cliente.py` busca los esquemas XSD subiendo tres carpetas desde su propia
ubicacion, que es correcto cuando el programa corre desde el repositorio.
Dentro de un ejecutable de PyInstaller no hay tales carpetas: el contenido
se extrae en una carpeta temporal cuya ruta esta en `sys._MEIPASS`.

Sin esto, el .exe abre la ventana, deja iniciar sesion y falla al validar
la primera respuesta con CONTRATO_AUSENTE.
"""
import os
import sys

_base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("CONTRATOS_XSD", os.path.join(_base, "contratos_xml"))

if _base not in sys.path:
    sys.path.insert(0, _base)

from app import main  # noqa: E402

if __name__ == "__main__":
    main()
