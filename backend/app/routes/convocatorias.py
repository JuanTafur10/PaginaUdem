"""Convocatoria endpoints."""
from __future__ import annotations

import base64
from binascii import Error as BinasciiError
from pathlib import Path
from typing import Dict, List

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import (
    Convocatoria,
    EstadoConvocatoria,
    EstadoPostulacion,
    InscripcionMonitoria,
    EvaluacionAspirante,
    Postulacion,
    ReporteDescartes,
    TipoNotificacion,
    Usuario,
)
from ..services.convocatorias import (
    auto_archivar_convocatorias,
    debug_log,
    parse_datetime_or_error,
    recalcular_estado,
    validar_requisitos_estudiante,
)
from ..services.ia import obtener_servicio_ia, registrar_descartes
from ..services.notifications import crear_notificacion
from ..utils.time import utc_now_naive


bp = Blueprint("convocatorias", __name__, url_prefix="/api/convocatorias")


@bp.post("")
@jwt_required()
def crear_convocatoria():
    user_id = int(get_jwt_identity())
    user = Usuario.query.get_or_404(user_id)

    if not (user.is_coordinator() or user.is_professor()):
        return jsonify({"msg": "Solo coordinadores y profesores pueden crear convocatorias"}), 403

    data = request.get_json() or {}
    debug_log("Payload crear_convocatoria recibido", data)

    for campo in ("curso", "semestre", "requisitos"):
        if not data.get(campo):
            return jsonify({"msg": f"Campo obligatorio faltante: {campo}"}), 400

    convocatoria = Convocatoria(
        curso=data["curso"],
        semestre=data["semestre"],
        requisitos=data["requisitos"],
        creado_por_id=user.id,
    )

    now = utc_now_naive()
    if data.get("fecha_apertura"):
        try:
            fa = parse_datetime_or_error(data["fecha_apertura"], "fecha_apertura")
            debug_log(
                "Fecha apertura parseada",
                {"original": data["fecha_apertura"], "normalizada": fa.isoformat()},
            )
            if fa < now:
                return jsonify({"msg": "fecha_apertura no puede estar en el pasado"}), 400
            convocatoria.fecha_apertura = fa
        except (ValueError, TypeError) as exc:
            debug_log("Error parseando fecha_apertura", str(exc))
            return jsonify({"msg": str(exc)}), 400

    if data.get("fecha_cierre"):
        try:
            fc = parse_datetime_or_error(data["fecha_cierre"], "fecha_cierre")
            debug_log(
                "Fecha cierre parseada",
                {"original": data["fecha_cierre"], "normalizada": fc.isoformat()},
            )
            if fc < now:
                return jsonify({"msg": "fecha_cierre no puede estar en el pasado"}), 400
            convocatoria.fecha_cierre = fc
        except (ValueError, TypeError) as exc:
            debug_log("Error parseando fecha_cierre", str(exc))
            return jsonify({"msg": str(exc)}), 400

    if convocatoria.fecha_apertura and convocatoria.fecha_cierre:
        if convocatoria.fecha_cierre <= convocatoria.fecha_apertura:
            debug_log(
                "Validación rango fechas falló",
                {
                    "fecha_apertura": convocatoria.fecha_apertura.isoformat(),
                    "fecha_cierre": convocatoria.fecha_cierre.isoformat(),
                },
            )
            return jsonify({"msg": "fecha_cierre debe ser posterior a fecha_apertura"}), 400

    recalcular_estado(convocatoria, now)

    db.session.add(convocatoria)
    db.session.commit()

    return jsonify(convocatoria.to_dict()), 201


