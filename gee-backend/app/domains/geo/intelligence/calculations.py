"""Pure calculation functions for operational intelligence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import geopandas as gpd

import numpy as np

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
    clasificar_terreno_dinamico_impl,
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


def clasificar_terreno_dinamico(
    sar_data: np.ndarray | None,
    sentinel2_data: np.ndarray | None,
    dem_data: np.ndarray | None,
) -> dict[str, Any]:
    return clasificar_terreno_dinamico_impl(sar_data, sentinel2_data, dem_data)
