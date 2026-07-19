from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domains.geo.geo_repository_support import paginated_results
from app.domains.geo.models import EstadoGeoJob, GeoJob, GeoLayer


class GeoRepositoryJobsLayersMixin:
    def get_job_by_id(self, db: Session, job_id: uuid.UUID) -> Optional[GeoJob]:
        return db.execute(select(GeoJob).where(GeoJob.id == job_id)).scalar_one_or_none()

    def get_jobs(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado_filter: Optional[str] = None,
        tipo_filter: Optional[str] = None,
    ) -> tuple[list[GeoJob], int]:
        base = select(GeoJob)
        if estado_filter:
            base = base.where(GeoJob.estado == estado_filter)
        if tipo_filter:
            base = base.where(GeoJob.tipo == tipo_filter)
        return paginated_results(
            db, base, page=page, limit=limit, order_by=GeoJob.created_at.desc()
        )

    def create_job(
        self,
        db: Session,
        *,
        tipo: str,
        parametros: Optional[dict] = None,
        usuario_id: Optional[uuid.UUID] = None,
    ) -> GeoJob:
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

    def update_job_status_if_current(
        self,
        db: Session,
        job_id: uuid.UUID,
        *,
        expected_estado: str,
        estado: Optional[str] = None,
        progreso: Optional[int] = None,
        resultado: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Compare-and-set a job transition without resurrecting stale work."""
        values: dict[str, object] = {"updated_at": func.now()}
        if estado is not None:
            values["estado"] = estado
        if progreso is not None:
            values["progreso"] = progreso
        if resultado is not None:
            values["resultado"] = resultado
        if error is not None:
            values["error"] = error

        result = db.execute(
            update(GeoJob)
            .where(GeoJob.id == job_id, GeoJob.estado == expected_estado)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0) == 1

    def get_layer_by_id(self, db: Session, layer_id: uuid.UUID) -> Optional[GeoLayer]:
        return db.execute(select(GeoLayer).where(GeoLayer.id == layer_id)).scalar_one_or_none()

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
        base = select(GeoLayer)
        if tipo_filter:
            base = base.where(GeoLayer.tipo == tipo_filter)
        if fuente_filter:
            base = base.where(GeoLayer.fuente == fuente_filter)
        if area_id_filter:
            base = base.where(GeoLayer.area_id == area_id_filter)
        return paginated_results(
            db, base, page=page, limit=limit, order_by=GeoLayer.created_at.desc()
        )

    def get_layer_by_tipo_and_area(
        self, db: Session, tipo: str, area_id: str
    ) -> Optional[GeoLayer]:
        stmt = select(GeoLayer).where(GeoLayer.tipo == tipo, GeoLayer.area_id == area_id)
        return db.execute(stmt).scalar_one_or_none()

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

    def upsert_layer(
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
        existing = self.get_layer_by_tipo_and_area(db, tipo, area_id) if area_id else None
        if existing:
            existing.nombre = nombre
            existing.fuente = fuente
            existing.archivo_path = archivo_path
            existing.formato = formato
            existing.srid = srid
            existing.bbox = bbox
            existing.metadata_extra = metadata_extra
            db.flush()
            return existing
        return self.create_layer(
            db,
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

    def delete_layers_by_area_id(self, db: Session, area_id: str) -> int:
        from sqlalchemy import delete

        result = db.execute(delete(GeoLayer).where(GeoLayer.area_id == area_id))
        db.flush()
        return result.rowcount
