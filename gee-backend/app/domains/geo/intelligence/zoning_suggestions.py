"""Helpers to generate editable draft zoning suggestions from basins."""

from __future__ import annotations

import re
from functools import lru_cache
from math import hypot
from typing import Any

from shapely.geometry import LineString, mapping, shape
from shapely.ops import split, unary_union

_ZONE_DEFINITIONS = {
    "draft-zone-norte": {
        "name": "Norte",
        "families": {"norte", "noroeste"},
        "color": "#1971c2",
    },
    "draft-zone-monte-lena": {
        "name": "Monte Leña",
        "families": {"ml"},
        "color": "#2b8a3e",
    },
    "draft-zone-candil": {
        "name": "Candil",
        "families": {"candil"},
        "color": "#e67700",
    },
}

_UNASSIGNED_TARGETS = ("draft-zone-monte-lena", "draft-zone-candil")
_SPECIAL_SPLIT_CUENCA = "sub_sin_asignar_9"
_SPECIAL_SPLIT_DIVIDER_COORDS = [
    (-62.5545096472, -32.5836607668933),
    (-62.5560625228, -32.5898658808026),
    (-62.5575208634, -32.5957160116114),
    (-62.5595894764999, -32.6040395152239),
    (-62.5600937946517, -32.606029174834),
]

_ZONE_NAME_BY_ID = {
    "draft-zone-norte": "Norte",
    "draft-zone-monte-lena": "Monte Leña",
    "draft-zone-candil": "Candil",
}


def extract_basin_family(cuenca: str | None, nombre: str | None = None) -> str:
    """Extract a readable basin family from current basin naming."""
    if cuenca:
        match = re.match(r"^sub_(.+)_\d+$", cuenca)
        if match:
            return match.group(1)
        return cuenca.replace("sub_", "")

    if nombre:
        lowered = nombre.lower()
        match = re.search(r"\(([^)]+)\)", lowered)
        if match:
            return match.group(1).strip()
        return lowered.strip().replace(" ", "_")

    return "sin_asignar"


