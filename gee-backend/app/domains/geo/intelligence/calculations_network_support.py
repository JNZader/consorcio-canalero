from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import mapping


def calcular_prioridad_canal_impl(
    canal_geom: Any,
    flow_acc_path: str,
    slope_path: str,
    *,
    sample_raster,
    round_score,
    zonas_criticas_gdf=None,
) -> float:
    fa_values = sample_raster(canal_geom, flow_acc_path)
    sl_values = sample_raster(canal_geom, slope_path)
    if not fa_values or not sl_values:
        return 0.0
    fa_norm = min(max(fa_values) / 10_000.0, 1.0)
    sl_norm = min((sum(sl_values) / len(sl_values)) / 10.0, 1.0)
    zona_factor = 0.0
    if zonas_criticas_gdf is not None and not zonas_criticas_gdf.empty:
        zona_factor = max(
            1.0 - (zonas_criticas_gdf.geometry.distance(canal_geom).min() / 1000.0), 0.0
        )
    return round_score((0.40 * fa_norm + 0.30 * sl_norm + 0.30 * zona_factor) * 100.0)


def calcular_riesgo_camino_impl(
    camino_geom: Any,
    flow_acc_path: str,
    slope_path: str,
    twi_path: str,
    *,
    sample_raster,
    round_score,
    drainage_gdf=None,
) -> float:
    fa_values = sample_raster(camino_geom, flow_acc_path)
    sl_values = sample_raster(camino_geom, slope_path)
    twi_values = sample_raster(camino_geom, twi_path)
    if not fa_values or not sl_values or not twi_values:
        return 0.0
    fa_norm = min(max(fa_values) / 10_000.0, 1.0)
    sl_norm = max(1.0 - ((sum(sl_values) / len(sl_values)) / 5.0), 0.0)
    twi_norm = min(max((sum(twi_values) / len(twi_values)) / 15.0, 0.0), 1.0)
    drain_factor = 0.0
    if drainage_gdf is not None and not drainage_gdf.empty:
        drain_factor = max(
            1.0 - (drainage_gdf.geometry.distance(camino_geom).min() / 500.0), 0.0
        )
    return round_score(
        (0.30 * fa_norm + 0.25 * sl_norm + 0.25 * twi_norm + 0.20 * drain_factor)
        * 100.0
    )


def clasificar_terreno_dinamico_impl(
    sar_data: np.ndarray | None,
    sentinel2_data: np.ndarray | None,
    dem_data: np.ndarray | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"clases": {}, "estadisticas": {}}
    shape = next(
        (
            data.shape
            for data in [sar_data, sentinel2_data, dem_data]
            if data is not None
        ),
        None,
    )
    if shape is None:
        return result
    classified = np.zeros(shape, dtype=np.uint8)
    if sar_data is not None:
        classified[sar_data < -15.0] = 1
    if sentinel2_data is not None:
        classified[(sentinel2_data > 0.5) & (classified == 0)] = 2
        classified[
            (sentinel2_data > 0.2) & (sentinel2_data <= 0.5) & (classified == 0)
        ] = 4
        classified[
            (sentinel2_data <= 0.2) & (sentinel2_data > -0.1) & (classified == 0)
        ] = 3
    class_names = {
        0: "sin_clasificar",
        1: "agua",
        2: "vegetacion_densa",
        3: "suelo_desnudo",
        4: "vegetacion_rala",
        5: "urbano",
    }
    total_pixels = classified.size
    stats = {
        name: {
            "pixeles": int(np.sum(classified == code)),
            "porcentaje": round(
                (int(np.sum(classified == code)) / total_pixels) * 100.0, 2
            )
            if total_pixels > 0
            else 0.0,
        }
        for code, name in class_names.items()
    }
    result["clasificacion"], result["clases"], result["estadisticas"] = (
        classified,
        class_names,
        stats,
    )
    return result


