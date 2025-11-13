"""Postulaciones management endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import (
    Convocatoria,
    EstadoPostulacion,
    Postulacion,
    TipoNotificacion,
    Usuario,
)
from ..services.notifications import crear_notificacion


bp = Blueprint("postulaciones", __name__, url_prefix="/api/postulaciones")


def _get_current_user() -> Usuario:
    user_id = int(get_jwt_identity())
    return Usuario.query.get_or_404(user_id)


def _require_gestor(usuario: Usuario):
    if not (usuario.is_coordinator() or usuario.is_professor()):
        return jsonify({"msg": "Solo coordinadores o profesores pueden gestionar postulaciones"}), 403
    return None


def _parse_estado(raw_estado: str | None) -> EstadoPostulacion | None:
    if not raw_estado:
        return None
    raw_normalized = str(raw_estado).strip().lower()
    mapping = {
        "pending": EstadoPostulacion.PENDING,
        "espera": EstadoPostulacion.PENDING,
        "eligible": EstadoPostulacion.ELIGIBLE,
        "preseleccionado": EstadoPostulacion.ELIGIBLE,
        "ineligible": EstadoPostulacion.INELIGIBLE,
        "rechazado": EstadoPostulacion.INELIGIBLE,
        "selected": EstadoPostulacion.SELECTED,
        "seleccionado": EstadoPostulacion.SELECTED,
        "not_selected": EstadoPostulacion.NOT_SELECTED,
        "no_seleccionado": EstadoPostulacion.NOT_SELECTED,
        "archived": EstadoPostulacion.ARCHIVED,
        "archivada": EstadoPostulacion.ARCHIVED,
    }
    try:
        return mapping.get(raw_normalized) or EstadoPostulacion(raw_normalized)
    except ValueError:
        return None


def _aplicar_estado(postulacion: Postulacion, estado: EstadoPostulacion, *, comentario: str | None, puntaje: float | None) -> None:
    if estado == EstadoPostulacion.SELECTED:
        postulacion.marcar_seleccionado(comentario)
        if puntaje is not None:
            postulacion.puntaje = puntaje
    elif estado == EstadoPostulacion.NOT_SELECTED:
        postulacion.marcar_no_seleccionado(comentario)
    elif estado == EstadoPostulacion.INELIGIBLE:
        postulacion.marcar_ineligible(comentario or "No cumple con los requisitos definidos")
    elif estado == EstadoPostulacion.ELIGIBLE:
        postulacion.marcar_elegible(puntaje or 0.0, comentario or "preseleccionado")
    elif estado == EstadoPostulacion.ARCHIVED:
        postulacion.estado = EstadoPostulacion.ARCHIVED
        postulacion.resultado = "archivada"
        postulacion.razones_rechazo = comentario or None
    else:
        postulacion.esperar_validacion()
        if comentario:
            postulacion.razones_rechazo = comentario


def _serialize_postulacion(postulacion: Postulacion) -> dict:
    data = postulacion.to_dict()
    if postulacion.estudiante:
        data["estudiante"] = postulacion.estudiante.to_dict()
    if postulacion.convocatoria:
        data["convocatoria"] = postulacion.convocatoria.to_dict()
    if postulacion.creador:
        data["creador"] = postulacion.creador.to_dict()
    return data


@bp.get("/preasignadas")
@jwt_required()
def listar_preasignadas():
    usuario = _get_current_user()
    query = Postulacion.query.filter_by(preasignada=True)

    convocatoria_param = request.args.get("convocatoria_id")
    if convocatoria_param:
        try:
            convocatoria_id = int(convocatoria_param)
            query = query.filter_by(convocatoria_id=convocatoria_id)
        except ValueError:
            return jsonify({"msg": "convocatoria_id inválido"}), 400

    if usuario.is_student():
        query = query.filter_by(estudiante_id=usuario.id)

    postulaciones = query.order_by(Postulacion.created_at.desc()).all()
    return jsonify([_serialize_postulacion(p) for p in postulaciones]), 200


@bp.post("/preasignadas")
@jwt_required()
def crear_preasignada():
    usuario = _get_current_user()
    error = _require_gestor(usuario)
    if error:
        return error

    datos = request.get_json() or {}

    convocatoria_id = datos.get("convocatoria_id")
    estudiante_id = datos.get("estudiante_id")
    comentario = (datos.get("comentario") or "").strip() or None
    puntaje = datos.get("puntaje")
    estado = _parse_estado(datos.get("estado")) or EstadoPostulacion.SELECTED
    formulario = datos.get("formulario") or {}
    soportes = datos.get("soportes") or {}

    if convocatoria_id is None:
        return jsonify({"msg": "convocatoria_id es obligatorio"}), 400
    if estudiante_id is None:
        return jsonify({"msg": "estudiante_id es obligatorio"}), 400

    convocatoria = Convocatoria.query.get_or_404(convocatoria_id)
    estudiante = Usuario.query.get_or_404(estudiante_id)

    postulacion = Postulacion(
        estudiante_id=estudiante.id,
        convocatoria_id=convocatoria.id,
    )
    postulacion.marcar_preasignada(usuario.id)
    postulacion.completar_formulario(formulario)
    postulacion.adjuntar_soportes(soportes)

    if puntaje is not None:
        try:
            postulacion.puntaje = float(puntaje)
        except (TypeError, ValueError):
            return jsonify({"msg": "puntaje debe ser numérico"}), 400

    _aplicar_estado(postulacion, estado, comentario=comentario, puntaje=postulacion.puntaje)

    db.session.add(postulacion)
    db.session.flush()

    metadata = {
        "preasignada": True,
        "convocatoria_id": convocatoria.id,
        "postulacion_id": postulacion.id,
        "estado": postulacion.estado.value if postulacion.estado else None,
    }
    if comentario:
        metadata["comentario"] = comentario

    tipo_notif = TipoNotificacion.SUCCESS if estado in {EstadoPostulacion.SELECTED, EstadoPostulacion.ELIGIBLE} else TipoNotificacion.INFO
    mensaje = (
        f"Has sido preasignado como monitor para {convocatoria.curso}."
        if estado == EstadoPostulacion.SELECTED
        else f"Se ha registrado una preasignación en {convocatoria.curso}."
    )
    crear_notificacion(
        usuario_id=estudiante.id,
        titulo=f"Preasignación registrada - {convocatoria.curso}",
        mensaje=mensaje if not comentario else f"{mensaje} Observaciones: {comentario}",
        tipo=tipo_notif,
        metadata=metadata,
    )

    db.session.commit()

    return jsonify(_serialize_postulacion(postulacion)), 201


@bp.patch("/preasignadas/<int:postulacion_id>")
@jwt_required()
def actualizar_preasignada(postulacion_id: int):
    usuario = _get_current_user()
    error = _require_gestor(usuario)
    if error:
        return error

    postulacion = Postulacion.query.filter_by(id=postulacion_id, preasignada=True).first_or_404()

    datos = request.get_json() or {}
    comentario = (datos.get("comentario") or "").strip() or None
    puntaje = datos.get("puntaje")
    estado_raw = datos.get("estado")
    convocatoria_id = datos.get("convocatoria_id")

    if convocatoria_id is not None:
        convocatoria = Convocatoria.query.get_or_404(convocatoria_id)
        postulacion.convocatoria_id = convocatoria.id
    else:
        convocatoria = postulacion.convocatoria

    if puntaje is not None:
        try:
            postulacion.puntaje = float(puntaje)
        except (TypeError, ValueError):
            return jsonify({"msg": "puntaje debe ser numérico"}), 400

    estado_actual = postulacion.estado
    if estado_raw:
        estado_nuevo = _parse_estado(estado_raw)
        if not estado_nuevo:
            return jsonify({"msg": "Estado inválido"}), 400
        _aplicar_estado(postulacion, estado_nuevo, comentario=comentario, puntaje=postulacion.puntaje)
    elif comentario is not None:
        postulacion.razones_rechazo = comentario

    postulacion.completar_formulario(datos.get("formulario") or postulacion.datos_formulario)

    db.session.flush()

    if estado_raw and estado_actual != postulacion.estado and postulacion.estudiante:
        metadata = {
            "preasignada": True,
            "convocatoria_id": postulacion.convocatoria_id,
            "postulacion_id": postulacion.id,
            "estado": postulacion.estado.value if postulacion.estado else None,
        }
        if comentario:
            metadata["comentario"] = comentario
        tipo_notif = TipoNotificacion.SUCCESS if postulacion.estado in {EstadoPostulacion.SELECTED, EstadoPostulacion.ELIGIBLE} else TipoNotificacion.INFO
        mensaje = (
            f"Tu estado en la preasignación de {convocatoria.curso if convocatoria else 'monitoría'} ahora es {postulacion.estado.value}."
        )
        crear_notificacion(
            usuario_id=postulacion.estudiante_id,
            titulo="Actualización de preasignación",
            mensaje=mensaje if not comentario else f"{mensaje} Observaciones: {comentario}",
            tipo=tipo_notif,
            metadata=metadata,
        )
    db.session.commit()

    return jsonify(_serialize_postulacion(postulacion)), 200


@bp.delete("/preasignadas/<int:postulacion_id>")
@jwt_required()
def eliminar_preasignada(postulacion_id: int):
    usuario = _get_current_user()
    error = _require_gestor(usuario)
    if error:
        return error

    postulacion = Postulacion.query.filter_by(id=postulacion_id, preasignada=True).first_or_404()
    db.session.delete(postulacion)
    db.session.commit()

    return jsonify({"msg": "Postulación preasignada eliminada"}), 200


@bp.get("/preasignadas/opciones")
@jwt_required()
def opciones_preasignadas():
    usuario = _get_current_user()
    error = _require_gestor(usuario)
    if error:
        return error

    estudiantes = (
        Usuario.query.filter_by(rol="STUDENT")
        .order_by(Usuario.nombre.asc())
        .all()
    )
    convocatorias = Convocatoria.query.order_by(Convocatoria.created_at.desc()).all()

    return (
        jsonify(
            {
                "estudiantes": [est.to_dict() for est in estudiantes],
                "convocatorias": [conv.to_dict() for conv in convocatorias],
            }
        ),
        200,
    )


__all__ = ["bp"]