@bp.patch("/<int:convocatoria_id>/fechas")
@jwt_required()
def asignar_fechas(convocatoria_id: int):
    user_id = int(get_jwt_identity())
    user = Usuario.query.get_or_404(user_id)

    if not (user.is_coordinator() or user.is_professor()):
        return jsonify({"msg": "Solo coordinadores y profesores pueden asignar fechas"}), 403

    convocatoria = Convocatoria.query.get_or_404(convocatoria_id)
    if convocatoria.estado == EstadoConvocatoria.CLOSED:
        return jsonify({"msg": "No se pueden modificar convocatorias cerradas"}), 400

    data = request.get_json() or {}
    now = utc_now_naive()

    if data.get("fecha_apertura"):
        try:
            fa_dt = parse_datetime_or_error(data["fecha_apertura"], "fecha_apertura")
            debug_log(
                "PATCH fecha_apertura parseada",
                {"original": data["fecha_apertura"], "normalizada": fa_dt.isoformat()},
            )
            if fa_dt < now:
                return jsonify({"msg": "fecha_apertura no puede estar en el pasado"}), 400
            convocatoria.fecha_apertura = fa_dt
        except (ValueError, TypeError) as exc:
            debug_log("PATCH error parseando fecha_apertura", str(exc))
            return jsonify({"msg": str(exc)}), 400

    if data.get("fecha_cierre"):
        try:
            fc_dt = parse_datetime_or_error(data["fecha_cierre"], "fecha_cierre")
            debug_log(
                "PATCH fecha_cierre parseada",
                {"original": data["fecha_cierre"], "normalizada": fc_dt.isoformat()},
            )
            if fc_dt < now:
                return jsonify({"msg": "fecha_cierre no puede estar en el pasado"}), 400
            convocatoria.fecha_cierre = fc_dt
        except (ValueError, TypeError) as exc:
            debug_log("PATCH error parseando fecha_cierre", str(exc))
            return jsonify({"msg": str(exc)}), 400

    if convocatoria.fecha_apertura and convocatoria.fecha_cierre:
        if convocatoria.fecha_cierre <= convocatoria.fecha_apertura:
            return jsonify({"msg": "fecha_cierre debe ser posterior a fecha_apertura"}), 400

    recalcular_estado(convocatoria, now)

    db.session.commit()
    return jsonify(convocatoria.to_dict()), 200


@bp.get("/activas")
def listar_activas():
    lang = request.args.get("lang")
    auto_archivar_convocatorias()
    now = utc_now_naive()
    convocatorias = Convocatoria.query.filter_by(archivada=False).all()
    for convocatoria in convocatorias:
        recalcular_estado(convocatoria, now)
    db.session.commit()
    activas = [c for c in convocatorias if c.estado == EstadoConvocatoria.ACTIVE]
    data = [c.to_dict() for c in activas]

    if lang == "en":
        estado_map = {
            "borrador": "draft",
            "programada": "scheduled",
            "activa": "active",
            "cerrada": "closed",
            "archivada": "archived",
        }
        for item in data:
            estado = item.get("estado")
            if estado:
                item["estado"] = estado_map.get(estado, estado)

    return jsonify(data), 200


@bp.get("")
def listar_convocatorias():
    lang = request.args.get("lang")
    estado_filtro = request.args.get("estado")
    archivadas_flag = request.args.get("archivadas")

    auto_archivar_convocatorias()

    query = Convocatoria.query
    if archivadas_flag in ("solo", "only", "true", "1", "yes"):
        query = query.filter_by(archivada=True)
    elif archivadas_flag in ("todas", "all"):
        query = query
    else:
        query = query.filter_by(archivada=False)

    now = utc_now_naive()
    convocatorias = query.all()
    for convocatoria in convocatorias:
        recalcular_estado(convocatoria, now)
    db.session.commit()

    if estado_filtro:
        estado_filtro = estado_filtro.lower()
        estado_map = {
            "draft": EstadoConvocatoria.DRAFT,
            "borrador": EstadoConvocatoria.DRAFT,
            "scheduled": EstadoConvocatoria.SCHEDULED,
            "programada": EstadoConvocatoria.SCHEDULED,
            "active": EstadoConvocatoria.ACTIVE,
            "activa": EstadoConvocatoria.ACTIVE,
            "closed": EstadoConvocatoria.CLOSED,
            "cerrada": EstadoConvocatoria.CLOSED,
            "archived": EstadoConvocatoria.ARCHIVED,
            "archivada": EstadoConvocatoria.ARCHIVED,
        }
        estado_obj = estado_map.get(estado_filtro)
        if estado_obj:
            convocatorias = [c for c in convocatorias if c.estado == estado_obj]

    data = [c.to_dict() for c in convocatorias]
    if lang == "en":
        estado_map = {
            "borrador": "draft",
            "programada": "scheduled",
            "activa": "active",
            "cerrada": "closed",
            "archivada": "archived",
        }
        for item in data:
            estado = item.get("estado")
            if estado:
                item["estado"] = estado_map.get(estado, estado)
    return jsonify(data), 200


