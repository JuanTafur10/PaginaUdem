"""Database models and enumerations."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from ..extensions import db
from ..utils.time import COL_TZ, utc_now_naive


class EstadoConvocatoria(enum.Enum):
    DRAFT = "borrador"
    SCHEDULED = "programada"
    ACTIVE = "activa"
    CLOSED = "cerrada"
    ARCHIVED = "archivada"


class TipoUsuario(enum.Enum):
    COORDINADOR = "COORDINATOR"
    PROFESOR = "PROFESSOR"
    ESTUDIANTE = "STUDENT"


class EstadoPostulacion(enum.Enum):
    PENDING = "pending"
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    SELECTED = "selected"
    NOT_SELECTED = "not_selected"
    ARCHIVED = "archived"


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), unique=True)
    correo = db.Column(db.String(120), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255))
    rol = db.Column(db.String(50), default="STUDENT")
    semestre = db.Column(db.String(10))
    promedio = db.Column(db.Float)
    horario = db.Column(db.String(255))
    horas_disponibles = db.Column(db.Integer)
    tipo_usuario = db.Column(db.Enum(TipoUsuario), default=TipoUsuario.ESTUDIANTE)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    inscripciones_monitoria = db.relationship("InscripcionMonitoria", backref="estudiante", lazy=True)

    def set_password(self, password: str) -> None:
        from werkzeug.security import generate_password_hash

        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        from werkzeug.security import check_password_hash

        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def autenticarse(self, password: str) -> bool:
        return self.check_password(password)

    def gestionar_credenciales(self, nuevo_password: Optional[str] = None) -> bool:
        if nuevo_password:
            self.set_password(nuevo_password)
        return True

    def gestionarCredenciales(self, nuevo_password: Optional[str] = None) -> bool:
        return self.gestionar_credenciales(nuevo_password)

    def actualizar_perfil(self, **datos) -> None:
        campos_permitidos = {"nombre", "semestre", "horario", "horas_disponibles", "promedio"}
        for clave, valor in datos.items():
            if clave in campos_permitidos:
                setattr(self, clave, valor)

    def actualizarPerfil(self, **datos) -> None:
        self.actualizar_perfil(**datos)

    def is_coordinator(self) -> bool:
        return self.rol == "COORDINATOR"

    def is_student(self) -> bool:
        return self.rol == "STUDENT"

    def is_professor(self) -> bool:
        return self.rol == "PROFESSOR"

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "id": self.id,
            "codigo": self.codigo,
            "correo": self.correo,
            "nombre": self.nombre,
            "rol": self.rol,
            "semestre": self.semestre,
            "promedio": self.promedio,
            "horario": self.horario,
            "horas_disponibles": self.horas_disponibles,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Convocatoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    curso = db.Column(db.String(200), nullable=False)
    semestre = db.Column(db.String(20), nullable=False)
    requisitos = db.Column(db.Text, nullable=False)
    fecha_apertura = db.Column(db.DateTime)
    fecha_cierre = db.Column(db.DateTime)
    estado = db.Column(db.Enum(EstadoConvocatoria), default=EstadoConvocatoria.DRAFT)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    archivada = db.Column(db.Boolean, default=False)
    archivada_at = db.Column(db.DateTime)
    inscripciones = db.relationship("InscripcionMonitoria", backref="convocatoria", lazy=True)

    def to_dict(self) -> Dict[str, Optional[str]]:
        def serialize_dt(dt: datetime | None) -> Tuple[Optional[str], Optional[str]]:
            if not dt:
                return None, None
            if dt.tzinfo is None:
                dt_utc = dt.replace(tzinfo=timezone.utc)
            else:
                dt_utc = dt.astimezone(timezone.utc)
            dt_col = dt_utc.astimezone(COL_TZ)
            return dt_col.isoformat(), dt_utc.isoformat()

        fa_local, fa_utc = serialize_dt(self.fecha_apertura)
        fc_local, fc_utc = serialize_dt(self.fecha_cierre)
        created_local, created_utc = serialize_dt(self.created_at)
        updated_local, updated_utc = serialize_dt(self.updated_at)
        archivada_local, _ = serialize_dt(self.archivada_at)

        return {
            "id": self.id,
            "curso": self.curso,
            "semestre": self.semestre,
            "requisitos": self.requisitos,
            "fecha_apertura": fa_local,
            "fecha_cierre": fc_local,
            "fecha_apertura_utc": fa_utc,
            "fecha_cierre_utc": fc_utc,
            "estado": self.estado.value if self.estado else None,
            "creado_por_id": self.creado_por_id,
            "created_at": created_local,
            "created_at_utc": created_utc,
            "updated_at": updated_local,
            "updated_at_utc": updated_utc,
            "archivada": self.archivada,
            "archivada_at": archivada_local,
        }

    def publicar_requisitos(self) -> str:
        return self.requisitos

    def publicarRequisitos(self) -> str:
        return self.publicar_requisitos()

    def recibir_postulacion(self, postulacion: "Postulacion") -> None:
        if postulacion not in self.postulaciones:
            self.postulaciones.append(postulacion)

    def recibirPostulaciones(self, postulacion: "Postulacion") -> None:
        self.recibir_postulacion(postulacion)

    def validar_informacion(self) -> bool:
        return bool(self.curso and self.semestre and self.requisitos)

    def validarInformacion(self) -> bool:
        return self.validar_informacion()

    def archivar(self, when: datetime | None = None) -> None:
        if self.archivada:
            return
        self.archivada = True
        self.archivada_at = when or utc_now_naive()
        self.estado = EstadoConvocatoria.ARCHIVED


class Postulacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    estudiante_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    convocatoria_id = db.Column(db.Integer, db.ForeignKey("convocatoria.id"), nullable=False)
    creada_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    estado = db.Column(db.Enum(EstadoPostulacion), default=EstadoPostulacion.PENDING, nullable=False)
    puntaje = db.Column(db.Float)
    resultado = db.Column(db.String(50))
    razones_rechazo = db.Column(db.Text)
    datos_formulario = db.Column(db.JSON, default=dict)
    datos_soportes = db.Column(db.JSON, default=dict)
    preasignada = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    estudiante = db.relationship(
        "Usuario",
        backref=db.backref("postulaciones", lazy=True),
        foreign_keys=[estudiante_id],
    )
    convocatoria = db.relationship("Convocatoria", backref=db.backref("postulaciones", lazy=True))
    creador = db.relationship(
        "Usuario",
        backref=db.backref("postulaciones_creadas", lazy=True),
        foreign_keys=[creada_por_id],
    )

    def completar_formulario(self, datos: Dict) -> None:
        self.datos_formulario = datos or {}

    def adjuntar_soportes(self, soportes: Dict) -> None:
        self.datos_soportes = soportes or {}

    def esperar_validacion(self) -> None:
        self.estado = EstadoPostulacion.PENDING

    def marcar_ineligible(self, razones: str) -> None:
        self.estado = EstadoPostulacion.INELIGIBLE
        self.razones_rechazo = razones

    def marcar_elegible(self, puntaje: float, resultado: str) -> None:
        self.estado = EstadoPostulacion.ELIGIBLE
        self.puntaje = puntaje
        self.resultado = resultado

    def marcar_seleccionado(self, comentario: Optional[str] = None) -> None:
        self.estado = EstadoPostulacion.SELECTED
        self.resultado = "seleccionado"
        self.razones_rechazo = comentario or None

    def marcar_no_seleccionado(self, comentario: Optional[str] = None) -> None:
        self.estado = EstadoPostulacion.NOT_SELECTED
        self.resultado = "no_seleccionado"
        self.razones_rechazo = comentario or None

    def marcar_preasignada(self, creada_por_id: int | None = None) -> None:
        self.preasignada = True
        if creada_por_id is not None:
            self.creada_por_id = creada_por_id

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "estado": self.estado.value if self.estado else None,
            "puntaje": self.puntaje,
            "resultado": self.resultado,
            "razones_rechazo": self.razones_rechazo,
            "convocatoria_id": self.convocatoria_id,
            "estudiante_id": self.estudiante_id,
            "creada_por_id": self.creada_por_id,
            "preasignada": self.preasignada,
            "datos_formulario": self.datos_formulario or {},
            "datos_soportes": self.datos_soportes or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class EvaluacionAspirante(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    postulacion_id = db.Column(db.Integer, db.ForeignKey("postulacion.id"), unique=True, nullable=False)
    puntaje = db.Column(db.Float, nullable=False)
    resultado = db.Column(db.String(50), nullable=False)
    detalles = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    postulacion = db.relationship("Postulacion", backref=db.backref("evaluacion", uselist=False))

    def registrar_resultado(self, puntaje: float, resultado: str, detalles: Dict) -> None:
        self.puntaje = puntaje
        self.resultado = resultado
        self.detalles = detalles or {}

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "postulacion_id": self.postulacion_id,
            "puntaje": self.puntaje,
            "resultado": self.resultado,
            "detalles": self.detalles or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class InscripcionMonitoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    estudiante_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    convocatoria_id = db.Column(db.Integer, db.ForeignKey("convocatoria.id"), nullable=False)
    comentario = db.Column(db.Text)
    horario_preferido = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        db.UniqueConstraint("estudiante_id", "convocatoria_id", name="uq_inscripcion_est_conv"),
    )

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "estudiante_id": self.estudiante_id,
            "convocatoria_id": self.convocatoria_id,
            "comentario": self.comentario,
            "horario_preferido": self.horario_preferido,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ConfiguracionIA(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    min_semestre = db.Column(db.Integer, default=1)
    min_promedio = db.Column(db.Float, default=0.0)
    peso_semestre = db.Column(db.Float, default=0.4)
    peso_promedio = db.Column(db.Float, default=0.6)
    peso_horas = db.Column(db.Float, default=0.2)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> Dict[str, float]:
        return {
            "min_semestre": self.min_semestre,
            "min_promedio": self.min_promedio,
            "peso_semestre": self.peso_semestre,
            "peso_promedio": self.peso_promedio,
            "peso_horas": self.peso_horas,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ReporteDescartes(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    convocatoria_id = db.Column(db.Integer, db.ForeignKey("convocatoria.id"), nullable=False)
    periodo = db.Column(db.String(20), nullable=False)
    contenido = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    convocatoria = db.relationship("Convocatoria", backref=db.backref("reportes_descartes", lazy=True))

    def generar(self, descartados: list[Dict]) -> None:
        self.contenido = {"descartados": descartados}

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "convocatoria_id": self.convocatoria_id,
            "periodo": self.periodo,
            "contenido": self.contenido or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TipoNotificacion(enum.Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class Notificacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    titulo = db.Column(db.String(255), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.Enum(TipoNotificacion), default=TipoNotificacion.INFO, nullable=False)
    leida = db.Column(db.Boolean, default=False, nullable=False)
    payload = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    read_at = db.Column(db.DateTime)

    usuario = db.relationship("Usuario", backref=db.backref("notificaciones", lazy=True))

    def marcar_leida(self, when: datetime | None = None) -> None:
        if self.leida:
            return
        self.leida = True
        self.read_at = when or utc_now_naive()

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "usuario_id": self.usuario_id,
            "titulo": self.titulo,
            "mensaje": self.mensaje,
            "tipo": self.tipo.value if self.tipo else TipoNotificacion.INFO.value,
            "leida": self.leida,
            "metadata": self.payload or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }


__all__ = [
    "db",
    "Usuario",
    "Convocatoria",
    "Postulacion",
    "InscripcionMonitoria",
    "EvaluacionAspirante",
    "ConfiguracionIA",
    "ReporteDescartes",
    "EstadoConvocatoria",
    "EstadoPostulacion",
    "TipoUsuario",
    "Notificacion",
    "TipoNotificacion",
]
