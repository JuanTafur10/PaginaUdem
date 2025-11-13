"""Blueprint registration."""
from __future__ import annotations

from flask import Flask

from . import auth, convocatorias, ia, notificaciones, system


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(system.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(convocatorias.bp)
    app.register_blueprint(ia.bp)
    app.register_blueprint(notificaciones.bp)


__all__ = ["register_blueprints"]
