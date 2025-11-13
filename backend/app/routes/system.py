"""System level utilities."""
from __future__ import annotations

from flask import Blueprint, jsonify


bp = Blueprint("system", __name__)


@bp.get("/api/test")
def test():
    return jsonify({"msg": "API funcionando correctamente", "status": "OK"})
