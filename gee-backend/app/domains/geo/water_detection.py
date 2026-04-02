"""
Water detection service for satellite imagery.

Level 1 (current): NDWI thresholding + morphological operations
Level 2 (future):  ML model plug-in (U-Net, WaterNet, etc.)

Detects water bodies and wet areas from Sentinel-2 imagery via GEE,
produces water masks, vectorizes to PostGIS polygons, and computes
water coverage statistics per zona operativa.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# NDWI thresholds calibrated for Argentine Pampas flat terrain
NDWI_WATER_THRESHOLD = 0.1       # Definite water
NDWI_WET_THRESHOLD = -0.05       # Wet/saturated soil
MIN_WATER_AREA_PIXELS = 10       # Minimum contiguous pixels to count as water body


def detect_water_from_gee(
    geometry_geojson: dict,
    target_date: str,
    *,
    days_window: int = 15,
    cloud_cover_max: int = 20,
) -> dict[str, Any]:
    """Detect water bodies using Sentinel-2 NDWI from GEE.

    Fetches the best available Sentinel-2 image near the target date,
    computes NDWI, and classifies into water/wet/dry.

    Args:
        geometry_geojson: GeoJSON geometry (Polygon).
        target_date: Target date (YYYY-MM-DD).
        days_window: Days before/after to search for imagery.
        cloud_cover_max: Max cloud cover percentage.

    Returns:
        Dict with water statistics and classification results.
    """
    import ee
    from app.domains.geo.gee_service import _ensure_initialized

    _ensure_initialized()

    ee_geom = ee.Geometry(geometry_geojson)

    # Parse date and create search window
    from datetime import datetime, timedelta
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    start = (dt - timedelta(days=days_window)).strftime("%Y-%m-%d")
    end = (dt + timedelta(days=days_window)).strftime("%Y-%m-%d")

    # Get best Sentinel-2 image (least cloudy)
    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(ee_geom)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_cover_max))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
        .first()
    )

    if s2 is None:
        info = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
            .filterBounds(ee_geom).filterDate(start, end).size().getInfo()
        return {
            "status": "no_imagery",
            "message": f"No Sentinel-2 images with <{cloud_cover_max}% clouds found ({info} total images in window)",
            "date_range": {"start": start, "end": end},
        }

    # Compute NDWI = (Green - NIR) / (Green + NIR)
    # Sentinel-2 SR: B3=Green, B8=NIR, values 0-10000
    green = s2.select("B3").divide(10000)
    nir = s2.select("B8").divide(10000)
    ndwi = green.subtract(nir).divide(green.add(nir)).rename("NDWI")

    # Classify
    water_mask = ndwi.gte(NDWI_WATER_THRESHOLD)  # Definite water
    wet_mask = ndwi.gte(NDWI_WET_THRESHOLD).And(ndwi.lt(NDWI_WATER_THRESHOLD))  # Wet soil

    # Morphological cleanup: remove isolated pixels, fill small holes
    kernel = ee.Kernel.circle(radius=2, units="pixels")
    water_clean = water_mask.focalMode(radius=2, kernelType="circle", units="pixels")
    water_clean = water_clean.updateMask(water_clean)

    # Compute area statistics
    pixel_area = ee.Image.pixelArea()

    water_area = water_mask.multiply(pixel_area).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=ee_geom,
        scale=10,
        maxPixels=1e8,
    ).getInfo()

    wet_area = wet_mask.multiply(pixel_area).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=ee_geom,
        scale=10,
        maxPixels=1e8,
    ).getInfo()

    total_area = pixel_area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=ee_geom,
        scale=10,
        maxPixels=1e8,
    ).getInfo()

    # NDWI statistics
    ndwi_stats = ndwi.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            ee.Reducer.stdDev(), sharedInputs=True
        ).combine(
            ee.Reducer.minMax(), sharedInputs=True
        ),
        geometry=ee_geom,
        scale=10,
        maxPixels=1e8,
    ).getInfo()

    # Get image date
    image_date = ee.Date(s2.get("system:time_start")).format("YYYY-MM-dd").getInfo()
    cloud_pct = s2.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()

    total_ha = (total_area.get("area", 0) or 0) / 10_000
    water_ha = (water_area.get("NDWI", 0) or 0) / 10_000
    wet_ha = (wet_area.get("NDWI", 0) or 0) / 10_000

    return {
        "status": "success",
        "image_date": image_date,
        "cloud_cover_pct": round(cloud_pct, 1) if cloud_pct else None,
        "search_window": {"start": start, "end": end},
        "area": {
            "total_ha": round(total_ha, 2),
            "water_ha": round(water_ha, 2),
            "wet_ha": round(wet_ha, 2),
            "dry_ha": round(total_ha - water_ha - wet_ha, 2),
            "water_pct": round((water_ha / total_ha) * 100, 2) if total_ha > 0 else 0,
            "wet_pct": round((wet_ha / total_ha) * 100, 2) if total_ha > 0 else 0,
        },
        "ndwi": {
            "mean": round(ndwi_stats.get("NDWI_mean", 0) or 0, 4),
            "std": round(ndwi_stats.get("NDWI_stdDev", 0) or 0, 4),
            "min": round(ndwi_stats.get("NDWI_min", 0) or 0, 4),
            "max": round(ndwi_stats.get("NDWI_max", 0) or 0, 4),
        },
        "thresholds": {
            "water": NDWI_WATER_THRESHOLD,
            "wet": NDWI_WET_THRESHOLD,
        },
    }


def detect_water_multi_date(
    geometry_geojson: dict,
    dates: list[str],
    *,
    cloud_cover_max: int = 20,
) -> dict[str, Any]:
    """Run water detection for multiple dates to track changes.

    Args:
        geometry_geojson: GeoJSON geometry.
        dates: List of target dates (YYYY-MM-DD).
        cloud_cover_max: Max cloud cover.

    Returns:
        Dict with per-date results and change summary.
    """
    results = []
    for target_date in dates:
        try:
            result = detect_water_from_gee(
                geometry_geojson,
                target_date,
                cloud_cover_max=cloud_cover_max,
            )
            results.append({"date": target_date, **result})
        except Exception as exc:
            results.append({
                "date": target_date,
                "status": "error",
                "message": str(exc),
            })

    # Change analysis
    successful = [r for r in results if r.get("status") == "success"]
    change = None
    if len(successful) >= 2:
        first = successful[0]
        last = successful[-1]
        change = {
            "from_date": first["image_date"],
            "to_date": last["image_date"],
            "water_ha_change": round(
                last["area"]["water_ha"] - first["area"]["water_ha"], 2
            ),
            "water_pct_change": round(
                last["area"]["water_pct"] - first["area"]["water_pct"], 2
            ),
            "trend": (
                "increasing" if last["area"]["water_pct"] > first["area"]["water_pct"] + 1
                else "decreasing" if last["area"]["water_pct"] < first["area"]["water_pct"] - 1
                else "stable"
            ),
        }

    return {
        "dates_requested": len(dates),
        "dates_successful": len(successful),
        "results": results,
        "change": change,
    }
