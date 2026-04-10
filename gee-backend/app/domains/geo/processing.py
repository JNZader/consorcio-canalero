from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.mask import mask as rasterio_mask
from rasterio.warp import Resampling, calculate_default_transform, reproject

from app.domains.geo.processing_support import (
    classify_terrain_arrays,
    clip_bbox_impl,
    clip_to_geometry_impl,
    compute_aspect_impl,
    compute_flow_accumulation_impl,
    compute_flow_direction_impl,
    compute_hand_impl,
    compute_profile_curvature_impl,
    compute_slope_impl,
    compute_tpi_impl,
    compute_twi_impl,
    compute_utm_crs_impl,
    convert_to_cog_impl,
    copy_if_projected_impl,
    download_dem_impl,
    ensure_nodata_impl,
    ensure_parent_dir_impl,
    extract_drainage_network_impl,
    fill_sinks_impl,
    load_optional_raster_impl,
    read_single_band_impl,
    remove_off_terrain_objects_impl,
    reproject_to_utm_impl,
    resolve_classify_terrain_inputs_impl,
    run_wbt_tool_impl,
    valid_percentile_impl,
    vectorize_basins_impl,
    write_feature_collection_impl,
    write_single_band_impl,
)

logger = logging.getLogger(__name__)

# WhiteboxTools singleton (lazy import — only available in geo-worker)

_wbt: Any | None = None


def _get_wbt() -> Any:
    global _wbt  # noqa: PLW0603
    if _wbt is None:
        from whitebox import WhiteboxTools  # noqa: PLC0415

        _wbt = WhiteboxTools()
        _wbt.set_verbose_mode(False)
    return _wbt


def _ensure_parent_dir(output_path: str) -> None:
    ensure_parent_dir_impl(path_cls=Path, output_path=output_path)


def _read_single_band(
    raster_path: str,
) -> tuple[np.ndarray, float | None, Any, dict[str, Any], Any]:
    return read_single_band_impl(rasterio_module=rasterio, raster_path=raster_path)


def _write_single_band(
    output_path: str,
    data: np.ndarray,
    meta: dict[str, Any],
) -> str:
    return write_single_band_impl(
        rasterio_module=rasterio,
        ensure_parent_dir=_ensure_parent_dir,
        output_path=output_path,
        data=data,
        meta=meta,
    )


def _copy_if_projected(src, input_path: str, output_path: str) -> bool:
    return copy_if_projected_impl(
        shutil_module=shutil,
        input_path=input_path,
        output_path=output_path,
        src=src,
    )


def _compute_utm_crs(bounds) -> str:
    return compute_utm_crs_impl(bounds=bounds)


def _run_wbt_tool(output_path: str, runner) -> str:
    return run_wbt_tool_impl(
        output_path=output_path,
        ensure_parent_dir=_ensure_parent_dir,
        get_wbt=_get_wbt,
        runner=runner,
    )


def _write_feature_collection(
    output_path: str,
    *,
    features: list[dict[str, Any]],
    crs_name: str,
) -> str:
    return write_feature_collection_impl(
        ensure_parent_dir=_ensure_parent_dir,
        output_path=output_path,
        features=features,
        crs_name=crs_name,
    )


def _load_optional_raster(path: str | None) -> tuple[np.ndarray | None, float | None]:
    return load_optional_raster_impl(path_cls=Path, rasterio_module=rasterio, path=path)


# 0a) Ensure nodata is set
def ensure_nodata(
    dem_path: str, output_path: str, nodata_value: float = -32768.0
) -> str:
    return ensure_nodata_impl(
        rasterio_module=rasterio,
        shutil_module=shutil,
        write_single_band=_write_single_band,
        dem_path=dem_path,
        output_path=output_path,
        nodata_value=nodata_value,
    )


# 0b) Reproject to UTM
def reproject_to_utm(dem_path: str, output_path: str) -> str:
    return reproject_to_utm_impl(
        rasterio_module=rasterio,
        copy_if_projected=_copy_if_projected,
        compute_utm_crs=_compute_utm_crs,
        ensure_parent_dir=_ensure_parent_dir,
        calculate_default_transform_fn=calculate_default_transform,
        reproject_fn=reproject,
        resampling_bilinear=Resampling.bilinear,
        dem_path=dem_path,
        output_path=output_path,
    )


