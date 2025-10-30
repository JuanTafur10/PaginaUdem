# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone, timedelta as _td
from zoneinfo import ZoneInfo
import enum
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from sqlalchemy import text
from dateutil import parser as date_parser
from datetime import timezone, timedelta as _td  # already imported above, keep for clarity

# Crear aplicación Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret'
app.config['JWT_SECRET_KEY'] = 'jwt-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dev.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Extender duración del token para desarrollo (8 horas)
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = _td(hours=8)

# Zona horaria Colombia
COL_TZ = ZoneInfo("America/Bogota")

# Configurar CORS
CORS(app, origins=["*"])

# Inicializar extensiones
db = SQLAlchemy(app)
jwt = JWTManager(app)


def ensure_schema_updates() -> None:
    """Garantiza que columnas agregadas recientemente existan en SQLite."""
    with db.engine.begin() as conn:
        columnas_convocatoria = {
            row[1] for row in conn.execute(text("PRAGMA table_info(convocatoria)"))
        }
        if "archivada" not in columnas_convocatoria:
            conn.execute(text("ALTER TABLE convocatoria ADD COLUMN archivada BOOLEAN DEFAULT 0"))
            conn.execute(text("UPDATE convocatoria SET archivada = 0 WHERE archivada IS NULL"))
        if "archivada_at" not in columnas_convocatoria:
            conn.execute(text("ALTER TABLE convocatoria ADD COLUMN archivada_at DATETIME"))

# Enums
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
    ARCHIVED = "archived"