@bp.patch("/<int:convocatoria_id>")
@jwt_required()
def editar_convocatoria(convocatoria_id: int):
    user_id = int(get_jwt_identity())
    user = Usuario.query.get_or_404(user_id)
    if not (user.is_coordinator() or user.is_professor()):
        return jsonify({"msg": "Solo coordinadores y profesores pueden editar"}), 403

    convocatoria = Convocatoria.query.get_or_404(convocatoria_id)
    if convocatoria.estado == EstadoConvocatoria.CLOSED:
        return jsonify({"msg": "No se puede editar una convocatoria cerrada"}), 400

    data = request.get_json() or {}
    cambios = 0
    if "curso" in data and data["curso"]:
        convocatoria.curso = data["curso"].strip()
        cambios += 1
    if "semestre" in data and data["semestre"]:
        convocatoria.semestre = data["semestre"].strip()
        cambios += 1
    if "requisitos" in data and data["requisitos"]:
        convocatoria.requisitos = data["requisitos"].strip()
        cambios += 1

    if cambios == 0:
        return jsonify({"msg": "No se proporcionaron cambios válidos"}), 400

    now = utc_now_naive()
    recalcular_estado(convocatoria, now)
    db.session.commit()
    return jsonify(convocatoria.to_dict()), 200


@bp.post("/<int:convocatoria_id>/postulaciones")
@jwt_required()
def crear_postulacion(convocatoria_id: int):
    estudiante_id = int(get_jwt_identity())
    estudiante = Usuario.query.get_or_404(estudiante_id)

    if not estudiante.is_student():
        return jsonify({"msg": "Solo los estudiantes pueden postularse"}), 403

    convocatoria = Convocatoria.query.get_or_404(convocatoria_id)

    auto_archivar_convocatorias()
    if convocatoria.archivada or convocatoria.estado in (EstadoConvocatoria.CLOSED, EstadoConvocatoria.ARCHIVED):
        return jsonify({"msg": "La convocatoria no admite nuevas postulaciones"}), 400

    existente = (
        Postulacion.query.filter_by(
            estudiante_id=estudiante.id,
            convocatoria_id=convocatoria.id,
        )
        .filter(Postulacion.estado != EstadoPostulacion.ARCHIVED)
        .first()
    )
    if existente:
        return (
            jsonify({"msg": "Ya existe una postulación para esta convocatoria", "postulacion": existente.to_dict()}),
            409,
        )

    payload = request.get_json() or {}
    formulario = payload.get("formulario") or {}
    soportes = payload.get("soportes") or {}

    if soportes:
        nombre_archivo = (soportes.get("cvNombre") or "").strip()
        contenido_b64 = soportes.get("cvBase64")
        if not nombre_archivo or not contenido_b64:
            return jsonify({"msg": "El archivo adjunto es inválido"}), 400

        extension = Path(nombre_archivo).suffix.lower()
        if extension not in {".pdf", ".doc", ".docx"}:
            return jsonify({"msg": "Solo se permiten archivos PDF o DOCX"}), 400

        try:
            contenido_bytes = base64.b64decode(contenido_b64, validate=True)
        except (BinasciiError, ValueError):
            return jsonify({"msg": "El archivo adjunto no es válido"}), 400

        max_bytes = 5 * 1024 * 1024
        if len(contenido_bytes) > max_bytes:
            return jsonify({"msg": "El archivo supera el tamaño máximo permitido de 5 MB"}), 400

        soportes = {
            "cvNombre": nombre_archivo,
            "cvBase64": contenido_b64,
            "cvSize": len(contenido_bytes),
        }

    postulacion = Postulacion(estudiante_id=estudiante.id, convocatoria_id=convocatoria.id)
    db.session.add(postulacion)
    postulacion.estudiante = estudiante
    postulacion.convocatoria = convocatoria
    postulacion.completar_formulario(formulario)
    postulacion.adjuntar_soportes(soportes)
    postulacion.esperar_validacion()
    db.session.flush()

    es_valido, razones = validar_requisitos_estudiante(convocatoria, estudiante)

    servicio_ia = obtener_servicio_ia()
    descartes_registrados: List[Dict] = []
    evaluacion_model = None

    if not es_valido:
        postulacion.marcar_ineligible("; ".join(razones) if razones else "No cumple requisitos")
        descartes_registrados.append(
            {
                "postulacion_id": None,
                "estudiante_id": estudiante.id,
                "convocatoria_id": convocatoria.id,
                "razones": razones or ["No cumple requisitos de la convocatoria"],
            }
        )
    else:
        elegibles, descartados = servicio_ia.filtrar_postulaciones([postulacion])
        descartes_registrados.extend(descartados)

        if elegibles:
            ranking = servicio_ia.clasificar_postulaciones(elegibles)
            detalles = ranking[0]["detalles"] if ranking else {}
            evaluacion_model = EvaluacionAspirante(postulacion_id=postulacion.id)
            evaluacion_model.postulacion = postulacion
            evaluacion_model.registrar_resultado(
                postulacion.puntaje or 0.0,
                postulacion.resultado or "pre-seleccionado",
                detalles,
            )
            db.session.add(evaluacion_model)
        else:
            motivos = descartados[0]["razones"] if descartados else ["No supera filtros automáticos"]
            postulacion.marcar_ineligible("; ".join(motivos))

    db.session.flush()

    for descarte in descartes_registrados:
        if descarte.get("postulacion_id") is None:
            descarte["postulacion_id"] = postulacion.id

    reporte = registrar_descartes(convocatoria.id, descartes_registrados)

    metadata_base = {
        "convocatoria_id": convocatoria.id,
        "postulacion_id": postulacion.id,
        "estado": postulacion.estado.value if postulacion.estado else None,
    }
    if postulacion.estado == EstadoPostulacion.ELIGIBLE:
        mensaje = (
            f"Tu postulación a {convocatoria.curso} fue pre-seleccionada con puntaje "
            f"{(postulacion.puntaje or 0):.1f}."
        )
        if evaluacion_model:
            metadata_base["detalles"] = evaluacion_model.detalles or {}
        crear_notificacion(
            usuario_id=estudiante.id,
            titulo=f"Postulación aprobada - {convocatoria.curso}",
            mensaje=mensaje,
            tipo=TipoNotificacion.SUCCESS,
            metadata=metadata_base,
        )
    elif postulacion.estado == EstadoPostulacion.INELIGIBLE:
        motivos_texto = postulacion.razones_rechazo or "No supera los requisitos de la convocatoria."
        crear_notificacion(
            usuario_id=estudiante.id,
            titulo=f"Postulación no elegible - {convocatoria.curso}",
            mensaje=(
                f"Tu postulación a {convocatoria.curso} no avanzó en el proceso. Motivos: {motivos_texto}."
            ),
            tipo=TipoNotificacion.WARNING,
            metadata={**metadata_base, "motivos": motivos_texto},
        )

    db.session.commit()

    respuesta = {
        "postulacion": postulacion.to_dict(),
        "convocatoria": convocatoria.to_dict(),
    }
    if evaluacion_model:
        respuesta["evaluacion"] = evaluacion_model.to_dict()
    if descartes_registrados:
        respuesta["descartados"] = descartes_registrados
    if reporte:
        respuesta["reporte"] = reporte.to_dict()

    status_code = 201 if postulacion.estado == EstadoPostulacion.ELIGIBLE else 202
    return jsonify(respuesta), status_code