# 0c) Clip DEM to polygon geometry
def clip_to_geometry(
    dem_path: str,
    geometry: dict[str, Any],
    output_path: str,
    geometry_crs: str = "EPSG:4326",
) -> str:
    return clip_to_geometry_impl(
        rasterio_module=rasterio,
        rasterio_mask_fn=rasterio_mask,
        ensure_parent_dir=_ensure_parent_dir,
        dem_path=dem_path,
        geometry=geometry,
        output_path=output_path,
        geometry_crs=geometry_crs,
    )


# a) Clip DEM
def clip_dem(
    dem_path: str,
    bbox: tuple[float, float, float, float],
    output_path: str,
) -> str:
    return clip_bbox_impl(
        rasterio_module=rasterio,
        rasterio_mask_fn=rasterio_mask,
        ensure_parent_dir=_ensure_parent_dir,
        bbox=bbox,
        dem_path=dem_path,
        output_path=output_path,
    )


# b0) Remove off-terrain objects (trees, buildings)
def remove_off_terrain_objects(
    dem_path: str,
    output_path: str,
    filter_size: int = 7,
    slope_threshold: float = 5.0,
) -> str:
    return remove_off_terrain_objects_impl(
        run_wbt_tool=_run_wbt_tool,
        dem_path=dem_path,
        output_path=output_path,
        filter_size=filter_size,
        slope_threshold=slope_threshold,
    )


# b) Fill sinks
def fill_sinks(dem_path: str, output_path: str) -> str:
    return fill_sinks_impl(
        run_wbt_tool=_run_wbt_tool,
        dem_path=dem_path,
        output_path=output_path,
    )


# c) Slope
def compute_slope(dem_path: str, output_path: str) -> str:
    return compute_slope_impl(
        read_single_band=_read_single_band,
        write_single_band=_write_single_band,
        dem_path=dem_path,
        output_path=output_path,
    )


# d) Aspect
def compute_aspect(dem_path: str, output_path: str) -> str:
    return compute_aspect_impl(
        read_single_band=_read_single_band,
        write_single_band=_write_single_band,
        dem_path=dem_path,
        output_path=output_path,
    )


# e) Flow direction (D8)
def compute_flow_direction(filled_dem_path: str, output_path: str) -> str:
    return compute_flow_direction_impl(
        run_wbt_tool=_run_wbt_tool,
        filled_dem_path=filled_dem_path,
        output_path=output_path,
    )


# f) Flow accumulation (D8)
def compute_flow_accumulation(flow_dir_path: str, output_path: str) -> str:
    return compute_flow_accumulation_impl(
        run_wbt_tool=_run_wbt_tool,
        flow_dir_path=flow_dir_path,
        output_path=output_path,
    )


# g) Topographic Wetness Index (TWI)

_MIN_SLOPE_RAD = np.float64(0.001)


def compute_twi(
    slope_path: str,
    flow_acc_path: str,
    output_path: str,
) -> str:
    return compute_twi_impl(
        read_single_band=_read_single_band,
        write_single_band=_write_single_band,
        min_slope_rad=_MIN_SLOPE_RAD,
        slope_path=slope_path,
        flow_acc_path=flow_acc_path,
        output_path=output_path,
    )


# h) Height Above Nearest Drainage (HAND)

_DEFAULT_DRAINAGE_THRESHOLD = 1000


def compute_hand(
    dem_path: str,
    flow_dir_path: str,
    flow_acc_path: str,
    output_path: str,
    drainage_threshold: int = _DEFAULT_DRAINAGE_THRESHOLD,
) -> str:
    return compute_hand_impl(
        read_single_band=_read_single_band,
        write_single_band=_write_single_band,
        get_wbt=_get_wbt,
        ensure_parent_dir=_ensure_parent_dir,
        dem_path=dem_path,
        flow_dir_path=flow_dir_path,
        flow_acc_path=flow_acc_path,
        output_path=output_path,
        drainage_threshold=drainage_threshold,
    )