# Modelos básicos
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
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
    creado_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    archivada = db.Column(db.Boolean, default=False)
    archivada_at = db.Column(db.DateTime)

    def to_dict(self):
        def serialize_dt(dt):
            if not dt:
                return None, None
            # asumir que dt almacenado es naive UTC
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
        return {
            "id": self.id,
            "curso": self.curso,
            "semestre": self.semestre,
            "requisitos": self.requisitos,
            # Campos con horario local Colombia (principal para frontend)
            "fecha_apertura": fa_local,
            "fecha_cierre": fc_local,
            # Referencia en UTC
            "fecha_apertura_utc": fa_utc,
            "fecha_cierre_utc": fc_utc,
            "estado": self.estado.value,
            "creado_por_id": self.creado_por_id,
            "created_at": created_local,
            "created_at_utc": created_utc,
            "updated_at": updated_local,
            "updated_at_utc": updated_utc,
            "archivada": self.archivada,
            "archivada_at": serialize_dt(self.archivada_at)[0]
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

    def archivar(self, when: Optional[datetime] = None) -> None:
        if self.archivada:
            return
        self.archivada = True
        self.archivada_at = when or datetime.utcnow()
        self.estado = EstadoConvocatoria.ARCHIVED


class Postulacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    estudiante_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    convocatoria_id = db.Column(db.Integer, db.ForeignKey('convocatoria.id'), nullable=False)
    estado = db.Column(db.Enum(EstadoPostulacion), default=EstadoPostulacion.PENDING, nullable=False)
    puntaje = db.Column(db.Float)
    resultado = db.Column(db.String(50))
    razones_rechazo = db.Column(db.Text)
    datos_formulario = db.Column(db.JSON, default=dict)
    datos_soportes = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    estudiante = db.relationship('Usuario', backref=db.backref('postulaciones', lazy=True))
    convocatoria = db.relationship('Convocatoria', backref=db.backref('postulaciones', lazy=True))

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

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "estado": self.estado.value,
            "puntaje": self.puntaje,
            "resultado": self.resultado,
            "razones_rechazo": self.razones_rechazo,
            "convocatoria_id": self.convocatoria_id,
            "estudiante_id": self.estudiante_id,
            "datos_formulario": self.datos_formulario or {},
            "datos_soportes": self.datos_soportes or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class EvaluacionAspirante(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    postulacion_id = db.Column(db.Integer, db.ForeignKey('postulacion.id'), unique=True, nullable=False)
    puntaje = db.Column(db.Float, nullable=False)
    resultado = db.Column(db.String(50), nullable=False)
    detalles = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    postulacion = db.relationship('Postulacion', backref=db.backref('evaluacion', uselist=False))

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


class ConfiguracionIA(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    min_semestre = db.Column(db.Integer, default=1)
    min_promedio = db.Column(db.Float, default=0.0)
    peso_semestre = db.Column(db.Float, default=0.4)
    peso_promedio = db.Column(db.Float, default=0.6)
    peso_horas = db.Column(db.Float, default=0.2)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    convocatoria_id = db.Column(db.Integer, db.ForeignKey('convocatoria.id'), nullable=False)
    periodo = db.Column(db.String(20), nullable=False)
    contenido = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    convocatoria = db.relationship('Convocatoria', backref=db.backref('reportes_descartes', lazy=True))

    def generar(self, descartados: List[Dict]) -> None:
        self.contenido = {"descartados": descartados}

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "convocatoria_id": self.convocatoria_id,
            "periodo": self.periodo,
            "contenido": self.contenido or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SeleccionIA:
    def __init__(self, configuracion: ConfiguracionIA):
        self.configuracion = configuracion

    def _obtener_semestre(self, usuario: Usuario) -> Optional[int]:
        if usuario.semestre is None:
            return None
        try:
            return int(str(usuario.semestre))
        except (ValueError, TypeError):
            return None

    def _calcular_puntaje(self, postulacion: Postulacion) -> Tuple[float, Dict[str, float]]:
        estudiante = postulacion.estudiante
        detalles: Dict[str, float] = {}
        puntaje = 0.0

        semestre_val = self._obtener_semestre(estudiante)
        if semestre_val is not None:
            factor_semestre = min(max(semestre_val / 10.0, 0), 1)
            detalles["puntaje_semestre"] = factor_semestre * self.configuracion.peso_semestre * 100
            puntaje += detalles["puntaje_semestre"]

        if estudiante.promedio is not None:
            factor_promedio = min(max(estudiante.promedio / 5.0, 0), 1)
            detalles["puntaje_promedio"] = factor_promedio * self.configuracion.peso_promedio * 100
            puntaje += detalles["puntaje_promedio"]

        if estudiante.horas_disponibles is not None:
            factor_horas = min(max(estudiante.horas_disponibles / 20.0, 0), 1)
            detalles["puntaje_horas"] = factor_horas * self.configuracion.peso_horas * 100
            puntaje += detalles["puntaje_horas"]

        detalles["puntaje_total"] = puntaje
        return puntaje, detalles

    def filtrar_postulaciones(self, postulaciones: List[Postulacion]) -> Tuple[List[Postulacion], List[Dict]]:
        elegibles: List[Postulacion] = []
        descartados: List[Dict] = []

        for postulacion in postulaciones:
            estudiante = postulacion.estudiante
            semestre_val = self._obtener_semestre(estudiante) or 0
            promedio_val = estudiante.promedio or 0.0

            razones: List[str] = []
            if semestre_val < self.configuracion.min_semestre:
                razones.append(
                    f"Semestre mínimo requerido: {self.configuracion.min_semestre}, estudiante: {semestre_val}"
                )
            if promedio_val < self.configuracion.min_promedio:
                razones.append(
                    f"Promedio mínimo requerido: {self.configuracion.min_promedio}, estudiante: {promedio_val}"
                )

            if razones:
                postulacion.marcar_ineligible("; ".join(razones))
                descartados.append(
                    {
                        "postulacion_id": postulacion.id,
                        "estudiante_id": postulacion.estudiante_id,
                        "convocatoria_id": postulacion.convocatoria_id,
                        "razones": razones,
                    }
                )
            else:
                elegibles.append(postulacion)

        return elegibles, descartados

    def clasificar_postulaciones(self, postulaciones: List[Postulacion]) -> List[Dict]:
        ranking: List[Dict] = []
        for postulacion in postulaciones:
            puntaje, detalles = self._calcular_puntaje(postulacion)
            postulacion.marcar_elegible(puntaje, "pre-seleccionado")
            ranking.append(
                {
                    "postulacion": postulacion.to_dict(),
                    "estudiante": postulacion.estudiante.to_dict(),
                    "puntaje": puntaje,
                    "detalles": detalles,
                }
            )
        ranking.sort(key=lambda item: item["puntaje"], reverse=True)
        return ranking

    def generar_reporte_descartados(self, descartados: List[Dict]) -> Dict:
        return {
            "total_descartados": len(descartados),
            "detalle": descartados,
        }


@dataclass
class Pagina:
    url: str
    moduloInicial: str

    def mostrarInformacion(self) -> Dict[str, str]:
        return {"url": self.url, "moduloInicial": self.moduloInicial}

    def autenticarUsuarios(self) -> bool:
        return True

    def redirigirModulos(self, modulo: Optional[str] = None) -> str:
        return modulo or self.moduloInicial


@dataclass
class Estudiante:
    codigo: str
    nombre: str
    correo: str

    def registrarse(self) -> bool:
        return all([self.codigo, self.nombre, self.correo])

    def postularse(self, convocatoria: Optional["Convocatoria"] = None) -> bool:
        if not convocatoria:
            return True
        estado = convocatoria.estado.value if isinstance(convocatoria.estado, EstadoConvocatoria) else convocatoria.estado
        if isinstance(estado, str):
            estado = estado.lower()
        return estado in ("activa", "active")

    def consultarConvocatorias(self) -> List[Dict[str, Any]]:
        return [c.to_dict() for c in Convocatoria.query.filter_by(archivada=False).all()]

    def revisarResultados(self, convocatoria: "Convocatoria") -> List[Dict[str, Any]]:
        return [p.to_dict() for p in Postulacion.query.filter_by(convocatoria_id=convocatoria.id).all()]

    def pideAsesorias(self) -> str:
        return "Solicitud de asesoría registrada"


@dataclass
class EstudianteAsistente(Estudiante):
    idAsistencia: Optional[int] = None
    horario: str = ""

    def consultarHorarios(self) -> str:
        return self.horario or "Horario pendiente"

    def apoyarMonitor(self) -> str:
        return "Asistencia programada"

    def asistirAsesorias(self) -> str:
        return "Asesoría atendida"


@dataclass
class EstudianteAspirante(Estudiante):
    idPostulacion: Optional[int] = None
    estado: str = "pendiente"

    def completarFormulario(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        return datos or {}

    def adjuntarSoportes(self, soportes: Dict[str, Any]) -> Dict[str, Any]:
        return soportes or {}

    def esperarValidacion(self) -> str:
        self.estado = "en_validacion"
        return self.estado


@dataclass
class EstudianteMonitor(Estudiante):
    idMonitor: Optional[int] = None
    horas: int = 0
    estado: str = "activo"

    def atenderConsultas(self) -> str:
        return "Consultas atendidas"

    def registrarAsesorias(self) -> str:
        return "Asesorías registradas"

    def generarReportes(self) -> str:
        return "Reportes generados"


@dataclass
class Profesor:
    idProfesor: int
    nombre: str

    def solicitarApoyo(self) -> str:
        return "Apoyo solicitado"

    def validarMonitores(self) -> str:
        return "Monitores validados"

    def generarReportes(self) -> str:
        return "Reportes generados"


@dataclass
class CoordinadorAcademico:
    idCoord: int
    nombre: str

    def validarConvocatorias(self) -> str:
        return "Convocatorias validadas"

    def aprobarMonitores(self) -> str:
        return "Monitores aprobados"

    def supervisarReportes(self) -> str:
        return "Reportes supervisados"


@dataclass
class ComiteSeleccion:
    idComite: int
    miembros: str

    def evaluarPostulaciones(self) -> str:
        return "Postulaciones evaluadas"

    def entrevistar(self) -> str:
        return "Entrevistas programadas"

    def decidirSeleccion(self) -> str:
        return "Selección decidida"


@dataclass
class Reporte:
    idReporte: int
    tipo: str
    periodo: str
    registros: List[Dict[str, Any]] = field(default_factory=list)

    def generarInformes(self, entrada: Dict[str, Any]) -> None:
        self.registros.append(entrada)

    def consolidarResultados(self) -> List[Dict[str, Any]]:
        return self.registros

    def enviarCoordinador(self) -> str:
        return "Reporte enviado al coordinador"


@dataclass
class CargaAcademica:
    idCarga: int
    horasSemana: int

    def registrarHorarios(self, horas: int) -> None:
        self.horasSemana = horas

    def controlarChoques(self) -> bool:
        return self.horasSemana <= 40

    def ajustarDisponibilidad(self, horas: int) -> int:
        self.horasSemana = max(horas, 0)
        return self.horasSemana


@dataclass
class HistorialDesempeno:
    idHistorial: int
    promedio: float
    observaciones: List[str] = field(default_factory=list)

    def registrarCalificaciones(self, promedio: float) -> None:
        self.promedio = promedio

    def guardarObservaciones(self, texto: str) -> None:
        self.observaciones.append(texto)

    def generarEvolucion(self) -> Dict[str, Any]:
        return {"promedio": self.promedio, "observaciones": self.observaciones}


@dataclass
class GestionAcademica:
    idGestion: int
    indicadores: str

    def centralizarDatos(self) -> str:
        return "Datos académicos centralizados"

    def controlarCarga(self) -> str:
        return "Carga controlada"

    def generarIndicadores(self) -> str:
        return self.indicadores


@dataclass
class ValidacionDocumentos:
    idValidacion: int
    estado: str = "pendiente"

    def confirmarAutenticidad(self) -> str:
        self.estado = "autentico"
        return self.estado

    def aprobarRechazar(self, aprobado: bool) -> str:
        self.estado = "aprobado" if aprobado else "rechazado"
        return self.estado

    def reportarErrores(self) -> str:
        return "Errores reportados"


@dataclass
class ContratoMonitoria:
    idContrato: int
    inicio: datetime
    fin: datetime

    def formalizarAcuerdo(self) -> str:
        return "Contrato formalizado"

    def definirObligaciones(self) -> str:
        return "Obligaciones definidas"

    def registrarVigencia(self) -> Dict[str, Any]:
        return {"inicio": self.inicio.isoformat(), "fin": self.fin.isoformat()}


@dataclass
class AsignacionMonitor:
    idAsignacion: int
    periodo: str
    materias: List[str] = field(default_factory=list)

    def asociarMonitores(self, monitor: str) -> None:
        self.materias.append(monitor)

    def registrarMaterias(self, materia: str) -> None:
        self.materias.append(materia)

    def validarDisponibilidad(self) -> bool:
        return bool(self.materias)


@dataclass
class Asesoria:
    idAsesoria: int
    fecha: datetime
    tema: str
    asistencia: List[str] = field(default_factory=list)

    def programarSesiones(self, fecha: datetime) -> None:
        self.fecha = fecha

    def registrarAsistencia(self, estudiante: str) -> None:
        self.asistencia.append(estudiante)

    def retroalimentar(self, retro: str) -> str:
        return retro


@dataclass
class AdministracionSistema:
    idAdmin: int
    politicaBackups: str

    def administrarCuentas(self) -> str:
        return "Cuentas administradas"

    def otorgarPermisos(self) -> str:
        return "Permisos otorgados"

    def respaldarDatos(self) -> str:
        return self.politicaBackups


@dataclass
class BaseDatos:
    motor: str
    esquema: str

    def almacenarInformacion(self) -> str:
        return "Información almacenada"

    def garantizarIntegridad(self) -> str:
        return "Integridad garantizada"

    def recuperarDatos(self) -> str:
        return "Datos recuperados"


@dataclass
class SeguimientoMonitoria:
    idSeguimiento: int
    estado: str

    def registrarCumplimiento(self) -> str:
        return "Cumplimiento registrado"

    def generarAlertas(self) -> str:
        return "Alertas generadas"

    def consolidarRetroalimentacion(self) -> str:
        return "Retroalimentación consolidada"


@dataclass
class SolicitudMonitoria:
    idSolicitud: int
    fecha: datetime

    def permitirSolicitud(self) -> str:
        return "Solicitud permitida"

    def enviarAlComite(self) -> str:
        return "Solicitud enviada al comité"

    def validarDisponibilidad(self) -> str:
        return "Disponibilidad validada"


@dataclass
class CalendarioAcademico:
    idCal: int
    cronograma: str

    def definirFechas(self) -> str:
        return self.cronograma

    def registrarEntrevistas(self) -> str:
        return "Entrevistas registradas"

    def notificarCronogramas(self) -> str:
        return "Cronogramas notificados"


@dataclass
class Notificacion:
    idNotif: int
    tipo: str
    fecha: datetime

    def enviarRecordatorios(self) -> str:
        return "Recordatorio enviado"

    def informarResultados(self) -> str:
        return "Resultados informados"

    def notificarAsignaciones(self) -> str:
        return "Asignaciones notificadas"


@dataclass
class EstadisticasMonitoria:
    idEstadistica: int
    metricas: str

    def generarMetricas(self) -> str:
        return self.metricas

    def compararDesempeno(self) -> str:
        return "Desempeño comparado"

    def reportarIndicadores(self) -> str:
        return self.metricas


@dataclass
class Alerta:
    idAlerta: int
    tipo: str
    severidad: str

    def detectarFallas(self) -> str:
        return "Fallas detectadas"

    def notificarResponsables(self) -> str:
        return "Responsables notificados"

    def escalarIncumplimientos(self) -> str:
        return "Incumplimientos escalados"


@dataclass
class Entrevista:
    idEntrevista: int
    fecha: datetime
    puntaje: int

    def registrarPreguntas(self, preguntas: List[str]) -> List[str]:
        return preguntas

    def puntuar(self, puntaje: int) -> int:
        self.puntaje = puntaje
        return self.puntaje

    def guardarObservaciones(self, observaciones: str) -> str:
        return observaciones


@dataclass
class CoordinadorUOC:
    idUOC: int
    nombre: str

    def supervisarLineamientos(self) -> str:
        return "Lineamientos supervisados"

    def autorizarCambios(self) -> str:
        return "Cambios autorizados"

    def generarReportesGlobales(self) -> str:
        return "Reportes globales generados"

def recalcular_estado(convocatoria: "Convocatoria", now: datetime):
    """Recalcula el estado según fechas y momento actual (now en UTC)."""
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

# Utilidad para parsear fechas de forma tolerante y con mensajes claros
def parse_datetime_or_error(raw_value, field_name):
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        value = raw_value.strip()
    else:
        value = str(raw_value)
    if not value:
        return None
    try:
        # Intento estricto ISO
        dt = date_parser.isoparse(value)
    except Exception:
        try:
            # Intento flexible
            dt = date_parser.parse(value)
        except Exception:
            raise ValueError(f"Formato de {field_name} inválido: '{value}' (usar ISO 8601, ej: 2025-10-02T15:30:00Z)")

    # Normalizar a UTC naive (sin tzinfo) para comparaciones y almacenamiento consistente
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

def debug_log(msg, payload=None):
    try:
        print(f"[DEBUG-CONVOCATORIAS] {msg}")
        if payload is not None:
            print(payload)
    except Exception:
        pass


def obtener_configuracion_ia() -> ConfiguracionIA:
    config = ConfiguracionIA.query.first()
    if not config:
        config = ConfiguracionIA()
        db.session.add(config)
        db.session.commit()
    return config


def obtener_servicio_ia() -> SeleccionIA:
    return SeleccionIA(obtener_configuracion_ia())


def auto_archivar_convocatorias(now: Optional[datetime] = None) -> None:
    now = now or datetime.utcnow()
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

    promedio_requerido = _extraer_patron_numero(requisitos_texto, r"promedio\s*(?:mínimo|minimo|mayor a)?\s*(\d+(?:[\.,]\d+)?)")
    if promedio_requerido is not None:
        promedio_estudiante = estudiante.promedio or 0.0
        if promedio_estudiante < promedio_requerido:
            razones.append(
                f"Promedio requerido: {promedio_requerido}, estudiante: {promedio_estudiante}"
            )

    return len(razones) == 0, razones


def registrar_descartes(convocatoria: Convocatoria, descartados: List[Dict]) -> Optional[ReporteDescartes]:
    if not descartados:
        return None
    periodo_actual = datetime.utcnow().strftime("%Y-%m")
    reporte = ReporteDescartes.query.filter_by(
        convocatoria_id=convocatoria.id,
        periodo=periodo_actual
    ).first()
    if not reporte:
        reporte = ReporteDescartes(convocatoria_id=convocatoria.id, periodo=periodo_actual)
        db.session.add(reporte)
    servicio = obtener_servicio_ia()
    reporte.generar(servicio.generar_reporte_descartados(descartados))
    return reporte

# Rutas de autenticación
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    correo = data.get("correo")
    password = data.get("password")
    
    if not correo or not password:
        return jsonify({"msg": "correo y password requeridos"}), 400
    
    user = Usuario.query.filter_by(correo=correo).first()
    if not user or not user.check_password(password):
        return jsonify({"msg": "credenciales inválidas"}), 401
    
    token = create_access_token(identity=str(user.id))
    return jsonify({
        "access_token": token, 
        "rol": user.rol,
        "user": user.to_dict()
    })

@app.route("/api/auth/profile", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = int(get_jwt_identity())
    user = Usuario.query.get_or_404(user_id)
    return jsonify(user.to_dict())

@app.route("/api/auth/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    user_id = int(get_jwt_identity())
    user = Usuario.query.get_or_404(user_id)
    data = request.get_json() or {}
    
    # Solo los estudiantes pueden actualizar su semestre
    if user.is_student() and "semestre" in data:
        semestre = data.get("semestre")
        if semestre and semestre in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]:
            user.semestre = semestre
        else:
            return jsonify({"msg": "Semestre inválido. Debe ser entre 1 y 10"}), 400
    
    # Actualizar nombre si se proporciona
    if "nombre" in data and data["nombre"]:
        user.nombre = data["nombre"]
    
    db.session.commit()
    return jsonify(user.to_dict())

# Endpoints de convocatorias
@app.route("/api/convocatorias", methods=["POST"])
@jwt_required()
def crear_convocatoria():
    user_id = int(get_jwt_identity())
    user = Usuario.query.get_or_404(user_id)
    
    if not (user.is_coordinator() or user.is_professor()):
        return jsonify({"msg": "Solo coordinadores y profesores pueden crear convocatorias"}), 403
    
    data = request.get_json() or {}
    debug_log("Payload crear_convocatoria recibido", data)
    
    # Validaciones HU-01
    for campo in ("curso", "semestre", "requisitos"):
        if not data.get(campo):
            return jsonify({"msg": f"Campo obligatorio faltante: {campo}"}), 400
    
    convocatoria = Convocatoria(
        curso=data["curso"],
        semestre=data["semestre"],
        requisitos=data["requisitos"],
        creado_por_id=user.id
    )
    
    # Si se proporcionan fechas, validarlas y determinar estado inicial
    now = datetime.utcnow()
    if data.get("fecha_apertura"):
        try:
            fa = parse_datetime_or_error(data["fecha_apertura"], "fecha_apertura")
            debug_log("Fecha apertura parseada", {"original": data["fecha_apertura"], "normalizada": fa.isoformat()})
            if fa < now:
                return jsonify({"msg": "fecha_apertura no puede estar en el pasado"}), 400
            convocatoria.fecha_apertura = fa
        except (ValueError, TypeError) as ve:
            debug_log("Error parseando fecha_apertura", str(ve))
            return jsonify({"msg": str(ve)}), 400
    
    if data.get("fecha_cierre"):
        try:
            fc = parse_datetime_or_error(data["fecha_cierre"], "fecha_cierre")
            debug_log("Fecha cierre parseada", {"original": data["fecha_cierre"], "normalizada": fc.isoformat()})
            if fc < now:
                return jsonify({"msg": "fecha_cierre no puede estar en el pasado"}), 400
            convocatoria.fecha_cierre = fc
        except (ValueError, TypeError) as ve:
            debug_log("Error parseando fecha_cierre", str(ve))
            return jsonify({"msg": str(ve)}), 400

    # Validar coherencia de rango
    if convocatoria.fecha_apertura and convocatoria.fecha_cierre:
        if convocatoria.fecha_cierre <= convocatoria.fecha_apertura:
            debug_log("Validación rango fechas falló", {
                "fecha_apertura": convocatoria.fecha_apertura.isoformat(),
                "fecha_cierre": convocatoria.fecha_cierre.isoformat()
            })
            return jsonify({"msg": "fecha_cierre debe ser posterior a fecha_apertura"}), 400

    # Determinar estado inicial según helper
    recalcular_estado(convocatoria, now)
    
    db.session.add(convocatoria)
    db.session.commit()
    
    return jsonify(convocatoria.to_dict()), 201

@app.route("/api/convocatorias/<int:id>/fechas", methods=["PATCH"])
@jwt_required()
def asignar_fechas(id):
    user_id = int(get_jwt_identity())
    user = Usuario.query.get_or_404(user_id)
    
    if not (user.is_coordinator() or user.is_professor()):
        return jsonify({"msg": "Solo coordinadores y profesores pueden asignar fechas"}), 403
    
    convocatoria = Convocatoria.query.get_or_404(id)
    if convocatoria.estado == EstadoConvocatoria.CLOSED:
        return jsonify({"msg": "No se pueden modificar convocatorias cerradas"}), 400
    
    data = request.get_json() or {}
    now = datetime.utcnow()
    
    # Validaciones HU-02
    if data.get("fecha_apertura"):
        try:
            fa_dt = parse_datetime_or_error(data["fecha_apertura"], "fecha_apertura")
            debug_log("PATCH fecha_apertura parseada", {"original": data["fecha_apertura"], "normalizada": fa_dt.isoformat()})
            if fa_dt < now:
                return jsonify({"msg": "fecha_apertura no puede estar en el pasado"}), 400
            convocatoria.fecha_apertura = fa_dt
        except (ValueError, TypeError) as ve:
            debug_log("PATCH error parseando fecha_apertura", str(ve))
            return jsonify({"msg": str(ve)}), 400
    
    if data.get("fecha_cierre"):
        try:
            fc_dt = parse_datetime_or_error(data["fecha_cierre"], "fecha_cierre")
            debug_log("PATCH fecha_cierre parseada", {"original": data["fecha_cierre"], "normalizada": fc_dt.isoformat()})
            if fc_dt < now:
                return jsonify({"msg": "fecha_cierre no puede estar en el pasado"}), 400
            convocatoria.fecha_cierre = fc_dt
        except (ValueError, TypeError) as ve:
            debug_log("PATCH error parseando fecha_cierre", str(ve))
            return jsonify({"msg": str(ve)}), 400
    
    # Validar que cierre > apertura
    if convocatoria.fecha_apertura and convocatoria.fecha_cierre:
        if convocatoria.fecha_cierre <= convocatoria.fecha_apertura:
            return jsonify({"msg": "fecha_cierre debe ser posterior a fecha_apertura"}), 400
    
    recalcular_estado(convocatoria, now)
    
    db.session.commit()
    return jsonify(convocatoria.to_dict()), 200

@app.route("/api/convocatorias/activas", methods=["GET"])
def listar_activas():
    """Devuelve únicamente las convocatorias activas.
    Acepta ?lang=en para traducir estado a valores esperados por frontend (draft, scheduled, active, closed).
    """
    lang = request.args.get('lang')
    auto_archivar_convocatorias()
    now = datetime.utcnow()
    convocatorias = Convocatoria.query.filter_by(archivada=False).all()
    for c in convocatorias:
        recalcular_estado(c, now)
    db.session.commit()
    activas = [c for c in convocatorias if c.estado == EstadoConvocatoria.ACTIVE]
    data = [c.to_dict() for c in activas]

    if lang == 'en':
        estado_map = {
            'borrador': 'draft',
            'programada': 'scheduled',
            'activa': 'active',
            'cerrada': 'closed',
            'archivada': 'archived'
        }
        for item in data:
            item['estado'] = estado_map.get(item['estado'], item['estado'])

    return jsonify(data), 200

@app.route("/api/convocatorias", methods=["GET"])
def listar_convocatorias():
    """Lista todas las convocatorias.
    Acepta ?lang=en para traducir estado a valores usados en frontend.
    """
    lang = request.args.get('lang')
    estado_filtro = request.args.get('estado')
    archivadas_flag = request.args.get('archivadas')

    auto_archivar_convocatorias()

    query = Convocatoria.query
    if archivadas_flag in ("solo", "only", "true", "1", "yes"):
        query = query.filter_by(archivada=True)
    elif archivadas_flag in ("todas", "all"):
        query = query
    else:
        query = query.filter_by(archivada=False)

    now = datetime.utcnow()
    convocatorias = query.all()
    for c in convocatorias:
        recalcular_estado(c, now)
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
    if lang == 'en':
        estado_map = {
            'borrador': 'draft',
            'programada': 'scheduled',
            'activa': 'active',
            'cerrada': 'closed',
            'archivada': 'archived'
        }
        for item in data:
            item['estado'] = estado_map.get(item['estado'], item['estado'])
    return jsonify(data), 200

@app.route("/api/convocatorias/<int:id>", methods=["PATCH"])
@jwt_required()
def editar_convocatoria(id):
    """Editar campos de una convocatoria (curso, semestre, requisitos) si no está cerrada.
    No maneja fechas (para eso está /fechas)."""
    user_id = int(get_jwt_identity())
    user = Usuario.query.get_or_404(user_id)
    if not (user.is_coordinator() or user.is_professor()):
        return jsonify({"msg": "Solo coordinadores y profesores pueden editar"}), 403

    convocatoria = Convocatoria.query.get_or_404(id)
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

    # Recalcular estado por si fechas influyen (solo lectura) 
    now = datetime.utcnow()
    recalcular_estado(convocatoria, now)
    db.session.commit()
    return jsonify(convocatoria.to_dict()), 200


@app.route("/api/convocatorias/<int:id>/postulaciones", methods=["POST"])
@jwt_required()
def crear_postulacion(id):
    estudiante_id = int(get_jwt_identity())
    estudiante = Usuario.query.get_or_404(estudiante_id)

    if not estudiante.is_student():
        return jsonify({"msg": "Solo los estudiantes pueden postularse"}), 403

    convocatoria = Convocatoria.query.get_or_404(id)

    auto_archivar_convocatorias()
    if convocatoria.archivada or convocatoria.estado in (EstadoConvocatoria.CLOSED, EstadoConvocatoria.ARCHIVED):
        return jsonify({"msg": "La convocatoria no admite nuevas postulaciones"}), 400

    existente = Postulacion.query.filter_by(
        estudiante_id=estudiante.id,
        convocatoria_id=convocatoria.id
    ).filter(Postulacion.estado != EstadoPostulacion.ARCHIVED).first()
    if existente:
        return jsonify({"msg": "Ya existe una postulación para esta convocatoria", "postulacion": existente.to_dict()}), 409

    payload = request.get_json() or {}
    formulario = payload.get("formulario") or {}
    soportes = payload.get("soportes") or {}

    postulacion = Postulacion(estudiante_id=estudiante.id, convocatoria_id=convocatoria.id)
    postulacion.estudiante = estudiante
    postulacion.convocatoria = convocatoria
    postulacion.completar_formulario(formulario)
    postulacion.adjuntar_soportes(soportes)
    postulacion.esperar_validacion()

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
            evaluacion_model = EvaluacionAspirante(postulacion=postulacion)
            evaluacion_model.registrar_resultado(postulacion.puntaje or 0.0, postulacion.resultado or "pre-seleccionado", detalles)
            db.session.add(evaluacion_model)
        else:
            motivos = descartados[0]["razones"] if descartados else ["No supera filtros automáticos"]
            postulacion.marcar_ineligible("; ".join(motivos))

    db.session.add(postulacion)
    db.session.flush()

    for descarte in descartes_registrados:
        if descarte.get("postulacion_id") is None:
            descarte["postulacion_id"] = postulacion.id

    reporte = registrar_descartes(convocatoria, descartes_registrados)

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


@app.route("/api/convocatorias/<int:id>/postulaciones", methods=["GET"])
@jwt_required()
def listar_postulaciones(id):
    usuario_id = int(get_jwt_identity())
    usuario = Usuario.query.get_or_404(usuario_id)
    convocatoria = Convocatoria.query.get_or_404(id)

    vista = request.args.get("view")
    estado_param = request.args.get("estado")

    auto_archivar_convocatorias()

    if usuario.is_student():
        postulaciones = Postulacion.query.filter_by(convocatoria_id=id, estudiante_id=usuario.id).all()
    else:
        postulaciones = Postulacion.query.filter_by(convocatoria_id=id).all()

    if estado_param == "descartadas":
        postulaciones = [p for p in postulaciones if p.estado == EstadoPostulacion.INELIGIBLE]
    elif estado_param == "elegibles":
        postulaciones = [p for p in postulaciones if p.estado == EstadoPostulacion.ELIGIBLE]

    datos_postulaciones = [p.to_dict() for p in postulaciones]

    if vista == "ranking":
        ranking = [
            {
                "postulacion": p.to_dict(),
                "estudiante": p.estudiante.to_dict(),
                "puntaje": p.puntaje or 0.0,
                "resultado": p.resultado,
            }
            for p in postulaciones
            if p.estado == EstadoPostulacion.ELIGIBLE
        ]
        ranking.sort(key=lambda item: item["puntaje"], reverse=True)
        return jsonify({
            "convocatoria": convocatoria.to_dict(),
            "ranking": ranking,
        }), 200

    reporte_descartes = None
    if not usuario.is_student():
        periodo = request.args.get("periodo") or datetime.utcnow().strftime("%Y-%m")
        reporte_descartes = ReporteDescartes.query.filter_by(
            convocatoria_id=convocatoria.id,
            periodo=periodo
        ).first()

    respuesta = {
        "convocatoria": convocatoria.to_dict(),
        "postulaciones": datos_postulaciones,
    }
    if reporte_descartes:
        respuesta["reporte_descartes"] = reporte_descartes.to_dict()

    return jsonify(respuesta), 200


@app.route("/api/ia/config", methods=["GET"])
@jwt_required()
def obtener_config_ia():
    usuario_id = int(get_jwt_identity())
    usuario = Usuario.query.get_or_404(usuario_id)
    if not usuario.is_coordinator():
        return jsonify({"msg": "Solo el coordinador puede consultar la configuración"}), 403

    config = obtener_configuracion_ia()
    return jsonify(config.to_dict()), 200


@app.route("/api/ia/config", methods=["PUT"])
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
            setattr(config, campo, valor if "min" not in campo else int(valor) if campo == "min_semestre" else valor)

    db.session.commit()
    return jsonify(config.to_dict()), 200

# Ruta de prueba
@app.route("/api/test", methods=["GET"])
def test():
    return jsonify({"msg": "API funcionando correctamente", "status": "OK"})

if __name__ == "__main__":
    # Crear las tablas automáticamente al iniciar
    with app.app_context():
        db.create_all()
        ensure_schema_updates()
        
        # Verificar si ya existen usuarios, si no, crearlos
        if not Usuario.query.first():
            print("📝 Creando usuarios de prueba...")
            
            coordinador = Usuario(
                codigo="UCOORD-001",
                correo="coordinador@udem.edu.co",
                nombre="Coordinador Académico",
                rol="COORDINATOR",
                horario="Lun-Vie 08:00-17:00",
                horas_disponibles=10
            )
            coordinador.set_password("123456")
            
            profesor = Usuario(
                codigo="UPROF-001",
                correo="profesor@udem.edu.co",
                nombre="Dr. Pedro Martínez",
                rol="PROFESSOR",
                horario="Lun-Jue 08:00-12:00",
                horas_disponibles=8
            )
            profesor.set_password("123456")
            
            estudiante1 = Usuario(
                codigo="USTUD-001",
                correo="estudiante@udem.edu.co", 
                nombre="Juan Pérez",
                rol="STUDENT",
                semestre="5",
                promedio=4.3,
                horas_disponibles=12
            )
            estudiante1.set_password("123456")
            
            estudiante2 = Usuario(
                codigo="USTUD-002",
                correo="maria@udem.edu.co",
                nombre="María González", 
                rol="STUDENT",
                semestre="3",
                promedio=4.0,
                horas_disponibles=10
            )
            estudiante2.set_password("123456")
            
            estudiante3 = Usuario(
                codigo="USTUD-003",
                correo="carlos@udem.edu.co",
                nombre="Carlos Rodríguez",
                rol="STUDENT", 
                semestre="7",
                promedio=4.6,
                horas_disponibles=6
            )
            estudiante3.set_password("123456")
            
            db.session.add_all([coordinador, profesor, estudiante1, estudiante2, estudiante3])
            db.session.commit()
            print("✅ Usuarios creados exitosamente")
        else:
            print("✅ Usuarios ya existen en la base de datos")

        obtener_configuracion_ia()
    
    print("🚀 Iniciando servidor Flask...")
    print("📍 Backend disponible en: http://localhost:5001")
    print("🔗 API Base URL: http://localhost:5001/api")
    print("📖 Endpoints disponibles:")
    print("   POST /api/auth/login")
    print("   GET  /api/auth/profile")
    print("   PUT  /api/auth/profile")
    print("   POST /api/convocatorias")
    print("   GET  /api/convocatorias")
    print("   PATCH /api/convocatorias/<id>/fechas")
    print("   POST /api/convocatorias/<id>/postulaciones")
    print("   GET  /api/convocatorias/<id>/postulaciones")
    print("   GET  /api/convocatorias/activas")
    print("   GET  /api/ia/config")
    print("   PUT  /api/ia/config")
    print("   GET  /api/test")
    print()
    print("👥 Usuarios de prueba:")
    print("   📋 coordinador@udem.edu.co / 123456")
    print("   👨‍🏫 profesor@udem.edu.co / 123456")
    print("   🎓 estudiante@udem.edu.co / 123456")
    print("   🎓 maria@udem.edu.co / 123456")
    print("   🎓 carlos@udem.edu.co / 123456")
    print()
    print("⏹️  Presiona Ctrl+C para detener el servidor")
    print()
    
    app.run(host='0.0.0.0', port=5001, debug=True)