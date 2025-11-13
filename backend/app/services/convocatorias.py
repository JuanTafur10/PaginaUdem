"""Convocatoria domain services."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from dateutil import parser as date_parser

from ..extensions import db
from ..models import Convocatoria, EstadoConvocatoria, Usuario
from ..utils.time import utc_now_naive


def recalcular_estado(convocatoria: Convocatoria, now: datetime) -> EstadoConvocatoria:
    if convocatoria.archivada:
        convocatoria.estado = EstadoConvocatoria.ARCHIVED
        return convocatoria.estado
    fa = convocatoria.fecha_apertura
    fc = convocatoria.fecha_cierre
    if fa and fa <= now and (not fc or fc > now):
        convocatoria.estado = EstadoConvocatoria.ACTIVE
    elif fa and fa > now:
        convocatoria.estado = EstadoConvocatoria.SCHEDULED
    if fc and fc <= now:
        convocatoria.estado = EstadoConvocatoria.CLOSED
    return convocatoria.estado


def parse_datetime_or_error(raw_value, field_name: str) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        value = raw_value.strip()
    else:
        value = str(raw_value)
    if not value:
        return None
    try:
        dt = date_parser.isoparse(value)
    except Exception:
        try:
            dt = date_parser.parse(value)
        except Exception as exc:
            raise ValueError(
                f"Formato de {field_name} inválido: '{value}' (usar ISO 8601, ej: 2025-10-02T15:30:00Z)"
            ) from exc
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def debug_log(msg: str, payload=None) -> None:
    try:
        print(f"[DEBUG-CONVOCATORIAS] {msg}")
        if payload is not None:
            print(payload)
    except Exception:
        pass


def auto_archivar_convocatorias(now: Optional[datetime] = None) -> None:
    now = now or utc_now_naive()
    convs = Convocatoria.query.all()
    cambios = False
    for conv in convs:
        if conv.archivada:
            continue
        recalcular_estado(conv, now)
        if conv.estado == EstadoConvocatoria.CLOSED and conv.fecha_cierre and conv.fecha_cierre <= now:
            conv.archivar(now)
            cambios = True
    if cambios:
        db.session.commit()


def _normalizar_numero(valor: Optional[str]) -> Optional[float]:
    if valor is None:
        return None
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _extraer_patron_numero(texto: str, patron: str) -> Optional[float]:
    match = re.search(patron, texto, flags=re.IGNORECASE)
    if not match:
        return None
    for group in match.groups():
        numero = _normalizar_numero(group)
        if numero is not None:
            return numero
    return None


def validar_requisitos_estudiante(convocatoria: Convocatoria, estudiante: Usuario) -> Tuple[bool, List[str]]:
    requisitos_texto = convocatoria.requisitos.lower()
    razones: List[str] = []

    semestre_requerido = _extraer_patron_numero(requisitos_texto, r"semestre[s]?\s*(?:mínimo|minimo|mayor a)?\s*(\d+)")
    if semestre_requerido is not None:
        try:
            semestre_estudiante = int(str(estudiante.semestre))
        except (TypeError, ValueError):
            semestre_estudiante = 0
        if semestre_estudiante < int(semestre_requerido):
            razones.append(
                f"Semestre requerido: {int(semestre_requerido)}, estudiante: {semestre_estudiante}"
            )

    promedio_requerido = _extraer_patron_numero(
        requisitos_texto,
        r"promedio\s*(?:mínimo|minimo|mayor a)?\s*(\d+(?:[\.,]\d+)?)",
    )
    if promedio_requerido is not None:
        promedio_estudiante = estudiante.promedio or 0.0
        if promedio_estudiante < promedio_requerido:
            razones.append(
                f"Promedio requerido: {promedio_requerido}, estudiante: {promedio_estudiante}"
            )

    return len(razones) == 0, razones


__all__ = [
    "recalcular_estado",
    "parse_datetime_or_error",
    "debug_log",
    "auto_archivar_convocatorias",
    "validar_requisitos_estudiante",
]
