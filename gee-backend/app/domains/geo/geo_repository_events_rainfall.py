from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import case, func, literal, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domains.geo.geo_repository_support import (
    build_rainfall_daily_subquery,
    build_rainfall_summary_subquery,
    compute_raster_zone_features,
    compute_water_zone_features,
    round_rainfall_summary_row,
)
from app.domains.geo.models import FloodEvent, FloodLabel, RainfallRecord

logger = logging.getLogger(__name__)


class GeoRepositoryEventsRainfallMixin:
    def get_flood_event_by_id(
        self, db: Session, event_id: uuid.UUID
    ) -> Optional[FloodEvent]:
        from sqlalchemy.orm import joinedload

        stmt = (
            select(FloodEvent)
            .options(joinedload(FloodEvent.labels))
            .where(FloodEvent.id == event_id)
        )
        return db.execute(stmt).unique().scalar_one_or_none()

    def list_flood_events(self, db: Session) -> list[dict]:
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
        return [
            {
                "id": row.id,
                "event_date": row.event_date,
                "description": row.description,
                "label_count": row.label_count,
                "created_at": row.created_at,
            }
            for row in db.execute(stmt).all()
        ]

    def create_flood_event(
        self,
        db: Session,
        *,
        event_date: date,
        description: Optional[str] = None,
        labels: list[dict],
    ) -> FloodEvent:
        event = FloodEvent(event_date=event_date, description=description)
        db.add(event)
        db.flush()
        for label_data in labels:
            db.add(
                FloodLabel(
                    event_id=event.id,
                    zona_id=label_data["zona_id"],
                    is_flooded=label_data["is_flooded"],
                )
            )
        db.flush()
        return event

    def delete_flood_event(self, db: Session, event_id: uuid.UUID) -> bool:
        event = self.get_flood_event_by_id(db, event_id)
        if event is None:
            return False
        db.delete(event)
        db.flush()
        return True

    def update_label_features(
        self, db: Session, label_id: uuid.UUID, features: dict[str, Any]
    ) -> None:
        label = db.execute(
            select(FloodLabel).where(FloodLabel.id == label_id)
        ).scalar_one_or_none()
        if label is not None:
            label.extracted_features = features
            db.flush()

    def get_labels_with_features(self, db: Session) -> list[FloodLabel]:
        from sqlalchemy.orm import joinedload

        stmt = (
            select(FloodLabel)
            .options(joinedload(FloodLabel.event))
            .where(FloodLabel.extracted_features.isnot(None))
        )
        return list(db.execute(stmt).scalars().all())

    def extract_zone_features(
        self, db: Session, zona_id: uuid.UUID, event_date: date
    ) -> dict[str, Any]:
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
        features = compute_raster_zone_features(
            db, zona_id=zona.id, zona_name=zona.nombre, zona_wkt=zona_wkt, logger=logger
        )
        features.update(
            compute_water_zone_features(
                zona_geojson_str=zona_geojson_str,
                event_date=event_date,
                zona_id=zona_id,
                logger=logger,
            )
        )
        try:
            features["rainfall_48h"] = self.get_accumulated_rainfall(
                db, zona_id, event_date, window_days=2
            )
            features["rainfall_7d"] = self.get_accumulated_rainfall(
                db, zona_id, event_date, window_days=7
            )
            features["rainfall_30d"] = self.get_accumulated_rainfall(
                db, zona_id, event_date, window_days=30
            )
        except Exception:
            logger.warning(
                "extract_zone_features: rainfall query failed for %s",
                zona_id,
                exc_info=True,
            )
        return features

    def _best_source_subquery(self, source: Optional[str] = None):
        if source is not None:
            return (
                select(RainfallRecord).where(RainfallRecord.source == source).subquery()
            )
        return text("""
            SELECT DISTINCT ON (zona_operativa_id, date)
                id, zona_operativa_id, date, precipitation_mm, source, created_at
            FROM rainfall_records
            ORDER BY zona_operativa_id, date, (source = 'IMERG') DESC
        """)

    def get_rainfall_by_zone(
        self,
        db: Session,
        zona_operativa_id: uuid.UUID,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        source: Optional[str] = None,
    ) -> list[RainfallRecord]:
        stmt = select(RainfallRecord).where(
            RainfallRecord.zona_operativa_id == zona_operativa_id
        )
        if source is not None:
            stmt = stmt.where(RainfallRecord.source == source)
        if start_date is not None:
            stmt = stmt.where(RainfallRecord.date >= start_date)
        if end_date is not None:
            stmt = stmt.where(RainfallRecord.date <= end_date)
        if source is None:
            stmt = stmt.distinct(RainfallRecord.date).order_by(
                RainfallRecord.date.asc(),
                case(
                    (RainfallRecord.source == "IMERG", literal(0)), else_=literal(1)
                ).asc(),
            )
        else:
            stmt = stmt.order_by(RainfallRecord.date.asc())
        return list(db.execute(stmt).scalars().all())

    def get_rainfall_summary(
        self,
        db: Session,
        *,
        start_date: date,
        end_date: date,
        zona_operativa_id: Optional[uuid.UUID] = None,
        source: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        sub = build_rainfall_summary_subquery(
            start_date=start_date,
            end_date=end_date,
            zona_operativa_id=zona_operativa_id,
            source=source,
        )
        stmt = select(
            sub.c.zona_operativa_id,
            func.sum(sub.c.precipitation_mm).label("total_mm"),
            func.avg(sub.c.precipitation_mm).label("avg_mm"),
            func.max(sub.c.precipitation_mm).label("max_mm"),
            func.count(func.nullif(sub.c.precipitation_mm > 0, False)).label(
                "rainy_days"
            ),
        ).group_by(sub.c.zona_operativa_id)
        return [round_rainfall_summary_row(row) for row in db.execute(stmt).all()]

    def get_rainfall_daily_max(
        self,
        db: Session,
        *,
        start_date: date,
        end_date: date,
        source: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        sub = build_rainfall_daily_subquery(
            start_date=start_date, end_date=end_date, source=source
        )
        stmt = (
            select(sub.c.date, func.max(sub.c.precipitation_mm).label("max_mm"))
            .group_by(sub.c.date)
            .order_by(sub.c.date)
        )
        return [
            {
                "date": row.date.isoformat(),
                "precipitation_mm": round(float(row.max_mm or 0), 2),
            }
            for row in db.execute(stmt).all()
        ]

    def get_accumulated_rainfall(
        self,
        db: Session,
        zona_operativa_id: uuid.UUID,
        reference_date: date,
        window_days: int,
    ) -> float:
        start = reference_date - timedelta(days=window_days)
        stmt = select(
            func.coalesce(func.sum(RainfallRecord.precipitation_mm), 0.0)
        ).where(
            RainfallRecord.zona_operativa_id == zona_operativa_id,
            RainfallRecord.date > start,
            RainfallRecord.date <= reference_date,
        )
        return float(db.execute(stmt).scalar_one())

    def insert_rainfall_record(
        self,
        db: Session,
        *,
        zona_operativa_id: uuid.UUID,
        record_date: date,
        precipitation_mm: float,
        source: str = "CHIRPS",
    ) -> RainfallRecord:
        record = RainfallRecord(
            zona_operativa_id=zona_operativa_id,
            date=record_date,
            precipitation_mm=precipitation_mm,
            source=source,
        )
        db.add(record)
        db.flush()
        return record

    def bulk_upsert_rainfall(self, db: Session, records: list[dict[str, Any]]) -> int:
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
