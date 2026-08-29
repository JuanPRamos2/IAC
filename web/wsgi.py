"""Punto de entrada WSGI (gunicorn web.wsgi:app)."""

from web.factory import create_app

app = create_app()
