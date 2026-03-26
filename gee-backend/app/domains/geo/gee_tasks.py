"""
Celery tasks for Google Earth Engine analysis.

Handles long-running GEE operations in the background.
These tasks run on the DEFAULT queue (not geo queue) because GEE
is cloud-based, not GDAL-based — no heavy local computation needed.

Each task:
  1. Creates/updates an AnalisisGeo record (estado → running)
  2. Initializes GEE and uses ImageExplorer / GEEService
  3. Runs analysis (flood comparison, NDVI classification, etc.)
  4. Persists resultado JSON to AnalisisGeo record
  5. Updates estado to completed (or failed on error)
"""

from __future__ import annotations

import math
import traceback
import uuid
from typing import Any

from celery.utils.log import get_task_logger

from app.core.celery_app import celery_app

logger = get_task_logger(__name__)


def _get_deps():
    """Lazy imports to avoid pulling in heavy modules at Celery startup."""
    from app.db.session import SessionLocal
    from app.domains.geo.models import EstadoGeoJob
    from app.domains.geo.repository import GeoRepository

    return {
        "SessionLocal": SessionLocal,
        "EstadoGeoJob": EstadoGeoJob,
        "repo": GeoRepository(),
    }


def _get_gee():
    """Lazy import and init of GEE service components."""
    from app.domains.geo.gee_service import (
        _ensure_initialized,
        get_image_explorer,
    )

    _ensure_initialized()
    return {
        "explorer": get_image_explorer(),
    }


