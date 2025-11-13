"""IA related helpers and scoring logic."""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..extensions import db
from ..models import ConfiguracionIA, Postulacion, ReporteDescartes, Usuario
from ..utils.time import utc_now_naive


class SeleccionIA:
    def __init__(self, configuracion: ConfiguracionIA):
        self.configuracion = configuracion

    def _obtener_semestre(self, usuario: Usuario) -> int | None:
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


def obtener_configuracion_ia() -> ConfiguracionIA:
    config = ConfiguracionIA.query.first()
    if not config:
        config = ConfiguracionIA()
        db.session.add(config)
        db.session.commit()
    return config


def obtener_servicio_ia() -> SeleccionIA:
    return SeleccionIA(obtener_configuracion_ia())


def registrar_descartes(convocatoria_id: int, descartados: List[Dict]) -> ReporteDescartes | None:
    if not descartados:
        return None
    periodo_actual = utc_now_naive().strftime("%Y-%m")
    reporte = ReporteDescartes.query.filter_by(
        convocatoria_id=convocatoria_id,
        periodo=periodo_actual,
    ).first()
    if not reporte:
        reporte = ReporteDescartes(convocatoria_id=convocatoria_id, periodo=periodo_actual)
        db.session.add(reporte)
    servicio = obtener_servicio_ia()
    reporte.generar(servicio.generar_reporte_descartados(descartados))
    return reporte


__all__ = [
    "SeleccionIA",
    "obtener_configuracion_ia",
    "obtener_servicio_ia",
    "registrar_descartes",
]
