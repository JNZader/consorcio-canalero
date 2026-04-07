"""
Rainfall service — CHIRPS daily precipitation via Google Earth Engine.

Fetches spatial-average rainfall per zona operativa using
ee.Image.reduceRegions() on the UCSB-CHG/CHIRPS/DAILY collection.
Backfill processes data in monthly batches to avoid GEE quota limits.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import date, timedelta
from typing import Any, Callable

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

IMERG_COLLECTION = "NASA/GPM_L3/IMERG_V06"
IMERG_BAND = "precipitationCal"  # mm/hr, 30-min granules

repo = GeoRepository()


# ── Geometry helpers ────────────────────────────


def _postgis_to_ee_geometry(db: Session, zona_id: uuid.UUID) -> ee.Geometry | None:
    """Convert a PostGIS geometry to an ee.Geometry for GEE queries."""
    geojson_str = db.execute(
        select(ST_AsGeoJSON(ZonaOperativa.geometria)).where(ZonaOperativa.id == zona_id)
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
    _ensure_initialized()
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
    features = [ee.Feature(z["ee_geometry"], {"zona_id": str(z["id"])}) for z in zones]
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


def fetch_imerg_daily(
    zones: list[dict],
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Fetch daily precipitation totals from NASA IMERG V07.

    IMERG has 30-minute granules (precipitationCal in mm/hr).
    Daily total = sum(precipitationCal * 0.5) over all 48 half-hour images in a day.

    Better than CHIRPS for capturing intense convective events (storms).
    Availability: ~2000-present with ~3-week latency for the Final run.
    """
    _ensure_initialized()

    features = [ee.Feature(z["ee_geometry"], {"zona_id": str(z["id"])}) for z in zones]
    zones_fc = ee.FeatureCollection(features)

    n_days = (end_date - start_date).days  # exclusive end

    def _daily_image(n: ee.Number) -> ee.Image:
        day_start = ee.Date(start_date.isoformat()).advance(n, "day")
        day_end = day_start.advance(1, "day")
        # Merge a zero-image fallback so the collection is never empty.
        # This prevents reduce.sum from failing on days with no IMERG granules.
        zero = (
            ee.Image.constant(0)
            .rename(IMERG_BAND)
            .set("system:time_start", day_start.millis())
        )
        daily = (
            ee.ImageCollection(IMERG_COLLECTION)
            .filterDate(day_start, day_end)
            .select(IMERG_BAND)
            .merge(ee.ImageCollection([zero]))  # guarantees ≥1 image
            .sum()
            .multiply(0.5)  # mm/hr × 0.5 hr = mm per granule → sum = daily total mm
        )
        return daily.set("system:time_start", day_start.millis()).set(
            "date", day_start.format("YYYY-MM-dd")
        )

    daily_collection = ee.ImageCollection(ee.List.sequence(0, n_days).map(_daily_image))

    def _reduce_image(image: ee.Image) -> ee.FeatureCollection:
        img_date = image.get("date")
        reduced = image.reduceRegions(
            collection=zones_fc,
            reducer=ee.Reducer.mean(),
            scale=11132,  # ~0.1° IMERG native resolution
        )
        return reduced.map(lambda f: f.set("image_date", img_date))

    all_results = daily_collection.map(_reduce_image).flatten()
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
                    "source": "IMERG",
                }
            )

    return records


# ── Backfill ────────────────────────────────────


def backfill_rainfall(
    db: Session,
    start_date: date,
    end_date: date,
    zona_ids: list[uuid.UUID] | None = None,
    source: str = "CHIRPS",
    on_batch_complete: Callable[[int, int, int], None] | None = None,
) -> dict[str, Any]:
    """Backfill rainfall data in monthly batches to avoid GEE quota issues.

    Processes one month at a time, calling fetch_chirps_daily() or
    fetch_imerg_daily() per batch depending on the source parameter,
    then bulk-upserting into the database.

    Args:
        db: SQLAlchemy session.
        start_date: Start of the backfill period.
        end_date: End of the backfill period.
        zona_ids: Optional list of specific zone IDs. If None, all zones.
        source: "CHIRPS" (default) or "IMERG".
        on_batch_complete: Optional callback(current_batch, total_batches, total_records).
            Called after each batch completes (success or failure).

    Returns:
        Summary dict: {total_records, batches_processed, total_batches, errors}.
    """
    zones = _load_zone_geometries(db, zona_ids)
    if not zones:
        return {
            "total_records": 0,
            "batches_processed": 0,
            "total_batches": 0,
            "errors": ["No zones found"],
        }

    # Pre-compute total number of batches so progress % is available upfront
    total_days = (end_date - start_date).days + 1
    total_batches = math.ceil(total_days / 30)

    total_records = 0
    batches_processed = 0
    errors: list[str] = []

    fetch_fn = fetch_imerg_daily if source == "IMERG" else fetch_chirps_daily

    # Process in monthly batches (~30 days)
    batch_start = start_date
    while batch_start <= end_date:
        # End of current batch: either 30 days later or end_date
        batch_end = min(batch_start + timedelta(days=29), end_date)

        try:
            records = fetch_fn(zones, batch_start, batch_end)
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
            batches_processed += 1  # count failed batches too so progress keeps moving

        if on_batch_complete:
            on_batch_complete(batches_processed, total_batches, total_records)

        # Move to next batch
        batch_start = batch_end + timedelta(days=1)

    return {
        "total_records": total_records,
        "batches_processed": batches_processed,
        "total_batches": total_batches,
        "errors": errors,
    }


# ── Event detection ───────────────────────────


