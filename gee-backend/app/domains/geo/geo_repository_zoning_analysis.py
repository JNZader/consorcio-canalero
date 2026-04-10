from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.geo.geo_repository_support import approved_zoning_stmt, paginated_results
from app.domains.geo.models import AnalisisGeo, EstadoGeoJob, GeoApprovedZoning


class GeoRepositoryZoningAnalysisMixin:
    def get_active_approved_zoning(self, db: Session, *, cuenca: Optional[str] = None) -> Optional[GeoApprovedZoning]:
        stmt = approved_zoning_stmt(active_only=True, cuenca=cuenca).order_by(GeoApprovedZoning.approved_at.desc())
        return db.execute(stmt).scalar_one_or_none()

    def list_approved_zonings(self, db: Session, *, cuenca: Optional[str] = None, limit: int = 20) -> list[GeoApprovedZoning]:
        stmt = approved_zoning_stmt(cuenca=cuenca).order_by(GeoApprovedZoning.version.desc(), GeoApprovedZoning.approved_at.desc()).limit(limit)
        return list(db.execute(stmt).scalars().all())

    def get_approved_zoning_by_id(self, db: Session, zoning_id: uuid.UUID) -> Optional[GeoApprovedZoning]:
        return db.execute(select(GeoApprovedZoning).where(GeoApprovedZoning.id == zoning_id)).scalar_one_or_none()

    def get_next_approved_zoning_version(self, db: Session, *, cuenca: Optional[str] = None) -> int:
        stmt = approved_zoning_stmt(cuenca=cuenca).with_only_columns(func.max(GeoApprovedZoning.version))
        return int(db.execute(stmt).scalar_one() or 0) + 1

    def create_approved_zoning_version(
        self,
        db: Session,
        *,
        feature_collection: dict,
        nombre: str = "Zonificación Consorcio aprobada",
        cuenca: Optional[str] = None,
        assignments: Optional[dict] = None,
        zone_names: Optional[dict] = None,
        approved_by_id: Optional[uuid.UUID] = None,
        notes: Optional[str] = None,
    ) -> GeoApprovedZoning:
        existing = self.get_active_approved_zoning(db, cuenca=cuenca)
        if existing:
            existing.is_active = False
        zoning = GeoApprovedZoning(
            nombre=nombre,
            version=self.get_next_approved_zoning_version(db, cuenca=cuenca),
            cuenca=cuenca,
            feature_collection=feature_collection,
            assignments=assignments,
            zone_names=zone_names,
            approved_by_id=approved_by_id,
            notes=notes,
            is_active=True,
        )
        db.add(zoning)
        db.flush()
        return zoning

    def clear_active_approved_zoning(self, db: Session, *, cuenca: Optional[str] = None) -> int:
        current = db.execute(approved_zoning_stmt(active_only=True, cuenca=cuenca)).scalar_one_or_none()
        if current is None:
            return 0
        current.is_active = False
        db.flush()
        return 1

    def get_analisis_by_id(self, db: Session, analisis_id: uuid.UUID) -> Optional[AnalisisGeo]:
        return db.execute(select(AnalisisGeo).where(AnalisisGeo.id == analisis_id)).scalar_one_or_none()

    def get_analisis_list(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        tipo_filter: Optional[str] = None,
        estado_filter: Optional[str] = None,
    ) -> tuple[list[AnalisisGeo], int]:
        base = select(AnalisisGeo)
        if tipo_filter:
            base = base.where(AnalisisGeo.tipo == tipo_filter)
        if estado_filter:
            base = base.where(AnalisisGeo.estado == estado_filter)
        return paginated_results(db, base, page=page, limit=limit, order_by=AnalisisGeo.created_at.desc())

    def create_analisis(
        self,
        db: Session,
        *,
        tipo: str,
        fecha_analisis: date,
        parametros: Optional[dict] = None,
        usuario_id: Optional[uuid.UUID] = None,
    ) -> AnalisisGeo:
        analisis = AnalisisGeo(
            tipo=tipo,
            fecha_analisis=fecha_analisis,
            estado=EstadoGeoJob.PENDING,
            parametros=parametros,
            usuario_id=usuario_id,
        )
        db.add(analisis)
        db.flush()
        return analisis

    def update_analisis_status(
        self,
        db: Session,
        analisis_id: uuid.UUID,
        *,
        estado: Optional[str] = None,
        celery_task_id: Optional[str] = None,
        resultado: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> Optional[AnalisisGeo]:
        analisis = self.get_analisis_by_id(db, analisis_id)
        if analisis is None:
            return None
        if estado is not None:
            analisis.estado = estado
        if celery_task_id is not None:
            analisis.celery_task_id = celery_task_id
        if resultado is not None:
            analisis.resultado = resultado
        if error is not None:
            analisis.error = error
        db.flush()
        return analisis
