"""
Temporal analysis service using xarray, rioxarray, and Xee.

Provides time-series analysis for:
  - NDWI trend analysis along canals (water index over time)
  - Multi-temporal raster comparison
  - Anomaly detection in satellite imagery time series
  - GEE ImageCollection → xarray via Xee (no local download needed)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def analyze_ndwi_trend_gee(
    geometry_geojson: dict,
    start_date: str,
    end_date: str,
    *,
    cloud_cover_max: int = 30,
) -> dict[str, Any]:
    """Analyze NDWI (water index) trend over time using GEE + Xee + xarray.

    Loads Sentinel-2 imagery for the given geometry and date range,
    computes NDWI per image, and returns the time series with trend.

    Args:
        geometry_geojson: GeoJSON geometry dict (Polygon).
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        cloud_cover_max: Max cloud cover percentage for Sentinel-2 filter.

    Returns:
        Dict with dates, ndwi_values, trend, and anomalies.
    """
    import ee
    import xarray as xr
    import xee  # noqa: F401 — registers the ee engine for xarray

    # Initialize GEE using the project's standard init
    from app.domains.geo.gee_service import _ensure_initialized
    _ensure_initialized()

    # Create GEE geometry
    ee_geom = ee.Geometry(geometry_geojson)

    # Load Sentinel-2 SR, filter by date and cloud cover
    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(ee_geom)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_cover_max))
        .select(["B3", "B8"])  # Green and NIR for NDWI
        .sort("system:time_start")
    )

    count = s2.size().getInfo()
    if count == 0:
        return {
            "dates": [],
            "ndwi_values": [],
            "trend": None,
            "anomalies": [],
            "image_count": 0,
            "message": "No Sentinel-2 images found for the given parameters",
        }

    # Compute NDWI = (Green - NIR) / (Green + NIR)
    def add_ndwi(image):
        ndwi = image.normalizedDifference(["B3", "B8"]).rename("NDWI")
        return image.addBands(ndwi)

    s2_ndwi = s2.map(add_ndwi).select("NDWI")

    # Use Xee to load as xarray Dataset
    ds = xr.open_dataset(
        s2_ndwi,
        engine="ee",
        geometry=ee_geom,
        scale=20,  # 20m resolution for Sentinel-2
    )

    # Compute mean NDWI per timestep over the geometry
    # Xee uses 'lon'/'lat' dims, rioxarray uses 'x'/'y' or 'X'/'Y'
    spatial_dims = [d for d in ds["NDWI"].dims if d != "time"]
    mean_ndwi = ds["NDWI"].mean(dim=spatial_dims).values
    times = ds.coords["time"].values

    # Convert to serializable format
    dates = [str(np.datetime_as_string(t, unit="D")) for t in times]
    values = [round(float(v), 4) if np.isfinite(v) else None for v in mean_ndwi]

    # Filter out None values for trend calculation
    valid_pairs = [(i, v) for i, v in enumerate(values) if v is not None]

    # Linear trend
    trend = None
    if len(valid_pairs) >= 3:
        x = np.array([p[0] for p in valid_pairs], dtype=np.float64)
        y = np.array([p[1] for p in valid_pairs], dtype=np.float64)
        coeffs = np.polyfit(x, y, 1)
        trend = {
            "slope_per_image": round(float(coeffs[0]), 6),
            "direction": "increasing" if coeffs[0] > 0.001 else
                        "decreasing" if coeffs[0] < -0.001 else "stable",
            "r_squared": round(float(1 - np.sum((y - np.polyval(coeffs, x))**2) /
                                    np.sum((y - np.mean(y))**2)), 4)
                        if np.std(y) > 0 else 0,
        }

    # Anomaly detection (2-sigma)
    anomalies = []
    if len(valid_pairs) >= 5:
        vals = np.array([p[1] for p in valid_pairs])
        mean_val = float(np.mean(vals))
        std_val = float(np.std(vals))
        if std_val > 0:
            for idx, val in valid_pairs:
                if abs(val - mean_val) > 2 * std_val:
                    anomalies.append({
                        "date": dates[idx],
                        "ndwi": val,
                        "deviation_sigma": round((val - mean_val) / std_val, 2),
                    })

    ds.close()

    return {
        "dates": dates,
        "ndwi_values": values,
        "trend": trend,
        "anomalies": anomalies,
        "image_count": count,
        "date_range": {"start": start_date, "end": end_date},
    }


def compare_rasters_temporal(
    raster_paths: list[str],
    labels: list[str],
    geometry_wkt: str | None = None,
) -> dict[str, Any]:
    """Compare multiple rasters (same type, different dates) using xarray.

    Args:
        raster_paths: List of raster file paths.
        labels: Labels for each raster (e.g., dates).
        geometry_wkt: Optional WKT polygon to clip analysis.

    Returns:
        Dict with per-raster stats and change analysis.
    """
    import rioxarray  # noqa: F401 — registers the rio accessor
    import xarray as xr
    from shapely import wkt as shapely_wkt

    if len(raster_paths) != len(labels):
        raise ValueError("raster_paths and labels must have the same length")

    stats = []
    arrays = []

    for path, label in zip(raster_paths, labels):
        if not Path(path).exists():
            continue

        da = xr.open_dataarray(path, engine="rasterio")

        # Clip to geometry if provided (reproject geometry to raster CRS)
        if geometry_wkt:
            from pyproj import Transformer
            from shapely.geometry import mapping
            from shapely.ops import transform as shapely_transform
            geom = shapely_wkt.loads(geometry_wkt)
            raster_crs = da.rio.crs
            if raster_crs and str(raster_crs) != "EPSG:4326":
                transformer = Transformer.from_crs("EPSG:4326", raster_crs, always_xy=True)
                geom = shapely_transform(transformer.transform, geom)
            da = da.rio.clip([mapping(geom)], all_touched=True)

        values = da.values[da.values != da.rio.nodata] if da.rio.nodata is not None else da.values
        values = values[np.isfinite(values)]

        stat = {
            "label": label,
            "path": path,
            "mean": round(float(np.mean(values)), 4) if values.size > 0 else None,
            "std": round(float(np.std(values)), 4) if values.size > 0 else None,
            "min": round(float(np.min(values)), 4) if values.size > 0 else None,
            "max": round(float(np.max(values)), 4) if values.size > 0 else None,
            "pixel_count": int(values.size),
        }
        stats.append(stat)
        arrays.append(values)

        da.close()

    # Change analysis between first and last
    change = None
    if len(arrays) >= 2 and arrays[0].size > 0 and arrays[-1].size > 0:
        mean_first = float(np.mean(arrays[0]))
        mean_last = float(np.mean(arrays[-1]))
        change = {
            "from": labels[0],
            "to": labels[-1],
            "mean_change": round(mean_last - mean_first, 4),
            "percent_change": round(((mean_last - mean_first) / abs(mean_first)) * 100, 2)
                              if mean_first != 0 else None,
        }

    return {
        "raster_count": len(stats),
        "stats": stats,
        "change": change,
    }
