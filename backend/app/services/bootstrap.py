"""Database bootstrap helpers."""
from __future__ import annotations

from sqlalchemy import text

from ..extensions import db
from ..models import TipoUsuario, Usuario


def ensure_schema_updates() -> None:
    with db.engine.begin() as conn:
        columnas_convocatoria = {
            row[1] for row in conn.execute(text("PRAGMA table_info(convocatoria)"))
        }
        if "archivada" not in columnas_convocatoria:
            conn.execute(text("ALTER TABLE convocatoria ADD COLUMN archivada BOOLEAN DEFAULT 0"))
            conn.execute(text("UPDATE convocatoria SET archivada = 0 WHERE archivada IS NULL"))
        if "archivada_at" not in columnas_convocatoria:
            conn.execute(text("ALTER TABLE convocatoria ADD COLUMN archivada_at DATETIME"))


def seed_default_data() -> None:
    if Usuario.query.first():
        return

    coordinador = Usuario(
        codigo="UCOORD-001",
        correo="coordinador@udem.edu.co",
        nombre="Coordinador Académico",
        rol="COORDINATOR",
        horario="Lun-Vie 08:00-17:00",
        horas_disponibles=10,
        tipo_usuario=TipoUsuario.COORDINADOR,
    )
    coordinador.set_password("123456")

    profesor = Usuario(
        codigo="UPROF-001",
        correo="profesor@udem.edu.co",
        nombre="Dr. Pedro Martínez",
        rol="PROFESSOR",
        horario="Lun-Jue 08:00-12:00",
        horas_disponibles=8,
        tipo_usuario=TipoUsuario.PROFESOR,
    )
    profesor.set_password("123456")

    estudiante1 = Usuario(
        codigo="USTUD-001",
        correo="estudiante@udem.edu.co",
        nombre="Juan Pérez",
        rol="STUDENT",
        semestre="5",
        promedio=4.3,
        horas_disponibles=12,
    )
    estudiante1.set_password("123456")

    estudiante2 = Usuario(
        codigo="USTUD-002",
        correo="maria@udem.edu.co",
        nombre="María González",
        rol="STUDENT",
        semestre="3",
        promedio=4.0,
        horas_disponibles=10,
    )
    estudiante2.set_password("123456")

    estudiante3 = Usuario(
        codigo="USTUD-003",
        correo="carlos@udem.edu.co",
        nombre="Carlos Rodríguez",
        rol="STUDENT",
        semestre="7",
        promedio=4.6,
        horas_disponibles=6,
    )
    estudiante3.set_password("123456")

    db.session.add_all([coordinador, profesor, estudiante1, estudiante2, estudiante3])
    db.session.commit()


__all__ = [
    "ensure_schema_updates",
    "seed_default_data",
]
