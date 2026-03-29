"""Repository layer — all database access for the monitoring domain."""

import uuid
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.monitoring.models import (
    AnalisisGee,
    EstadoSugerencia,
    Sugerencia,
)
from app.domains.monitoring.schemas import SugerenciaCreate, SugerenciaUpdate


class MonitoringRepository:
    """Data-access layer for sugerencias, analyses, and dashboard stats."""

    # ── SUGERENCIA CRUD ────────────────────────

    def get_sugerencia_by_id(
        self, db: Session, sugerencia_id: uuid.UUID
    ) -> Optional[Sugerencia]:
        stmt = select(Sugerencia).where(Sugerencia.id == sugerencia_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_all_sugerencias(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado_filter: Optional[str] = None,
        categoria_filter: Optional[str] = None,
    ) -> tuple[list[Sugerencia], int]:
        """Paginated list of sugerencias with optional filters."""
        base = select(Sugerencia)

        if estado_filter:
            base = base.where(Sugerencia.estado == estado_filter)
        if categoria_filter:
            base = base.where(Sugerencia.categoria == categoria_filter)

        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        offset = (page - 1) * limit
        items_stmt = (
            base.order_by(Sugerencia.created_at.desc()).offset(offset).limit(limit)
        )
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    def create_sugerencia(
        self, db: Session, data: SugerenciaCreate
    ) -> Sugerencia:
        sugerencia = Sugerencia(
            titulo=data.titulo,
            descripcion=data.descripcion,
            categoria=data.categoria,
            estado=EstadoSugerencia.PENDIENTE,
            contacto_email=data.contacto_email,
            contacto_nombre=data.contacto_nombre,
        )
        db.add(sugerencia)
        db.flush()
        return sugerencia

    def update_sugerencia(
        self,
        db: Session,
        sugerencia_id: uuid.UUID,
        data: SugerenciaUpdate,
    ) -> Optional[Sugerencia]:
        sugerencia = self.get_sugerencia_by_id(db, sugerencia_id)
        if sugerencia is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(sugerencia, field, value)

        db.flush()
        return sugerencia

    def get_sugerencias_stats(self, db: Session) -> dict[str, Any]:
        """Aggregate counts of sugerencias by estado and tipo."""
        estado_rows = db.execute(
            select(Sugerencia.estado, func.count()).group_by(Sugerencia.estado)
        ).all()
        por_estado = {row[0]: row[1] for row in estado_rows}

        total = sum(por_estado.values())

        # Count by whether the sugerencia has a usuario_id (interna) or not (ciudadana)
        ciudadanas: int = db.execute(
            select(func.count())
            .select_from(Sugerencia)
            .where(Sugerencia.usuario_id.is_(None))
        ).scalar_one()
        internas = total - ciudadanas

        return {
            "pendiente": por_estado.get(EstadoSugerencia.PENDIENTE, 0),
            "en_agenda": por_estado.get(EstadoSugerencia.REVISADA, 0),
            "tratado": por_estado.get(EstadoSugerencia.IMPLEMENTADA, 0),
            "descartado": por_estado.get(EstadoSugerencia.DESCARTADA, 0),
            "total": total,
            "ciudadanas": ciudadanas,
            "internas": internas,
        }

    def get_proxima_reunion(self, db: Session) -> list[Sugerencia]:
        """Return sugerencias in 'revisada' (en_agenda) state, ordered by creation."""
        stmt = (
            select(Sugerencia)
            .where(Sugerencia.estado == EstadoSugerencia.REVISADA)
            .order_by(Sugerencia.created_at.desc())
            .limit(20)
        )
        return list(db.execute(stmt).scalars().all())

    # ── ANALISIS GEE ───────────────────────────

    def save_analysis(
        self, db: Session, data: dict[str, Any]
    ) -> AnalisisGee:
        """Persist a GEE analysis result."""
        analysis = AnalisisGee(
            tipo=data["tipo"],
            fecha_inicio=data["fecha_inicio"],
            fecha_fin=data["fecha_fin"],
            resultados=data.get("resultados", {}),
            hectareas_afectadas=data.get("hectareas_afectadas"),
            porcentaje_area=data.get("porcentaje_area"),
            parametros=data.get("parametros", {}),
            usuario_id=data["usuario_id"],
        )
        db.add(analysis)
        db.flush()
        return analysis

    def get_analysis_by_id(
        self, db: Session, analysis_id: uuid.UUID
    ) -> Optional[AnalisisGee]:
        stmt = select(AnalisisGee).where(AnalisisGee.id == analysis_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_analysis_history(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        tipo_filter: Optional[str] = None,
    ) -> tuple[list[AnalisisGee], int]:
        base = select(AnalisisGee)

        if tipo_filter:
            base = base.where(AnalisisGee.tipo == tipo_filter)

        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        offset = (page - 1) * limit
        items_stmt = (
            base.order_by(AnalisisGee.created_at.desc()).offset(offset).limit(limit)
        )
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    def get_latest_analyses(
        self, db: Session, *, limit: int = 5
    ) -> list[AnalisisGee]:
        stmt = (
            select(AnalisisGee)
            .order_by(AnalisisGee.created_at.desc())
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    # ── DASHBOARD STATS ────────────────────────

    def get_dashboard_stats(self, db: Session) -> dict[str, Any]:
        """
        Cross-domain read-only aggregation for the admin dashboard.

        Queries denuncias, infraestructura assets, tramites, sugerencias,
        and finanzas tables to produce summary counts.
        """
        from app.domains.denuncias.models import Denuncia
        from app.domains.infraestructura.models import Asset
        from app.domains.tramites.models import Tramite
        from app.domains.finanzas.models import Gasto, Ingreso

        # Denuncias by estado
        denuncia_rows = db.execute(
            select(Denuncia.estado, func.count()).group_by(Denuncia.estado)
        ).all()
        denuncias_por_estado = {row[0]: row[1] for row in denuncia_rows}
        total_denuncias = sum(denuncias_por_estado.values())

        # Assets total
        total_assets: int = db.execute(
            select(func.count()).select_from(Asset)
        ).scalar_one()

        # Tramites total
        total_tramites: int = db.execute(
            select(func.count()).select_from(Tramite)
        ).scalar_one()

        # Sugerencias total
        total_sugerencias: int = db.execute(
            select(func.count()).select_from(Sugerencia)
        ).scalar_one()

        # Financial summary
        total_gastos = (
            db.execute(select(func.coalesce(func.sum(Gasto.monto), 0))).scalar_one()
        )
        total_ingresos = (
            db.execute(select(func.coalesce(func.sum(Ingreso.monto), 0))).scalar_one()
        )

        # Latest analyses
        latest = self.get_latest_analyses(db, limit=5)

        return {
            "denuncias": {
                "por_estado": denuncias_por_estado,
                "total": total_denuncias,
            },
            "total_assets": total_assets,
            "total_tramites": total_tramites,
            "total_sugerencias": total_sugerencias,
            "resumen_financiero": {
                "total_gastos": float(total_gastos),
                "total_ingresos": float(total_ingresos),
                "balance": float(total_ingresos) - float(total_gastos),
            },
            "latest_analyses": latest,
        }
