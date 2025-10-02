from flask import Flask
from flask_cors import CORS
from .config import Config
from .extensions import db, migrate, jwt
from .routes.convocatorias import bp as convocatorias_bp
from .routes.auth import bp as auth_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Configurar CORS para permitir conexión con frontend
    CORS(app, origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8080", "file://"])
    
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # blueprints
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(convocatorias_bp, url_prefix="/api/convocatorias")

    return app
