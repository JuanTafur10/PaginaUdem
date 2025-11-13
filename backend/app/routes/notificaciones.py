"""Notification endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import TipoNotificacion, Usuario
from ..services.notifications import (
    crear_notificacion,
    listar_notificaciones,
    marcar_notificacion_leida_por_id,
    marcar_todas_leidas,
)


bp = Blueprint("notificaciones", __name__, url_prefix="/api/notificaciones")


def _get_current_user() -> Usuario:
    user_id = int(get_jwt_identity())
    return Usuario.query.get_or_404(user_id)


@bp.get("")
@jwt_required()
def obtener_notificaciones():
    usuario = _get_current_user()
    estado = (request.args.get("estado") or "all").lower()
    limite_param = request.args.get("limit")
    try:
        limite = int(limite_param) if limite_param else None
    except ValueError:
        return jsonify({"msg": "Parámetro 'limit' inválido"}), 400

    solo_no_leidas = estado in {"unread", "no_leidas", "pendientes"}
    notificaciones = listar_notificaciones(usuario.id, solo_no_leidas=solo_no_leidas, limite=limite)
    return jsonify([notif.to_dict() for notif in notificaciones])


@bp.post("")
@jwt_required()
def crear_notificacion_manual():
    usuario = _get_current_user()
    data = request.get_json() or {}
    usuario_destino = int(data.get("usuario_id", usuario.id))
    titulo = (data.get("titulo") or "").strip()
    mensaje = (data.get("mensaje") or "").strip()
    tipo = data.get("tipo")
    metadata = data.get("metadata") or {}

    if not titulo or not mensaje:
        return jsonify({"msg": "Los campos 'titulo' y 'mensaje' son obligatorios"}), 400

    if usuario_destino != usuario.id and not (usuario.is_coordinator() or usuario.is_professor()):
        return jsonify({"msg": "No tiene permisos para enviar notificaciones a otros usuarios"}), 403

    try:
        tipo_enum = TipoNotificacion(tipo) if tipo else TipoNotificacion.INFO
    except ValueError:
        return jsonify({"msg": "Tipo de notificación inválido"}), 400

    notificacion = crear_notificacion(
        usuario_id=usuario_destino,
        titulo=titulo,
        mensaje=mensaje,
        tipo=tipo_enum,
        metadata=metadata,
    )
    db.session.commit()
    return jsonify(notificacion.to_dict()), 201


@bp.post("/<int:notificacion_id>/leer")
@jwt_required()
def marcar_notificacion_leida(notificacion_id: int):
    usuario = _get_current_user()
    notificacion = marcar_notificacion_leida_por_id(notificacion_id, usuario.id)
    if not notificacion:
        return jsonify({"msg": "Notificación no encontrada"}), 404
    db.session.commit()
    return jsonify(notificacion.to_dict())


@bp.post("/marcar-todas")
@jwt_required()
def marcar_todas_notificaciones():
    usuario = _get_current_user()
    total = marcar_todas_leidas(usuario.id)
    db.session.commit()
    return jsonify({"total_actualizadas": total})


__all__ = [
    "bp",
]
