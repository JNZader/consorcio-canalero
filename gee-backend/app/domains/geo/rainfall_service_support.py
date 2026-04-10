"""Support helpers for rainfall service geometry loading and event processing."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from typing import Any


def postgis_to_ee_geometry_impl(
    *,
    db,
    select_fn,
    st_as_geojson,
    zona_model,
    json_module,
    ee_module,
    zona_id: uuid.UUID,
):
    geojson_str = db.execute(
        select_fn(st_as_geojson(zona_model.geometria)).where(zona_model.id == zona_id)
    ).scalar()
    if geojson_str is None:
        return None
    return ee_module.Geometry(json_module.loads(geojson_str))


def load_zone_geometries_impl(
    *,
    db,
    ensure_initialized,
    select_fn,
    st_as_geojson,
    zona_model,
    json_module,
    ee_module,
    zona_ids=None,
) -> list[dict[str, Any]]:
    stmt = select_fn(
        zona_model.id,
        zona_model.nombre,
        st_as_geojson(zona_model.geometria).label("geojson"),
    )
    if zona_ids:
        stmt = stmt.where(zona_model.id.in_(zona_ids))
    rows = db.execute(stmt).all()
    return [
        {
            "id": row.id,
            "nombre": row.nombre,
            "ee_geometry": ee_module.Geometry(json_module.loads(row.geojson)),
        }
        for row in rows
    ]


def build_reduce_regions_records(
    *, result_info, date_type, uuid_type, source: str
) -> list[dict[str, Any]]:
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
                    "zona_operativa_id": uuid_type(zona_id_str),
                    "date": date_type.fromisoformat(img_date_str),
                    "precipitation_mm": round(float(precip), 2),
                    "source": source,
                }
            )
    return records


def run_backfill_impl(
    *,
    db,
    load_zones,
    start_date: date,
    end_date: date,
    zona_ids,
    source: str,
    fetch_chirps,
    fetch_imerg,
    repo,
    logger,
    timedelta_cls,
    math_module,
    on_batch_complete=None,
) -> dict[str, Any]:
    zones = load_zones(db, zona_ids)
    if not zones:
        return {
            "total_records": 0,
            "batches_processed": 0,
            "total_batches": 0,
            "errors": ["No zones found"],
        }

    total_days = (end_date - start_date).days + 1
    total_batches = math_module.ceil(total_days / 30)
    total_records = 0
    batches_processed = 0
    errors: list[str] = []
    fetch_fn = fetch_imerg if source == "IMERG" else fetch_chirps
    batch_start = start_date
    while batch_start <= end_date:
        batch_end = min(batch_start + timedelta_cls(days=29), end_date)
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
            batches_processed += 1
        if on_batch_complete:
            on_batch_complete(batches_processed, total_batches, total_records)
        batch_start = batch_end + timedelta_cls(days=1)
    return {
        "total_records": total_records,
        "batches_processed": batches_processed,
        "total_batches": total_batches,
        "errors": errors,
    }


def detect_rainfall_events_impl(
    *,
    records,
    start_date: date,
    end_date: date,
    threshold_mm: float,
    window_days: int,
    timedelta_cls,
) -> list[dict[str, Any]]:
    zone_records: dict[uuid.UUID, dict[date, float]] = defaultdict(dict)
    for rec in records:
        zone_records[rec.zona_operativa_id][rec.date] = rec.precipitation_mm

    events: list[dict[str, Any]] = []
    for zona_id, daily_map in zone_records.items():
        flagged_dates: list[tuple[date, float]] = []
        current = start_date
        while current <= end_date:
            rolling_sum = 0.0
            for offset in range(window_days):
                day = current - timedelta_cls(days=offset)
                rolling_sum += daily_map.get(day, 0.0)
            if rolling_sum >= threshold_mm:
                flagged_dates.append((current, rolling_sum))
            current += timedelta_cls(days=1)
        if not flagged_dates:
            continue
        cluster_start = flagged_dates[0][0]
        cluster_max_acc = flagged_dates[0][1]
        prev_date = flagged_dates[0][0]
        for d, acc in flagged_dates[1:]:
            if (d - prev_date).days <= 1:
                cluster_max_acc = max(cluster_max_acc, acc)
                prev_date = d
            else:
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
                cluster_start = d
                cluster_max_acc = acc
                prev_date = d
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
    events.sort(key=lambda e: e["event_start"], reverse=True)
    return events


def build_image_suggestions_impl(
    *, result, event_end_date: date, date_type
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    if not result or "features" not in result:
        return suggestions
    date_best: dict[str, float] = {}
    for feat in result["features"]:
        props = feat.get("properties", {})
        d = props.get("date")
        cc = props.get("cloud_cover_pct")
        if d and cc is not None and (d not in date_best or cc < date_best[d]):
            date_best[d] = cc
    for d_str, cc in sorted(date_best.items(), key=lambda x: x[1]):
        suggestions.append(
            {
                "date": date_type.fromisoformat(d_str),
                "cloud_cover_pct": round(float(cc), 2),
            }
        )
    return suggestions
