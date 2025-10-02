# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import enum

# Crear aplicación Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret'
app.config['JWT_SECRET_KEY'] = 'jwt-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dev.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    
    # Si se proporcionan fechas, validarlas
    if data.get("fecha_apertura"):
        try:
            from dateutil.parser import isoparse
            convocatoria.fecha_apertura = isoparse(data["fecha_apertura"])
        except:
            return jsonify({"msg": "Formato de fecha_apertura inválido"}), 400
    
    if data.get("fecha_cierre"):
        try:
            from dateutil.parser import isoparse
            convocatoria.fecha_cierre = isoparse(data["fecha_cierre"])
        except:
            return jsonify({"msg": "Formato de fecha_cierre inválido"}), 400
    
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
            from dateutil.parser import isoparse
            fa_dt = isoparse(data["fecha_apertura"])
            if fa_dt < now:
                return jsonify({"msg": "fecha_apertura no puede estar en el pasado"}), 400
            convocatoria.fecha_apertura = fa_dt
        except:
            return jsonify({"msg": "Formato de fecha_apertura inválido"}), 400
    
    if data.get("fecha_cierre"):
        try:
            from dateutil.parser import isoparse
            fc_dt = isoparse(data["fecha_cierre"])
            if fc_dt < now:
                return jsonify({"msg": "fecha_cierre no puede estar en el pasado"}), 400
            convocatoria.fecha_cierre = fc_dt
        except:
            return jsonify({"msg": "Formato de fecha_cierre inválido"}), 400
    
    # Validar que cierre > apertura
    if convocatoria.fecha_apertura and convocatoria.fecha_cierre:
        if convocatoria.fecha_cierre <= convocatoria.fecha_apertura:
            return jsonify({"msg": "fecha_cierre debe ser posterior a fecha_apertura"}), 400
    
    # Actualizar estado según fechas
    if convocatoria.fecha_apertura and convocatoria.fecha_apertura > now:
        convocatoria.estado = EstadoConvocatoria.SCHEDULED
    elif convocatoria.fecha_apertura and convocatoria.fecha_apertura <= now and (not convocatoria.fecha_cierre or convocatoria.fecha_cierre > now):
        convocatoria.estado = EstadoConvocatoria.ACTIVE
    
    db.session.commit()
    return jsonify(convocatoria.to_dict()), 200

@app.route("/api/convocatorias/activas", methods=["GET"])
def listar_activas():
    # Procesar estados antes de mostrar
    now = datetime.utcnow()
    convocatorias = Convocatoria.query.all()
    
    # Actualizar estados según fechas
    for c in convocatorias:
        if c.fecha_apertura and c.fecha_apertura <= now and (not c.fecha_cierre or c.fecha_cierre > now):
            c.estado = EstadoConvocatoria.ACTIVE
        elif c.fecha_cierre and c.fecha_cierre <= now:
            c.estado = EstadoConvocatoria.CLOSED
    
    db.session.commit()
    
    # Devolver solo activas
    activas = Convocatoria.query.filter_by(estado=EstadoConvocatoria.ACTIVE).all()
    return jsonify([c.to_dict() for c in activas]), 200

@app.route("/api/convocatorias", methods=["GET"])
def listar_convocatorias():
    # Endpoint público para HU-01 verificación - mostrar todas las convocatorias
    convocatorias = Convocatoria.query.all()
    return jsonify([c.to_dict() for c in convocatorias]), 200

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