"""Support helpers for GEE Celery task orchestration."""

from __future__ import annotations

import math
import traceback
from typing import Any


def update_status_if_needed(*, analisis_id, repo, db, uuid_module, estado, resultado=None, error=None) -> None:
    if not analisis_id:
        return
    kwargs = {"estado": estado}
    if resultado is not None:
        kwargs["resultado"] = resultado
    if error is not None:
        kwargs["error"] = error
    repo.update_analisis_status(db, uuid_module.UUID(analisis_id), **kwargs)


def filtered_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k != "error"}


def days_buffer(*, start_date, end_date) -> int:
    return (end_date - start_date).days or 10


def build_flood_analysis_result(*, explorer, start_date, end_date, method: str) -> dict[str, Any]:
    resultado: dict[str, Any] = {}
    buffer_days = days_buffer(start_date=start_date, end_date=end_date)
    if method in ("fusion", "optical_only"):
        optical_result = explorer.get_sentinel2_image(target_date=start_date, days_buffer=buffer_days, max_cloud=60, visualization="inundacion")
        resultado["optical"] = filtered_result(optical_result)
        if "error" in optical_result:
            resultado["optical"]["warning"] = optical_result["error"]
        ndwi_result = explorer.get_sentinel2_image(target_date=start_date, days_buffer=buffer_days, max_cloud=60, visualization="ndwi")
        resultado["ndwi"] = filtered_result(ndwi_result)
    if method in ("fusion", "sar_only"):
        sar_result = explorer.get_sentinel1_image(target_date=start_date, days_buffer=buffer_days, visualization="vv_flood")
        resultado["sar"] = filtered_result(sar_result)
        if "error" in sar_result:
            resultado["sar"]["warning"] = sar_result["error"]
    if method == "fusion" and (end_date - start_date).days > 5:
        try:
            resultado["comparison"] = explorer.get_flood_comparison(flood_date=start_date, normal_date=end_date, days_buffer=15, max_cloud=60)
        except Exception as comp_err:
            resultado["comparison_error"] = str(comp_err)
    return resultado


