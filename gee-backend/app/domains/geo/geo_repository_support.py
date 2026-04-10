"""Shared helper functions for the geo repository."""

from __future__ import annotations

import json as _json
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import case, func, literal, select
from sqlalchemy.orm import Session

from app.domains.geo.models import GeoApprovedZoning, GeoLayer, RainfallRecord


def paginated_results(
    db: Session,
    base_stmt,
    *,
    page: int,
    limit: int,
    order_by,
) -> tuple[list[Any], int]:
    """Execute a filtered select with count + paginated items."""
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total: int = db.execute(count_stmt).scalar_one()
    offset = (page - 1) * limit
    items_stmt = base_stmt.order_by(order_by).offset(offset).limit(limit)
    items = list(db.execute(items_stmt).scalars().all())
    return items, total


def approved_zoning_stmt(*, active_only: bool = False, cuenca: Optional[str] = None):
    """Build the base approved-zoning select with optional active/cuenca filters."""
    stmt = select(GeoApprovedZoning)
    if active_only:
        stmt = stmt.where(GeoApprovedZoning.is_active == True)  # noqa: E712
    if cuenca is None:
        stmt = stmt.where(GeoApprovedZoning.cuenca.is_(None))
    else:
        stmt = stmt.where(GeoApprovedZoning.cuenca == cuenca)
    return stmt


def round_rainfall_summary_row(row) -> dict[str, Any]:
    """Serialize an aggregated rainfall row to a response dict."""
    return {
        "zona_operativa_id": row.zona_operativa_id,
        "total_mm": round(float(row.total_mm or 0), 2),
        "avg_mm": round(float(row.avg_mm or 0), 2),
        "max_mm": round(float(row.max_mm or 0), 2),
        "rainy_days": int(row.rainy_days or 0),
    }


def rainfall_priority_case():
    return case(
        (RainfallRecord.source == "IMERG", literal(0)),
        else_=literal(1),
    )


def build_rainfall_summary_subquery(
    *,
    start_date: date,
    end_date: date,
    zona_operativa_id: Optional[uuid.UUID] = None,
    source: Optional[str] = None,
):
    """Return the deduplicated rainfall subquery used by summary/daily aggregations."""
    inner = (
        select(
            RainfallRecord.zona_operativa_id,
            RainfallRecord.date,
            RainfallRecord.precipitation_mm,
        )
        .where(
            RainfallRecord.date >= start_date,
            RainfallRecord.date <= end_date,
        )
        .distinct(RainfallRecord.zona_operativa_id, RainfallRecord.date)
        .order_by(
            RainfallRecord.zona_operativa_id,
            RainfallRecord.date,
            rainfall_priority_case().asc(),
        )
    )
    if source is not None:
        inner = inner.where(RainfallRecord.source == source)
    if zona_operativa_id is not None:
        inner = inner.where(RainfallRecord.zona_operativa_id == zona_operativa_id)
    return inner.subquery()


def build_rainfall_daily_subquery(
    *,
    start_date: date,
    end_date: date,
    source: Optional[str] = None,
):
    inner = (
        select(
            RainfallRecord.date,
            RainfallRecord.zona_operativa_id,
            RainfallRecord.precipitation_mm,
        )
        .where(
            RainfallRecord.date >= start_date,
            RainfallRecord.date <= end_date,
        )
        .distinct(RainfallRecord.date, RainfallRecord.zona_operativa_id)
        .order_by(
            RainfallRecord.date,
            RainfallRecord.zona_operativa_id,
            rainfall_priority_case().asc(),
        )
    )
    if source is not None:
        inner = inner.where(RainfallRecord.source == source)
    return inner.subquery()


def compute_raster_zone_features(
    db: Session,
    *,
    zona_id: uuid.UUID,
    zona_name: str,
    zona_wkt: str,
    logger,
) -> dict[str, Any]:
    """Extract DEM-derived raster stats for a zone."""
    from app.domains.geo.zonal_stats import compute_stats_for_zones

    features: dict[str, Any] = {}
    zone_data = [(str(zona_id), zona_wkt, zona_name)]

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
                _apply_raster_feature_stats(features, tipo, stats[0])
        except Exception:
            logger.warning(
                "extract_zone_features: failed raster stats for %s/%s",
                tipo,
                zona_id,
                exc_info=True,
            )

    return features


def _apply_raster_feature_stats(
    features: dict[str, Any], tipo: str, stats: dict[str, Any]
) -> None:
    if tipo == "hand":
        features["hand_mean"] = stats.get("mean", 0) or 0
        features["hand_max"] = stats.get("max", 0) or 0
    elif tipo == "twi":
        features["twi_mean"] = stats.get("mean", 0) or 0
    elif tipo == "slope":
        features["slope_mean"] = stats.get("mean", 0) or 0
    elif tipo == "flow_acc":
        import numpy as np

        raw_max = stats.get("max", 0) or 0
        features["flow_acc_log_max"] = float(np.log1p(raw_max))


def compute_water_zone_features(
    *, zona_geojson_str: Optional[str], event_date: date, zona_id: uuid.UUID, logger
) -> dict[str, Any]:
    """Extract current and historical water coverage features for a zone."""
    if not zona_geojson_str:
        return {}

    from app.domains.geo.water_detection import detect_water_from_gee

    geojson_geom = _json.loads(zona_geojson_str)
    features: dict[str, Any] = {}

    try:
        result = detect_water_from_gee(
            geojson_geom,
            event_date.isoformat(),
            days_window=15,
        )
        if result.get("status") == "success":
            features["water_pct_current"] = result["area"].get("water_pct", 0)
    except Exception:
        logger.warning(
            "extract_zone_features: water detection failed for %s",
            zona_id,
            exc_info=True,
        )

    try:
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
                    historical_pcts.append(hist_result["area"].get("water_pct", 0))
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
