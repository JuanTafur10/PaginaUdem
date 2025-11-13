"""Application factory for the monitorias backend."""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from .config import Config, config_by_name
from .extensions import cors, db, jwt
from .routes import register_blueprints
from .services.bootstrap import ensure_schema_updates, seed_default_data
from .services.ia import obtener_configuracion_ia


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(
        __name__,
        instance_relative_config=True,
        static_folder=None,
        template_folder=None,
    )

    config_key = config_name or os.getenv("FLASK_ENV", "default")
    config_obj = config_by_name.get(config_key, Config)
    app.config.from_object(config_obj)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})
    db.init_app(app)
    jwt.init_app(app)

    register_blueprints(app)

    with app.app_context():
        from . import models  # noqa: F401 - ensure models are registered

        db.create_all()
        ensure_schema_updates()
        seed_default_data()
        obtener_configuracion_ia()

    return app


__all__ = ["create_app"]