@bp.post("/<int:convocatoria_id>/inscripciones")
@jwt_required()
def inscribirse_monitoria(convocatoria_id: int):
    estudiante_id = int(get_jwt_identity())
    estudiante = Usuario.query.get_or_404(estudiante_id)

    if not estudiante.is_student():
        return jsonify({"msg": "Solo los estudiantes pueden inscribirse"}), 403

    convocatoria = Convocatoria.query.get_or_404(convocatoria_id)

    auto_archivar_convocatorias()
    if convocatoria.archivada or convocatoria.estado not in {EstadoConvocatoria.ACTIVE, EstadoConvocatoria.SCHEDULED}:
        return jsonify({"msg": "La convocatoria no admite nuevas inscripciones"}), 400

    existente = InscripcionMonitoria.query.filter_by(
        estudiante_id=estudiante.id,
        convocatoria_id=convocatoria.id,
    ).first()
    if existente:
        return (
            jsonify({"msg": "Ya tienes una inscripción en esta convocatoria", "inscripcion": existente.to_dict()}),
            409,
        )

    data = request.get_json() or {}
    comentario = (data.get("comentario") or "").strip() or None
    horario_preferido = (data.get("horario_preferido") or "").strip() or None

    inscripcion = InscripcionMonitoria(
        estudiante_id=estudiante.id,
        convocatoria_id=convocatoria.id,
        comentario=comentario,
        horario_preferido=horario_preferido,
    )
    db.session.add(inscripcion)
    db.session.flush()

    crear_notificacion(
        usuario_id=estudiante.id,
        titulo=f"Inscripción registrada en {convocatoria.curso}",
        mensaje="Te has inscrito exitosamente a la monitoría. Recibirás novedades por este medio.",
        tipo=TipoNotificacion.SUCCESS,
    )
    db.session.commit()

    return jsonify({"inscripcion": inscripcion.to_dict()}), 201

