from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models import User
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

bp = Blueprint("auth", __name__)

@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    correo = data.get("correo")
    password = data.get("password")
    if not correo or not password:
        return jsonify({"msg":"correo y password requeridos"}), 400
    user = User.query.filter_by(correo=correo).first()
    if not user or not user.check_password(password):
        return jsonify({"msg":"credenciales inválidas"}), 401
    token = create_access_token(identity=user.id)
    return jsonify({
        "access_token": token, 
        "rol": user.rol,
        "user": user.to_dict()
    })

@bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    """Obtener el perfil del usuario actual"""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())

@bp.route("/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    """Actualizar el perfil del usuario actual"""
    user_id = get_jwt_identity()
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
