"""
Advanced hydrology analysis for canal management.

Extends the existing DEM pipeline with canal-specific analysis:
  - TWI classification into actionable zones
  - Canal capacity analysis (flow accumulation at canal segments)
  - Upstream contributing area per canal segment
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

logger = logging.getLogger(__name__)

# TWI classification thresholds for flat Pampas terrain
TWI_CLASSES = {
    "seco": {"label": "Terreno seco", "min": None, "max": 7.0, "color": "#f59e0b"},
    "normal": {"label": "Humedad normal", "min": 7.0, "max": 11.0, "color": "#22c55e"},
    "humedo": {"label": "Acumulación moderada", "min": 11.0, "max": 15.0, "color": "#3b82f6"},
    "saturado": {"label": "Saturación alta", "min": 15.0, "max": None, "color": "#ef4444"},
}


def classify_twi(twi_path: str, output_path: str) -> str:
    """Classify TWI raster into actionable wetness zones.

    Classes:
        1 = Seco (TWI < 7)
        2 = Normal (7 <= TWI < 11)
        3 = Húmedo (11 <= TWI < 15)
        4 = Saturado (TWI >= 15)

    Args:
        twi_path: Path to the TWI raster.
        output_path: Output classified raster path.

    Returns:
        output_path on success.
    """
    with rasterio.open(twi_path) as src:
        twi = src.read(1).astype(np.float64)
        nodata = src.nodata
        meta = src.meta.copy()

    nodata_mask = np.zeros(twi.shape, dtype=bool)
    if nodata is not None:
        nodata_mask = twi == nodata
    nodata_mask |= ~np.isfinite(twi)

    classified = np.zeros(twi.shape, dtype=np.uint8)
    valid = ~nodata_mask

    classified[valid & (twi < 7.0)] = 1   # seco
    classified[valid & (twi >= 7.0) & (twi < 11.0)] = 2   # normal
    classified[valid & (twi >= 11.0) & (twi < 15.0)] = 3  # humedo
    classified[valid & (twi >= 15.0)] = 4  # saturado

    meta.update(dtype="uint8", nodata=0)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(classified, 1)

    return output_path


def compute_twi_zone_summary(twi_path: str) -> dict[str, Any]:
    """Compute area statistics for each TWI class.

    Returns:
        Dict with class names, pixel counts, and area percentages.
    """
    with rasterio.open(twi_path) as src:
        twi = src.read(1).astype(np.float64)
        nodata = src.nodata
        cell_size = abs(src.transform.a)

    nodata_mask = np.zeros(twi.shape, dtype=bool)
    if nodata is not None:
        nodata_mask = twi == nodata
    nodata_mask |= ~np.isfinite(twi)

    valid = ~nodata_mask
    total_valid = int(np.sum(valid))
    cell_area_m2 = cell_size ** 2

    classes = []
    for key, info in TWI_CLASSES.items():
        mask = valid.copy()
        if info["min"] is not None:
            mask &= twi >= info["min"]
        if info["max"] is not None:
            mask &= twi < info["max"]

        count = int(np.sum(mask))
        area_ha = round((count * cell_area_m2) / 10_000, 2)
        pct = round((count / total_valid * 100), 1) if total_valid > 0 else 0

        classes.append({
            "class": key,
            "label": info["label"],
            "color": info["color"],
            "pixel_count": count,
            "area_ha": area_ha,
            "percentage": pct,
        })

    return {
        "total_pixels": total_valid,
        "total_area_ha": round((total_valid * cell_area_m2) / 10_000, 2),
        "classes": classes,
    }


def compute_flow_acc_at_canals(
    flow_acc_path: str,
    canal_geojson_path: str,
) -> list[dict[str, Any]]:
    """Compute flow accumulation statistics along canal segments.

    For each canal LineString, samples the flow accumulation raster
    at regular intervals and returns max, mean, and hotspot locations.
    This indicates which canal segments receive the most upstream water.

    Args:
        flow_acc_path: Path to the flow accumulation raster.
        canal_geojson_path: Path to the canal GeoJSON.

    Returns:
        List of per-canal statistics.
    """
    import json
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as shapely_transform

    with rasterio.open(flow_acc_path) as src:
        flow_acc = src.read(1).astype(np.float64)
        nodata = src.nodata
        raster_crs = str(src.crs)
        transform = src.transform

    # Load canals
    data = json.loads(Path(canal_geojson_path).read_text())
    features = data.get("features", [])

    # Setup reprojection if needed
    transformer = None
    if "4326" not in raster_crs:
        transformer = Transformer.from_crs("EPSG:4326", raster_crs, always_xy=True)

    results = []
    for feat in features:
        if feat["geometry"]["type"] not in ("LineString", "MultiLineString"):
            continue

        props = feat.get("properties", {})
        nombre = props.get("name") or props.get("nombre") or "unnamed"
        geom = shape(feat["geometry"])

        # Reproject to raster CRS
        if transformer:
            geom = shapely_transform(transformer.transform, geom)

        # Sample along the line at regular intervals
        length = geom.length
        num_samples = max(int(length / 100), 10)  # sample every ~100m
        sample_values = []

        for i in range(num_samples + 1):
            frac = i / num_samples
            point = geom.interpolate(frac, normalized=True)
            col, row = ~transform * (point.x, point.y)
            row, col = int(row), int(col)

            if 0 <= row < flow_acc.shape[0] and 0 <= col < flow_acc.shape[1]:
                val = flow_acc[row, col]
                if nodata is None or val != nodata:
                    sample_values.append(float(val))

        if sample_values:
            results.append({
                "nombre": nombre,
                "samples": len(sample_values),
                "flow_acc_max": round(max(sample_values), 0),
                "flow_acc_mean": round(sum(sample_values) / len(sample_values), 0),
                "flow_acc_min": round(min(sample_values), 0),
                "capacity_risk": "alto" if max(sample_values) > 5000 else
                                 "medio" if max(sample_values) > 1000 else "bajo",
            })

    # Sort by max flow accumulation descending
    results.sort(key=lambda r: r["flow_acc_max"], reverse=True)
    return results
