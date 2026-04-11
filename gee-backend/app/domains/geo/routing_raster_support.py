"""Raster corridor helpers for real multi-criteria routing."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, mapping, shape
from shapely.ops import transform as shapely_transform
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.domains.geo.intelligence.calculations import (
    cost_distance,
    generate_cost_surface,
    least_cost_path,
)
from app.domains.geo.models import GeoLayer

RASTER_COMPONENT_KEYS = ("slope", "twi", "roads", "property", "canals")

RASTER_PROFILE_WEIGHTS = {
    "balanceado":       {"slope": 0.20, "twi": 0.30, "roads": 0.20, "property": 0.15, "canals": 0.15},
    "hidraulico":       {"slope": 0.15, "twi": 0.45, "roads": 0.15, "property": 0.10, "canals": 0.15},
    "evitar_propiedad": {"slope": 0.15, "twi": 0.20, "roads": 0.15, "property": 0.40, "canals": 0.10},
}


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(value, 0.0) for value in weights.values())
    if total <= 0:
        return dict(RASTER_PROFILE_WEIGHTS["balanceado"])
    return {key: round(max(value, 0.0) / total, 4) for key, value in weights.items()}


def _resolve_raster_profile_weights(
    profile: str,
    weight_overrides: dict[str, float | None] | None = None,
) -> dict[str, float]:
    weights = dict(
        RASTER_PROFILE_WEIGHTS.get(profile, RASTER_PROFILE_WEIGHTS["balanceado"])
    )
    if weight_overrides:
        # Accept legacy keys: hydric→twi, landcover→canals
        legacy_map = {"hydric": "twi", "landcover": "canals"}
        for key, value in weight_overrides.items():
            if value is None:
                continue
            mapped = legacy_map.get(key, key)
            if mapped in RASTER_COMPONENT_KEYS:
                weights[mapped] = float(value)
    return _normalize_weights(weights)


def _resolve_layer_path(layer: GeoLayer) -> str:
    metadata = layer.metadata_extra or {}
    for candidate in (metadata.get("cog_path"), layer.archivo_path):
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise NotFoundError(f"Geo raster not found for layer {layer.id}")


def get_latest_slope_raster_path(db: Session, area_id: str | None = None) -> str:
    query = db.query(GeoLayer).filter(GeoLayer.tipo == "slope")
    if area_id:
        query = query.filter(GeoLayer.area_id == area_id)
    layer = query.order_by(GeoLayer.created_at.desc()).first()
    if layer is None and area_id is None:
        raise NotFoundError(
            "No slope raster layer available for raster corridor routing"
        )
    if layer is None:
        raise NotFoundError(
            f"No slope raster layer available for area_id={area_id!r}"
        )
    return _resolve_layer_path(layer)


def get_latest_twi_raster_path(db: Session, area_id: str | None = None) -> str | None:
    """Return the most recent TWI raster path, or None if not available.

    TWI is optional in the cost surface — if no TWI raster exists for the
    requested area, the surface falls back to slope-only behaviour.
    """
    query = db.query(GeoLayer).filter(GeoLayer.tipo == "twi")
    if area_id:
        query = query.filter(GeoLayer.area_id == area_id)
    layer = query.order_by(GeoLayer.created_at.desc()).first()
    if layer is None:
        return None
    try:
        return _resolve_layer_path(layer)
    except NotFoundError:
        return None


def _vector_shapes_for_raster(
    db: Session,
    sql: str,
    *,
    srid: int,
    value_key: str,
) -> list[tuple[dict[str, Any], float]]:
    rows = db.execute(text(sql), {"srid": srid}).mappings()
    shapes: list[tuple[dict[str, Any], float]] = []
    for row in rows:
        geometry = row.get("geometry")
        value = row.get(value_key)
        if geometry is None or value is None:
            continue
        shapes.append((geometry, float(value)))
    return shapes


def build_multicriteria_cost_surface(
    db: Session,
    slope_raster_path: str,
    output_path: str,
    *,
    profile: str,
    weight_overrides: dict[str, float | None] | None = None,
    twi_raster_path: str | None = None,
) -> tuple[str, dict[str, Any]]:
    import rasterio
    from rasterio.features import rasterize

    base_cost_path = str(
        Path(output_path).with_name(f"{Path(output_path).stem}_base.tif")
    )
    generate_cost_surface(slope_raster_path, base_cost_path)

    with rasterio.open(base_cost_path) as src:
        data = src.read(1).astype(np.float32)
        meta = src.meta.copy()
        transform = src.transform
        raster_crs = src.crs
        nodata = float(src.nodata if src.nodata is not None else -9999.0)
        valid_mask = np.isfinite(data) & (data != nodata)

    if not np.any(valid_mask):
        raise ValueError("Cost surface contains only nodata")

    srid = int(raster_crs.to_epsg() or 4326) if raster_crs else 4326
    weights = _resolve_raster_profile_weights(profile, weight_overrides)
    meta_breakdown: dict[str, Any] = {
        "mode": "raster",
        "weights": weights,
        "property_features": 0,
        "roads_features": 0,
        "canals_features": 0,
        "twi_used": False,
    }

    # ── Component 1: TWI per-pixel (attractor for natural drainage paths) ─────
    twi_norm = np.zeros_like(data, dtype=np.float32)
    if twi_raster_path and weights.get("twi", 0) > 0:
        try:
            with rasterio.open(twi_raster_path) as twi_src:
                twi_data = twi_src.read(
                    1,
                    out_shape=data.shape,
                    resampling=rasterio.enums.Resampling.bilinear,
                ).astype(np.float32)
                twi_nodata = twi_src.nodata
            twi_valid = np.isfinite(twi_data)
            if twi_nodata is not None:
                twi_valid &= twi_data != twi_nodata
            if np.any(twi_valid):
                lo = float(np.percentile(twi_data[twi_valid], 5))
                hi = float(np.percentile(twi_data[twi_valid], 95))
                if hi > lo:
                    twi_norm = np.clip((twi_data - lo) / (hi - lo), 0.0, 1.0)
                    twi_norm[~twi_valid] = 0.0
                    meta_breakdown["twi_used"] = True
                    meta_breakdown["twi_range"] = [round(lo, 2), round(hi, 2)]
        except Exception as exc:  # pragma: no cover - defensive
            meta_breakdown["twi_error"] = str(exc)[:200]

    # ── Component 2: Property catastro penalty (rasterized polygons) ──────────
    property_raster = np.zeros_like(data, dtype=np.float32)
    property_shapes = _vector_shapes_for_raster(
        db,
        """
        SELECT
            ST_AsGeoJSON(ST_Transform(geometria, :srid))::json AS geometry,
            1.0 AS penalty
        FROM parcelas_catastro
        WHERE geometria IS NOT NULL
        """,
        srid=srid,
        value_key="penalty",
    )
    if property_shapes:
        property_raster = rasterize(
            [(shape(geom), value) for geom, value in property_shapes],
            out_shape=data.shape,
            fill=0.0,
            transform=transform,
            dtype="float32",
        )
        meta_breakdown["property_features"] = len(property_shapes)

    # ── Component 3: Roads penalty (10m buffer each side) ─────────────────────
    roads_raster = np.zeros_like(data, dtype=np.float32)
    roads_shapes = _vector_shapes_for_raster(
        db,
        """
        SELECT
            ST_AsGeoJSON(
                ST_Transform(
                    ST_Buffer(ST_Transform(c.geometria, 32720), 10),
                    :srid
                )
            )::json AS geometry,
            1.0 AS penalty
        FROM caminos_geo c
        WHERE c.geometria IS NOT NULL
        """,
        srid=srid,
        value_key="penalty",
    )
    if roads_shapes:
        roads_raster = rasterize(
            [(shape(geom), value) for geom, value in roads_shapes],
            out_shape=data.shape,
            fill=0.0,
            transform=transform,
            dtype="float32",
        )
        meta_breakdown["roads_features"] = len(roads_shapes)

    # ── Component 4: Existing canals attractor (40m buffer) ───────────────────
    canals_raster = np.zeros_like(data, dtype=np.float32)
    canals_shapes = _vector_shapes_for_raster(
        db,
        """
        SELECT
            ST_AsGeoJSON(
                ST_Transform(
                    ST_Buffer(ST_Transform(cn.geom, 32720), 40),
                    :srid
                )
            )::json AS geometry,
            1.0 AS suitability
        FROM canal_network cn
        WHERE cn.geom IS NOT NULL
        """,
        srid=srid,
        value_key="suitability",
    )
    if canals_shapes:
        canals_raster = rasterize(
            [(shape(geom), value) for geom, value in canals_shapes],
            out_shape=data.shape,
            fill=0.0,
            transform=transform,
            dtype="float32",
        )
        meta_breakdown["canals_features"] = len(canals_shapes)

    # ── Combine: penalties ADD to cost, attractors SUBTRACT from cost ─────────
    # Penalty/attractor magnitudes are scaled by their profile weight so that
    # rebalancing the profile reshapes routing behaviour predictably.
    cost = data.copy()

    # Slope (per-pixel) is already in `data` from generate_cost_surface; scale by weight
    if weights["slope"] != 1.0:
        cost[valid_mask] *= max(weights["slope"] * 2.0, 0.1)

    # TWI: strong attractor — high TWI (drainage) reduces cost significantly
    if meta_breakdown["twi_used"] and weights["twi"] > 0:
        cost[valid_mask] -= twi_norm[valid_mask] * (12.0 * weights["twi"])

    # Roads penalty: hard penalty to discourage routing along/across roads
    if weights["roads"] > 0:
        cost[valid_mask] += roads_raster[valid_mask] * (10.0 * weights["roads"])

    # Property penalty
    if weights["property"] > 0:
        cost[valid_mask] += property_raster[valid_mask] * (6.0 * weights["property"])

    # Existing canals: strong attractor — being inside the buffer subtracts cost
    if weights["canals"] > 0:
        cost[valid_mask] -= canals_raster[valid_mask] * (8.0 * weights["canals"])

    # WhiteboxTools cost_distance requires positive cost values; clip to a small floor
    cost[valid_mask] = np.clip(cost[valid_mask], 0.01, None)

    cost[~valid_mask] = nodata
    meta.update({"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": nodata})
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(cost.astype(np.float32), 1)

    return output_path, meta_breakdown


def _line_to_wgs84(line: LineString, source_epsg: int | None) -> LineString:
    if source_epsg in (None, 4326):
        return line
    transformer = Transformer.from_crs(source_epsg, 4326, always_xy=True)
    return shapely_transform(transformer.transform, line)


def _line_length_m(line: LineString, source_epsg: int | None) -> float:
    if source_epsg not in (None, 4326):
        return float(line.length)
    transformer = Transformer.from_crs(4326, 32720, always_xy=True)
    return float(shapely_transform(transformer.transform, line).length)


def _project_point_to_raster_crs(
    lon: float,
    lat: float,
    *,
    target_epsg: int | None,
) -> tuple[float, float]:
    if target_epsg in (None, 4326):
        return lon, lat
    transformer = Transformer.from_crs(4326, target_epsg, always_xy=True)
    x, y = transformer.transform(lon, lat)
    return float(x), float(y)


def _snap_point_to_valid_cell(
    raster_path: str,
    x: float,
    y: float,
    *,
    max_radius_pixels: int = 300,
    label: str = "point",
) -> tuple[float, float, float]:
    """Snap a point to the nearest valid (non-nodata) raster cell.

    WhiteboxTools cost_distance / cost_pathway treat nodata cells as
    impassable barriers. If the input point lands on a nodata pixel the
    raster routing fails silently with a vague "no path" error. This helper
    walks an expanding window around the requested cell to find the closest
    valid pixel and returns its center coordinates plus the snap distance.

    Returns ``(x_snapped, y_snapped, snap_distance_m)``. Raises NotFoundError
    if no valid cell exists within ``max_radius_pixels``.
    """
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(raster_path) as src:
        try:
            row, col = src.index(x, y)
        except (IndexError, ValueError) as exc:
            raise NotFoundError(
                f"{label} ({x:.2f}, {y:.2f}) falls outside the cost surface extent"
            ) from exc

        if not (0 <= row < src.height and 0 <= col < src.width):
            raise NotFoundError(
                f"{label} ({x:.2f}, {y:.2f}) falls outside the cost surface extent"
            )

        nodata = src.nodata
        center_value = src.read(1, window=Window(col, row, 1, 1))[0, 0]
        if np.isfinite(center_value) and (nodata is None or center_value != nodata):
            return float(x), float(y), 0.0

        win_col = max(0, col - max_radius_pixels)
        win_row = max(0, row - max_radius_pixels)
        win_width = min(src.width - win_col, max_radius_pixels * 2 + 1)
        win_height = min(src.height - win_row, max_radius_pixels * 2 + 1)
        window = Window(win_col, win_row, win_width, win_height)
        block = src.read(1, window=window)

        if nodata is not None:
            valid = np.isfinite(block) & (block != nodata)
        else:
            valid = np.isfinite(block)

        if not np.any(valid):
            raise NotFoundError(
                f"{label} falls in a nodata region and no valid cell exists within "
                f"{max_radius_pixels} pixels. The cost surface coverage is too sparse "
                f"for this location — try a different point or expand raster coverage."
            )

        valid_rows, valid_cols = np.where(valid)
        local_row = row - win_row
        local_col = col - win_col
        distances_sq = (valid_rows - local_row) ** 2 + (valid_cols - local_col) ** 2
        nearest_idx = int(np.argmin(distances_sq))
        snapped_local_row = int(valid_rows[nearest_idx])
        snapped_local_col = int(valid_cols[nearest_idx])
        snapped_row = win_row + snapped_local_row
        snapped_col = win_col + snapped_local_col

        x_snapped, y_snapped = src.xy(snapped_row, snapped_col)
        pixel_size_m = abs(src.transform.a)
        snap_distance_m = float(np.sqrt(distances_sq[nearest_idx])) * pixel_size_m
        return float(x_snapped), float(y_snapped), snap_distance_m


def build_raster_route_feature_collection(line: LineString) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {"edge_id": None, "path_seq": 1},
            }
        ],
    }


def raster_corridor_routing(
    db: Session,
    *,
    from_lon: float,
    from_lat: float,
    to_lon: float,
    to_lat: float,
    profile: str,
    corridor_width_m: float,
    area_id: str | None = None,
    weight_overrides: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    slope_raster_path = get_latest_slope_raster_path(db, area_id)
    twi_raster_path = get_latest_twi_raster_path(db, area_id)
    with tempfile.TemporaryDirectory(prefix="routing-raster-") as tmpdir:
        cost_surface_path, cost_meta = build_multicriteria_cost_surface(
            db,
            slope_raster_path,
            str(Path(tmpdir) / "corridor_cost_surface.tif"),
            profile=profile,
            weight_overrides=weight_overrides,
            twi_raster_path=twi_raster_path,
        )
        accum_path = str(Path(tmpdir) / "corridor_accum.tif")
        backlink_path = str(Path(tmpdir) / "corridor_backlink.tif")
        import rasterio

        with rasterio.open(cost_surface_path) as src:
            source_epsg = (
                int(src.crs.to_epsg()) if src.crs and src.crs.to_epsg() else None
            )

        from_point = _project_point_to_raster_crs(
            from_lon,
            from_lat,
            target_epsg=source_epsg,
        )
        to_point = _project_point_to_raster_crs(
            to_lon,
            to_lat,
            target_epsg=source_epsg,
        )

        from_x, from_y, from_snap = _snap_point_to_valid_cell(
            cost_surface_path, *from_point, label="source"
        )
        to_x, to_y, to_snap = _snap_point_to_valid_cell(
            cost_surface_path, *to_point, label="target"
        )
        from_point = (from_x, from_y)
        to_point = (to_x, to_y)
        cost_meta["snap_source_m"] = round(from_snap, 2)
        cost_meta["snap_target_m"] = round(to_snap, 2)

        cost_distance(
            cost_surface_path, [from_point], accum_path, backlink_path
        )
        path_geom = least_cost_path(accum_path, backlink_path, to_point)
        if path_geom is None:
            raise NotFoundError(
                "No raster corridor path could be traced between the selected points. "
                "The cost surface likely has nodata gaps blocking all routes between source "
                "and target. Try points closer together or in a denser coverage area."
            )

        line_wgs84 = _line_to_wgs84(path_geom, source_epsg)
        return {
            "line": line_wgs84,
            "total_distance_m": round(_line_length_m(path_geom, source_epsg), 2),
            "cost_meta": cost_meta,
            "raster_source": slope_raster_path,
        }
