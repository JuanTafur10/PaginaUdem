"""Pruebas unitarias que validan las 16 historias de usuario del sistema."""
from __future__ import annotations

import base64
import unittest
from datetime import UTC, datetime, timedelta

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models import Convocatoria, EstadoConvocatoria, EstadoPostulacion, Postulacion
from backend.app.utils.time import utc_now_naive


class HistoriasUsuarioTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app("testing")
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        self.coordinator_token = self._login("coordinador@udem.edu.co")
        self.student_token = self._login("estudiante@udem.edu.co")
        self.student_maria_token = self._login("maria@udem.edu.co")
        self.student_carlos_token = self._login("carlos@udem.edu.co")

    def tearDown(self) -> None:
        db.session.remove()
        self.app_context.pop()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _login(self, correo: str, password: str = "123456") -> str:
        response = self.client.post(
            "/api/auth/login",
            json={"correo": correo, "password": password},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("access_token", data)
        return data["access_token"]

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _crear_convocatoria(self, curso: str) -> dict:
        response = self.client.post(
            "/api/convocatorias",
            headers=self._auth_headers(self.coordinator_token),
            json={
                "curso": curso,
                "semestre": "2025-1",
                "requisitos": "Semestre mínimo 4, promedio mínimo 3.5",
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    # ------------------------------------------------------------------
    # Tests principales (16 HU)
    # ------------------------------------------------------------------
    def test_historias_de_usuario(self) -> None:
        # HU-01: Crear Convocatoria (validaciones de campos obligatorios)
        invalid_response = self.client.post(
            "/api/convocatorias",
            headers=self._auth_headers(self.coordinator_token),
            json={"curso": "Faltan datos"},
        )
        self.assertEqual(invalid_response.status_code, 400)

        curso_principal = f"Convocatoria Principal {datetime.now(UTC).timestamp()}"
        convocatoria = self._crear_convocatoria(curso_principal)
        convocatoria_id = convocatoria["id"]

        # HU-02: Asignar fechas y validar rangos
        future_open = datetime.now(UTC) + timedelta(days=3)
        future_close = datetime.now(UTC) + timedelta(days=2)
        response_invalid_dates = self.client.patch(
            f"/api/convocatorias/{convocatoria_id}/fechas",
            headers=self._auth_headers(self.coordinator_token),
            json={
                "fecha_apertura": future_open.isoformat(),
                "fecha_cierre": future_close.isoformat(),
            },
        )
        self.assertEqual(response_invalid_dates.status_code, 400)

        valid_open = datetime.now(UTC) + timedelta(days=1)
        valid_close = datetime.now(UTC) + timedelta(days=5)
        response_valid_dates = self.client.patch(
            f"/api/convocatorias/{convocatoria_id}/fechas",
            headers=self._auth_headers(self.coordinator_token),
            json={
                "fecha_apertura": valid_open.isoformat(),
                "fecha_cierre": valid_close.isoformat(),
            },
        )
        self.assertEqual(response_valid_dates.status_code, 200)

        # Dejar la convocatoria activa para las siguientes pruebas
        convocatoria_db = db.session.get(Convocatoria, convocatoria_id)
        self.assertIsNotNone(convocatoria_db)
        convocatoria_db.fecha_apertura = utc_now_naive() - timedelta(hours=1)
        convocatoria_db.fecha_cierre = utc_now_naive() + timedelta(days=1)
        convocatoria_db.estado = EstadoConvocatoria.ACTIVE
        db.session.commit()

        # HU-03: Mostrar convocatorias activas
        response_list_active = self.client.get(
            "/api/convocatorias",
            headers=self._auth_headers(self.student_token),
            query_string={"estado": "active"},
        )
        self.assertEqual(response_list_active.status_code, 200)
        convocatorias_activas = response_list_active.get_json()
        self.assertTrue(any(c["id"] == convocatoria_id for c in convocatorias_activas))

        response_public_activas = self.client.get("/api/convocatorias/activas")
        self.assertEqual(response_public_activas.status_code, 200)
        listado_publico = response_public_activas.get_json()
        self.assertTrue(any(c["id"] == convocatoria_id for c in listado_publico))

        # HU-05: Editar convocatoria publicada
        response_edit = self.client.patch(
            f"/api/convocatorias/{convocatoria_id}",
            headers=self._auth_headers(self.coordinator_token),
            json={"requisitos": "Semestre mínimo 4 y promedio mínimo 3.5 (actualizado)"},
        )
        self.assertEqual(response_edit.status_code, 200)
        self.assertIn("actualizado", response_edit.get_json()["requisitos"])

        # HU-04: Archivar convocatorias vencidas (convocatoria independiente)
        curso_archivo = f"Convocatoria Archivo {datetime.now(UTC).timestamp()}"
        convocatoria_archivo = self._crear_convocatoria(curso_archivo)
        convocatoria_archivo_id = convocatoria_archivo["id"]
        convoc_arch_db = db.session.get(Convocatoria, convocatoria_archivo_id)
        convoc_arch_db.fecha_apertura = utc_now_naive() - timedelta(days=10)
        convoc_arch_db.fecha_cierre = utc_now_naive() - timedelta(days=1)
        convoc_arch_db.estado = EstadoConvocatoria.CLOSED
        db.session.commit()
        self.client.get(
            "/api/convocatorias",
            headers=self._auth_headers(self.coordinator_token),
        )
        convoc_arch_db = db.session.get(Convocatoria, convocatoria_archivo_id)
        self.assertTrue(convoc_arch_db.archivada)

        # HU-06: Registrar postulación
        curso_cerrado = f"Convocatoria Cerrada {datetime.now(UTC).timestamp()}"
        conv_cerrada = self._crear_convocatoria(curso_cerrado)
        conv_cerrada_id = conv_cerrada["id"]
        conv_cerrada_db = db.session.get(Convocatoria, conv_cerrada_id)
        conv_cerrada_db.estado = EstadoConvocatoria.CLOSED
        conv_cerrada_db.fecha_cierre = utc_now_naive() - timedelta(days=1)
        db.session.commit()

        respuesta_conv_cerrada = self.client.post(
            f"/api/convocatorias/{conv_cerrada_id}/postulaciones",
            headers=self._auth_headers(self.student_token),
            json={},
        )
        self.assertEqual(respuesta_conv_cerrada.status_code, 400)

        # HU-07: Adjuntar hoja de vida (validaciones)
        cv_base64 = base64.b64encode(b"PDF").decode()
        invalid_extension = self.client.post(
            f"/api/convocatorias/{convocatoria_id}/postulaciones",
            headers=self._auth_headers(self.student_token),
            json={
                "formulario": {"comentario": "Intento con extensión inválida"},
                "soportes": {"cvNombre": "cv.txt", "cvBase64": cv_base64},
            },
        )
        self.assertEqual(invalid_extension.status_code, 400)

        largo_bytes = base64.b64encode(b"a" * (5 * 1024 * 1024 + 10)).decode()
        archivo_pesado = self.client.post(
            f"/api/convocatorias/{convocatoria_id}/postulaciones",
            headers=self._auth_headers(self.student_token),
            json={
                "formulario": {"comentario": "Archivo muy grande"},
                "soportes": {"cvNombre": "cv.pdf", "cvBase64": largo_bytes},
            },
        )
        self.assertEqual(archivo_pesado.status_code, 400)

        # HU-08: Validar requisitos mínimos (postulación ineligible)
        respuesta_ineligible = self.client.post(
            f"/api/convocatorias/{convocatoria_id}/postulaciones",
            headers=self._auth_headers(self.student_maria_token),
            json={
                "formulario": {"comentario": "Quiero participar"},
                "soportes": {"cvNombre": "cv.pdf", "cvBase64": cv_base64},
            },
        )
        self.assertEqual(respuesta_ineligible.status_code, 202)
        data_ineligible = respuesta_ineligible.get_json()
        self.assertEqual(data_ineligible["postulacion"]["estado"], "ineligible")
        self.assertTrue(data_ineligible.get("descartados"))

        # HU-09: Confirmación de registro (postulación válida)
        respuesta_valida = self.client.post(
            f"/api/convocatorias/{convocatoria_id}/postulaciones",
            headers=self._auth_headers(self.student_token),
            json={
                "formulario": {"comentario": "Preparado para apoyar el curso"},
                "soportes": {"cvNombre": "cv.pdf", "cvBase64": cv_base64},
            },
        )
        self.assertEqual(respuesta_valida.status_code, 201)
        data_valida = respuesta_valida.get_json()
        self.assertEqual(data_valida["postulacion"]["estado"], "eligible")
        postulacion_id = data_valida["postulacion"]["id"]

        # HU-06 (duplicados)
        respuesta_duplicada = self.client.post(
            f"/api/convocatorias/{convocatoria_id}/postulaciones",
            headers=self._auth_headers(self.student_token),
            json={},
        )
        self.assertEqual(respuesta_duplicada.status_code, 409)

        # Segundo estudiante elegible para ranking
        respuesta_carlos = self.client.post(
            f"/api/convocatorias/{convocatoria_id}/postulaciones",
            headers=self._auth_headers(self.student_carlos_token),
            json={
                "formulario": {"comentario": "Experiencia previa"},
                "soportes": {"cvNombre": "cv.pdf", "cvBase64": cv_base64},
            },
        )
        self.assertEqual(respuesta_carlos.status_code, 201)
        postulacion_carlos_id = respuesta_carlos.get_json()["postulacion"]["id"]

        # HU-09: verificar notificaciones de confirmación
        notificaciones_estudiante = self.client.get(
            "/api/notificaciones",
            headers=self._auth_headers(self.student_token),
        ).get_json()
        self.assertTrue(any(n["tipo"] == "success" for n in notificaciones_estudiante))

        notificaciones_maria = self.client.get(
            "/api/notificaciones",
            headers=self._auth_headers(self.student_maria_token),
        ).get_json()
        self.assertTrue(any(n["tipo"] == "warning" for n in notificaciones_maria))

        # HU-10: Consultar estado de postulación
        estados_estudiante = self.client.get(
            f"/api/convocatorias/{convocatoria_id}/postulaciones",
            headers=self._auth_headers(self.student_token),
        ).get_json()["postulaciones"]
        self.assertTrue(any(p["estado"] == "eligible" for p in estados_estudiante))

        estados_maria = self.client.get(
            f"/api/convocatorias/{convocatoria_id}/postulaciones",
            headers=self._auth_headers(self.student_maria_token),
        ).get_json()["postulaciones"]
        self.assertTrue(any(p["estado"] == "ineligible" for p in estados_maria))

        # HU-11, HU-12 y HU-13: Filtrar, clasificar y consultar ranking IA
        ranking_response = self.client.get(
            f"/api/convocatorias/{convocatoria_id}/postulaciones",
            headers=self._auth_headers(self.coordinator_token),
            query_string={"view": "ranking"},
        )
        self.assertEqual(ranking_response.status_code, 200)
        ranking = ranking_response.get_json()["ranking"]
        self.assertGreaterEqual(len(ranking), 2)
        estados_ranking = {item["postulacion"]["estado"] for item in ranking}
        self.assertNotIn("ineligible", estados_ranking)
        puntajes = [item["puntaje"] for item in ranking]
        self.assertEqual(puntajes, sorted(puntajes, reverse=True))

        # HU-14: Ajustar parámetros de IA
        config_response = self.client.put(
            "/api/ia/config",
            headers=self._auth_headers(self.coordinator_token),
            json={"min_semestre": 3, "peso_horas": 0.3},
        )
        self.assertEqual(config_response.status_code, 200)
        config_data = config_response.get_json()
        self.assertEqual(config_data["min_semestre"], 3)
        self.assertAlmostEqual(config_data["peso_horas"], 0.3)

        # HU-18: Notificar estudiante seleccionado
        decision_selected = self.client.patch(
            f"/api/convocatorias/{convocatoria_id}/postulaciones/{postulacion_id}/decision",
            headers=self._auth_headers(self.coordinator_token),
            json={"decision": "selected", "comentario": "Bienvenido al equipo"},
        )
        self.assertEqual(decision_selected.status_code, 200)
        data_selected = decision_selected.get_json()["postulacion"]
        self.assertEqual(data_selected["estado"], "selected")

        # HU-19: Notificar estudiantes no seleccionados
        decision_not_selected = self.client.patch(
            f"/api/convocatorias/{convocatoria_id}/postulaciones/{postulacion_carlos_id}/decision",
            headers=self._auth_headers(self.coordinator_token),
            json={"decision": "not_selected", "comentario": "Se priorizó otro perfil"},
        )
        self.assertEqual(decision_not_selected.status_code, 200)
        data_not_selected = decision_not_selected.get_json()["postulacion"]
        self.assertEqual(data_not_selected["estado"], "not_selected")

        # Verificar estados finales en base de datos
        postulacion_seleccionada = db.session.get(Postulacion, postulacion_id)
        postulacion_no_seleccionada = db.session.get(Postulacion, postulacion_carlos_id)
        self.assertEqual(postulacion_seleccionada.estado, EstadoPostulacion.SELECTED)
        self.assertEqual(postulacion_no_seleccionada.estado, EstadoPostulacion.NOT_SELECTED)

        # Confirmar que se registraron notificaciones por las decisiones
        notificaciones_finales_estudiante = self.client.get(
            "/api/notificaciones",
            headers=self._auth_headers(self.student_token),
        ).get_json()
        self.assertTrue(
            any(n.get("metadata", {}).get("decision") == "selected" for n in notificaciones_finales_estudiante)
        )

        notificaciones_finales_carlos = self.client.get(
            "/api/notificaciones",
            headers=self._auth_headers(self.student_carlos_token),
        ).get_json()
        self.assertTrue(
            any(n.get("metadata", {}).get("decision") == "not_selected" for n in notificaciones_finales_carlos)
        )


if __name__ == "__main__":  # pragma: no cover - ejecución manual
    unittest.main()