# i) Extract drainage network (vector)
def extract_drainage_network(
    flow_acc_path: str,
    threshold: int,
    output_path: str,
) -> str:
    return extract_drainage_network_impl(
        read_single_band=_read_single_band,
        write_feature_collection=_write_feature_collection,
        shapes_fn=shapes,
        flow_acc_path=flow_acc_path,
        threshold=threshold,
        output_path=output_path,
    )


# j-1) Profile curvature
def compute_profile_curvature(filled_dem_path: str, output_dir: str) -> str:
    return compute_profile_curvature_impl(
        path_cls=Path,
        run_wbt_tool=_run_wbt_tool,
        filled_dem_path=filled_dem_path,
        output_dir=output_dir,
    )


# j-2) Topographic Position Index (TPI)
def compute_tpi(
    filled_dem_path: str,
    output_dir: str,
    radius: int = 10,
) -> str:
    return compute_tpi_impl(
        path_cls=Path,
        run_wbt_tool=_run_wbt_tool,
        filled_dem_path=filled_dem_path,
        output_dir=output_dir,
        radius=radius,
    )


# j) Terrain classification — 5 actionable classes for flat terrain management

TERRAIN_SIN_RIESGO = 0  # No risk — transparent on map
TERRAIN_DRENAJE_NATURAL = 1  # Natural drainage lines
TERRAIN_RIESGO_ALTO = 2  # High flood risk
TERRAIN_RIESGO_MEDIO = 3  # Moderate flood risk

TERRAIN_CLASS_LABELS = {
    0: "Drenaje Natural",
    1: "Zona Inundable",
    2: "Necesita Drenaje",
    3: "Loma / Divisoria",
    4: "Terreno Funcional",
}

TERRAIN_PLANO_SECO = 0
TERRAIN_PLANO_HUMEDO = 1
TERRAIN_DRENAJE_ACTIVO = 2
TERRAIN_ACUMULACION = 3


def _valid_percentile(
    data: np.ndarray | None,
    valid_mask: np.ndarray,
    percentile: float,
) -> float:
    return valid_percentile_impl(
        np_module=np,
        data=data,
        valid_mask=valid_mask,
        percentile=percentile,
    )


def _resolve_classify_terrain_inputs(
    *,
    filled_dem_path: str | None,
    output_dir: str | None,
    hand_path: str | None,
    tpi_path: str | None,
    flow_acc_path: str | None,
    twi_path: str | None,
    slope_path: str | None,
    output_path: str | None,
) -> tuple[bool, str, str, str | None, str | None, str | None]:
    return resolve_classify_terrain_inputs_impl(
        path_cls=Path,
        filled_dem_path=filled_dem_path,
        output_dir=output_dir,
        hand_path=hand_path,
        tpi_path=tpi_path,
        flow_acc_path=flow_acc_path,
        twi_path=twi_path,
        slope_path=slope_path,
        output_path=output_path,
    )


