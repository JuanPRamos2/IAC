"""CLI del clasificador y arranque de desarrollo."""

from __future__ import annotations

import argparse
import sys

from web.factory import create_app
from web.services.classifier import ClasificadorModelosNube


def _imprimir_resultado(resultado) -> None:
    if resultado.modelo == "Error":
        print("Error en la clasificación. Revisa la API key y la conexión.")
        return
    print(f"Modelo: {resultado.modelo}")
    print(f"Confianza: {resultado.confianza:.2f}")
    print("Puntajes:")
    for tipo, puntaje in resultado.puntajes.items():
        print(f"  {tipo}: {puntaje:.2f}")


def _clasificar_texto(texto: str) -> int:
    clasificador = ClasificadorModelosNube()
    try:
        resultado = clasificador.clasificar(texto)
    except ValueError as exc:
        print(f"Entrada inválida: {exc}")
        return 1
    _imprimir_resultado(resultado)
    return 0 if resultado.modelo != "Error" else 1


def _modo_interactivo() -> int:
    print("Clasificador de servicios en la nube (IaaS, PaaS, SaaS, FaaS)")
    print("Escribe 'salir' para terminar.\n")
    while True:
        try:
            texto = input("Texto: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
        if texto.lower() in {"salir", "exit", "quit"}:
            return 0
        if not texto:
            continue
        _clasificar_texto(texto)
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sitio IAC: servidor web o clasificador por consola.",
    )
    parser.add_argument("-t", "--texto", help="Clasificar un texto y salir")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Modo interactivo de consola (sin servidor web)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host del servidor de desarrollo",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Puerto del servidor de desarrollo",
    )
    args = parser.parse_args(argv)

    if args.texto:
        return _clasificar_texto(args.texto)
    if args.cli:
        return _modo_interactivo()

    app = create_app()
    host = args.host or app.config["HOST"]
    port = args.port or app.config["PORT"]
    app.run(host=host, port=port, debug=app.config["DEBUG"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
