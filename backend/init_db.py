import sys
import os

# Agregar el directorio actual al path de Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash

# Configuración directa
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dev.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modelos simplificados para la inicialización
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    correo = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(50), nullable=False)
    semestre = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

def init_db():
    """Inicializar la base de datos con datos de prueba"""
    with app.app_context():
        # Crear todas las tablas
        db.create_all()
        
        # Verificar si ya existen usuarios
        if User.query.first():
            print("La base de datos ya está inicializada")
            return
        
        # Crear usuarios de ejemplo
        coordinador = User(
            correo="coordinador@udem.edu.co",
            nombre="Coordinador Académico",
            rol="COORDINATOR"
        )
        coordinador.set_password("123456")
        
        estudiante1 = User(
            correo="estudiante@udem.edu.co", 
            nombre="Juan Pérez",
            rol="STUDENT",
            semestre="5"
        )
        estudiante1.set_password("123456")
        
        estudiante2 = User(
            correo="maria@udem.edu.co", 
            nombre="María García",
            rol="STUDENT",
            semestre="3"
        )
        estudiante2.set_password("123456")
        
        estudiante3 = User(
            correo="carlos@udem.edu.co", 
            nombre="Carlos Rodríguez",
            rol="STUDENT",
            semestre="8"
        )
        estudiante3.set_password("123456")
        
        # Guardar en la base de datos
        db.session.add(coordinador)
        db.session.add(estudiante1)
        db.session.add(estudiante2)
        db.session.add(estudiante3)
        db.session.commit()
        
        print("✅ Base de datos inicializada correctamente")
        print("👥 Usuarios creados:")
        print("   📋 Coordinador: coordinador@udem.edu.co / 123456")
        print("   🎓 Estudiante 1: estudiante@udem.edu.co / 123456 (5to semestre)")
        print("   🎓 Estudiante 2: maria@udem.edu.co / 123456 (3er semestre)")
        print("   🎓 Estudiante 3: carlos@udem.edu.co / 123456 (8vo semestre)")
        print("")
        print("🗄️  Base de datos: dev.db")

if __name__ == "__main__":
    init_db()