def rank_canal_hotspots_impl(
    canal_geometries: list[dict],
    flow_acc_raster_path: str,
    *,
    num_points: int,
    sample_raster,
) -> list[dict]:
    from shapely.geometry import shape as shapely_shape

    if not Path(flow_acc_raster_path).exists():
        raise FileNotFoundError(
            f"Flow accumulation raster not found: {flow_acc_raster_path}"
        )
    raw_results: list[dict] = []
    for idx, canal in enumerate(canal_geometries):
        geom = canal.get("geometry")
        if geom is None:
            continue
        if isinstance(geom, dict):
            geom = shapely_shape(geom)
        values = sample_raster(geom, flow_acc_raster_path, num_points)
        if not values:
            continue
        fa_max, fa_mean = max(values), sum(values) / len(values)
        raw_results.append(
            {
                "geometry": mapping(geom),
                "segment_index": idx,
                "id": canal.get("id"),
                "nombre": canal.get("nombre"),
                "flow_acc_max": round(fa_max, 2),
                "flow_acc_mean": round(fa_mean, 2),
                "score": round(fa_max, 2),
            }
        )
    if not raw_results:
        return []
    all_maxes = [r["flow_acc_max"] for r in raw_results]
    p75, p50, p25 = (
        float(np.percentile(all_maxes, 75)),
        float(np.percentile(all_maxes, 50)),
        float(np.percentile(all_maxes, 25)),
    )
    for r in raw_results:
        r["risk_level"] = (
            "critico"
            if r["flow_acc_max"] >= p75
            else "alto"
            if r["flow_acc_max"] >= p50
            else "medio"
            if r["flow_acc_max"] >= p25
            else "bajo"
        )
    raw_results.sort(key=lambda r: r["flow_acc_max"], reverse=True)
    return raw_results


def detect_coverage_gaps_impl(
    zones: list[dict],
    hci_scores: dict[str, float],
    canal_geometries: list[dict],
    *,
    threshold_km: float,
    hci_threshold: float,
    extract_geometries,
    normalize_shape,
) -> list[dict]:
    from shapely.ops import nearest_points, unary_union

    canal_shapes = extract_geometries(canal_geometries)
    if not canal_shapes:
        return []
    canal_union = unary_union(canal_shapes)
    gaps: list[dict] = []
    for zone in zones:
        zone_id, hci = (
            str(zone.get("id", "")),
            hci_scores.get(str(zone.get("id", "")), 0.0),
        )
        if hci < hci_threshold:
            continue
        geom = zone.get("geometry")
        if geom is None:
            continue
        centroid = normalize_shape(geom).centroid
        _, nearest_pt = nearest_points(centroid, canal_union)
        dist_km = centroid.distance(nearest_pt) * 111.0
        if dist_km < threshold_km:
            continue
        severity = (
            "critico"
            if hci > 80.0 and dist_km > 5.0
            else "alto"
            if hci > 60.0 and dist_km > 3.0
            else "moderado"
        )
        gaps.append(
            {
                "geometry": mapping(centroid),
                "gap_km": round(dist_km, 2),
                "hci_score": round(hci, 2),
                "zone_id": zone_id,
                "severity": severity,
            }
        )
    severity_order = {"critico": 0, "alto": 1, "moderado": 2}
    gaps.sort(key=lambda g: (severity_order.get(g["severity"], 3), -g["hci_score"]))
    return gaps


def compute_maintenance_priority_impl(
    centrality_scores: dict[int, float],
    flow_acc_scores: dict[int, float],
    hci_scores: dict[str, float],
    conflict_counts: dict[int, int],
    *,
    min_max,
    normalize_score,
) -> list[dict]:
    all_ids = (
        set(centrality_scores)
        | set(flow_acc_scores)
        | {int(k) for k in hci_scores if k.isdigit()}
        | set(conflict_counts)
    )
    if not all_ids:
        return []
    cent_min, cent_max = min_max(list(centrality_scores.values()))
    fa_min, fa_max = min_max(list(flow_acc_scores.values()))
    hci_min, hci_max = min_max(list(hci_scores.values()))
    conf_min, conf_max = min_max([float(v) for v in conflict_counts.values()])
    base_weights = {
        "centrality": 0.30,
        "flow_acc": 0.25,
        "upstream_hci": 0.25,
        "conflict_count": 0.20,
    }
    results = []
    for node_id in all_ids:
        components, available_weight, missing_factors = {}, 0.0, []
        for key, raw, mn, mx in [
            ("centrality", centrality_scores.get(node_id), cent_min, cent_max),
            ("flow_acc", flow_acc_scores.get(node_id), fa_min, fa_max),
            ("upstream_hci", hci_scores.get(str(node_id)), hci_min, hci_max),
            (
                "conflict_count",
                float(conflict_counts[node_id]) if node_id in conflict_counts else None,
                conf_min,
                conf_max,
            ),
        ]:
            if raw is None:
                missing_factors.append(key)
                continue
            components[key] = {
                "raw": int(raw)
                if key == "conflict_count"
                else round(raw, 6 if key == "centrality" else 2),
                "normalized": round(normalize_score(float(raw), mn, mx), 4),
            }
            available_weight += base_weights[key]
        if available_weight == 0.0:
            continue
        composite = sum(
            base_weights[f] * (1.0 / available_weight) * components[f]["normalized"]
            for f in components
        )
        results.append(
            {
                "node_id": node_id,
                "composite_score": round(composite, 4),
                "components": components,
                "missing_factors": missing_factors or None,
            }
        )
    results.sort(key=lambda r: r["composite_score"], reverse=True)
    return results
