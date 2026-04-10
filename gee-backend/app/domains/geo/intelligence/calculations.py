"""Pure calculation functions for operational intelligence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import geopandas as gpd

import numpy as np
from shapely.geometry import LineString

from app.domains.geo.intelligence.calculations_hydrology_support import (
    calcular_indice_criticidad_hidrica_impl,
    clasificar_nivel_riesgo_impl,
    clasificar_severidad_conflicto_impl,
    detectar_puntos_conflicto_impl,
    empty_runoff_geojson_impl,
    generar_zonificacion_impl,
    simular_escorrentia_impl,
)
from app.domains.geo.intelligence.calculations_network_support import (
    calcular_prioridad_canal_impl,
    calcular_riesgo_camino_impl,
    clasificar_terreno_dinamico_impl,
    compute_maintenance_priority_impl,
    detect_coverage_gaps_impl,
    rank_canal_hotspots_impl,
)
from app.domains.geo.intelligence.calculations_routing_support import (
    cost_distance_impl,
    generate_cost_surface_impl,
    least_cost_path_impl,
    sample_raster_along_line_impl,
    suggest_canal_routes_impl,
)

_wbt = None


def _get_wbt():
    global _wbt
    if _wbt is None:
        from whitebox import WhiteboxTools

        _wbt = WhiteboxTools()
        _wbt.set_verbose_mode(False)
    return _wbt


def _normalize_shape(geometry: Any):
    if isinstance(geometry, dict):
        from shapely.geometry import shape as shapely_shape

        return shapely_shape(geometry)
    return geometry


def _extract_geometries(items: list[dict]) -> list[Any]:
    return [
        _normalize_shape(geometry)
        for item in items
        if (geometry := item.get("geometry")) is not None
    ]


def _round_score(value: float) -> float:
    return round(min(max(value, 0.0), 100.0), 2)


def _build_empty_geojson(columns: list[str]) -> "gpd.GeoDataFrame":
    import geopandas as gpd

    return gpd.GeoDataFrame(columns=columns, geometry="geometry")


def _normalize_score(raw: float, minimum: float, maximum: float) -> float:
    return 0.0 if maximum == minimum else (raw - minimum) / (maximum - minimum)


def _min_max(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    mn, mx = min(values), max(values)
    return (mn, mn + 1.0) if mn == mx else (mn, mx)


DEFAULT_HCI_WEIGHTS = {
    "pendiente": 0.15,
    "acumulacion": 0.30,
    "twi": 0.25,
    "dist_canal": 0.15,
    "hist_inundacion": 0.15,
}


def _rasterio_module():
    try:
        return rasterio  # type: ignore[name-defined]
    except NameError:
        import rasterio as rasterio_module

        return rasterio_module


def calcular_indice_criticidad_hidrica(
    pendiente: float,
    acumulacion: float,
    twi: float,
    dist_canal: float,
    hist_inundacion: float,
    pesos: Optional[dict[str, float]] = None,
) -> float:
    return calcular_indice_criticidad_hidrica_impl(
        pendiente,
        acumulacion,
        twi,
        dist_canal,
        hist_inundacion,
        pesos=pesos,
        default_weights=DEFAULT_HCI_WEIGHTS,
        round_score=_round_score,
    )


def clasificar_nivel_riesgo(indice: float) -> str:
    return clasificar_nivel_riesgo_impl(indice)


def detectar_puntos_conflicto(
    canales_gdf: "gpd.GeoDataFrame",
    caminos_gdf: "gpd.GeoDataFrame",
    drenajes_gdf: "gpd.GeoDataFrame",
    flow_acc_path: str,
    slope_path: str,
    buffer_m: float = 50.0,
    flow_acc_threshold: float = 500.0,
    slope_threshold: float = 5.0,
) -> "gpd.GeoDataFrame":
    _pair_types = ("canal_camino", "canal_drenaje", "camino_drenaje")
    return detectar_puntos_conflicto_impl(
        canales_gdf,
        caminos_gdf,
        drenajes_gdf,
        flow_acc_path,
        slope_path,
        buffer_m=buffer_m,
        flow_acc_threshold=flow_acc_threshold,
        slope_threshold=slope_threshold,
        classify_severity=_clasificar_severidad_conflicto,
        build_empty_geojson=_build_empty_geojson,
    )


def _clasificar_severidad_conflicto(acumulacion: float, pendiente: float) -> str:
    return clasificar_severidad_conflicto_impl(acumulacion, pendiente)


def simular_escorrentia(
    flow_dir_path: str,
    flow_acc_path: str,
    punto_inicio: tuple[float, float],
    lluvia_mm: float,
    max_steps: int = 5000,
) -> dict[str, Any]:
    _d8_offsets = {
        1: (0, 1),
        2: (-1, 1),
        4: (-1, 0),
        8: (-1, -1),
        16: (0, -1),
        32: (1, -1),
        64: (1, 0),
        128: (1, 1),
    }
    return simular_escorrentia_impl(
        flow_dir_path,
        flow_acc_path,
        punto_inicio,
        lluvia_mm,
        max_steps=max_steps,
        rasterio_module=_rasterio_module(),
        empty_geojson=_empty_runoff_geojson,
    )


def _empty_runoff_geojson(
    punto: tuple[float, float], lluvia_mm: float, error: str
) -> dict[str, Any]:
    return empty_runoff_geojson_impl(punto, lluvia_mm, error)


def generar_zonificacion(
    dem_path: str, flow_acc_path: str, threshold: int = 2000
) -> "gpd.GeoDataFrame":
    return generar_zonificacion_impl(
        dem_path,
        flow_acc_path,
        threshold=threshold,
        get_wbt=_get_wbt,
        build_empty_geojson=_build_empty_geojson,
    )


def calcular_prioridad_canal(
    canal_geom: Any,
    flow_acc_path: str,
    slope_path: str,
    zonas_criticas_gdf: Optional["gpd.GeoDataFrame"] = None,
) -> float:
    return calcular_prioridad_canal_impl(
        canal_geom,
        flow_acc_path,
        slope_path,
        sample_raster=_sample_raster_along_line,
        round_score=_round_score,
        zonas_criticas_gdf=zonas_criticas_gdf,
    )


def calcular_riesgo_camino(
    camino_geom: Any,
    flow_acc_path: str,
    slope_path: str,
    twi_path: str,
    drainage_gdf: Optional["gpd.GeoDataFrame"] = None,
) -> float:
    return calcular_riesgo_camino_impl(
        camino_geom,
        flow_acc_path,
        slope_path,
        twi_path,
        sample_raster=_sample_raster_along_line,
        round_score=_round_score,
        drainage_gdf=drainage_gdf,
    )


def clasificar_terreno_dinamico(
    sar_data: np.ndarray | None,
    sentinel2_data: np.ndarray | None,
    dem_data: np.ndarray | None,
) -> dict[str, Any]:
    return clasificar_terreno_dinamico_impl(sar_data, sentinel2_data, dem_data)


def rank_canal_hotspots(
    canal_geometries: list[dict], flow_acc_raster_path: str, num_points: int = 20
) -> list[dict]:
    return rank_canal_hotspots_impl(
        canal_geometries,
        flow_acc_raster_path,
        num_points=num_points,
        sample_raster=_sample_raster_along_line,
    )


def detect_coverage_gaps(
    zones: list[dict],
    hci_scores: dict[str, float],
    canal_geometries: list[dict],
    threshold_km: float = 2.0,
    hci_threshold: float = 50.0,
) -> list[dict]:
    return detect_coverage_gaps_impl(
        zones,
        hci_scores,
        canal_geometries,
        threshold_km=threshold_km,
        hci_threshold=hci_threshold,
        extract_geometries=_extract_geometries,
        normalize_shape=_normalize_shape,
    )


def compute_maintenance_priority(
    centrality_scores: dict[int, float],
    flow_acc_scores: dict[int, float],
    hci_scores: dict[str, float],
    conflict_counts: dict[int, int],
) -> list[dict]:
    return compute_maintenance_priority_impl(
        centrality_scores,
        flow_acc_scores,
        hci_scores,
        conflict_counts,
        min_max=_min_max,
        normalize_score=_normalize_score,
    )


def generate_cost_surface(slope_raster_path: str, output_path: str) -> str:
    return generate_cost_surface_impl(
        slope_raster_path, output_path, rasterio_module=_rasterio_module()
    )


def cost_distance(
    cost_surface_path: str,
    source_points: list[tuple[float, float]],
    output_accum_path: str,
    output_backlink_path: str,
) -> tuple[str, str]:
    return cost_distance_impl(
        cost_surface_path,
        source_points,
        output_accum_path,
        output_backlink_path,
        rasterio_module=_rasterio_module(),
        get_wbt=_get_wbt,
    )


def least_cost_path(
    cost_distance_path: str, backlink_path: str, target_point: tuple[float, float]
) -> Optional[LineString]:
    return least_cost_path_impl(
        cost_distance_path,
        backlink_path,
        target_point,
        rasterio_module=_rasterio_module(),
        get_wbt=_get_wbt,
    )


def suggest_canal_routes(
    gap_centroids: list[dict],
    canal_geometries: list[dict],
    slope_raster_path: str,
    output_dir: str | None = None,
) -> list[dict]:
    return suggest_canal_routes_impl(
        gap_centroids,
        canal_geometries,
        slope_raster_path,
        output_dir=output_dir,
        normalize_shape=_normalize_shape,
        extract_geometries=_extract_geometries,
        generate_cost_surface=generate_cost_surface,
        cost_distance=cost_distance,
        least_cost_path=least_cost_path,
    )


def _sample_raster_along_line(
    line_geom: Any, raster_path: str, num_points: int = 20
) -> list[float]:
    return sample_raster_along_line_impl(
        line_geom,
        raster_path,
        num_points=num_points,
        rasterio_module=_rasterio_module(),
    )
