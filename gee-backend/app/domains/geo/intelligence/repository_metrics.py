from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.domains.geo.intelligence.models import (
    AlertaGeo,
    IndiceHidrico,
    PuntoConflicto,
    ZonaOperativa,
)


class IntelligenceRepositoryMetricsMixin:
    def _empty_dict_from_matview(self, db: Session, sql: str) -> dict[str, Any]:
        row = db.execute(text(sql)).mappings().first()
        return dict(row) if row is not None else {}

    def get_indices_hidricos(
        self,
        db: Session,
        *,
        zona_id: Optional[uuid.UUID] = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[IndiceHidrico], int]:
        base = select(IndiceHidrico)
        if zona_id:
            base = base.where(IndiceHidrico.zona_id == zona_id)
        return self._paginated_results(
            db,
            base,
            page=page,
            limit=limit,
            order_by=IndiceHidrico.fecha_calculo.desc(),
        )

    def create_indice_hidrico(
        self,
        db: Session,
        *,
        zona_id: uuid.UUID,
        fecha_calculo: date,
        pendiente_media: float,
        acumulacion_media: float,
        twi_medio: float,
        proximidad_canal_m: float,
        historial_inundacion: float,
        indice_final: float,
        nivel_riesgo: str,
    ) -> IndiceHidrico:
        ih = IndiceHidrico(
            zona_id=zona_id,
            fecha_calculo=fecha_calculo,
            pendiente_media=pendiente_media,
            acumulacion_media=acumulacion_media,
            twi_medio=twi_medio,
            proximidad_canal_m=proximidad_canal_m,
            historial_inundacion=historial_inundacion,
            indice_final=indice_final,
            nivel_riesgo=nivel_riesgo,
        )
        db.add(ih)
        db.flush()
        return ih

    def get_conflictos(
        self,
        db: Session,
        *,
        tipo_filter: Optional[str] = None,
        severidad_filter: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[PuntoConflicto], int]:
        base = select(PuntoConflicto)
        if tipo_filter:
            base = base.where(PuntoConflicto.tipo == tipo_filter)
        if severidad_filter:
            base = base.where(PuntoConflicto.severidad == severidad_filter)
        return self._paginated_results(
            db, base, page=page, limit=limit, order_by=PuntoConflicto.created_at.desc()
        )

    def get_conflictos_por_zona(
        self, db: Session, zona_id: uuid.UUID
    ) -> list[PuntoConflicto]:
        zona = self.get_zona_by_id(db, zona_id)
        if zona is None:
            return []
        return list(
            db.execute(
                select(PuntoConflicto).where(
                    func.ST_Within(PuntoConflicto.geometria, zona.geometria)
                )
            )
            .scalars()
            .all()
        )

    def create_conflicto(
        self,
        db: Session,
        *,
        tipo: str,
        geometria: str,
        descripcion: str,
        severidad: str,
        infraestructura_ids: Optional[list[str]] = None,
        acumulacion_valor: float = 0.0,
        pendiente_valor: float = 0.0,
    ) -> PuntoConflicto:
        conflicto = PuntoConflicto(
            tipo=tipo,
            geometria=geometria,
            descripcion=descripcion,
            severidad=severidad,
            infraestructura_ids=infraestructura_ids,
            acumulacion_valor=acumulacion_valor,
            pendiente_valor=pendiente_valor,
        )
        db.add(conflicto)
        db.flush()
        return conflicto

    def bulk_create_conflictos(
        self, db: Session, conflictos: list[dict[str, Any]]
    ) -> int:
        objects = [PuntoConflicto(**c) for c in conflictos]
        db.add_all(objects)
        db.flush()
        return len(objects)

    def get_alertas_activas(self, db: Session, *, limit: int = 100) -> list[AlertaGeo]:
        stmt = (
            select(AlertaGeo)
            .where(AlertaGeo.activa.is_(True))
            .order_by(AlertaGeo.created_at.desc())
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    def create_alerta(
        self,
        db: Session,
        *,
        tipo: str,
        mensaje: str,
        nivel: str,
        zona_id: Optional[uuid.UUID] = None,
        datos: Optional[dict] = None,
    ) -> AlertaGeo:
        alerta = AlertaGeo(
            tipo=tipo, mensaje=mensaje, nivel=nivel, zona_id=zona_id, datos=datos
        )
        db.add(alerta)
        db.flush()
        return alerta

    def deactivate_alerta(
        self, db: Session, alerta_id: uuid.UUID
    ) -> Optional[AlertaGeo]:
        alerta = db.execute(
            select(AlertaGeo).where(AlertaGeo.id == alerta_id)
        ).scalar_one_or_none()
        if alerta:
            alerta.activa = False
            db.flush()
        return alerta

    def get_dashboard_inteligente(self, db: Session) -> dict[str, Any]:
        zonas_total = db.execute(
            select(func.count()).select_from(ZonaOperativa)
        ).scalar_one()
        latest_hci = (
            select(
                IndiceHidrico.zona_id,
                func.max(IndiceHidrico.fecha_calculo).label("max_fecha"),
            )
            .group_by(IndiceHidrico.zona_id)
            .subquery()
        )
        zonas_por_nivel = {"bajo": 0, "medio": 0, "alto": 0, "critico": 0}
        for nivel, count in db.execute(
            select(IndiceHidrico.nivel_riesgo, func.count())
            .join(
                latest_hci,
                (IndiceHidrico.zona_id == latest_hci.c.zona_id)
                & (IndiceHidrico.fecha_calculo == latest_hci.c.max_fecha),
            )
            .group_by(IndiceHidrico.nivel_riesgo)
        ).all():
            if nivel in zonas_por_nivel:
                zonas_por_nivel[nivel] = count
        at_risk_count = (
            zonas_por_nivel.get("medio", 0)
            + zonas_por_nivel.get("alto", 0)
            + zonas_por_nivel.get("critico", 0)
        )
        conflictos = db.execute(
            select(func.count()).select_from(PuntoConflicto)
        ).scalar_one()
        alertas = db.execute(
            select(func.count()).select_from(
                select(AlertaGeo).where(AlertaGeo.activa.is_(True)).subquery()
            )
        ).scalar_one()
        return {
            "porcentaje_area_riesgo": round(
                (at_risk_count / zonas_total * 100.0) if zonas_total > 0 else 0.0, 2
            ),
            "canales_criticos": 0,
            "caminos_vulnerables": 0,
            "conflictos_activos": conflictos,
            "alertas_activas": alertas,
            "zonas_por_nivel": zonas_por_nivel,
            "evolucion_temporal": [],
        }

    def refresh_materialized_views(self, db: Session) -> dict[str, str]:
        results: dict[str, str] = {}
        for view in ["mv_dashboard_geo_stats", "mv_hci_por_zona", "mv_alertas_resumen"]:
            try:
                db.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
                results[view] = "ok"
            except Exception:
                db.rollback()
                try:
                    db.execute(text(f"REFRESH MATERIALIZED VIEW {view}"))
                    results[view] = "ok (non-concurrent)"
                except Exception as inner_exc:
                    results[view] = f"error: {inner_exc!s}"
        db.commit()
        return results

    def get_dashboard_stats(self, db: Session) -> dict[str, Any]:
        return self._empty_dict_from_matview(
            db, "SELECT * FROM mv_dashboard_geo_stats LIMIT 1"
        )

    def get_hci_por_zona(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 50,
        cuenca_filter: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        params: dict[str, Any] = {}
        where_clause = ""
        if cuenca_filter:
            where_clause = "WHERE cuenca = :cuenca"
            params["cuenca"] = cuenca_filter
        total: int = db.execute(
            text(f"SELECT COUNT(*) FROM mv_hci_por_zona {where_clause}"), params
        ).scalar_one()
        params.update({"offset": (page - 1) * limit, "limit": limit})
        data_sql = f"SELECT zona_id, zona_nombre, cuenca, superficie_ha, indice_final, nivel_riesgo, fecha_calculo FROM mv_hci_por_zona {where_clause} ORDER BY indice_final DESC OFFSET :offset LIMIT :limit"
        return [
            dict(r) for r in db.execute(text(data_sql), params).mappings().all()
        ], total

    def get_alertas_resumen(self, db: Session) -> dict[str, Any]:
        return self._empty_dict_from_matview(
            db, "SELECT * FROM mv_alertas_resumen LIMIT 1"
        )
