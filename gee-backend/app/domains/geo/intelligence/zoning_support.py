"""Support helpers for zoning suggestion generation."""

from __future__ import annotations

from typing import Any, Callable

from shapely.geometry import mapping, shape
from shapely.ops import unary_union


def basin_record(feature: dict[str, Any], extract_family: Callable[[str | None, str | None], str]) -> dict[str, Any]:
    props = feature.get("properties") or {}
    geom = shape(feature["geometry"])
    return {
        "id": props.get("id"),
        "nombre": props.get("nombre"),
        "cuenca": props.get("cuenca"),
        "family": extract_family(props.get("cuenca"), props.get("nombre")),
        "superficie_ha": float(props.get("superficie_ha") or 0.0),
        "geometry": geom,
        "centroid": geom.centroid,
    }


def display_basin_name(record: dict[str, Any], zone_name_by_id: dict[str, str], zone_id: str | None = None) -> str:
    import re

    raw_name = str(record.get("nombre") or "Sub-cuenca")
    zone_name = zone_name_by_id.get(zone_id or "", None)
    split_index = None
    if "::split-" in str(record.get("id") or ""):
        try:
            split_index = int(str(record["id"]).rsplit("::split-", 1)[1])
        except (TypeError, ValueError):
            split_index = None
    number_match = re.search(r"Sub-cuenca\s+(\d+)", raw_name, flags=re.IGNORECASE)
    basin_number = number_match.group(1) if number_match else None
    if split_index and basin_number:
        suffix = chr(ord("A") + split_index - 1)
        return f"Sub-cuenca {basin_number}{suffix} — {zone_name}" if zone_name else f"Sub-cuenca {basin_number}{suffix}"
    if basin_number and zone_name:
        return f"Sub-cuenca {basin_number} — {zone_name}"
    return re.sub(r"\s*\(([^)]+)\)", "", raw_name).strip()


def attach_zone_gaps(
    records: list[dict[str, Any]],
    consorcio_zone_geometry_fn: Callable[[], Any],
    iter_gap_polygons_fn: Callable[[Any], list[Any]],
) -> list[dict[str, Any]]:
    if not records:
        return records
    zona_geom = consorcio_zone_geometry_fn()
    if zona_geom is None:
        return records
    coverage = unary_union([record["geometry"] for record in records])
    total_surface_ha = sum(float(record["superficie_ha"]) for record in records)
    area_to_ha_factor = (total_surface_ha / coverage.area) if coverage.area > 0 else 0.0
    gap_polygons = [polygon for polygon in iter_gap_polygons_fn(zona_geom.difference(coverage)) if polygon.area > 0]
    if not gap_polygons:
        return records

    updated_records = [dict(record) for record in records]
    for gap in gap_polygons:
        best_index = None
        best_score = -1.0
        for index, record in enumerate(updated_records):
            if not (
                gap.touches(record["geometry"])
                or gap.distance(record["geometry"]) < 1e-9
                or gap.intersects(record["geometry"])
            ):
                continue
            shared = gap.boundary.intersection(record["geometry"].boundary)
            shared_length = shared.length if not shared.is_empty else 0.0
            if shared_length > best_score:
                best_score = shared_length
                best_index = index

        if best_index is None:
            best_index = min(
                range(len(updated_records)),
                key=lambda idx: gap.centroid.distance(updated_records[idx]["centroid"]),
            )

        target = updated_records[best_index]
        target_geometry = target["geometry"].union(gap)
        target["geometry"] = target_geometry
        target["centroid"] = target_geometry.centroid
        target["superficie_ha"] = float(target["superficie_ha"]) + (gap.area * area_to_ha_factor)

    return updated_records


def build_split_display_features(
    split_records: list[dict[str, Any]],
    assignments: dict[str, str],
    display_name_fn: Callable[[dict[str, Any], str | None], str],
) -> list[dict[str, Any]]:
    display_features: list[dict[str, Any]] = []
    for record in split_records:
        properties = {
            "id": record["id"],
            "nombre": display_name_fn(record, assignments.get(record["id"])),
            "cuenca": record["cuenca"],
            "superficie_ha": round(record["superficie_ha"], 1),
        }
        if record.get("source_basin_id"):
            properties["source_basin_id"] = record["source_basin_id"]
        if record.get("target_hint"):
            properties["target_hint"] = record["target_hint"]
        display_features.append(
            {
                "type": "Feature",
                "geometry": mapping(record["geometry"]),
                "properties": properties,
            }
        )
    return display_features
