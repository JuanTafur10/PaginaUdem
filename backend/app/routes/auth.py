"""Authentication endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Usuario


bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/login")
def login() -> tuple[object, int] | tuple[object, int, dict]:
    data = request.get_json() or {}
    correo = data.get("correo")
    password = data.get("password")

    if not correo or not password:
        return jsonify({"msg": "correo y password requeridos"}), 400

    user = Usuario.query.filter_by(correo=correo).first()
    if not user or not user.check_password(password):
        return jsonify({"msg": "credenciales inválidas"}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "rol": user.rol, "user": user.to_dict()})


@bp.get("/profile")
@jwt_required()
def get_profile() -> object:
    user_id = int(get_jwt_identity())
    user = Usuario.query.get_or_404(user_id)
    return jsonify(user.to_dict())


@bp.put("/profile")
@jwt_required()
def update_profile() -> tuple[object, int] | object:
    user_id = int(get_jwt_identity())
    user = Usuario.query.get_or_404(user_id)
    data = request.get_json() or {}

    if user.is_student() and "semestre" in data:
        semestre = data.get("semestre")
        if semestre and semestre in [str(number) for number in range(1, 11)]:
            user.semestre = semestre
        else:
            return jsonify({"msg": "Semestre inválido. Debe ser entre 1 y 10"}), 400

    if "nombre" in data and data["nombre"]:
        user.nombre = data["nombre"]

    db.session.commit()
    return jsonify(user.to_dict())