@celery_app.task(name="gee.analyze_flood", bind=True)
def analyze_flood_task(
    self,
    start_date_str: str,
    end_date_str: str,
    method: str = "fusion",
    analisis_id: str | None = None,
    job_id: str | None = None,
):
    """
    Analyze floods using SAR and Optical imagery via GEE.

    Uses ImageExplorer to fetch Sentinel-1 (SAR) and Sentinel-2 (optical)
    imagery, then runs flood comparison and NDWI-based water detection.

    Args:
        start_date_str: Analysis start date (ISO format).
        end_date_str: Analysis end date (ISO format).
        method: Analysis method — "fusion" (SAR+optical), "sar_only", "optical_only".
        analisis_id: Optional AnalisisGeo record ID for status tracking.
        job_id: Optional GeoJob ID (from dispatch_job).
    """
    deps = _get_deps()
    db = deps["SessionLocal"]()
    repo = deps["repo"]
    Estado = deps["EstadoGeoJob"]

    # Mark as running
    if analisis_id:
        repo.update_analisis_status(
            db, uuid.UUID(analisis_id), estado=Estado.RUNNING
        )
        db.commit()

    try:
        from datetime import date

        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        gee = _get_gee()
        explorer = gee["explorer"]

        resultado = {}

        # Optical-based flood detection (NDWI water mask)
        if method in ("fusion", "optical_only"):
            optical_result = explorer.get_sentinel2_image(
                target_date=start_date,
                days_buffer=(end_date - start_date).days or 10,
                max_cloud=60,
                visualization="inundacion",
            )
            resultado["optical"] = {
                k: v for k, v in optical_result.items() if k != "error"
            }
            if "error" in optical_result:
                resultado["optical"]["warning"] = optical_result["error"]

            # Also get NDWI for stats
            ndwi_result = explorer.get_sentinel2_image(
                target_date=start_date,
                days_buffer=(end_date - start_date).days or 10,
                max_cloud=60,
                visualization="ndwi",
            )
            resultado["ndwi"] = {
                k: v for k, v in ndwi_result.items() if k != "error"
            }

        # SAR-based water detection
        if method in ("fusion", "sar_only"):
            sar_result = explorer.get_sentinel1_image(
                target_date=start_date,
                days_buffer=(end_date - start_date).days or 10,
                visualization="vv_flood",
            )
            resultado["sar"] = {
                k: v for k, v in sar_result.items() if k != "error"
            }
            if "error" in sar_result:
                resultado["sar"]["warning"] = sar_result["error"]

        # Flood comparison if we have both dates
        if method == "fusion" and (end_date - start_date).days > 5:
            try:
                comparison = explorer.get_flood_comparison(
                    flood_date=start_date,
                    normal_date=end_date,
                    days_buffer=15,
                    max_cloud=60,
                )
                resultado["comparison"] = comparison
            except Exception as comp_err:
                resultado["comparison_error"] = str(comp_err)

        resultado["method"] = method
        resultado["start_date"] = start_date_str
        resultado["end_date"] = end_date_str
        resultado["status"] = "completed"

        # Persist results
        if analisis_id:
            repo.update_analisis_status(
                db,
                uuid.UUID(analisis_id),
                estado=Estado.COMPLETED,
                resultado=resultado,
            )
            db.commit()

        logger.info(
            "analyze_flood_task.completed",
            analisis_id=analisis_id,
            method=method,
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("analyze_flood_task.failed", error=str(exc))

        if analisis_id:
            try:
                repo.update_analisis_status(
                    db,
                    uuid.UUID(analisis_id),
                    estado=Estado.FAILED,
                    error=error_msg[:2000],
                )
                db.commit()
            except Exception:
                db.rollback()

        raise
    finally:
        db.close()


@celery_app.task(name="gee.supervised_classification", bind=True)
def supervised_classification_task(
    self,
    start_date_str: str,
    end_date_str: str,
    analisis_id: str | None = None,
    job_id: str | None = None,
):
    """
    Land-use classification using NDVI from Sentinel-2.

    Uses ImageExplorer to fetch NDVI imagery, then runs
    clasificar_terreno_dinamico() for pixel-level classification
    (water, dense vegetation, sparse vegetation, bare soil).

    Args:
        start_date_str: Analysis start date (ISO format).
        end_date_str: Analysis end date (ISO format).
        analisis_id: Optional AnalisisGeo record ID for status tracking.
        job_id: Optional GeoJob ID (from dispatch_job).
    """
    deps = _get_deps()
    db = deps["SessionLocal"]()
    repo = deps["repo"]
    Estado = deps["EstadoGeoJob"]

    # Mark as running
    if analisis_id:
        repo.update_analisis_status(
            db, uuid.UUID(analisis_id), estado=Estado.RUNNING
        )
        db.commit()

    try:
        from datetime import date

        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        gee = _get_gee()
        explorer = gee["explorer"]

        resultado = {}

        # Get NDVI visualization tiles
        ndvi_result = explorer.get_sentinel2_image(
            target_date=start_date,
            days_buffer=(end_date - start_date).days or 10,
            max_cloud=60,
            visualization="ndvi",
        )
        resultado["ndvi"] = {
            k: v for k, v in ndvi_result.items() if k != "error"
        }
        if "error" in ndvi_result:
            resultado["ndvi"]["warning"] = ndvi_result["error"]

        # Get RGB reference tiles
        rgb_result = explorer.get_sentinel2_image(
            target_date=start_date,
            days_buffer=(end_date - start_date).days or 10,
            max_cloud=60,
            visualization="rgb",
        )
        resultado["rgb"] = {
            k: v for k, v in rgb_result.items() if k != "error"
        }

        # Get agriculture visualization
        agri_result = explorer.get_sentinel2_image(
            target_date=start_date,
            days_buffer=(end_date - start_date).days or 10,
            max_cloud=60,
            visualization="agricultura",
        )
        resultado["agricultura"] = {
            k: v for k, v in agri_result.items() if k != "error"
        }

        # Get false color for vegetation analysis
        fc_result = explorer.get_sentinel2_image(
            target_date=start_date,
            days_buffer=(end_date - start_date).days or 10,
            max_cloud=60,
            visualization="falso_color",
        )
        resultado["falso_color"] = {
            k: v for k, v in fc_result.items() if k != "error"
        }

        # ── Pixel-level classification via GEE reduceRegion ──
        # Uses NDVI + NDWI thresholds to classify land cover and compute
        # area percentages per class (water, dense veg, sparse veg, bare soil)
        try:
            import ee

            days_buf = (end_date - start_date).days or 10
            use_toa = start_date.year < 2019
            collection_name = (
                "COPERNICUS/S2_HARMONIZED"
                if use_toa
                else "COPERNICUS/S2_SR_HARMONIZED"
            )
            zona = explorer.zona

            collection = (
                ee.ImageCollection(collection_name)
                .filterBounds(zona)
                .filterDate(
                    (start_date - __import__("datetime").timedelta(days=days_buf)).isoformat(),
                    (start_date + __import__("datetime").timedelta(days=days_buf)).isoformat(),
                )
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
            )

            img_count = collection.size().getInfo()
            if img_count > 0:
                composite = collection.median().clip(zona)

                ndvi = composite.normalizedDifference(["B8", "B4"]).rename("ndvi")
                ndwi = composite.normalizedDifference(["B3", "B8"]).rename("ndwi")

                # Classification rules:
                #   water:            NDWI > 0.3
                #   dense_vegetation: NDVI > 0.5 (and not water)
                #   sparse_vegetation: 0.2 < NDVI <= 0.5 (and not water)
                #   bare_soil:        NDVI <= 0.2 (and not water)
                water = ndwi.gt(0.3)
                dense_veg = ndvi.gt(0.5).And(water.Not())
                sparse_veg = ndvi.gt(0.2).And(ndvi.lte(0.5)).And(water.Not())
                bare_soil = ndvi.lte(0.2).And(water.Not())

                classified = (
                    ee.Image(0)
                    .where(water, 1)
                    .where(dense_veg, 2)
                    .where(sparse_veg, 3)
                    .where(bare_soil, 4)
                    .rename("classification")
                    .clip(zona)
                )

                # Count pixels per class using reduceRegion
                class_names = {
                    1: "agua",
                    2: "vegetacion_densa",
                    3: "vegetacion_rala",
                    4: "suelo_desnudo",
                }

                pixel_counts = {}
                total_pixels = 0
                for class_val, class_name in class_names.items():
                    mask = classified.eq(class_val)
                    count_img = mask.rename("count")
                    stats = count_img.reduceRegion(
                        reducer=ee.Reducer.sum(),
                        geometry=zona.geometry(),
                        scale=10,
                        maxPixels=1e9,
                        bestEffort=True,
                    ).getInfo()
                    px_count = int(stats.get("count", 0))
                    pixel_counts[class_name] = px_count
                    total_pixels += px_count

                # Compute percentages
                classification_stats = {}
                for class_name, px_count in pixel_counts.items():
                    pct = round((px_count / total_pixels) * 100.0, 2) if total_pixels > 0 else 0.0
                    classification_stats[class_name] = {
                        "pixeles": px_count,
                        "porcentaje": pct,
                    }

                resultado["classification"] = {
                    "stats": classification_stats,
                    "total_pixels": total_pixels,
                    "thresholds": {
                        "agua": "NDWI > 0.3",
                        "vegetacion_densa": "NDVI > 0.5",
                        "vegetacion_rala": "0.2 < NDVI <= 0.5",
                        "suelo_desnudo": "NDVI <= 0.2",
                    },
                    "scale_m": 10,
                }
            else:
                resultado["classification"] = {
                    "warning": "No images available for classification stats"
                }
        except Exception as cls_err:
            logger.warning(
                "supervised_classification_task.classification_stats_failed",
                error=str(cls_err),
            )
            resultado["classification"] = {"error": str(cls_err)}

        resultado["start_date"] = start_date_str
        resultado["end_date"] = end_date_str
        resultado["status"] = "completed"
        resultado["classification_type"] = "ndvi_ndwi_based"

        # Persist results
        if analisis_id:
            repo.update_analisis_status(
                db,
                uuid.UUID(analisis_id),
                estado=Estado.COMPLETED,
                resultado=resultado,
            )
            db.commit()

        logger.info(
            "supervised_classification_task.completed",
            analisis_id=analisis_id,
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("supervised_classification_task.failed", error=str(exc))

        if analisis_id:
            try:
                repo.update_analisis_status(
                    db,
                    uuid.UUID(analisis_id),
                    estado=Estado.FAILED,
                    error=error_msg[:2000],
                )
                db.commit()
            except Exception:
                db.rollback()

        raise
    finally:
        db.close()


# ── Pure function: anomaly detection ──────────────────────


def detect_vv_anomalies(
    dates: list[str],
    vv_values: list[float],
    sigma: float = 2.0,
) -> dict[str, Any]:
    """Detect anomalies in a VV backscatter time series.

    An anomaly is a date where VV drops below baseline - sigma * std,
    indicating potential waterlogging (lower VV = smoother/wetter surface).

    Args:
        dates: ISO date strings, same length as vv_values.
        vv_values: Mean VV backscatter values (dB).
        sigma: Number of standard deviations for threshold (default 2.0).

    Returns:
        Dict with baseline, std, threshold, and anomalies list.
    """
    if not vv_values:
        return {
            "baseline": None,
            "std": None,
            "threshold": None,
            "anomalies": [],
        }

    n = len(vv_values)
    baseline = sum(vv_values) / n
    variance = sum((v - baseline) ** 2 for v in vv_values) / n
    std = math.sqrt(variance)
    threshold = baseline - sigma * std

    anomalies = [
        {"date": dates[i], "vv": round(vv_values[i], 4)}
        for i in range(n)
        if vv_values[i] < threshold
    ]

    return {
        "baseline": round(baseline, 4),
        "std": round(std, 4),
        "threshold": round(threshold, 4),
        "anomalies": anomalies,
    }


# ── Celery task: SAR temporal analysis ───────────────────


@celery_app.task(name="gee.sar_temporal", bind=True)
def sar_temporal_task(
    self,
    start_date_str: str,
    end_date_str: str,
    scale: int = 100,
    analisis_id: str | None = None,
):
    """
    SAR temporal analysis: VV backscatter time series + anomaly detection.

    Computes mean VV per Sentinel-1 image over the zona geometry,
    then flags dates where VV drops below baseline - 2*std.

    Args:
        start_date_str: Analysis start date (ISO format).
        end_date_str: Analysis end date (ISO format).
        scale: Pixel scale in meters for reduceRegion (default 100).
        analisis_id: Optional AnalisisGeo record ID for status tracking.
    """
    deps = _get_deps()
    db = deps["SessionLocal"]()
    repo = deps["repo"]
    Estado = deps["EstadoGeoJob"]

    # Mark as running
    if analisis_id:
        repo.update_analisis_status(
            db, uuid.UUID(analisis_id), estado=Estado.RUNNING
        )
        db.commit()

    try:
        from datetime import date

        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        gee = _get_gee()
        explorer = gee["explorer"]

        # Step 1: Generate time series via GEE
        time_series = explorer.get_sar_time_series(
            start_date=start_date,
            end_date=end_date,
            scale=scale,
        )

        # Step 2: Detect anomalies
        anomaly_result = detect_vv_anomalies(
            dates=time_series["dates"],
            vv_values=time_series["vv_mean"],
        )

        # Step 3: Build resultado
        resultado = {
            "dates": time_series["dates"],
            "vv_mean": time_series["vv_mean"],
            "image_count": time_series["image_count"],
            "baseline": anomaly_result["baseline"],
            "std": anomaly_result["std"],
            "threshold": anomaly_result["threshold"],
            "anomalies": anomaly_result["anomalies"],
            "start_date": start_date_str,
            "end_date": end_date_str,
            "scale_m": scale,
            "status": "completed",
        }

        # Include warning if no images found
        if "warning" in time_series:
            resultado["warning"] = time_series["warning"]

        # Persist results
        if analisis_id:
            repo.update_analisis_status(
                db,
                uuid.UUID(analisis_id),
                estado=Estado.COMPLETED,
                resultado=resultado,
            )
            db.commit()

        logger.info(
            "sar_temporal_task.completed",
            analisis_id=analisis_id,
            image_count=time_series["image_count"],
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("sar_temporal_task.failed", error=str(exc))

        if analisis_id:
            try:
                repo.update_analisis_status(
                    db,
                    uuid.UUID(analisis_id),
                    estado=Estado.FAILED,
                    error=error_msg[:2000],
                )
                db.commit()
            except Exception:
                db.rollback()

        raise
    finally:
        db.close()