def _basin_record(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties") or {}
    geom = shape(feature["geometry"])
    return {
        "id": props.get("id"),
        "nombre": props.get("nombre"),
        "cuenca": props.get("cuenca"),
        "family": extract_basin_family(props.get("cuenca"), props.get("nombre")),
        "superficie_ha": float(props.get("superficie_ha") or 0.0),
        "geometry": geom,
        "centroid": geom.centroid,
    }


def _display_basin_name(record: dict[str, Any], zone_id: str | None = None) -> str:
    """Return a cleaner operator-facing basin name."""
    raw_name = str(record.get("nombre") or "Sub-cuenca")
    zone_name = _ZONE_NAME_BY_ID.get(zone_id or "", None)

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
        if zone_name:
            return f"Sub-cuenca {basin_number}{suffix} — {zone_name}"
        return f"Sub-cuenca {basin_number}{suffix}"

    if basin_number and zone_name:
        return f"Sub-cuenca {basin_number} — {zone_name}"

    cleaned = re.sub(r"\s*\(([^)]+)\)", "", raw_name).strip()
    return cleaned


@lru_cache(maxsize=1)
def _special_split_divider() -> LineString | None:
    """Build the T391-06 divider line used to split sub-cuenca 9."""
    coords = list(_SPECIAL_SPLIT_DIVIDER_COORDS)
    if len(coords) < 2:
        return None

    start_x1, start_y1 = coords[0]
    start_x2, start_y2 = coords[1]
    start_dx, start_dy = start_x1 - start_x2, start_y1 - start_y2
    start_len = hypot(start_dx, start_dy)
    extended_start = (
        start_x1 + (0.05 * start_dx / start_len),
        start_y1 + (0.05 * start_dy / start_len),
    )

    end_x1, end_y1 = coords[-2]
    end_x2, end_y2 = coords[-1]
    end_dx, end_dy = end_x2 - end_x1, end_y2 - end_y1
    end_len = hypot(end_dx, end_dy)
    extended_end = (
        end_x2 + (0.05 * end_dx / end_len),
        end_y2 + (0.05 * end_dy / end_len),
    )

    return LineString([extended_start, *coords[1:-1], extended_end])


def _split_special_basin_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split sub-cuenca 9 with the user-approved T391-06 divider."""
    divider = _special_split_divider()
    if divider is None:
        return records

    ml_union = unary_union([record["geometry"] for record in records if record["family"] == "ml"])
    candil_union = unary_union(
        [record["geometry"] for record in records if record["family"] == "candil"]
    )
    if ml_union.is_empty or candil_union.is_empty:
        return records

    split_records: list[dict[str, Any]] = []
    for record in records:
        if record["cuenca"] != _SPECIAL_SPLIT_CUENCA:
            split_records.append(record)
            continue

        pieces = list(split(record["geometry"], divider).geoms)
        if len(pieces) < 2:
            split_records.append(record)
            continue

        for index, piece in enumerate(pieces, start=1):
            target_hint = (
                "candil"
                if piece.centroid.distance(candil_union.centroid)
                <= piece.centroid.distance(ml_union.centroid)
                else "ml"
            )
            split_records.append(
                {
                    "id": f"{record['id']}::split-{index}",
                    "source_basin_id": record["id"],
                    "nombre": f"{record['nombre']} - parte {index}",
                    "cuenca": record["cuenca"],
                    "family": "sin_asignar",
                    "target_hint": target_hint,
                    "superficie_ha": record["superficie_ha"] * (piece.area / record["geometry"].area),
                    "geometry": piece,
                    "centroid": piece.centroid,
                }
            )

    return split_records


@lru_cache(maxsize=1)
def _consorcio_zone_geometry():
    """Return the authoritative consorcio zone geometry from GEE."""
    from app.domains.geo.gee_service import get_layer_geojson

    zona_geojson = get_layer_geojson("zona")
    features = zona_geojson.get("features", [])
    if not features:
        return None
    return unary_union([shape(feature["geometry"]) for feature in features if feature.get("geometry")])


def _iter_gap_polygons(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return list(geom.geoms)
    return [part for part in getattr(geom, "geoms", []) if part.geom_type in {"Polygon", "MultiPolygon"}]


def _attach_zone_gaps(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach uncovered consorcio-zone gaps to the neighboring basin record."""
    if not records:
        return records

    zona_geom = _consorcio_zone_geometry()
    if zona_geom is None:
        return records

    coverage = unary_union([record["geometry"] for record in records])
    total_surface_ha = sum(float(record["superficie_ha"]) for record in records)
    area_to_ha_factor = (total_surface_ha / coverage.area) if coverage.area > 0 else 0.0
    gaps = zona_geom.difference(coverage)
    gap_polygons = [polygon for polygon in _iter_gap_polygons(gaps) if polygon.area > 0]
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


def split_basins_for_display(basin_features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return basin features with special visual splits applied."""
    if not basin_features:
        return []

    split_records = _attach_zone_gaps(
        _split_special_basin_records([_basin_record(feature) for feature in basin_features])
    )
    assignments = _resolve_zone_assignments(split_records)
    display_features: list[dict[str, Any]] = []

    for record in split_records:
        properties = {
            "id": record["id"],
            "nombre": _display_basin_name(record, assignments.get(record["id"])),
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


def _anchor_centroids(records: list[dict[str, Any]]) -> dict[str, Any]:
    anchors: dict[str, Any] = {}
    for zone_id, zone_def in _ZONE_DEFINITIONS.items():
        members = [record for record in records if record["family"] in zone_def["families"]]
        if not members:
            continue
        union_geom = unary_union([record["geometry"] for record in members])
        anchors[zone_id] = union_geom.centroid
    return anchors


def _assign_zone_id(record: dict[str, Any], anchors: dict[str, Any]) -> str:
    family = record["family"]
    target_hint = record.get("target_hint")
    for zone_id, zone_def in _ZONE_DEFINITIONS.items():
        if family in zone_def["families"]:
            return zone_id

    if family == "sin_asignar":
        if target_hint == "ml":
            return "draft-zone-monte-lena"
        if target_hint == "candil":
            return "draft-zone-candil"
        candidate_zone_ids = [zone_id for zone_id in _UNASSIGNED_TARGETS if zone_id in anchors]
        if candidate_zone_ids:
            return min(
                candidate_zone_ids,
                key=lambda zone_id: record["centroid"].distance(anchors[zone_id]),
            )

    candidate_zone_ids = list(anchors)
    if candidate_zone_ids:
        return min(
            candidate_zone_ids,
            key=lambda zone_id: record["centroid"].distance(anchors[zone_id]),
        )

    return "draft-zone-norte"


def _resolve_zone_assignments(records: list[dict[str, Any]]) -> dict[str, str]:
    """Assign each basin record to a target zone using family, hints and adjacency."""
    anchors = _anchor_centroids(records)
    assignments: dict[str, str] = {}

    for record in records:
        family = record["family"]
        if family in {"norte", "noroeste"}:
            assignments[record["id"]] = "draft-zone-norte"
        elif family == "ml":
            assignments[record["id"]] = "draft-zone-monte-lena"
        elif family == "candil":
            assignments[record["id"]] = "draft-zone-candil"
        elif record.get("target_hint") == "ml":
            assignments[record["id"]] = "draft-zone-monte-lena"
        elif record.get("target_hint") == "candil":
            assignments[record["id"]] = "draft-zone-candil"

    remaining_ids = {record["id"] for record in records if record["id"] not in assignments}

    while remaining_ids:
        progressed = False
        for record in records:
            record_id = record["id"]
            if record_id not in remaining_ids:
                continue

            neighbor_scores: dict[str, float] = {}
            for other in records:
                other_id = other["id"]
                if other_id == record_id or other_id not in assignments:
                    continue
                if not (
                    record["geometry"].touches(other["geometry"])
                    or record["geometry"].distance(other["geometry"]) < 1e-9
                ):
                    continue

                shared = record["geometry"].boundary.intersection(other["geometry"].boundary)
                shared_length = shared.length if not shared.is_empty else 0.0
                if shared_length <= 0:
                    continue
                zone_id = assignments[other_id]
                neighbor_scores[zone_id] = neighbor_scores.get(zone_id, 0.0) + shared_length

            if neighbor_scores:
                assignments[record_id] = max(neighbor_scores.items(), key=lambda item: item[1])[0]
                remaining_ids.remove(record_id)
                progressed = True

        if not progressed:
            for record in records:
                record_id = record["id"]
                if record_id in remaining_ids:
                    assignments[record_id] = _assign_zone_id(record, anchors)
            break

    return assignments


def suggest_grouped_zones(basin_features: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a territorial draft FeatureCollection from operational basins.

    Strategy v2:
    - Norte absorbs `norte` + `noroeste`
    - Monte Leña absorbs `ml`
    - Candil absorbs `candil`
    - `sin_asignar` basins are absorbed by the nearest anchor between
      Monte Leña and Candil so the southern/eastern leftovers join those
      operational areas instead of creating a separate manual zone.
    """
    if not basin_features:
        return {
            "type": "FeatureCollection",
            "features": [],
            "metadata": {
                "status": "draft",
                "suggestion_method": "fixed-three-zones-nearest-unassigned-v2",
                "zone_count": 0,
                "basin_count": 0,
                "zone_names": [],
            },
        }

    records = _attach_zone_gaps(
        _split_special_basin_records([_basin_record(feature) for feature in basin_features])
    )
    grouped: dict[str, list[dict[str, Any]]] = {zone_id: [] for zone_id in _ZONE_DEFINITIONS}
    assignments = _resolve_zone_assignments(records)
    for record in records:
        zone_id = assignments[record["id"]]
        grouped.setdefault(zone_id, []).append(record)

    draft_features: list[dict[str, Any]] = []
    for zone_id, zone_def in _ZONE_DEFINITIONS.items():
        members = grouped.get(zone_id) or []
        if not members:
            continue
        union_geom = unary_union([item["geometry"] for item in members])
        draft_features.append(
            {
                "type": "Feature",
                "geometry": mapping(union_geom),
                "properties": {
                    "draft_zone_id": zone_id,
                    "nombre": zone_def["name"],
                    "family": "+".join(sorted(zone_def["families"])),
                    "status": "draft",
                    "suggestion_method": "fixed-three-zones-nearest-unassigned-v2",
                    "superficie_ha": round(sum(item["superficie_ha"] for item in members), 1),
                    "basin_count": len(members),
                    "member_basin_ids": [item["id"] for item in members],
                    "member_basin_names": [
                        _display_basin_name(item, assignments.get(item["id"])) for item in members
                    ],
                    "member_basin_families": [item["family"] for item in members],
                    "__color": zone_def["color"],
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": draft_features,
        "metadata": {
            "status": "draft",
            "suggestion_method": "fixed-three-zones-nearest-unassigned-v2",
            "zone_count": len(draft_features),
            "basin_count": len(basin_features),
            "zone_names": [feature["properties"]["nombre"] for feature in draft_features],
        },
    }


def build_zones_from_assignments(
    basin_features: list[dict[str, Any]],
    *,
    basin_zone_assignments: dict[str, str] | None = None,
    zone_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build dissolved zone polygons from explicit basin→zone assignments."""

    manual_assignments = basin_zone_assignments or {}
    default_suggestion = suggest_grouped_zones(basin_features)
    zone_meta = {
        feature["properties"]["draft_zone_id"]: {
            "default_name": feature["properties"]["nombre"],
            "family": feature["properties"].get("family"),
            "color": feature["properties"].get("__color", "#1971c2"),
        }
        for feature in default_suggestion["features"]
    }

    effective_assignments: dict[str, str] = {}
    for feature in default_suggestion["features"]:
        zone_id = feature["properties"]["draft_zone_id"]
        for basin_id in feature["properties"].get("member_basin_ids", []):
            if isinstance(basin_id, str):
                effective_assignments[basin_id] = zone_id

    for basin_id, zone_id in manual_assignments.items():
        if basin_id in effective_assignments and zone_id in zone_meta:
            effective_assignments[basin_id] = zone_id

    grouped: dict[str, list[dict[str, Any]]] = {zone_id: [] for zone_id in zone_meta}
    for record in _attach_zone_gaps(
        _split_special_basin_records([_basin_record(feature) for feature in basin_features])
    ):
        zone_id = effective_assignments.get(record["id"])
        if zone_id is None and record.get("source_basin_id") in manual_assignments:
            zone_id = manual_assignments.get(record["source_basin_id"])
        if zone_id in grouped:
            grouped[zone_id].append(record)

    approved_features: list[dict[str, Any]] = []
    for zone_id, members in grouped.items():
        if not members:
            continue
        meta = zone_meta[zone_id]
        union_geom = unary_union([item["geometry"] for item in members])
        display_name = (zone_names or {}).get(zone_id, meta["default_name"]).strip() or meta["default_name"]
        approved_features.append(
            {
                "type": "Feature",
                "geometry": mapping(union_geom),
                "properties": {
                    "zone_id": zone_id,
                    "nombre": display_name,
                    "family": meta["family"],
                    "status": "approved-draft",
                    "source": "suggested-zones-editor",
                    "superficie_ha": round(sum(item["superficie_ha"] for item in members), 1),
                    "basin_count": len(members),
                    "member_basin_ids": [item["id"] for item in members],
                    "member_basin_names": [
                        _display_basin_name(item, zone_id) for item in members
                    ],
                    "__color": meta["color"],
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": approved_features,
        "metadata": {
            "status": "approved-draft",
            "zone_count": len(approved_features),
            "basin_count": len(basin_features),
            "source": "suggested-zones-editor",
        },
    }
