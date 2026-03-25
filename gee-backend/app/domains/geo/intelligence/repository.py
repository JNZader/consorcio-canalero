"""Repository layer — all database access for the intelligence sub-module."""

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


class IntelligenceRepository:
    """Data-access layer for operational intelligence entities."""

    # ── ZONA OPERATIVA ────────────────────────────

    def get_zona_by_id(
        self, db: Session, zona_id: uuid.UUID
    ) -> Optional[ZonaOperativa]:
        stmt = select(ZonaOperativa).where(ZonaOperativa.id == zona_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_zonas(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 50,
        cuenca_filter: Optional[str] = None,
    ) -> tuple[list[ZonaOperativa], int]:
        base = select(ZonaOperativa)
        if cuenca_filter:
            base = base.where(ZonaOperativa.cuenca == cuenca_filter)

        total: int = db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        offset = (page - 1) * limit
        items = list(
            db.execute(
                base.order_by(ZonaOperativa.nombre).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

    def create_zona(
        self,
        db: Session,
        *,
        nombre: str,
        geometria: str,
        cuenca: str,
        superficie_ha: float = 0.0,
    ) -> ZonaOperativa:
        zona = ZonaOperativa(
            nombre=nombre,
            geometria=geometria,
            cuenca=cuenca,
            superficie_ha=superficie_ha,
        )
        db.add(zona)
        db.flush()
        return zona

    def get_zonas_criticas(
        self, db: Session, nivel_riesgo_min: str = "alto"
    ) -> list[ZonaOperativa]:
        """Get zones whose latest HCI is above the given risk threshold.

        Args:
            db: Database session.
            nivel_riesgo_min: Minimum risk level ('medio', 'alto', 'critico').

        Returns:
            List of zones at or above the threshold.
        """
        niveles = ["bajo", "medio", "alto", "critico"]
        min_idx = niveles.index(nivel_riesgo_min) if nivel_riesgo_min in niveles else 2
        target_niveles = niveles[min_idx:]

        # Subquery: latest HCI per zone
        latest_hci = (
            select(
                IndiceHidrico.zona_id,
                func.max(IndiceHidrico.fecha_calculo).label("max_fecha"),
            )
            .group_by(IndiceHidrico.zona_id)
            .subquery()
        )

        stmt = (
            select(ZonaOperativa)
            .join(IndiceHidrico, IndiceHidrico.zona_id == ZonaOperativa.id)
            .join(
                latest_hci,
                (IndiceHidrico.zona_id == latest_hci.c.zona_id)
                & (IndiceHidrico.fecha_calculo == latest_hci.c.max_fecha),
            )
            .where(IndiceHidrico.nivel_riesgo.in_(target_niveles))
        )
        return list(db.execute(stmt).scalars().all())

    # ── INDICE HIDRICO ────────────────────────────

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

        total: int = db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        offset = (page - 1) * limit
        items = list(
            db.execute(
                base.order_by(IndiceHidrico.fecha_calculo.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

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

    # ── PUNTO DE CONFLICTO ────────────────────────

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

        total: int = db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        offset = (page - 1) * limit
        items = list(
            db.execute(
                base.order_by(PuntoConflicto.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

    def get_conflictos_por_zona(
        self, db: Session, zona_id: uuid.UUID
    ) -> list[PuntoConflicto]:
        """Get conflicts within an operational zone (spatial query)."""
        zona = self.get_zona_by_id(db, zona_id)
        if zona is None:
            return []

        stmt = select(PuntoConflicto).where(
            func.ST_Within(PuntoConflicto.geometria, zona.geometria)
        )
        return list(db.execute(stmt).scalars().all())

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
        """Bulk insert conflict points. Returns count of inserted rows."""
        objects = [PuntoConflicto(**c) for c in conflictos]
        db.add_all(objects)
        db.flush()
        return len(objects)

    # ── ALERTAS ───────────────────────────────────

    def get_alertas_activas(
        self, db: Session, *, limit: int = 100
    ) -> list[AlertaGeo]:
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
            tipo=tipo,
            mensaje=mensaje,
            nivel=nivel,
            zona_id=zona_id,
            datos=datos,
        )
        db.add(alerta)
        db.flush()
        return alerta

    def deactivate_alerta(
        self, db: Session, alerta_id: uuid.UUID
    ) -> Optional[AlertaGeo]:
        stmt = select(AlertaGeo).where(AlertaGeo.id == alerta_id)
        alerta = db.execute(stmt).scalar_one_or_none()
        if alerta:
            alerta.activa = False
            db.flush()
        return alerta

    # ── DASHBOARD ─────────────────────────────────

    def get_dashboard_inteligente(self, db: Session) -> dict[str, Any]:
        """Compute aggregated intelligence dashboard metrics."""
        # Total zones and their areas
        zonas_total = db.execute(
            select(func.count()).select_from(ZonaOperativa)
        ).scalar_one()

        area_total = db.execute(
            select(func.coalesce(func.sum(ZonaOperativa.superficie_ha), 0.0))
        ).scalar_one()

        # Count zones by risk level (latest HCI per zone)
        latest_hci = (
            select(
                IndiceHidrico.zona_id,
                func.max(IndiceHidrico.fecha_calculo).label("max_fecha"),
            )
            .group_by(IndiceHidrico.zona_id)
            .subquery()
        )

        zonas_por_nivel: dict[str, int] = {"bajo": 0, "medio": 0, "alto": 0, "critico": 0}
        nivel_counts = db.execute(
            select(IndiceHidrico.nivel_riesgo, func.count())
            .join(
                latest_hci,
                (IndiceHidrico.zona_id == latest_hci.c.zona_id)
                & (IndiceHidrico.fecha_calculo == latest_hci.c.max_fecha),
            )
            .group_by(IndiceHidrico.nivel_riesgo)
        ).all()

        for nivel, count in nivel_counts:
            if nivel in zonas_por_nivel:
                zonas_por_nivel[nivel] = count

        # Area at risk (medio+)
        at_risk_count = (
            zonas_por_nivel.get("medio", 0)
            + zonas_por_nivel.get("alto", 0)
            + zonas_por_nivel.get("critico", 0)
        )
        pct_risk = (at_risk_count / zonas_total * 100.0) if zonas_total > 0 else 0.0

        # Active conflicts and alerts
        conflictos = db.execute(
            select(func.count()).select_from(PuntoConflicto)
        ).scalar_one()

        alertas = db.execute(
            select(func.count()).select_from(
                select(AlertaGeo).where(AlertaGeo.activa.is_(True)).subquery()
            )
        ).scalar_one()

        return {
            "porcentaje_area_riesgo": round(pct_risk, 2),
            "canales_criticos": 0,  # Computed in service layer
            "caminos_vulnerables": 0,  # Computed in service layer
            "conflictos_activos": conflictos,
            "alertas_activas": alertas,
            "zonas_por_nivel": zonas_por_nivel,
            "evolucion_temporal": [],  # Computed in service layer
        }

    # ── MATERIALIZED VIEWS ─────────────────────────

    def refresh_materialized_views(self, db: Session) -> dict[str, str]:
        """Refresh all 3 geo materialized views concurrently.

        Requires the unique indexes to exist (created by migration).
        Returns a dict with view names and their refresh status.
        """
        views = [
            "mv_dashboard_geo_stats",
            "mv_hci_por_zona",
            "mv_alertas_resumen",
        ]
        results: dict[str, str] = {}
        for view in views:
            try:
                db.execute(
                    text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                )
                results[view] = "ok"
            except Exception as exc:
                # If the view has no data yet, CONCURRENTLY fails — fallback
                db.rollback()
                try:
                    db.execute(text(f"REFRESH MATERIALIZED VIEW {view}"))
                    results[view] = "ok (non-concurrent)"
                except Exception as inner_exc:
                    results[view] = f"error: {inner_exc!s}"
        db.commit()
        return results

    def get_dashboard_stats(self, db: Session) -> dict[str, Any]:
        """Read pre-computed dashboard KPIs from mv_dashboard_geo_stats."""
        row = db.execute(
            text("SELECT * FROM mv_dashboard_geo_stats LIMIT 1")
        ).mappings().first()

        if row is None:
            return {}
        return dict(row)

    def get_hci_por_zona(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 50,
        cuenca_filter: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Read latest HCI per zone from mv_hci_por_zona (paginated)."""
        where_clause = ""
        params: dict[str, Any] = {}
        if cuenca_filter:
            where_clause = "WHERE cuenca = :cuenca"
            params["cuenca"] = cuenca_filter

        # Total count
        count_sql = f"SELECT COUNT(*) FROM mv_hci_por_zona {where_clause}"
        total: int = db.execute(text(count_sql), params).scalar_one()

        # Paginated data
        offset = (page - 1) * limit
        data_sql = (
            f"SELECT zona_id, zona_nombre, cuenca, superficie_ha, "
            f"indice_final, nivel_riesgo, fecha_calculo "
            f"FROM mv_hci_por_zona {where_clause} "
            f"ORDER BY indice_final DESC "
            f"OFFSET :offset LIMIT :limit"
        )
        params["offset"] = offset
        params["limit"] = limit

        rows = db.execute(text(data_sql), params).mappings().all()
        return [dict(r) for r in rows], total

    def get_alertas_resumen(self, db: Session) -> dict[str, Any]:
        """Read active alerts summary from mv_alertas_resumen."""
        row = db.execute(
            text("SELECT * FROM mv_alertas_resumen LIMIT 1")
        ).mappings().first()

        if row is None:
            return {}
        return dict(row)