def classify_terrain(
    filled_dem_path: str | None = None,
    output_dir: str | None = None,
    hand_path: str | None = None,
    tpi_path: str | None = None,
    curvature_path: str | None = None,
    flow_acc_path: str | None = None,
    twi_path: str | None = None,
    slope_path: str | None = None,
    output_path: str | None = None,
) -> str:
    (
        legacy_mode,
        reference_raster_path,
        resolved_output_path,
        hand_path,
        flow_acc_path,
        twi_path,
    ) = _resolve_classify_terrain_inputs(
        filled_dem_path=filled_dem_path,
        output_dir=output_dir,
        hand_path=hand_path,
        tpi_path=tpi_path,
        flow_acc_path=flow_acc_path,
        twi_path=twi_path,
        slope_path=slope_path,
        output_path=output_path,
    )

    # Reference metadata from filled DEM
    with rasterio.open(reference_raster_path) as src:
        ref_shape = (
            getattr(src, "height", src.meta["height"]),
            getattr(src, "width", src.meta["width"]),
        )
        meta = src.meta.copy()

    hand, nodata_hand = _load_optional_raster(hand_path)
    flow_acc, nodata_fa = _load_optional_raster(flow_acc_path)
    twi, nodata_twi = _load_optional_raster(twi_path)

    # --- Combined nodata mask -------------------------------------------------
    nodata_mask = np.zeros(ref_shape, dtype=bool)
    for data, nodata in [
        (hand, nodata_hand),
        (flow_acc, nodata_fa),
        (twi, nodata_twi),
    ]:
        if data is not None and nodata is not None:
            nodata_mask |= data == nodata
            nodata_mask |= ~np.isfinite(data)
        elif data is not None:
            nodata_mask |= ~np.isfinite(data)

    valid = ~nodata_mask

    if not legacy_mode:
        fa_p99 = _valid_percentile(flow_acc, valid, 99)
        twi_p55 = _valid_percentile(twi, valid, 55)
        twi_p35 = _valid_percentile(twi, valid, 35)
        logger.info(
            "classify_terrain thresholds fa_p99=%.2f twi_p55=%.2f twi_p35=%.2f",
            fa_p99,
            twi_p55,
            twi_p35,
        )

    classified = classify_terrain_arrays(
        ref_shape=ref_shape,
        valid=valid,
        legacy_mode=legacy_mode,
        hand=hand,
        flow_acc=flow_acc,
        twi=twi,
        valid_percentile=_valid_percentile,
        terreno_consts={
            "plano_seco": TERRAIN_PLANO_SECO,
            "plano_humedo": TERRAIN_PLANO_HUMEDO,
            "drenaje_activo": TERRAIN_DRENAJE_ACTIVO,
            "acumulacion": TERRAIN_ACUMULACION,
            "sin_riesgo": TERRAIN_SIN_RIESGO,
            "riesgo_medio": TERRAIN_RIESGO_MEDIO,
            "riesgo_alto": TERRAIN_RIESGO_ALTO,
            "drenaje_natural": TERRAIN_DRENAJE_NATURAL,
        },
    )

    # --- Nodata ---------------------------------------------------------------
    out_nodata = np.uint8(255)
    classified[nodata_mask] = out_nodata

    meta.update(
        {"dtype": "uint8", "count": 1, "driver": "GTiff", "nodata": int(out_nodata)}
    )
    return _write_single_band(resolved_output_path, classified, meta)


# k) Download DEM from Google Earth Engine
def download_dem_from_gee(
    zona_geometry: dict[str, Any],
    output_path: str,
    scale: int = 30,
) -> str:
    import ee
    import requests

    return download_dem_impl(
        ee_module=ee,
        requests_module=requests,
        rasterio_module=rasterio,
        ensure_parent_dir=_ensure_parent_dir,
        zona_geometry=zona_geometry,
        output_path=output_path,
        scale=scale,
    )


# l) Delineate watershed basins
def delineate_basins(
    flow_dir_path: str,
    output_raster_path: str,
    output_geojson_path: str,
    min_area_ha: float = 10.0,
) -> str:
    return vectorize_basins_impl(
        read_single_band=_read_single_band,
        write_feature_collection=_write_feature_collection,
        shapes_fn=shapes,
        flow_dir_path=flow_dir_path,
        output_raster_path=output_raster_path,
        output_geojson_path=output_geojson_path,
        min_area_ha=min_area_ha,
        get_wbt=_get_wbt,
        ensure_parent_dir=_ensure_parent_dir,
    )


# m) Convert GeoTIFF to Cloud-Optimized GeoTIFF (COG)
def convert_to_cog(input_path: str, output_path: str | None = None) -> str:
    from rio_cogeo.cogeo import cog_translate
    from rio_cogeo.profiles import cog_profiles

    return convert_to_cog_impl(
        path_cls=Path,
        ensure_parent_dir=_ensure_parent_dir,
        cog_translate_fn=cog_translate,
        cog_profiles_get=cog_profiles.get,
        input_path=input_path,
        output_path=output_path,
    )
