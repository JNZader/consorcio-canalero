"""Repository layer — all database access for the geo domain."""

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.geo.models import AnalisisGeo, EstadoGeoJob, GeoJob, GeoLayer


class GeoRepository:
    """Data-access layer for geo jobs and layers."""

    # ── JOB READ ─────────────────────────────────

    def get_job_by_id(self, db: Session, job_id: uuid.UUID) -> Optional[GeoJob]:
        """Return a single geo job, or None."""
        stmt = select(GeoJob).where(GeoJob.id == job_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_jobs(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado_filter: Optional[str] = None,
        tipo_filter: Optional[str] = None,
    ) -> tuple[list[GeoJob], int]:
        """Paginated list of geo jobs with optional filters."""
        base = select(GeoJob)

        if estado_filter:
            base = base.where(GeoJob.estado == estado_filter)
        if tipo_filter:
            base = base.where(GeoJob.tipo == tipo_filter)

        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        offset = (page - 1) * limit
        items_stmt = (
            base.order_by(GeoJob.created_at.desc()).offset(offset).limit(limit)
        )
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    # ── JOB WRITE ────────────────────────────────

    def create_job(
        self,
        db: Session,
        *,
        tipo: str,
        parametros: Optional[dict] = None,
        usuario_id: Optional[uuid.UUID] = None,
    ) -> GeoJob:
        """Create a new geo processing job."""
        job = GeoJob(
            tipo=tipo,
            estado=EstadoGeoJob.PENDING,
            parametros=parametros,
            usuario_id=usuario_id,
        )
        db.add(job)
        db.flush()
        return job

    def update_job_status(
        self,
        db: Session,
        job_id: uuid.UUID,
        *,
        estado: Optional[str] = None,
        celery_task_id: Optional[str] = None,
        progreso: Optional[int] = None,
        resultado: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> Optional[GeoJob]:
        """Update job status fields."""
        job = self.get_job_by_id(db, job_id)
        if job is None:
            return None

        if estado is not None:
            job.estado = estado
        if celery_task_id is not None:
            job.celery_task_id = celery_task_id
        if progreso is not None:
            job.progreso = progreso
        if resultado is not None:
            job.resultado = resultado
        if error is not None:
            job.error = error

        db.flush()
        return job

    # ── LAYER READ ───────────────────────────────

    def get_layer_by_id(
        self, db: Session, layer_id: uuid.UUID
    ) -> Optional[GeoLayer]:
        """Return a single geo layer, or None."""
        stmt = select(GeoLayer).where(GeoLayer.id == layer_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_layers(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        tipo_filter: Optional[str] = None,
        fuente_filter: Optional[str] = None,
        area_id_filter: Optional[str] = None,
    ) -> tuple[list[GeoLayer], int]:
        """Paginated list of geo layers with optional filters."""
        base = select(GeoLayer)

        if tipo_filter:
            base = base.where(GeoLayer.tipo == tipo_filter)
        if fuente_filter:
            base = base.where(GeoLayer.fuente == fuente_filter)
        if area_id_filter:
            base = base.where(GeoLayer.area_id == area_id_filter)

        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        offset = (page - 1) * limit
        items_stmt = (
            base.order_by(GeoLayer.created_at.desc()).offset(offset).limit(limit)
        )
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    # ── LAYER WRITE ──────────────────────────────

    def create_layer(
        self,
        db: Session,
        *,
        nombre: str,
        tipo: str,
        fuente: str,
        archivo_path: str,
        formato: str = "geotiff",
        srid: int = 4326,
        bbox: Optional[list[float]] = None,
        metadata_extra: Optional[dict] = None,
        area_id: Optional[str] = None,
    ) -> GeoLayer:
        """Create a new geo layer record."""
        layer = GeoLayer(
            nombre=nombre,
            tipo=tipo,
            fuente=fuente,
            archivo_path=archivo_path,
            formato=formato,
            srid=srid,
            bbox=bbox,
            metadata_extra=metadata_extra,
            area_id=area_id,
        )
        db.add(layer)
        db.flush()
        return layer

    # ── ANALISIS GEO READ ─────────────────────────

    def get_analisis_by_id(
        self, db: Session, analisis_id: uuid.UUID
    ) -> Optional[AnalisisGeo]:
        """Return a single GEE analysis, or None."""
        stmt = select(AnalisisGeo).where(AnalisisGeo.id == analisis_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_analisis_list(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        tipo_filter: Optional[str] = None,
        estado_filter: Optional[str] = None,
    ) -> tuple[list[AnalisisGeo], int]:
        """Paginated list of GEE analyses with optional filters."""
        base = select(AnalisisGeo)

        if tipo_filter:
            base = base.where(AnalisisGeo.tipo == tipo_filter)
        if estado_filter:
            base = base.where(AnalisisGeo.estado == estado_filter)

        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        offset = (page - 1) * limit
        items_stmt = (
            base.order_by(AnalisisGeo.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    # ── ANALISIS GEO WRITE ────────────────────────

    def create_analisis(
        self,
        db: Session,
        *,
        tipo: str,
        fecha_analisis: "date",
        parametros: Optional[dict] = None,
        usuario_id: Optional[uuid.UUID] = None,
    ) -> AnalisisGeo:
        """Create a new GEE analysis record in PENDING state."""
        from datetime import date as _date  # avoid circular at module level

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
        """Update analysis status fields (used by task completion callbacks)."""
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
