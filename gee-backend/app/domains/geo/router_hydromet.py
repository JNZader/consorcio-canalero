"""Flood event listing, rainfall and NDWI baseline endpoints."""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.repository import GeoRepository
from app.domains.geo.router_common import (
    _get_repo,
    _require_admin,
    _require_authenticated,
    _require_operator,
)
from app.domains.geo.schemas import (
    BackfillRequest,
    NdwiBaselineComputeRequest,
    NdwiBaselineResponse,
)

logger = get_logger(__name__)
router = APIRouter(tags=["Geo Processing"])


@router.get("/flood-events")
def list_flood_events(
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """List all flood events ordered by event_date desc."""
    events = repo.list_flood_events(db)
    return [
        {
            "id": str(e["id"]),
            "event_date": str(e["event_date"]),
            "description": e["description"],
            "label_count": e["label_count"],
            "created_at": e["created_at"].isoformat(),
        }
        for e in events
    ]


@router.get("/flood-events/{event_id}")
def get_flood_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """Get a single flood event with all labels."""
    event = repo.get_flood_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Flood event not found")

    return {
        "id": str(event.id),
        "event_date": str(event.event_date),
        "description": event.description,
        "satellite_source": event.satellite_source,
        "labels": [
            {
                "id": str(lbl.id),
                "zona_id": str(lbl.zona_id),
                "is_flooded": lbl.is_flooded,
                "ndwi_value": lbl.ndwi_value,
                "extracted_features": lbl.extracted_features,
            }
            for lbl in event.labels
        ],
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat(),
    }


@router.delete("/flood-events/{event_id}", status_code=204)
def delete_flood_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Delete a flood event and all its labels (cascade)."""
    deleted = repo.delete_flood_event(db, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Flood event not found")
    db.commit()
    return Response(status_code=204)


@router.post("/rainfall/backfill", status_code=202)
def trigger_rainfall_backfill(
    payload: BackfillRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_admin()),
):
    """Trigger a rainfall backfill (admin only).

    Supports CHIRPS (long historical record) and IMERG (better extreme events).
    Enqueues a Celery task that processes data in monthly batches.
    Returns 202 with the Celery task ID for status polling.
    """
    from app.domains.geo.tasks import rainfall_backfill

    zona_ids_str = [str(z) for z in payload.zona_ids] if payload.zona_ids else None
    task = rainfall_backfill.delay(
        start_date=payload.start_date.isoformat(),
        end_date=payload.end_date.isoformat(),
        zona_ids=zona_ids_str,
        source=payload.source,
    )
    return {
        "job_id": task.id,
        "status": "accepted",
        "message": f"Backfill enqueued ({payload.source}) from {payload.start_date} to {payload.end_date}",
    }


@router.get("/rainfall/backfill/{task_id}")
def get_backfill_status(
    task_id: str,
    _user=Depends(_require_admin()),
):
    """Poll the status of a rainfall backfill Celery task.

    Returns:
        state: PENDING | PROGRESS | SUCCESS | FAILURE
        current, total: batch progress (only when state=PROGRESS)
        records: records upserted so far
        result: final summary (only when state=SUCCESS)
        error: error message (only when state=FAILURE)
    """
    from app.core.celery_app import celery_app as _celery

    result = _celery.AsyncResult(task_id)
    state = result.state

    if state == "PENDING":
        return {"state": "PENDING", "current": 0, "total": 0, "records": 0}

    if state == "PROGRESS":
        meta = result.info or {}
        return {
            "state": "PROGRESS",
            "current": meta.get("current", 0),
            "total": meta.get("total", 0),
            "records": meta.get("records", 0),
            "source": meta.get("source", "CHIRPS"),
        }

    if state == "SUCCESS":
        info = result.info or {}
        return {
            "state": "SUCCESS",
            "current": info.get("batches_processed", 0),
            "total": info.get("total_batches", 0),
            "records": info.get("total_records", 0),
            "errors": info.get("errors", []),
        }

    # FAILURE or REVOKED
    return {
        "state": state,
        "error": str(result.info) if result.info else "Task failed",
    }


@router.get("/rainfall/zones/{zone_id}")
def get_rainfall_for_zone(
    zone_id: uuid.UUID,
    start: Optional[date] = Query(None, description="Start date (inclusive)"),
    end: Optional[date] = Query(None, description="End date (inclusive)"),
    source: Optional[str] = Query(
        None,
        description="Filter by source: CHIRPS or IMERG. If omitted, IMERG takes priority over CHIRPS for the same day.",
    ),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Get daily rainfall records for a specific zone.

    Returns a list of {date, precipitation_mm, source} sorted by date ascending.
    When source is omitted, IMERG takes priority over CHIRPS for duplicate dates.
    """
    records = repo.get_rainfall_by_zone(
        db, zone_id, start_date=start, end_date=end, source=source
    )
    return {
        "zona_operativa_id": str(zone_id),
        "count": len(records),
        "records": [
            {
                "date": r.date.isoformat(),
                "precipitation_mm": r.precipitation_mm,
                "source": r.source,
            }
            for r in records
        ],
    }


@router.get("/rainfall/summary")
def get_rainfall_summary(
    start: date = Query(..., description="Start date (inclusive)"),
    end: date = Query(..., description="End date (inclusive)"),
    source: Optional[str] = Query(
        None,
        description="Filter by source: CHIRPS or IMERG. If omitted, IMERG takes priority over CHIRPS for the same day.",
    ),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Get rainfall summary across all zones for a date range.

    Returns per-zone aggregates: total_mm, avg_mm, max_mm, rainy_days.
    When source is omitted, IMERG takes priority over CHIRPS for duplicate dates.
    """
    from app.domains.geo.intelligence.models import ZonaOperativa

    summaries = repo.get_rainfall_summary(
        db, start_date=start, end_date=end, source=source
    )

    zona_ids = [s["zona_operativa_id"] for s in summaries]
    if zona_ids:
        zones = (
            db.query(ZonaOperativa.id, ZonaOperativa.nombre)
            .filter(ZonaOperativa.id.in_(zona_ids))
            .all()
        )
        name_map = {z.id: z.nombre for z in zones}
    else:
        name_map = {}

    for s in summaries:
        s["zona_name"] = name_map.get(s["zona_operativa_id"])
        s["zona_operativa_id"] = str(s["zona_operativa_id"])

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "source_filter": source,
        "zones": summaries,
    }


@router.get("/rainfall/daily")
def get_rainfall_daily(
    start: date = Query(..., description="Start date (inclusive)"),
    end: date = Query(..., description="End date (inclusive)"),
    source: Optional[str] = Query(
        None,
        description="Filter by source: CHIRPS or IMERG. If omitted, IMERG takes priority over CHIRPS for the same day.",
    ),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Get max daily rainfall across all zones (for calendar overlay).

    When source is omitted, IMERG takes priority over CHIRPS for duplicate dates.
    """
    return repo.get_rainfall_daily_max(
        db, start_date=start, end_date=end, source=source
    )


@router.get("/rainfall/events")
def get_rainfall_events(
    start: Optional[date] = Query(None, description="Start date (inclusive)"),
    end: Optional[date] = Query(None, description="End date (inclusive)"),
    threshold_mm: float = Query(
        50.0, ge=1.0, description="Precipitation threshold in mm"
    ),
    window_days: int = Query(3, ge=1, le=30, description="Rolling window in days"),
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Detect rainfall events where accumulated precipitation exceeds a threshold.

    Uses a rolling window over cached rainfall data — zero GEE dependency at query time.
    Returns detected events with affected zones and accumulated mm.
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events

    events = detect_rainfall_events(
        db,
        start_date=start,
        end_date=end,
        threshold_mm=threshold_mm,
        window_days=window_days,
    )

    # Enrich with zone names
    from app.domains.geo.intelligence.models import ZonaOperativa

    zona_ids = list({e["zona_operativa_id"] for e in events})
    name_map: dict = {}
    if zona_ids:
        zones = (
            db.query(ZonaOperativa.id, ZonaOperativa.nombre)
            .filter(ZonaOperativa.id.in_(zona_ids))
            .all()
        )
        name_map = {z.id: z.nombre for z in zones}

    return {
        "threshold_mm": threshold_mm,
        "window_days": window_days,
        "total": len(events),
        "events": [
            {
                "zona_operativa_id": str(e["zona_operativa_id"]),
                "zona_name": name_map.get(e["zona_operativa_id"]),
                "event_start": e["event_start"].isoformat(),
                "event_end": e["event_end"].isoformat(),
                "accumulated_mm": e["accumulated_mm"],
                "duration_days": e["duration_days"],
            }
            for e in events
        ],
    }


@router.get("/rainfall/suggestions")
def get_rainfall_suggestions(
    start: Optional[date] = Query(None, description="Start date (inclusive)"),
    end: Optional[date] = Query(None, description="End date (inclusive)"),
    threshold_mm: float = Query(
        50.0, ge=1.0, description="Precipitation threshold in mm"
    ),
    window_days: int = Query(3, ge=1, le=30, description="Rolling window in days"),
    days_after: int = Query(
        5, ge=1, le=15, description="Max days after event to search for S2 images"
    ),
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Detect rainfall events and suggest Sentinel-2 images for each.

    Combines event detection (cached PostgreSQL data) with GEE Sentinel-2
    catalog queries to recommend post-event imagery sorted by cloud cover.
    """
    from app.domains.geo.rainfall_service import (
        detect_rainfall_events,
        suggest_images_for_event,
    )

    events = detect_rainfall_events(
        db,
        start_date=start,
        end_date=end,
        threshold_mm=threshold_mm,
        window_days=window_days,
    )

    # Enrich with zone names
    from app.domains.geo.intelligence.models import ZonaOperativa

    zona_ids = list({e["zona_operativa_id"] for e in events})
    name_map: dict = {}
    if zona_ids:
        zones = (
            db.query(ZonaOperativa.id, ZonaOperativa.nombre)
            .filter(ZonaOperativa.id.in_(zona_ids))
            .all()
        )
        name_map = {z.id: z.nombre for z in zones}

    # For each event, find S2 image suggestions
    results = []
    for e in events:
        try:
            suggestions = suggest_images_for_event(
                e["event_end"],
                days_after_min=2,
                days_after_max=days_after,
            )
        except Exception:
            logger.warning(
                "Failed to get S2 suggestions for event %s-%s",
                e["event_start"],
                e["event_end"],
                exc_info=True,
            )
            suggestions = []

        best = suggestions[0] if suggestions else None

        results.append(
            {
                "zona_operativa_id": str(e["zona_operativa_id"]),
                "zona_name": name_map.get(e["zona_operativa_id"]),
                "event_start": e["event_start"].isoformat(),
                "event_end": e["event_end"].isoformat(),
                "accumulated_mm": e["accumulated_mm"],
                "duration_days": e["duration_days"],
                "suggested_image_date": (best["date"].isoformat() if best else None),
                "cloud_cover_pct": best["cloud_cover_pct"] if best else None,
                "all_suggestions": [
                    {
                        "date": s["date"].isoformat(),
                        "cloud_cover_pct": s["cloud_cover_pct"],
                    }
                    for s in suggestions
                ],
            }
        )

    return {
        "threshold_mm": threshold_mm,
        "window_days": window_days,
        "days_after": days_after,
        "total": len(results),
        "suggestions": results,
    }


# ──────────────────────────────────────────────
# NDWI BASELINE ENDPOINTS
# ──────────────────────────────────────────────


@router.post("/ndwi/baseline/compute", status_code=202)
def compute_ndwi_baseline(
    payload: NdwiBaselineComputeRequest,
    _user=Depends(_require_admin()),
):
    """Trigger NDWI dry-season baseline computation (admin only).

    Enqueues a Celery task that queries S2_SR_HARMONIZED for each zona
    over the requested dry-season months and years, computing mean and
    std NDWI per zone. Results are upserted to ndwi_baselines table.

    Returns 202 with the Celery task ID for status polling.
    """
    from app.domains.geo.tasks import compute_ndwi_baselines_task

    zona_ids_str = [str(z) for z in payload.zona_ids] if payload.zona_ids else None
    task = compute_ndwi_baselines_task.delay(
        zona_ids=zona_ids_str,
        dry_season_months=payload.dry_season_months,
        years_back=payload.years_back,
    )
    return {
        "job_id": task.id,
        "status": "accepted",
        "message": f"NDWI baseline computation enqueued for {payload.years_back} years of dry-season data",
    }


@router.get("/ndwi/baseline/status/{task_id}")
def get_ndwi_baseline_status(
    task_id: str,
    _user=Depends(_require_admin()),
):
    """Poll the status of a NDWI baseline computation task (admin only)."""
    from app.core.celery_app import celery_app as _celery

    result = _celery.AsyncResult(task_id)
    state = result.state

    if state == "PENDING":
        return {"state": "PENDING"}
    if state == "PROGRESS":
        return {"state": "PROGRESS", **(result.info or {})}
    if state == "SUCCESS":
        return {"state": "SUCCESS", **(result.info or {})}
    return {"state": state, "error": str(result.info) if result.info else "Task failed"}


@router.get("/ndwi/baseline", response_model=list[NdwiBaselineResponse])
def get_ndwi_baselines(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Get NDWI dry-season baselines for all zones (operator+).

    Use these baselines to compute z-scores at analysis time:
        z = (ndwi_observed - ndwi_mean) / ndwi_std
    """
    from app.domains.geo.models import NdwiBaseline
    from sqlalchemy import select

    return list(db.execute(select(NdwiBaseline)).scalars().all())