@bp.get("/<int:convocatoria_id>/postulaciones")
@jwt_required()
def listar_postulaciones(convocatoria_id: int):
    usuario_id = int(get_jwt_identity())
    usuario = Usuario.query.get_or_404(usuario_id)
    convocatoria = Convocatoria.query.get_or_404(convocatoria_id)

    vista = request.args.get("view")
    estado_param = request.args.get("estado")

    auto_archivar_convocatorias()

    if usuario.is_student():
        postulaciones = Postulacion.query.filter_by(convocatoria_id=convocatoria_id, estudiante_id=usuario.id).all()
    else:
        postulaciones = Postulacion.query.filter_by(convocatoria_id=convocatoria_id).all()

    if estado_param == "descartadas":
        postulaciones = [p for p in postulaciones if p.estado == EstadoPostulacion.INELIGIBLE]
    elif estado_param == "elegibles":
        postulaciones = [p for p in postulaciones if p.estado == EstadoPostulacion.ELIGIBLE]

    datos_postulaciones = [p.to_dict() for p in postulaciones]

    if vista == "ranking":
        estados_ranking = {EstadoPostulacion.ELIGIBLE, EstadoPostulacion.SELECTED}
        ranking = [
            {
                "postulacion": p.to_dict(),
                "estudiante": p.estudiante.to_dict(),
                "puntaje": p.puntaje or 0.0,
                "resultado": p.resultado,
            }
            for p in postulaciones
            if p.estado in estados_ranking
        ]
        ranking.sort(key=lambda item: item["puntaje"], reverse=True)
        return jsonify({"convocatoria": convocatoria.to_dict(), "ranking": ranking}), 200

    reporte_descartes = None
    if not usuario.is_student():
        periodo = request.args.get("periodo") or utc_now_naive().strftime("%Y-%m")
        reporte_descartes = ReporteDescartes.query.filter_by(
            convocatoria_id=convocatoria.id,
            periodo=periodo,
        ).first()

    respuesta = {
        "convocatoria": convocatoria.to_dict(),
        "postulaciones": datos_postulaciones,
    }
    if reporte_descartes:
        respuesta["reporte_descartes"] = reporte_descartes.to_dict()

    return jsonify(respuesta), 200


@bp.patch("/<int:convocatoria_id>/postulaciones/<int:postulacion_id>/decision")
@jwt_required()
def decidir_postulacion(convocatoria_id: int, postulacion_id: int):
    usuario_id = int(get_jwt_identity())
    usuario = Usuario.query.get_or_404(usuario_id)
    if not (usuario.is_coordinator() or usuario.is_professor()):
        return jsonify({"msg": "Solo coordinadores y profesores pueden registrar decisiones"}), 403

    convocatoria = Convocatoria.query.get_or_404(convocatoria_id)
    postulacion = (
        Postulacion.query.filter_by(id=postulacion_id, convocatoria_id=convocatoria.id).first_or_404()
    )

    data = request.get_json() or {}
    decision = str(data.get("decision", "")).lower()
    comentario = (data.get("comentario") or "").strip()

    if decision not in {"selected", "not_selected"}:
        return jsonify({"msg": "Decisión inválida"}), 400

    if decision == "selected":
        postulacion.marcar_seleccionado(comentario)
        titulo = f"Has sido seleccionado(a) como monitor de {convocatoria.curso}"
        mensaje = (
            f"Felicitaciones, has sido asignado(a) como monitor de {convocatoria.curso}."
            + (f" Observaciones: {comentario}" if comentario else "")
        )
        tipo = TipoNotificacion.SUCCESS
    else:
        postulacion.marcar_no_seleccionado(comentario)
        titulo = f"Resultado de la convocatoria {convocatoria.curso}"
        mensaje = (
            "Gracias por participar. En esta ocasión no fuiste seleccionado(a)."
            + (f" Motivo: {comentario}" if comentario else "")
        )
        tipo = TipoNotificacion.WARNING

    metadata = {
        "convocatoria_id": convocatoria.id,
        "postulacion_id": postulacion.id,
        "decision": decision,
    }
    if comentario:
        metadata["comentario"] = comentario

    try:
        crear_notificacion(
            usuario_id=postulacion.estudiante_id,
            titulo=titulo,
            mensaje=mensaje,
            tipo=tipo,
            metadata=metadata,
        )
    except Exception as exc:  # pragma: no cover - logging path
        current_app.logger.exception("Error enviando notificación de decisión: %s", exc)
        alerta_msg = (
            f"No fue posible notificar a {postulacion.estudiante.nombre} sobre la decisión."  # type: ignore[attr-defined]
        )
        try:
            crear_notificacion(
                usuario_id=usuario.id,
                titulo="Fallo en notificación",
                mensaje=alerta_msg,
                tipo=TipoNotificacion.ERROR,
                metadata={**metadata, "error": str(exc)},
            )
        except Exception:
            current_app.logger.exception("Error registrando alerta de fallo de notificación")

    db.session.commit()

    return jsonify({"postulacion": postulacion.to_dict()}), 200
