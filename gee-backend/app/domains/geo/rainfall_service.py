"""
Rainfall service — CHIRPS daily precipitation via Google Earth Engine.

Fetches spatial-average rainfall per zona operativa using
ee.Image.reduceRegions() on the UCSB-CHG/CHIRPS/DAILY collection.
Backfill processes data in monthly batches to avoid GEE quota limits.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, timedelta
from typing import Any

import ee
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.geo.gee_service import _ensure_initialized
from app.domains.geo.intelligence.models import ZonaOperativa
from app.domains.geo.repository import GeoRepository

logger = logging.getLogger(__name__)

CHIRPS_COLLECTION = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_BAND = "precipitation"

repo = GeoRepository()


# ── Geometry helpers ────────────────────────────


def _postgis_to_ee_geometry(db: Session, zona_id: uuid.UUID) -> ee.Geometry | None:
    """Convert a PostGIS geometry to an ee.Geometry for GEE queries."""
    geojson_str = db.execute(
        select(ST_AsGeoJSON(ZonaOperativa.geometria)).where(
            ZonaOperativa.id == zona_id
        )
    ).scalar()
    if geojson_str is None:
        return None
    geojson = json.loads(geojson_str)
    return ee.Geometry(geojson)


def _load_zone_geometries(
    db: Session,
    zona_ids: list[uuid.UUID] | None = None,
) -> list[dict[str, Any]]:
    """Load zone IDs and their ee.Geometry objects.

    Returns list of dicts: {id, nombre, ee_geometry}.
    """
    stmt = select(
        ZonaOperativa.id,
        ZonaOperativa.nombre,
        ST_AsGeoJSON(ZonaOperativa.geometria).label("geojson"),
    )
    if zona_ids:
        stmt = stmt.where(ZonaOperativa.id.in_(zona_ids))

    rows = db.execute(stmt).all()
    zones = []
    for row in rows:
        geojson = json.loads(row.geojson)
        zones.append(
            {
                "id": row.id,
                "nombre": row.nombre,
                "ee_geometry": ee.Geometry(geojson),
            }
        )
    return zones


# ── CHIRPS fetch ────────────────────────────────


def fetch_chirps_daily(
    zones: list[dict[str, Any]],
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Query GEE CHIRPS/DAILY using reduceRegions() over zone geometries.

    Args:
        zones: List of dicts with 'id', 'nombre', 'ee_geometry' keys.
        start_date: Start of the date range (inclusive).
        end_date: End of the date range (inclusive).

    Returns:
        List of dicts: {zona_operativa_id, date, precipitation_mm, source}.
    """
    _ensure_initialized()

    # Build a FeatureCollection from zone geometries
    features = [
        ee.Feature(z["ee_geometry"], {"zona_id": str(z["id"])}) for z in zones
    ]
    zones_fc = ee.FeatureCollection(features)

    # GEE filterDate is exclusive on end
    end_exclusive = (end_date + timedelta(days=1)).isoformat()

    collection = (
        ee.ImageCollection(CHIRPS_COLLECTION)
        .filterDate(start_date.isoformat(), end_exclusive)
        .select(CHIRPS_BAND)
    )

    def _reduce_image(image: ee.Image) -> ee.FeatureCollection:
        """Reduce a single CHIRPS image over all zones."""
        img_date = ee.Date(image.get("system:time_start")).format("YYYY-MM-dd")
        reduced = image.reduceRegions(
            collection=zones_fc,
            reducer=ee.Reducer.mean(),
            scale=5566,  # ~0.05 deg CHIRPS native resolution
        )
        return reduced.map(lambda f: f.set("image_date", img_date))

    # Map over all images and flatten results
    all_results = collection.map(_reduce_image).flatten()
    result_info = all_results.getInfo()

    records: list[dict[str, Any]] = []
    if not result_info or "features" not in result_info:
        return records

    for feat in result_info["features"]:
        props = feat.get("properties", {})
        zona_id_str = props.get("zona_id")
        img_date_str = props.get("image_date")
        precip = props.get("mean")

        if zona_id_str and img_date_str and precip is not None:
            records.append(
                {
                    "zona_operativa_id": uuid.UUID(zona_id_str),
                    "date": date.fromisoformat(img_date_str),
                    "precipitation_mm": round(float(precip), 2),
                    "source": "CHIRPS",
                }
            )

    return records


# ── Backfill ────────────────────────────────────


def backfill_rainfall(
    db: Session,
    start_date: date,
    end_date: date,
    zona_ids: list[uuid.UUID] | None = None,
) -> dict[str, Any]:
    """Backfill rainfall data in monthly batches to avoid GEE quota issues.

    Processes one month at a time, calling fetch_chirps_daily() per batch,
    then bulk-upserting into the database.

    Args:
        db: SQLAlchemy session.
        start_date: Start of the backfill period.
        end_date: End of the backfill period.
        zona_ids: Optional list of specific zone IDs. If None, all zones.

    Returns:
        Summary dict: {total_records, batches_processed, errors}.
    """
    zones = _load_zone_geometries(db, zona_ids)
    if not zones:
        return {"total_records": 0, "batches_processed": 0, "errors": ["No zones found"]}

    total_records = 0
    batches_processed = 0
    errors: list[str] = []

    # Process in monthly batches (~30 days)
    batch_start = start_date
    while batch_start <= end_date:
        # End of current batch: either 30 days later or end_date
        batch_end = min(batch_start + timedelta(days=29), end_date)

        try:
            records = fetch_chirps_daily(zones, batch_start, batch_end)
            if records:
                count = repo.bulk_upsert_rainfall(db, records)
                total_records += count
                db.commit()
                logger.info(
                    "Backfill batch %s to %s: %d records upserted",
                    batch_start.isoformat(),
                    batch_end.isoformat(),
                    count,
                )
            batches_processed += 1

        except Exception as exc:
            error_msg = f"Batch {batch_start} to {batch_end} failed: {exc}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)
            db.rollback()

        # Move to next batch
        batch_start = batch_end + timedelta(days=1)

    return {
        "total_records": total_records,
        "batches_processed": batches_processed,
        "errors": errors,
    }
