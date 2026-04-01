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

from rasterstats import zonal_stats as _zonal_stats
from shapely import wkt

logger = logging.getLogger(__name__)

SUPPORTED_STATS = ["min", "max", "mean", "std", "median", "count", "sum"]


def compute_zonal_stats(
    geometries: list[dict[str, Any]],
    raster_path: str,
    stats: list[str] | None = None,
    *,
    all_touched: bool = True,
) -> list[dict[str, Any]]:
    """Compute zonal statistics for a list of geometries against a raster.

    Args:
        geometries: List of dicts with 'id', 'name' (optional), and
                    'geometry' (GeoJSON dict or WKT string).
        raster_path: Path to the raster file (GeoTIFF or COG).
        stats: List of statistics to compute. Defaults to all supported.
        all_touched: If True, include all pixels touched by the geometry.

    Returns:
        List of dicts with original id/name plus computed statistics.
    """
    if not geometries:
        return []

    if not Path(raster_path).exists():
        raise FileNotFoundError(f"Raster not found: {raster_path}")

    stats = stats or SUPPORTED_STATS

    # Normalize geometries to GeoJSON dicts
    geojson_geoms = []
    for g in geometries:
        geom = g["geometry"]
        if isinstance(geom, str):
            geom = wkt.loads(geom).__geo_interface__
        geojson_geoms.append(geom)

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
