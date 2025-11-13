"""Application configuration objects."""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR.parent / "instance" / "dev.db"


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-secret")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{DEFAULT_DB_PATH}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "mixtral-8x7b-32768")
    GROQ_TIMEOUT = float(os.environ.get("GROQ_TIMEOUT", "15"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)


class DevConfig(Config):
    DEBUG = True


config_by_name = {
    "default": Config,
    "development": DevConfig,
    "testing": TestConfig,
}
