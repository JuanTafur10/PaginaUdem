"""Notification domain services."""
from __future__ import annotations

from typing import List

from sqlalchemy import desc

from ..extensions import db
from ..models import Notificacion, TipoNotificacion
from ..utils.time import utc_now_naive


def _coerce_tipo(tipo: str | TipoNotificacion | None) -> TipoNotificacion:
    if isinstance(tipo, TipoNotificacion):
        return tipo
    if isinstance(tipo, str):
        try:
            return TipoNotificacion(tipo)
        except ValueError:
            try:
                return TipoNotificacion(tipo.lower())
            except Exception:
                return TipoNotificacion.INFO
    return TipoNotificacion.INFO


def crear_notificacion(
    *,
    usuario_id: int,
    titulo: str,
    mensaje: str,
    tipo: str | TipoNotificacion | None = None,
    metadata: dict | None = None,
    commit: bool = False,
) -> Notificacion:
    """Create and optionally persist a notification."""
    notificacion = Notificacion(
        usuario_id=usuario_id,
        titulo=titulo,
        mensaje=mensaje,
        tipo=_coerce_tipo(tipo),
        payload=metadata or {},
    )
    db.session.add(notificacion)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return notificacion


def listar_notificaciones(
    usuario_id: int,
    *,
    solo_no_leidas: bool = False,
    limite: int | None = None,
) -> List[Notificacion]:
    query = Notificacion.query.filter_by(usuario_id=usuario_id)
    if solo_no_leidas:
        query = query.filter_by(leida=False)
    query = query.order_by(desc(Notificacion.created_at))
    if limite:
        query = query.limit(limite)
    return list(query.all())


def marcar_notificacion_leida(notificacion: Notificacion, when=None) -> Notificacion:
    notificacion.marcar_leida(when or utc_now_naive())
    db.session.flush()
    return notificacion


def marcar_notificacion_leida_por_id(notificacion_id: int, usuario_id: int) -> Notificacion | None:
    notificacion = Notificacion.query.filter_by(id=notificacion_id, usuario_id=usuario_id).first()
    if not notificacion:
        return None
    marcar_notificacion_leida(notificacion)
    return notificacion


def marcar_todas_leidas(usuario_id: int) -> int:
    notificaciones = Notificacion.query.filter_by(usuario_id=usuario_id, leida=False).all()
    contador = 0
    for notificacion in notificaciones:
        notificacion.marcar_leida()
        contador += 1
    if contador:
        db.session.flush()
    return contador


__all__ = [
    "crear_notificacion",
    "listar_notificaciones",
    "marcar_notificacion_leida",
    "marcar_notificacion_leida_por_id",
    "marcar_todas_leidas",
]
