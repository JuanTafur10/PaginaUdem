# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone, timedelta as _td
from zoneinfo import ZoneInfo
import enum
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

# Enums
class EstadoConvocatoria(enum.Enum):
    DRAFT = "borrador"
    SCHEDULED = "programada"
    ACTIVE = "activa"
    CLOSED = "cerrada"

class TipoUsuario(enum.Enum):
    COORDINADOR = "COORDINATOR"
    PROFESOR = "PROFESSOR"
    ESTUDIANTE = "STUDENT"

# Modelos básicos
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    correo = db.Column(db.String(120), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255))
    rol = db.Column(db.String(50), default="STUDENT")
    semestre = db.Column(db.String(10))
    tipo_usuario = db.Column(db.Enum(TipoUsuario), default=TipoUsuario.ESTUDIANTE)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_coordinator(self):
        return self.rol == "COORDINATOR"
    
    def is_student(self):
        return self.rol == "STUDENT"
    
    def is_professor(self):
        return self.rol == "PROFESSOR"

    def to_dict(self):
        return {
            "id": self.id,
            "correo": self.correo,
            "nombre": self.nombre,
            "rol": self.rol,
            "semestre": self.semestre,
            "created_at": self.created_at.isoformat()
        }

class Convocatoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    curso = db.Column(db.String(200), nullable=False)
    semestre = db.Column(db.String(20), nullable=False)
    requisitos = db.Column(db.Text, nullable=False)
    fecha_apertura = db.Column(db.DateTime)
    fecha_cierre = db.Column(db.DateTime)
    estado = db.Column(db.Enum(EstadoConvocatoria), default=EstadoConvocatoria.DRAFT)
    creado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
        }

def recalcular_estado(convocatoria: "Convocatoria", now: datetime):
    """Recalcula el estado según fechas y momento actual (now en UTC)."""
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

# Rutas de autenticación
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    correo = data.get("correo")
    password = data.get("password")
    
    if not correo or not password:
        return jsonify({"msg": "correo y password requeridos"}), 400
    
    user = User.query.filter_by(correo=correo).first()
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
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())

@app.route("/api/auth/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
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
    user = User.query.get_or_404(user_id)
    
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
    user = User.query.get_or_404(user_id)
    
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
    # Procesar estados antes de mostrar
    now = datetime.utcnow()
    convocatorias = Convocatoria.query.all()
    for c in convocatorias:
        recalcular_estado(c, now)
    db.session.commit()
    activas = Convocatoria.query.filter_by(estado=EstadoConvocatoria.ACTIVE).all()
    data = [c.to_dict() for c in activas]

    if lang == 'en':
        estado_map = {
            'borrador': 'draft',
            'programada': 'scheduled',
            'activa': 'active',
            'cerrada': 'closed'
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
    now = datetime.utcnow()
    convocatorias = Convocatoria.query.all()
    for c in convocatorias:
        recalcular_estado(c, now)
    db.session.commit()
    data = [c.to_dict() for c in convocatorias]
    if lang == 'en':
        estado_map = {
            'borrador': 'draft',
            'programada': 'scheduled',
            'activa': 'active',
            'cerrada': 'closed'
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
    user = User.query.get_or_404(user_id)
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

# Ruta de prueba
@app.route("/api/test", methods=["GET"])
def test():
    return jsonify({"msg": "API funcionando correctamente", "status": "OK"})

if __name__ == "__main__":
    # Crear las tablas automáticamente al iniciar
    with app.app_context():
        db.create_all()
        
        # Verificar si ya existen usuarios, si no, crearlos
        if not User.query.first():
            print("📝 Creando usuarios de prueba...")
            
            coordinador = User(
                correo="coordinador@udem.edu.co",
                nombre="Coordinador Académico",
                rol="COORDINATOR"
            )
            coordinador.set_password("123456")
            
            profesor = User(
                correo="profesor@udem.edu.co",
                nombre="Dr. Pedro Martínez",
                rol="PROFESSOR"
            )
            profesor.set_password("123456")
            
            estudiante1 = User(
                correo="estudiante@udem.edu.co", 
                nombre="Juan Pérez",
                rol="STUDENT",
                semestre="5"
            )
            estudiante1.set_password("123456")
            
            estudiante2 = User(
                correo="maria@udem.edu.co",
                nombre="María González", 
                rol="STUDENT",
                semestre="3"
            )
            estudiante2.set_password("123456")
            
            estudiante3 = User(
                correo="carlos@udem.edu.co",
                nombre="Carlos Rodríguez",
                rol="STUDENT", 
                semestre="7"
            )
            estudiante3.set_password("123456")
            
            db.session.add_all([coordinador, profesor, estudiante1, estudiante2, estudiante3])
            db.session.commit()
            print("✅ Usuarios creados exitosamente")
        else:
            print("✅ Usuarios ya existen en la base de datos")
    
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
    print("   GET  /api/convocatorias/activas")
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