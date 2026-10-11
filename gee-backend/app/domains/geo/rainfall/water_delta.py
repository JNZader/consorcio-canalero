"""Water hectares on zona_cc_ampliada for two operator-picked optical scenes.

Optical MNDWI ≥ 0.1 only. SAR pairs are not comparable. Not a classifier.
Stored pre/post slots are not the pair — those often prefer Sentinel-1.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Protocol, Sequence

from app.domains.geo.gee_service_imagery_support import LANDSAT_SENSORS


class SceneRow(Protocol):
    sensor: str
    scene_id: str
    scene_date: date
    slot: str


MNDWI_WATER = 0.1
DISCLAIMER = (
    "Agua = MNDWI ≥ 0.1 sobre zona_cc_ampliada. No es un clasificador ni un "
    "perímetro de inundación de campo. SAR no entra en el Δ."
)

S2_SPEC = {
    "collection": "COPERNICUS/S2_SR_HARMONIZED",
    "green": "B3",
    "swir": "B11",
    "scale": 30,
    "reflectance": 10000.0,
}

OPTICAL_SENSORS = frozenset({"sentinel2", "landsat9", "landsat8", "landsat7", "landsat5"})


def optical_spec(sensor: str) -> dict[str, Any] | None:
    if sensor == "sentinel2":
        return S2_SPEC
    meta = LANDSAT_SENSORS.get(sensor)
    if not meta or "mndwi" not in meta:
        return None
    green, swir = meta["mndwi"]
    return {
        "collection": meta["collection"],
        "green": green,
        "swir": swir,
        "scale": 30,
        "reflectance": 1.0,
    }


def resolve_pair_rows(
    rows: Sequence[SceneRow],
    pre_scene_id: str | None,
    post_scene_id: str | None,
) -> tuple[SceneRow | None, SceneRow | None]:
    """Look up the two scene ids the operator picked. First row wins on duplicates."""
    by_id: dict[str, SceneRow] = {}
    for row in rows:
        by_id.setdefault(row.scene_id, row)
    return by_id.get(pre_scene_id or ""), by_id.get(post_scene_id or "")


def pair_delta_payload(
    pre: SceneRow | None,
    post: SceneRow | None,
    *,
    water_ha: Callable[[SceneRow], float | None],
) -> dict[str, Any]:
    """Pure Δ. ``water_ha`` is the GEE (or test) seam."""
    base = {"disclaimer": DISCLAIMER, "method": "mndwi>=0.1", "zona": "zona_cc_ampliada"}
    if pre is None or post is None:
        return {**base, "comparable": False, "reason": "missing_pair"}
    pre_pub = _scene(pre)
    post_pub = _scene(post)
    if pre.sensor not in OPTICAL_SENSORS or post.sensor not in OPTICAL_SENSORS:
        return {
            **base,
            "comparable": False,
            "reason": "not_optical",
            "pre": pre_pub,
            "post": post_pub,
        }
    pre_ha = water_ha(pre)
    post_ha = water_ha(post)
    pre_pub["water_ha"] = pre_ha
    post_pub["water_ha"] = post_ha
    if pre_ha is None or post_ha is None:
        return {
            **base,
            "comparable": False,
            "reason": "scene_unavailable",
            "pre": pre_pub,
            "post": post_pub,
        }
    return {
        **base,
        "comparable": True,
        "reason": None,
        "pre": pre_pub,
        "post": post_pub,
        "delta_ha": round(post_ha - pre_ha, 2),
    }


def _scene(row: SceneRow) -> dict[str, Any]:
    return {
        "sensor": row.sensor,
        "scene_id": row.scene_id,
        "scene_date": row.scene_date.isoformat(),
        "slot": row.slot,
    }


def water_ha_from_gee(row: SceneRow) -> float | None:
    spec = optical_spec(row.sensor)
    if spec is None:
        return None
    import ee
    from app.domains.geo.rainfall.adapters.gee_client import GeeZonalClient

    client = GeeZonalClient()
    geom = client.geometry(scope_kind="provider_asset", scope_id="zona_cc_ampliada")
    collection = ee.ImageCollection(spec["collection"]).filter(
        ee.Filter.eq("system:index", row.scene_id)
    )
    if int(collection.size().getInfo() or 0) == 0:
        return None
    image = collection.first()
    green = image.select(spec["green"]).divide(spec["reflectance"])
    swir = image.select(spec["swir"]).divide(spec["reflectance"])
    mndwi = green.subtract(swir).divide(green.add(swir))
    water = mndwi.gte(MNDWI_WATER)
    raw = (
        water.multiply(ee.Image.pixelArea())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=spec["scale"],
            maxPixels=1e8,
            bestEffort=True,
        )
        .getInfo()
    )
    if not raw:
        return None
    metres = next((value for value in raw.values() if isinstance(value, (int, float))), None)
    if metres is None:
        return None
    return round(float(metres) / 10_000.0, 2)


def delta_for_event(
    pre: SceneRow | None,
    post: SceneRow | None,
) -> dict[str, Any]:
    return pair_delta_payload(pre, post, water_ha=water_ha_from_gee)
