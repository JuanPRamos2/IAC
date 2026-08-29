"""Fábrica de la aplicación Flask monolítica."""

from flask import Flask

from web.config import Config, ROOT_DIR


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(ROOT_DIR / "web" / "templates"),
        static_folder=str(ROOT_DIR / "web" / "static"),
    )
    app.config.from_object(Config)

    from web.blueprints.pages import pages_bp
    from web.blueprints.api import api_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
