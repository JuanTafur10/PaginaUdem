from datetime import datetime
from .extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
import enum

# ---------- Helpers ----------
class EstadoConvocatoria(enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"

# ---------- Usuario y roles ----------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    correo = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(50), nullable=False)  # 'COORDINATOR', 'STUDENT', 'PROFESSOR', etc.
    semestre = db.Column(db.String(10), nullable=True)  # Solo para estudiantes: '1', '2', '3', etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_coordinator(self):
        return self.rol == "COORDINATOR"

    def is_student(self):
        return self.rol == "STUDENT"

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'correo': self.correo,
            'rol': self.rol,
            'semestre': self.semestre if self.is_student() else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# ---------- Convocatoria y soporte ----------
class Convocatoria(db.Model):
    __tablename__ = "convocatorias"
    id = db.Column(db.Integer, primary_key=True)
    curso = db.Column(db.String(200), nullable=False)
    semestre = db.Column(db.String(50), nullable=False)
    requisitos = db.Column(db.Text, nullable=False)
    fecha_apertura = db.Column(db.DateTime, nullable=True)
    fecha_cierre = db.Column(db.DateTime, nullable=True)
    estado = db.Column(db.Enum(EstadoConvocatoria), default=EstadoConvocatoria.DRAFT, nullable=False)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    creado_por = db.relationship("User", backref="convocatorias_creadas")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    history = db.relationship("ConvocatoriaHistory", backref="convocatoria", cascade="all, delete-orphan")
    postulaciones = db.relationship("Postulacion", backref="convocatoria", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "curso": self.curso,
            "semestre": self.semestre,
            "requisitos": self.requisitos,
            "fecha_apertura": self.fecha_apertura.isoformat() if self.fecha_apertura else None,
            "fecha_cierre": self.fecha_cierre.isoformat() if self.fecha_cierre else None,
            "estado": self.estado.value,
            "creado_por_id": self.creado_por_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

class ConvocatoriaHistory(db.Model):
    __tablename__ = "convocatoria_history"
    id = db.Column(db.Integer, primary_key=True)
    convocatoria_id = db.Column(db.Integer, db.ForeignKey("convocatorias.id"), nullable=False)
    accion = db.Column(db.String(200), nullable=False)
    detalle = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ---------- Postulaciones (Estudiante Aspirante) ----------
class Postulacion(db.Model):
    __tablename__ = "postulaciones"
    id = db.Column(db.Integer, primary_key=True)
    estudiante_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    convocatoria_id = db.Column(db.Integer, db.ForeignKey("convocatorias.id"), nullable=False)
    estado = db.Column(db.String(50), default="registrada")  # registrada, en_evaluacion, preseleccionado, descartado
    hoja_vida_filename = db.Column(db.String(250), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---------- Resto de modelos (esqueleto) - total ~30 ----------
class Pagina(db.Model):  # página del sistema
    __tablename__ = "paginas"
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(250))
    modulo_inicial = db.Column(db.String(100))

class Estudiante(db.Model):
    __tablename__ = "estudiantes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    codigo = db.Column(db.String(50))
    user = db.relationship("User")

class EstudianteAsistente(db.Model):
    __tablename__ = "estudiantes_asistente"
    id = db.Column(db.Integer, primary_key=True)
    id_asistencia = db.Column(db.String(50))
    horario = db.Column(db.String(100))

class EstudianteMonitor(db.Model):
    __tablename__ = "estudiantes_monitor"
    id = db.Column(db.Integer, primary_key=True)
    horas = db.Column(db.Integer)
    estado = db.Column(db.String(50))

class Profesor(db.Model):
    __tablename__ = "profesores"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150))

class CoordinadorAcademico(db.Model):
    __tablename__ = "coordinadores"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150))

class CoordinadorUOC(db.Model):
    __tablename__ = "coordinador_uoc"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150))

class ComiteSeleccion(db.Model):
    __tablename__ = "comite_seleccion"
    id = db.Column(db.Integer, primary_key=True)
    miembros = db.Column(db.Text)

class EvaluacionAspirante(db.Model):
    __tablename__ = "evaluacion_aspirante"
    id = db.Column(db.Integer, primary_key=True)
    puntaje = db.Column(db.Integer)
    resultado = db.Column(db.String(50))

class ValidacionDocumentos(db.Model):
    __tablename__ = "validacion_documentos"
    id = db.Column(db.Integer, primary_key=True)
    estado = db.Column(db.String(50))

class Entrevista(db.Model):
    __tablename__ = "entrevistas"
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime)
    puntaje = db.Column(db.Integer)

class SeleccionIA(db.Model):
    __tablename__ = "seleccion_ia"
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(50))

class AsignacionMonitor(db.Model):
    __tablename__ = "asignaciones_monitor"
    id = db.Column(db.Integer, primary_key=True)
    periodo = db.Column(db.String(50))

class ContratoMonitoria(db.Model):
    __tablename__ = "contratos_monitoria"
    id = db.Column(db.Integer, primary_key=True)
    inicio = db.Column(db.Date)
    fin = db.Column(db.Date)

class CargaAcademica(db.Model):
    __tablename__ = "carga_academica"
    id = db.Column(db.Integer, primary_key=True)
    horas_semana = db.Column(db.Integer)

class SeguimientoMonitoria(db.Model):
    __tablename__ = "seguimiento_monitoria"
    id = db.Column(db.Integer, primary_key=True)
    estado = db.Column(db.String(50))

class HistorialDesempeno(db.Model):
    __tablename__ = "historial_desempeno"
    id = db.Column(db.Integer, primary_key=True)
    promedio = db.Column(db.Float)

class Reporte(db.Model):
    __tablename__ = "reportes"
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(50))
    periodo = db.Column(db.String(50))

class GestionAcademica(db.Model):
    __tablename__ = "gestion_academica"
    id = db.Column(db.Integer, primary_key=True)
    indicadores = db.Column(db.Text)

class Asesoria(db.Model):
    __tablename__ = "asesorias"
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime)
    tema = db.Column(db.String(200))

class SolicitudMonitoria(db.Model):
    __tablename__ = "solicitud_monitoria"
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime)

class AdministracionSistema(db.Model):
    __tablename__ = "administracion_sistema"
    id = db.Column(db.Integer, primary_key=True)
    politica_backups = db.Column(db.Text)

class CalendarioAcademico(db.Model):
    __tablename__ = "calendario_academico"
    id = db.Column(db.Integer, primary_key=True)
    cronograma = db.Column(db.Text)

class Notificacion(db.Model):
    __tablename__ = "notificaciones"
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(50))
    fecha = db.Column(db.DateTime)

class EstadisticasMonitoria(db.Model):
    __tablename__ = "estadisticas_monitoria"
    id = db.Column(db.Integer, primary_key=True)
    metricas = db.Column(db.Text)

class Alerta(db.Model):
    __tablename__ = "alertas"
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(50))
    severidad = db.Column(db.String(50))

# Base de datos como "entidad" 
class BaseDeDatos:
    def __init__(self, motor="sqlite", esquema="public"):
        self.motor = motor
        self.esquema = esquema
    def almacenar_informacion(self):
        pass