def build_supervised_classification_stats(*, explorer, start_date, end_date, logger, datetime_module, ee_module) -> dict[str, Any]:
    days_buf = days_buffer(start_date=start_date, end_date=end_date)
    use_toa = start_date.year < 2019
    collection_name = "COPERNICUS/S2_HARMONIZED" if use_toa else "COPERNICUS/S2_SR_HARMONIZED"
    zona = explorer.zona
    collection = (
        ee_module.ImageCollection(collection_name)
        .filterBounds(zona)
        .filterDate((start_date - datetime_module.timedelta(days=days_buf)).isoformat(), (start_date + datetime_module.timedelta(days=days_buf)).isoformat())
        .filter(ee_module.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
    )
    img_count = collection.size().getInfo()
    if img_count <= 0:
        return {"warning": "No images available for classification stats"}
    composite = collection.median().clip(zona)
    ndvi = composite.normalizedDifference(["B8", "B4"]).rename("ndvi")
    ndwi = composite.normalizedDifference(["B3", "B8"]).rename("ndwi")
    water = ndwi.gt(0.3)
    dense_veg = ndvi.gt(0.5).And(water.Not())
    sparse_veg = ndvi.gt(0.2).And(ndvi.lte(0.5)).And(water.Not())
    bare_soil = ndvi.lte(0.2).And(water.Not())
    classified = ee_module.Image(0).where(water, 1).where(dense_veg, 2).where(sparse_veg, 3).where(bare_soil, 4).rename("classification").clip(zona)
    class_names = {1: "agua", 2: "vegetacion_densa", 3: "vegetacion_rala", 4: "suelo_desnudo"}
    pixel_counts = {}
    total_pixels = 0
    for class_val, class_name in class_names.items():
        mask = classified.eq(class_val)
        count_img = mask.rename("count")
        stats = count_img.reduceRegion(reducer=ee_module.Reducer.sum(), geometry=zona.geometry(), scale=10, maxPixels=1e9, bestEffort=True).getInfo()
        px_count = int(stats.get("count", 0))
        pixel_counts[class_name] = px_count
        total_pixels += px_count
    classification_stats = {}
    for class_name, px_count in pixel_counts.items():
        pct = round((px_count / total_pixels) * 100.0, 2) if total_pixels > 0 else 0.0
        classification_stats[class_name] = {"pixeles": px_count, "porcentaje": pct}
    return {"stats": classification_stats, "total_pixels": total_pixels, "thresholds": {"agua": "NDWI > 0.3", "vegetacion_densa": "NDVI > 0.5", "vegetacion_rala": "0.2 < NDVI <= 0.5", "suelo_desnudo": "NDVI <= 0.2"}, "scale_m": 10}


def build_classification_result(*, explorer, start_date, end_date, logger, ee_module, datetime_module) -> dict[str, Any]:
    resultado: dict[str, Any] = {}
    buffer_days = days_buffer(start_date=start_date, end_date=end_date)
    ndvi_result = explorer.get_sentinel2_image(target_date=start_date, days_buffer=buffer_days, max_cloud=60, visualization="ndvi")
    resultado["ndvi"] = filtered_result(ndvi_result)
    if "error" in ndvi_result:
        resultado["ndvi"]["warning"] = ndvi_result["error"]
    rgb_result = explorer.get_sentinel2_image(target_date=start_date, days_buffer=buffer_days, max_cloud=60, visualization="rgb")
    resultado["rgb"] = filtered_result(rgb_result)
    agri_result = explorer.get_sentinel2_image(target_date=start_date, days_buffer=buffer_days, max_cloud=60, visualization="agricultura")
    resultado["agricultura"] = filtered_result(agri_result)
    fc_result = explorer.get_sentinel2_image(target_date=start_date, days_buffer=buffer_days, max_cloud=60, visualization="falso_color")
    resultado["falso_color"] = filtered_result(fc_result)
    try:
        resultado["classification"] = build_supervised_classification_stats(
            explorer=explorer,
            start_date=start_date,
            end_date=end_date,
            logger=logger,
            datetime_module=datetime_module,
            ee_module=ee_module,
        )
    except Exception as cls_err:
        logger.warning("supervised_classification_task.classification_stats_failed: %s", cls_err)
        resultado["classification"] = {"error": str(cls_err)}
    resultado["classification_type"] = "ndvi_ndwi_based"
    return resultado


def detect_vv_anomalies_impl(*, dates: list[str], vv_values: list[float], sigma: float) -> dict[str, Any]:
    if not vv_values:
        return {"baseline": None, "std": None, "threshold": None, "anomalies": []}
    n = len(vv_values)
    baseline = sum(vv_values) / n
    variance = sum((v - baseline) ** 2 for v in vv_values) / n
    std = math.sqrt(variance)
    threshold = baseline - sigma * std
    anomalies = [{"date": dates[i], "vv": round(vv_values[i], 4)} for i in range(n) if vv_values[i] < threshold]
    return {"baseline": round(baseline, 4), "std": round(std, 4), "threshold": round(threshold, 4), "anomalies": anomalies}


def build_sar_temporal_result(*, explorer, start_date, end_date, scale: int, detect_fn) -> dict[str, Any]:
    time_series = explorer.get_sar_time_series(start_date=start_date, end_date=end_date, scale=scale)
    anomaly_result = detect_fn(dates=time_series["dates"], vv_values=time_series["vv_mean"], sigma=2.0)
    resultado = {
        "dates": time_series["dates"],
        "vv_mean": time_series["vv_mean"],
        "image_count": time_series["image_count"],
        "baseline": anomaly_result["baseline"],
        "std": anomaly_result["std"],
        "threshold": anomaly_result["threshold"],
        "anomalies": anomaly_result["anomalies"],
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "scale_m": scale,
        "status": "completed",
    }
    if "warning" in time_series:
        resultado["warning"] = time_series["warning"]
    return resultado


def failure_error_message(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
