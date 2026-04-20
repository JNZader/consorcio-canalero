"""Clip features to the ZONA CC AMPLIADA polygon using shapely.

The WFS BBOX filter returns whatever's in the envelope — we tighten with a
real intersection.  Features fully outside drop out; features straddling the
boundary get trimmed to the zona.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry


def _as_polygon(zona_polygon_feature: dict[str, Any]) -> BaseGeometry:
    if zona_polygon_feature.get("type") == "FeatureCollection":
        features = zona_polygon_feature.get("features") or []
        if not features:
            raise ValueError("zona FeatureCollection is empty")
        geom = features[0].get("geometry")
    elif zona_polygon_feature.get("type") == "Feature":
        geom = zona_polygon_feature.get("geometry")
    else:
        geom = zona_polygon_feature

    if geom is None:
        raise ValueError("zona polygon has no geometry")
    return shape(geom)


def clip_to_zona(
    features: list[dict[str, Any]],
    *,
    zona_polygon_feature: dict[str, Any],
) -> list[dict[str, Any]]:
    """Intersect each feature's geometry with the zona polygon.

    Features fully outside the zona are dropped; features crossing the boundary
    are trimmed.  Feature properties are preserved verbatim.
    """
    zona_geom = _as_polygon(zona_polygon_feature)

    kept: list[dict[str, Any]] = []
    for feature in features:
        geom = feature.get("geometry")
        if geom is None:
            continue
        feature_geom = shape(geom)
        if not feature_geom.intersects(zona_geom):
            continue
        if zona_geom.contains(feature_geom):
            kept.append(feature)
            continue
        clipped = feature_geom.intersection(zona_geom)
        if clipped.is_empty:
            continue
        kept.append(
            {
                "type": "Feature",
                "properties": feature.get("properties") or {},
                "geometry": mapping(clipped),
            }
        )
    return kept
