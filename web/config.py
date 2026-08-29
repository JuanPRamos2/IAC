"""Configuración de la aplicación a partir de variables de entorno."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Ajustes compartidos por la app web y los servicios internos."""

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")
    DEBUG = _bool_env("FLASK_DEBUG", default=os.getenv("FLASK_ENV") == "development")
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = int(os.getenv("FLASK_PORT", "5000"))

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_API_URL = os.getenv(
        "OPENROUTER_API_URL",
        "https://openrouter.ai/api/v1/chat/completions",
    )
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat")
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "50"))
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))
    MIN_TEXT_LENGTH = int(os.getenv("MIN_TEXT_LENGTH", "3"))
    MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "1000"))
    API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "30"))
