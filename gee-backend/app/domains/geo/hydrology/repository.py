"""Repository layer — all database access for the hydrology subdomain."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domains.geo.hydrology.models import FloodFlowResult


class FloodFlowRepository:
    """Data-access layer for FloodFlowResult entities."""

    def upsert(
        self,
        db: Session,
        zona_id: uuid.UUID,
        fecha_lluvia: date,
        data: dict[str, Any],
    ) -> FloodFlowResult:
        """Insert or update a flood flow result for (zona_id, fecha_lluvia).

        If a record with the same zona_id + fecha_lluvia already exists, its
        fields are updated in-place. Otherwise a new record is inserted.

        Args:
            db: SQLAlchemy session.
            zona_id: Target operational zone ID.
            fecha_lluvia: Rainfall event date (unique key together with zona_id).
            data: Dict of column values to set (all non-key FloodFlowResult fields).

        Returns:
            The created or updated FloodFlowResult ORM instance (not yet committed).
        """
        stmt = select(FloodFlowResult).where(
            FloodFlowResult.zona_id == zona_id,
            FloodFlowResult.fecha_lluvia == fecha_lluvia,
        )
        existing = db.execute(stmt).scalar_one_or_none()

        if existing is not None:
            for key, value in data.items():
                setattr(existing, key, value)
            db.flush()
            return existing

        record = FloodFlowResult(
            zona_id=zona_id,
            fecha_lluvia=fecha_lluvia,
            **data,
        )
        db.add(record)
        db.flush()
        return record

    def get_by_zona(
        self,
        db: Session,
        zona_id: uuid.UUID,
        limit: int = 10,
    ) -> list[FloodFlowResult]:
        """Return the most recent flood flow records for a zone.

        Args:
            db: SQLAlchemy session.
            zona_id: Target operational zone ID.
            limit: Maximum number of records to return (default 10).

        Returns:
            List of FloodFlowResult ordered by fecha_lluvia descending.
        """
        stmt = (
            select(FloodFlowResult)
            .where(FloodFlowResult.zona_id == zona_id)
            .order_by(FloodFlowResult.fecha_lluvia.desc())
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    def get_latest_by_all_zonas(
        self,
        db: Session,
        fecha: date,
    ) -> list[FloodFlowResult]:
        """Return the latest flood flow record per zone where fecha_lluvia <= fecha.

        Uses a subquery to find the maximum fecha_lluvia per zone up to ``fecha``,
        then joins back to retrieve the full records.

        Args:
            db: SQLAlchemy session.
            fecha: Upper bound date (inclusive).

        Returns:
            List of FloodFlowResult (one per zone), ordered by zona_id.
        """
        from sqlalchemy import func

        latest_per_zona = (
            select(
                FloodFlowResult.zona_id,
                func.max(FloodFlowResult.fecha_lluvia).label("max_fecha"),
            )
            .where(FloodFlowResult.fecha_lluvia <= fecha)
            .group_by(FloodFlowResult.zona_id)
            .subquery()
        )

        stmt = (
            select(FloodFlowResult)
            .join(
                latest_per_zona,
                (FloodFlowResult.zona_id == latest_per_zona.c.zona_id)
                & (FloodFlowResult.fecha_lluvia == latest_per_zona.c.max_fecha),
            )
            .order_by(FloodFlowResult.zona_id)
        )
        return list(db.execute(stmt).scalars().all())

    def get_annual_maxima(
        self,
        db: Session,
        zona_id: uuid.UUID,
    ) -> list[dict]:
        """Return annual maximum daily precipitation per year for a zona.

        Uses CHIRPS/IMERG rainfall_records with IMERG priority (DISTINCT ON).
        """
        sql = text("""
            WITH deduped AS (
                SELECT DISTINCT ON (date)
                    date,
                    precipitation_mm
                FROM rainfall_records
                WHERE zona_operativa_id = :zona_id
                ORDER BY date,
                         CASE WHEN source = 'IMERG' THEN 0 ELSE 1 END
            )
            SELECT
                EXTRACT(YEAR FROM date)::int AS year,
                MAX(precipitation_mm)        AS max_mm
            FROM deduped
            GROUP BY EXTRACT(YEAR FROM date)
            ORDER BY year
        """)
        rows = db.execute(sql, {"zona_id": str(zona_id)}).mappings().all()
        return [{"year": r["year"], "max_mm": float(r["max_mm"])} for r in rows]