def detect_rainfall_events(
    db: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    threshold_mm: float = 50.0,
    window_days: int = 3,
) -> list[dict[str, Any]]:
    """Detect rainfall events where accumulated precipitation exceeds a threshold.

    For each zone and each date in the range, computes the rolling sum of
    precipitation over the previous ``window_days``. Dates where that sum
    exceeds ``threshold_mm`` are flagged, then consecutive flagged dates are
    clustered into single events.

    Returns a list of event dicts:
        {zona_operativa_id, event_start, event_end, accumulated_mm, duration_days}
    """
    from app.domains.geo.models import RainfallRecord

    # Default range: last 90 days
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=90)

    # We need records starting window_days *before* start_date for the
    # rolling window to be accurate on the first date.
    query_start = start_date - timedelta(days=window_days)

    # Fetch all records in the extended range, grouped by zone
    stmt = (
        select(RainfallRecord)
        .where(
            RainfallRecord.date >= query_start,
            RainfallRecord.date <= end_date,
        )
        .order_by(RainfallRecord.zona_operativa_id, RainfallRecord.date)
    )
    records = db.execute(stmt).scalars().all()

    # Group by zone
    from collections import defaultdict

    zone_records: dict[uuid.UUID, dict[date, float]] = defaultdict(dict)
    for rec in records:
        zone_records[rec.zona_operativa_id][rec.date] = rec.precipitation_mm

    events: list[dict[str, Any]] = []

    for zona_id, daily_map in zone_records.items():
        # For each date in the user-requested range, compute rolling sum
        flagged_dates: list[tuple[date, float]] = []
        current = start_date
        while current <= end_date:
            rolling_sum = 0.0
            for offset in range(window_days):
                day = current - timedelta(days=offset)
                rolling_sum += daily_map.get(day, 0.0)

            if rolling_sum >= threshold_mm:
                flagged_dates.append((current, rolling_sum))
            current += timedelta(days=1)

        if not flagged_dates:
            continue

        # Cluster consecutive flagged dates into events
        cluster_start = flagged_dates[0][0]
        cluster_max_acc = flagged_dates[0][1]
        prev_date = flagged_dates[0][0]

        for d, acc in flagged_dates[1:]:
            if (d - prev_date).days <= 1:
                # Continue cluster
                cluster_max_acc = max(cluster_max_acc, acc)
                prev_date = d
            else:
                # Close previous cluster
                duration = (prev_date - cluster_start).days + 1
                events.append(
                    {
                        "zona_operativa_id": zona_id,
                        "event_start": cluster_start,
                        "event_end": prev_date,
                        "accumulated_mm": round(cluster_max_acc, 2),
                        "duration_days": duration,
                    }
                )
                # Start new cluster
                cluster_start = d
                cluster_max_acc = acc
                prev_date = d

        # Close last cluster
        duration = (prev_date - cluster_start).days + 1
        events.append(
            {
                "zona_operativa_id": zona_id,
                "event_start": cluster_start,
                "event_end": prev_date,
                "accumulated_mm": round(cluster_max_acc, 2),
                "duration_days": duration,
            }
        )

    # Sort by event_start descending
    events.sort(key=lambda e: e["event_start"], reverse=True)
    return events


# ── Sentinel-2 image suggestions ──────────────


def suggest_images_for_event(
    event_end_date: date,
    *,
    days_after_min: int = 2,
    days_after_max: int = 5,
    max_cloud: int = 60,
) -> list[dict[str, Any]]:
    """Find Sentinel-2 images available after a rainfall event.

    Queries the GEE S2 catalog for images between ``event_end_date + days_after_min``
    and ``event_end_date + days_after_max``, filtered by cloud cover, and returns
    them sorted by cloud cover ascending (best candidates first).

    Reuses the same GEE pattern as ImageExplorer.get_available_dates().

    Returns list of dicts: {date, cloud_cover_pct}
    """
    _ensure_initialized()

    from app.domains.geo.gee_service import ImageExplorer

    explorer = ImageExplorer()

    search_start = event_end_date + timedelta(days=days_after_min)
    search_end = event_end_date + timedelta(days=days_after_max)
    end_exclusive = (search_end + timedelta(days=1)).isoformat()

    # Use SR collection for post-2019, TOA for earlier dates
    use_toa = search_start.year < 2019
    collection_name = (
        "COPERNICUS/S2_HARMONIZED" if use_toa else "COPERNICUS/S2_SR_HARMONIZED"
    )

    collection = (
        ee.ImageCollection(collection_name)
        .filterBounds(explorer.zona)
        .filterDate(search_start.isoformat(), end_exclusive)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
    )

    # Extract date and cloud cover for each image
    def _extract_info(image: ee.Image) -> ee.Feature:
        img_date = ee.Date(image.get("system:time_start")).format("YYYY-MM-dd")
        cloud = image.get("CLOUDY_PIXEL_PERCENTAGE")
        return ee.Feature(None, {"date": img_date, "cloud_cover_pct": cloud})

    info_fc = collection.map(_extract_info)
    result = info_fc.getInfo()

    suggestions: list[dict[str, Any]] = []
    if not result or "features" not in result:
        return suggestions

    # Deduplicate by date (keep lowest cloud cover per date)
    date_best: dict[str, float] = {}
    for feat in result["features"]:
        props = feat.get("properties", {})
        d = props.get("date")
        cc = props.get("cloud_cover_pct")
        if d and cc is not None:
            if d not in date_best or cc < date_best[d]:
                date_best[d] = cc

    for d_str, cc in sorted(date_best.items(), key=lambda x: x[1]):
        suggestions.append(
            {
                "date": date.fromisoformat(d_str),
                "cloud_cover_pct": round(float(cc), 2),
            }
        )

    return suggestions
