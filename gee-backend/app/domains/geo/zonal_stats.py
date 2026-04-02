"""
Zonal statistics service using rasterstats.

Computes raster statistics (mean, min, max, std, count) for vector
geometries pulled from PostGIS. Designed for answering questions like:
  - "What's the average slope along canal section X?"
  - "What's the elevation range in zone Y?"
  - "Which assets have the highest flood risk?"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import rasterio
from pyproj import Transformer
from rasterstats import zonal_stats as _zonal_stats
from shapely import wkt
from shapely.ops import transform as shapely_transform

logger = logging.getLogger(__name__)

SUPPORTED_STATS = ["min", "max", "mean", "std", "median", "count", "sum"]


def _reproject_geom(geom_shape, src_crs: str, dst_crs: str):
    """Reproject a shapely geometry from src_crs to dst_crs."""
    if src_crs == dst_crs:
        return geom_shape
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return shapely_transform(transformer.transform, geom_shape)


def compute_zonal_stats(
    geometries: list[dict[str, Any]],
    raster_path: str,
    stats: list[str] | None = None,
    *,
    all_touched: bool = True,
    geometry_crs: str = "EPSG:4326",
) -> list[dict[str, Any]]:
    """Compute zonal statistics for a list of geometries against a raster.

    Automatically reprojects geometries to the raster's CRS if they differ.

    Args:
        geometries: List of dicts with 'id', 'name' (optional), and
                    'geometry' (GeoJSON dict or WKT string).
        raster_path: Path to the raster file (GeoTIFF or COG).
        stats: List of statistics to compute. Defaults to all supported.
        all_touched: If True, include all pixels touched by the geometry.
        geometry_crs: CRS of the input geometries (default EPSG:4326).

    Returns:
        List of dicts with original id/name plus computed statistics.
    """
    if not geometries:
        return []

    if not Path(raster_path).exists():
        raise FileNotFoundError(f"Raster not found: {raster_path}")

    stats = stats or SUPPORTED_STATS

    # Read raster CRS for reprojection
    with rasterio.open(raster_path) as src:
        raster_crs = str(src.crs)

    # Normalize geometries to shapely, reproject if needed, then to GeoJSON
    geojson_geoms = []
    for g in geometries:
        geom = g["geometry"]
        if isinstance(geom, str):
            geom_shape = wkt.loads(geom)
        else:
            from shapely.geometry import shape
            geom_shape = shape(geom)
        geom_shape = _reproject_geom(geom_shape, geometry_crs, raster_crs)
        geojson_geoms.append(geom_shape.__geo_interface__)

    results = _zonal_stats(
        geojson_geoms,
        raster_path,
        stats=stats,
        all_touched=all_touched,
        nodata=-32768,
    )

    # Merge stats with original metadata
    output = []
    for i, stat_result in enumerate(results):
        entry = {
            "id": geometries[i].get("id"),
            "name": geometries[i].get("name"),
        }
        # Round floats for cleaner output
        for key, value in stat_result.items():
            entry[key] = round(value, 4) if isinstance(value, float) else value
        output.append(entry)

    return output


def compute_stats_for_zones(
    zone_wkts: list[tuple[str, str, str | None]],
    raster_path: str,
    stats: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Convenience wrapper for PostGIS zone geometries.

    Args:
        zone_wkts: List of (id, wkt_geometry, name) tuples from PostGIS.
        raster_path: Path to the raster.
        stats: Statistics to compute.

    Returns:
        List of stat dicts.
    """
    geometries = [
        {"id": str(zid), "geometry": zwkt, "name": zname}
        for zid, zwkt, zname in zone_wkts
    ]
    return compute_zonal_stats(geometries, raster_path, stats)
