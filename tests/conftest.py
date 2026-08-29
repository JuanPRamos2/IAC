"""Pruebas de la aplicación IAC."""

import pytest

from web.factory import create_app


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, OPENROUTER_API_KEY="")
    return application


@pytest.fixture
def client(app):
    return app.test_client()
