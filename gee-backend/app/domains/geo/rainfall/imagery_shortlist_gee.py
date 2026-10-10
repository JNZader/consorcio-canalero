"""Earth Engine metadata lister for the imagery shortlist CLI.

Kept out of ``imagery_shortlist.py`` so unit tests never import ``ee``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.domains.geo.rainfall.imagery_shortlist import SceneHit

_explorer = None


def _explorer_cached():
    global _explorer
    if _explorer is None:
        from app.domains.geo.gee_service import get_image_explorer

        _explorer = get_image_explorer()
    return _explorer


def _ms_to_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    ms = float(value)
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).date()


def list_gee_scenes(sensor: str, start: date, end: date) -> list[SceneHit]:
    """Inclusive ``end``. Scene-level cloud only."""
    explorer = _explorer_cached()
    end_exclusive = end + timedelta(days=1)
    cloud_key: str | None
    if sensor == "sentinel2":
        _name, collection = explorer._sentinel2_collection(
            start, end_exclusive, 80, use_toa=False
        )
        cloud_key = "CLOUDY_PIXEL_PERCENTAGE"
    elif sensor == "sentinel1":
        collection = explorer._sentinel1_collection(start, end_exclusive)
        cloud_key = None
    elif sensor in {"landsat8", "landsat7", "landsat5"}:
        collection = explorer._landsat_collection(sensor, start, end_exclusive, 80)
        cloud_key = "CLOUD_COVER"
    else:
        return []

    collection = collection.limit(40)
    indexes = collection.aggregate_array("system:index").getInfo() or []
    starts = collection.aggregate_array("system:time_start").getInfo() or []
    clouds = (
        collection.aggregate_array(cloud_key).getInfo() if cloud_key else [None] * len(indexes)
    )
    hits: list[SceneHit] = []
    for scene_id, start_ms, cloud in zip(indexes, starts, clouds, strict=False):
        scene_date = _ms_to_date(start_ms)
        if scene_date is None or not scene_id:
            continue
        cloud_pct = None if cloud is None else float(cloud)
        hits.append(
            SceneHit(
                sensor=sensor,
                scene_id=str(scene_id),
                scene_date=scene_date,
                cloud_pct=cloud_pct,
            )
        )
    return hits
