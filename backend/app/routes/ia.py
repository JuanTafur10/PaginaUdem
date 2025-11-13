"""IA configuration endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Usuario
from ..services.ia import obtener_configuracion_ia


bp = Blueprint("ia", __name__, url_prefix="/api/ia")


@bp.get("/config")
@jwt_required()
def obtener_config_ia():
    usuario_id = int(get_jwt_identity())
    usuario = Usuario.query.get_or_404(usuario_id)
    if not usuario.is_coordinator():
        return jsonify({"msg": "Solo el coordinador puede consultar la configuración"}), 403

    config = obtener_configuracion_ia()
    return jsonify(config.to_dict()), 200


@bp.put("/config")
@jwt_required()
def actualizar_config_ia():
    usuario_id = int(get_jwt_identity())
    usuario = Usuario.query.get_or_404(usuario_id)
    if not usuario.is_coordinator():
        return jsonify({"msg": "Solo el coordinador puede actualizar la configuración"}), 403

    data = request.get_json() or {}
    config = obtener_configuracion_ia()

    for campo in ("min_semestre", "min_promedio", "peso_semestre", "peso_promedio", "peso_horas"):
        if campo in data and data[campo] is not None:
            try:
                valor = float(data[campo])
            except (ValueError, TypeError):
                return jsonify({"msg": f"Valor inválido para {campo}"}), 400
            if campo == "min_semestre":
                setattr(config, campo, int(valor))
            else:
                setattr(config, campo, valor)

    db.session.commit()
    return jsonify(config.to_dict()), 200
