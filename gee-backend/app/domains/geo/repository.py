"""Repository layer — all database access for the geo domain."""

import logging
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domains.geo.models import (
    AnalisisGeo,
    EstadoGeoJob,
    FloodEvent,
    FloodLabel,
    GeoApprovedZoning,
    GeoJob,
    GeoLayer,
    RainfallRecord,
)

logger = logging.getLogger(__name__)


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

    def get_layer_by_tipo_and_area(
        self, db: Session, tipo: str, area_id: str
    ) -> Optional[GeoLayer]:
        """Return a layer matching (tipo, area_id), or None."""
        stmt = select(GeoLayer).where(
            GeoLayer.tipo == tipo,
            GeoLayer.area_id == area_id,
        )
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
        """Create or update a geo layer by (tipo, area_id).

        If a layer with the same tipo+area_id exists, update it in place.
        Otherwise create a new record.
        """
        existing = (
            self.get_layer_by_tipo_and_area(db, tipo, area_id)
            if area_id
            else None
        )
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
        """Delete all GeoLayer records for a given area_id. Returns count deleted."""
        from sqlalchemy import delete

        stmt = delete(GeoLayer).where(GeoLayer.area_id == area_id)
        result = db.execute(stmt)
        db.flush()
        return result.rowcount

    # ── APPROVED ZONING ─────────────────────────

    def get_active_approved_zoning(
        self,
        db: Session,
        *,
        cuenca: Optional[str] = None,
    ) -> Optional[GeoApprovedZoning]:
        """Return the current active approved zoning for an optional cuenca."""
        stmt = select(GeoApprovedZoning).where(GeoApprovedZoning.is_active == True)  # noqa: E712
        if cuenca is None:
            stmt = stmt.where(GeoApprovedZoning.cuenca.is_(None))
        else:
            stmt = stmt.where(GeoApprovedZoning.cuenca == cuenca)
        stmt = stmt.order_by(GeoApprovedZoning.approved_at.desc())
        return db.execute(stmt).scalar_one_or_none()

    def list_approved_zonings(
        self,
        db: Session,
        *,
        cuenca: Optional[str] = None,
        limit: int = 20,
    ) -> list[GeoApprovedZoning]:
        """Return approved zoning history ordered by newest first."""
        stmt = select(GeoApprovedZoning)
        if cuenca is None:
            stmt = stmt.where(GeoApprovedZoning.cuenca.is_(None))
        else:
            stmt = stmt.where(GeoApprovedZoning.cuenca == cuenca)
        stmt = stmt.order_by(GeoApprovedZoning.version.desc(), GeoApprovedZoning.approved_at.desc()).limit(limit)
        return list(db.execute(stmt).scalars().all())

    def get_approved_zoning_by_id(
        self,
        db: Session,
        zoning_id: uuid.UUID,
    ) -> Optional[GeoApprovedZoning]:
        """Return one approved zoning by id."""
        stmt = select(GeoApprovedZoning).where(GeoApprovedZoning.id == zoning_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_next_approved_zoning_version(
        self,
        db: Session,
        *,
        cuenca: Optional[str] = None,
    ) -> int:
        """Return the next version number for an approved zoning series."""
        stmt = select(func.max(GeoApprovedZoning.version))
        if cuenca is None:
            stmt = stmt.where(GeoApprovedZoning.cuenca.is_(None))
        else:
            stmt = stmt.where(GeoApprovedZoning.cuenca == cuenca)
        current_max = db.execute(stmt).scalar_one()
        return int(current_max or 0) + 1

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
        """Create a new approved zoning version and deactivate the previous active one."""
        existing = self.get_active_approved_zoning(db, cuenca=cuenca)
        if existing:
            existing.is_active = False

        next_version = self.get_next_approved_zoning_version(db, cuenca=cuenca)

        zoning = GeoApprovedZoning(
            nombre=nombre,
            version=next_version,
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

    def clear_active_approved_zoning(
        self,
        db: Session,
        *,
        cuenca: Optional[str] = None,
    ) -> int:
        """Deactivate the active approved zoning for the optional cuenca, preserving history."""
        stmt = select(GeoApprovedZoning).where(GeoApprovedZoning.is_active == True)  # noqa: E712
        if cuenca is None:
            stmt = stmt.where(GeoApprovedZoning.cuenca.is_(None))
        else:
            stmt = stmt.where(GeoApprovedZoning.cuenca == cuenca)
        current = db.execute(stmt).scalar_one_or_none()
        if current is None:
            return 0
        current.is_active = False
        db.flush()
        return 1

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

    # ── FLOOD EVENT READ ─────────────────────────

    def get_flood_event_by_id(
        self, db: Session, event_id: uuid.UUID
    ) -> Optional[FloodEvent]:
        """Return a single flood event with labels eagerly loaded, or None."""
        from sqlalchemy.orm import joinedload

        stmt = (
            select(FloodEvent)
            .options(joinedload(FloodEvent.labels))
            .where(FloodEvent.id == event_id)
        )
        return db.execute(stmt).unique().scalar_one_or_none()

    def list_flood_events(self, db: Session) -> list[dict]:
        """Return all flood events ordered by event_date desc, with label count."""
        stmt = (
            select(
                FloodEvent.id,
                FloodEvent.event_date,
                FloodEvent.description,
                FloodEvent.created_at,
                func.count(FloodLabel.id).label("label_count"),
            )
            .outerjoin(FloodLabel, FloodLabel.event_id == FloodEvent.id)
            .group_by(FloodEvent.id)
            .order_by(FloodEvent.event_date.desc())
        )
        rows = db.execute(stmt).all()
        return [
            {
                "id": row.id,
                "event_date": row.event_date,
                "description": row.description,
                "label_count": row.label_count,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    # ── FLOOD EVENT WRITE ────────────────────────

    def create_flood_event(
        self,
        db: Session,
        *,
        event_date: "date",
        description: Optional[str] = None,
        labels: list[dict],
    ) -> FloodEvent:
        """Create a flood event with its labels.

        Args:
            labels: list of dicts with keys: zona_id (UUID), is_flooded (bool)
        """
        event = FloodEvent(
            event_date=event_date,
            description=description,
        )
        db.add(event)
        db.flush()

        for label_data in labels:
            label = FloodLabel(
                event_id=event.id,
                zona_id=label_data["zona_id"],
                is_flooded=label_data["is_flooded"],
            )
            db.add(label)

        db.flush()
        return event

    def delete_flood_event(
        self, db: Session, event_id: uuid.UUID
    ) -> bool:
        """Delete a flood event and its labels (cascade). Returns True if found."""
        event = self.get_flood_event_by_id(db, event_id)
        if event is None:
            return False

        db.delete(event)
        db.flush()
        return True

    def update_label_features(
        self,
        db: Session,
        label_id: uuid.UUID,
        features: dict[str, Any],
    ) -> None:
        """Update the extracted_features JSONB on a FloodLabel."""
        stmt = select(FloodLabel).where(FloodLabel.id == label_id)
        label = db.execute(stmt).scalar_one_or_none()
        if label is not None:
            label.extracted_features = features
            db.flush()

    def get_labels_with_features(self, db: Session) -> list[FloodLabel]:
        """Return all FloodLabel rows that have non-null extracted_features."""
        from sqlalchemy.orm import joinedload

        stmt = (
            select(FloodLabel)
            .options(joinedload(FloodLabel.event))
            .where(FloodLabel.extracted_features.isnot(None))
        )
        return list(db.execute(stmt).scalars().all())

    # ── FEATURE EXTRACTION ──────────────────────

    def extract_zone_features(
        self,
        db: Session,
        zona_id: uuid.UUID,
        event_date: date,
    ) -> dict[str, Any]:
        """Extract DEM-based and water detection features for a zone+date.

        Uses existing zonal_stats (raster layers) and detect_water_from_gee
        to build the feature vector stored in FloodLabel.extracted_features.
        """
        from geoalchemy2.functions import ST_AsGeoJSON, ST_AsText
        from sqlalchemy import select as sa_select

        from app.domains.geo.intelligence.models import ZonaOperativa

        zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == zona_id).first()
        if zona is None:
            logger.warning("extract_zone_features: zona %s not found", zona_id)
            return {}

        zona_wkt = db.execute(
            sa_select(ST_AsText(ZonaOperativa.geometria)).where(
                ZonaOperativa.id == zona_id
            )
        ).scalar()

        zona_geojson_str = db.execute(
            sa_select(ST_AsGeoJSON(ZonaOperativa.geometria)).where(
                ZonaOperativa.id == zona_id
            )
        ).scalar()

        features: dict[str, Any] = {}

        # ── DEM raster stats (HAND, TWI, slope, flow_acc) ──
        from app.domains.geo.zonal_stats import compute_stats_for_zones

        zone_data = [(str(zona.id), zona_wkt, zona.nombre)]

        for tipo in ["hand", "twi", "slope", "flow_acc"]:
            layer = (
                db.query(GeoLayer)
                .filter(GeoLayer.tipo == tipo)
                .order_by(GeoLayer.created_at.desc())
                .first()
            )
            if not layer:
                continue

            path = layer.archivo_path
            if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
                cog = layer.metadata_extra["cog_path"]
                if Path(cog).exists():
                    path = cog

            if not Path(path).exists():
                continue

            try:
                stats = compute_stats_for_zones(
                    zone_data, path, ["mean", "max", "min", "count"]
                )
                if stats and stats[0].get("count", 0) > 0:
                    s = stats[0]
                    if tipo == "hand":
                        features["hand_mean"] = s.get("mean", 0) or 0
                        features["hand_max"] = s.get("max", 0) or 0
                    elif tipo == "twi":
                        features["twi_mean"] = s.get("mean", 0) or 0
                    elif tipo == "slope":
                        features["slope_mean"] = s.get("mean", 0) or 0
                    elif tipo == "flow_acc":
                        import numpy as np

                        raw_max = s.get("max", 0) or 0
                        features["flow_acc_log_max"] = float(
                            np.log1p(raw_max)
                        )
            except Exception:
                logger.warning(
                    "extract_zone_features: failed raster stats for %s/%s",
                    tipo,
                    zona_id,
                    exc_info=True,
                )

        # ── Water detection (current date) ──
        if zona_geojson_str:
            import json as _json

            geojson_geom = _json.loads(zona_geojson_str)

            try:
                from app.domains.geo.water_detection import detect_water_from_gee

                result = detect_water_from_gee(
                    geojson_geom,
                    event_date.isoformat(),
                    days_window=15,
                )
                if result.get("status") == "success":
                    features["water_pct_current"] = result["area"].get(
                        "water_pct", 0
                    )
            except Exception:
                logger.warning(
                    "extract_zone_features: water detection failed for %s",
                    zona_id,
                    exc_info=True,
                )

            # ── Water detection (historical avg last 2 years) ──
            try:
                from app.domains.geo.water_detection import detect_water_from_gee

                historical_pcts: list[float] = []
                for months_back in [6, 12, 18, 24]:
                    hist_date = event_date - timedelta(days=months_back * 30)
                    try:
                        hist_result = detect_water_from_gee(
                            geojson_geom,
                            hist_date.isoformat(),
                            days_window=30,
                        )
                        if hist_result.get("status") == "success":
                            historical_pcts.append(
                                hist_result["area"].get("water_pct", 0)
                            )
                    except Exception:
                        pass

                if historical_pcts:
                    features["water_pct_historical"] = round(
                        sum(historical_pcts) / len(historical_pcts), 2
                    )
            except Exception:
                logger.warning(
                    "extract_zone_features: historical water detection failed for %s",
                    zona_id,
                    exc_info=True,
                )

        return features

    # ── RAINFALL RECORD READ ───────────────────────

    def get_rainfall_by_zone(
        self,
        db: Session,
        zona_operativa_id: uuid.UUID,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[RainfallRecord]:
        """Return rainfall records for a zone, optionally filtered by date range."""
        stmt = select(RainfallRecord).where(
            RainfallRecord.zona_operativa_id == zona_operativa_id
        )
        if start_date is not None:
            stmt = stmt.where(RainfallRecord.date >= start_date)
        if end_date is not None:
            stmt = stmt.where(RainfallRecord.date <= end_date)
        stmt = stmt.order_by(RainfallRecord.date.asc())
        return list(db.execute(stmt).scalars().all())

    def get_rainfall_summary(
        self,
        db: Session,
        *,
        start_date: date,
        end_date: date,
        zona_operativa_id: Optional[uuid.UUID] = None,
    ) -> list[dict[str, Any]]:
        """Return aggregated rainfall stats per zone for a date range.

        Returns list of dicts with: zona_operativa_id, total_mm, avg_mm, max_mm, rainy_days.
        """
        stmt = (
            select(
                RainfallRecord.zona_operativa_id,
                func.sum(RainfallRecord.precipitation_mm).label("total_mm"),
                func.avg(RainfallRecord.precipitation_mm).label("avg_mm"),
                func.max(RainfallRecord.precipitation_mm).label("max_mm"),
                func.count(
                    func.nullif(RainfallRecord.precipitation_mm > 0, False)
                ).label("rainy_days"),
            )
            .where(
                RainfallRecord.date >= start_date,
                RainfallRecord.date <= end_date,
            )
            .group_by(RainfallRecord.zona_operativa_id)
        )

        if zona_operativa_id is not None:
            stmt = stmt.where(
                RainfallRecord.zona_operativa_id == zona_operativa_id
            )

        rows = db.execute(stmt).all()
        return [
            {
                "zona_operativa_id": row.zona_operativa_id,
                "total_mm": round(float(row.total_mm or 0), 2),
                "avg_mm": round(float(row.avg_mm or 0), 2),
                "max_mm": round(float(row.max_mm or 0), 2),
                "rainy_days": int(row.rainy_days or 0),
            }
            for row in rows
        ]

    def get_accumulated_rainfall(
        self,
        db: Session,
        zona_operativa_id: uuid.UUID,
        reference_date: date,
        window_days: int,
    ) -> float:
        """Return total accumulated precipitation (mm) for a zone over a lookback window.

        Used by the flood model for feature extraction (48h, 7d, 30d windows).
        """
        start = reference_date - timedelta(days=window_days)
        stmt = select(
            func.coalesce(func.sum(RainfallRecord.precipitation_mm), 0.0)
        ).where(
            RainfallRecord.zona_operativa_id == zona_operativa_id,
            RainfallRecord.date > start,
            RainfallRecord.date <= reference_date,
        )
        result = db.execute(stmt).scalar_one()
        return float(result)

    # ── RAINFALL RECORD WRITE ──────────────────────

    def insert_rainfall_record(
        self,
        db: Session,
        *,
        zona_operativa_id: uuid.UUID,
        record_date: date,
        precipitation_mm: float,
        source: str = "CHIRPS",
    ) -> RainfallRecord:
        """Insert a single rainfall record."""
        record = RainfallRecord(
            zona_operativa_id=zona_operativa_id,
            date=record_date,
            precipitation_mm=precipitation_mm,
            source=source,
        )
        db.add(record)
        db.flush()
        return record

    def bulk_upsert_rainfall(
        self,
        db: Session,
        records: list[dict[str, Any]],
    ) -> int:
        """Bulk upsert rainfall records using PostgreSQL ON CONFLICT.

        Each dict in records must have: zona_operativa_id, date, precipitation_mm, source.
        On conflict (zona_operativa_id, date, source), updates precipitation_mm.

        Returns the number of rows affected.
        """
        if not records:
            return 0

        stmt = pg_insert(RainfallRecord).values(records)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_rainfall_zona_date_source",
            set_={"precipitation_mm": stmt.excluded.precipitation_mm},
        )
        result = db.execute(stmt)
        db.flush()
        return result.rowcount
