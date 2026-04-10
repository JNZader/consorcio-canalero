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

RASTER_PROFILE_WEIGHTS = {
    "balanceado": {"slope": 0.45, "hydric": 0.25, "property": 0.30},
    "hidraulico": {"slope": 0.35, "hydric": 0.55, "property": 0.10},
    "evitar_propiedad": {"slope": 0.25, "hydric": 0.15, "property": 0.60},
}


def _resolve_raster_profile_weights(profile: str) -> dict[str, float]:
    return dict(
        RASTER_PROFILE_WEIGHTS.get(profile, RASTER_PROFILE_WEIGHTS["balanceado"])
    )


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
    if layer is None:
        raise NotFoundError(
            "No slope raster layer available for raster corridor routing"
        )
    return _resolve_layer_path(layer)


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
    weights = _resolve_raster_profile_weights(profile)
    meta_breakdown: dict[str, Any] = {
        "mode": "raster",
        "weights": weights,
        "property_features": 0,
        "hydric_features": 0,
    }

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
    hydric_shapes = _vector_shapes_for_raster(
        db,
        """
        WITH latest_hci AS (
            SELECT ih.zona_id, ih.indice_final
            FROM indices_hidricos ih
            JOIN (
                SELECT zona_id, MAX(fecha_calculo) AS max_fecha
                FROM indices_hidricos
                GROUP BY zona_id
            ) latest
              ON latest.zona_id = ih.zona_id
             AND latest.max_fecha = ih.fecha_calculo
        )
        SELECT
            ST_AsGeoJSON(ST_Transform(zo.geometria, :srid))::json AS geometry,
            COALESCE(latest_hci.indice_final, 0.0) AS hydric_value
        FROM zonas_operativas zo
        LEFT JOIN latest_hci ON latest_hci.zona_id = zo.id
        WHERE zo.geometria IS NOT NULL
        """,
        srid=srid,
        value_key="hydric_value",
    )

    property_raster = np.zeros_like(data, dtype=np.float32)
    hydric_raster = np.zeros_like(data, dtype=np.float32)

    if property_shapes:
        property_raster = rasterize(
            [(shape(geom), value) for geom, value in property_shapes],
            out_shape=data.shape,
            fill=0.0,
            transform=transform,
            dtype="float32",
        )
        meta_breakdown["property_features"] = len(property_shapes)

    if hydric_shapes:
        hydric_raster = rasterize(
            [(shape(geom), value) for geom, value in hydric_shapes],
            out_shape=data.shape,
            fill=0.0,
            transform=transform,
            dtype="float32",
        )
        meta_breakdown["hydric_features"] = len(hydric_shapes)

    cost = data.copy()
    if weights["property"] > 0:
        cost[valid_mask] += property_raster[valid_mask] * (6.0 * weights["property"])
    if weights["hydric"] > 0:
        hydric_penalty = 1.0 - np.clip(hydric_raster / 100.0, 0.0, 1.0)
        cost[valid_mask] += hydric_penalty[valid_mask] * (6.0 * weights["hydric"])

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
) -> dict[str, Any]:
    slope_raster_path = get_latest_slope_raster_path(db, area_id)
    with tempfile.TemporaryDirectory(prefix="routing-raster-") as tmpdir:
        cost_surface_path, cost_meta = build_multicriteria_cost_surface(
            db,
            slope_raster_path,
            str(Path(tmpdir) / "corridor_cost_surface.tif"),
            profile=profile,
        )
        accum_path = str(Path(tmpdir) / "corridor_accum.tif")
        backlink_path = str(Path(tmpdir) / "corridor_backlink.tif")
        cost_distance(
            cost_surface_path, [(from_lon, from_lat)], accum_path, backlink_path
        )
        path_geom = least_cost_path(accum_path, backlink_path, (to_lon, to_lat))
        if path_geom is None:
            raise NotFoundError(
                "No raster corridor path could be traced between the selected points"
            )

        import rasterio

        with rasterio.open(cost_surface_path) as src:
            source_epsg = (
                int(src.crs.to_epsg()) if src.crs and src.crs.to_epsg() else None
            )

        line_wgs84 = _line_to_wgs84(path_geom, source_epsg)
        return {
            "line": line_wgs84,
            "total_distance_m": round(_line_length_m(path_geom, source_epsg), 2),
            "cost_meta": cost_meta,
            "raster_source": slope_raster_path,
        }
