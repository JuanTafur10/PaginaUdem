"""Pruebas de escritorio automatizadas para los flujos principales."""
import base64
from datetime import datetime, timedelta, UTC
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models import Convocatoria, Notificacion, Postulacion
from backend.app.services.bootstrap import ensure_schema_updates, seed_default_data


def _print(title: str, payload):
    print(f"\n=== {title} ===")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload)


def login(client, correo: str, password: str):
    response = client.post(
        "/api/auth/login",
        json={"correo": correo, "password": password},
    )
    assert response.status_code == 200, f"Fallo inicio de sesión para {correo}: {response.get_data(as_text=True)}"
    data = response.get_json()
    assert "access_token" in data, "No se recibió token"
    return data


def crear_convocatoria(client, token: str, curso: str):
    ahora = datetime.now(UTC)
    payload = {
        "curso": curso,
        "semestre": "2026-1",
        "requisitos": "Semestre mínimo 4, promedio mínimo 3.5",
        "fecha_apertura": (ahora + timedelta(days=1)).isoformat(),
        "fecha_cierre": (ahora + timedelta(days=10)).isoformat(),
    }
    response = client.post(
        "/api/convocatorias",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 201, f"Creación convocatoria falló: {response.get_data(as_text=True)}"
    data = response.get_json()
    assert data.get("curso") == curso
    return data


def postularse(client, token: str, convocatoria_id: int):
    cv_base64 = base64.b64encode(b"CV de prueba").decode()
    payload = {
        "formulario": {"comentario": "Postulación de prueba"},
        "soportes": {"cvNombre": "cv.pdf", "cvBase64": cv_base64},
    }
    response = client.post(
        f"/api/convocatorias/{convocatoria_id}/postulaciones",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code in (201, 202), (
        f"Postulación falló ({response.status_code}): {response.get_data(as_text=True)}"
    )
    return response.get_json()


def obtener_postulaciones(client, token: str, convocatoria_id: int, params: dict | None = None):
    params = params or {}
    response = client.get(
        f"/api/convocatorias/{convocatoria_id}/postulaciones",
        headers={"Authorization": f"Bearer {token}"},
        query_string=params,
    )
    assert response.status_code == 200, (
        f"Listar postulaciones falló ({response.status_code}): {response.get_data(as_text=True)}"
    )
    return response.get_json()


def obtener_notificaciones(client, token: str, params: dict | None = None):
    params = params or {}
    response = client.get(
        "/api/notificaciones",
        headers={"Authorization": f"Bearer {token}"},
        query_string=params,
    )
    assert response.status_code == 200, (
        f"Listado de notificaciones falló ({response.status_code}): {response.get_data(as_text=True)}"
    )
    return response.get_json()


def main():
    curso = f"Convocatoria QA {datetime.now(UTC).isoformat()}"
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        ensure_schema_updates()
        seed_default_data()
        client = app.test_client()

        # 1. Login de coordinador
        login_coord = login(client, "coordinador@udem.edu.co", "123456")
        _print("Login coordinador", login_coord)

        # 2. Crear convocatoria
        convocatoria = crear_convocatoria(client, login_coord["access_token"], curso)
        convocatoria_id = convocatoria["id"]
        _print("Convocatoria creada", convocatoria)

        # 3. Login estudiante
        login_student = login(client, "estudiante@udem.edu.co", "123456")
        _print("Login estudiante", login_student)

        # 4. Listar convocatorias para estudiante y verificar que aparezca
        response_conv = client.get(
            "/api/convocatorias",
            headers={"Authorization": f"Bearer {login_student['access_token']}"},
            query_string={"lang": "en"},
        )
        assert response_conv.status_code == 200, "Listado de convocatorias falló"
        data_conv = response_conv.get_json()
        assert any(item["id"] == convocatoria_id for item in data_conv), "Convocatoria no está visible"
        _print("Convocatorias disponibles", data_conv)

        # 5. Postularse
        postulacion = postularse(client, login_student["access_token"], convocatoria_id)
        _print("Resultado postulación", postulacion)

        # 5.1 Verificar notificaciones para el estudiante
        notificaciones = obtener_notificaciones(client, login_student["access_token"])
        assert notificaciones, "El estudiante debería recibir al menos una notificación"
        _print("Notificaciones estudiante", notificaciones)

        # 6. Obtener postulaciones como coordinador
        listado_coord = obtener_postulaciones(client, login_coord["access_token"], convocatoria_id)
        _print("Listado postulaciones coordinador", listado_coord)

        ranking_coord = obtener_postulaciones(
            client,
            login_coord["access_token"],
            convocatoria_id,
            params={"view": "ranking"},
        )
        _print("Ranking IA", ranking_coord)

        # 7. Registrar preasignación manual por el coordinador
        pre_payload = {
            "convocatoria_id": convocatoria_id,
            "estudiante_id": login_student["user"]["id"],
            "estado": "selected",
            "comentario": "Asignación manual de prueba",
            "puntaje": 4.8,
        }
        resp_pre = client.post(
            "/api/postulaciones/preasignadas",
            headers={"Authorization": f"Bearer {login_coord['access_token']}"},
            json=pre_payload,
        )
        assert resp_pre.status_code == 201, f"Registro de preasignación falló: {resp_pre.get_data(as_text=True)}"
        preasignada = resp_pre.get_json()
        assert preasignada.get("preasignada") is True
        _print("Preasignación creada", preasignada)

        # 7.1 Actualizar estado de la preasignación
        resp_update = client.patch(
            f"/api/postulaciones/preasignadas/{preasignada['id']}",
            headers={"Authorization": f"Bearer {login_coord['access_token']}"},
            json={"estado": "not_selected", "comentario": "Prueba finalizada"},
        )
        assert resp_update.status_code == 200, f"Actualización preasignada falló: {resp_update.get_data(as_text=True)}"
        _print("Preasignación actualizada", resp_update.get_json())

        # 7.2 Verificar notificaciones adicionales
        notificaciones_post = obtener_notificaciones(client, login_student["access_token"])
        assert len(notificaciones_post) >= len(notificaciones), "El estudiante debería recibir notificaciones de la preasignación"
        _print("Notificaciones actualizadas", notificaciones_post)

        # Limpieza: eliminar postulaciones y convocatoria generadas para no dejar datos "basura".
        Postulacion.query.filter_by(convocatoria_id=convocatoria_id).delete()
        Convocatoria.query.filter_by(id=convocatoria_id).delete()
        Notificacion.query.delete()
        db.session.commit()
        print("\nDatos de prueba eliminados correctamente")


if __name__ == "__main__":
    main()
