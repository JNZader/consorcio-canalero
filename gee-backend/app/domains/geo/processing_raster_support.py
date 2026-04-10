"""Raster/core support helpers for terrain processing."""

from __future__ import annotations

from typing import Any

import numpy as np
from shapely.geometry import mapping, shape


def ensure_nodata_impl(
    *,
    rasterio_module,
    shutil_module,
    write_single_band,
    dem_path: str,
    output_path: str,
    nodata_value: float,
) -> str:
    with rasterio_module.open(dem_path) as src:
        if src.nodata is not None:
            shutil_module.copy2(dem_path, output_path)
            return output_path
        profile = src.profile.copy()
        data = src.read(1)
    profile.update(nodata=nodata_value)
    return write_single_band(output_path, data, profile)


def reproject_to_utm_impl(
    *,
    rasterio_module,
    copy_if_projected,
    compute_utm_crs,
    ensure_parent_dir,
    calculate_default_transform_fn,
    reproject_fn,
    resampling_bilinear,
    dem_path: str,
    output_path: str,
) -> str:
    with rasterio_module.open(dem_path) as src:
        if copy_if_projected(src, dem_path, output_path):
            return output_path
        dst_crs = compute_utm_crs(src.bounds)
        transform, width, height = calculate_default_transform_fn(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )
        profile = src.profile.copy()
        profile.update(crs=dst_crs, transform=transform, width=width, height=height)
        ensure_parent_dir(output_path)
        with rasterio_module.open(output_path, "w", **profile) as dst:
            reproject_fn(
                source=rasterio_module.band(src, 1),
                destination=rasterio_module.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=dst_crs,
                resampling=resampling_bilinear,
            )
    return output_path


def compute_slope_impl(
    *,
    read_single_band,
    write_single_band,
    dem_path: str,
    output_path: str,
) -> str:
    dem, nodata, transform, meta, _ = read_single_band(dem_path)
    dem = dem.astype(np.float64)
    cell_x = abs(transform.a)
    cell_y = abs(transform.e)
    dz_dy, dz_dx = np.gradient(dem, cell_y, cell_x)
    slope_deg = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))).astype(np.float32)
    if nodata is not None:
        slope_deg[dem == nodata] = np.float32(nodata)
    meta.update({"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": nodata})
    return write_single_band(output_path, slope_deg, meta)


def compute_aspect_impl(
    *,
    read_single_band,
    write_single_band,
    dem_path: str,
    output_path: str,
) -> str:
    dem, nodata, transform, meta, _ = read_single_band(dem_path)
    dem = dem.astype(np.float64)
    cell_x = abs(transform.a)
    cell_y = abs(transform.e)
    dz_dy, dz_dx = np.gradient(dem, cell_y, cell_x)
    aspect_deg = np.mod(
        np.degrees(np.arctan2(-dz_dy, dz_dx)).astype(np.float32), np.float32(360.0)
    )
    if nodata is not None:
        aspect_deg[dem == nodata] = np.float32(nodata)
    meta.update({"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": nodata})
    return write_single_band(output_path, aspect_deg, meta)


def compute_twi_impl(
    *,
    read_single_band,
    write_single_band,
    min_slope_rad: float,
    slope_path: str,
    flow_acc_path: str,
    output_path: str,
) -> str:
    slope_deg, nodata_slope, transform, meta, _ = read_single_band(slope_path)
    slope_deg = slope_deg.astype(np.float64)
    cell_size = abs(transform.a)
    flow_acc, nodata_fa, _, _, _ = read_single_band(flow_acc_path)
    flow_acc = flow_acc.astype(np.float64)
    nodata_mask = np.zeros(slope_deg.shape, dtype=bool)
    if nodata_slope is not None:
        nodata_mask |= slope_deg == nodata_slope
    if nodata_fa is not None:
        nodata_mask |= flow_acc == nodata_fa
    slope_rad = np.maximum(np.radians(slope_deg), np.float64(min_slope_rad))
    specific_area = np.maximum(flow_acc * cell_size, np.float64(1e-10))
    twi = np.log(specific_area / np.tan(slope_rad)).astype(np.float32)
    out_nodata = np.float32(-9999.0)
    twi[nodata_mask] = out_nodata
    meta.update(
        {"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": float(out_nodata)}
    )
    return write_single_band(output_path, twi, meta)


def convert_to_cog_impl(
    *,
    path_cls,
    ensure_parent_dir,
    cog_translate_fn,
    cog_profiles_get,
    input_path: str,
    output_path: str | None,
) -> str:
    if output_path is None:
        output_path = str(path_cls(input_path).with_suffix(".cog.tif"))
    ensure_parent_dir(output_path)
    output_profile = cog_profiles_get("deflate")
    config = {
        "GDAL_NUM_THREADS": "ALL_CPUS",
        "GDAL_TIFF_OVR_BLOCKSIZE": "512",
    }
    cog_translate_fn(
        input_path,
        output_path,
        output_profile,
        overview_level=5,
        overview_resampling="nearest",
        config=config,
        quiet=True,
    )
    return output_path


def clip_to_geometry_impl(
    *,
    rasterio_module,
    rasterio_mask_fn,
    ensure_parent_dir,
    dem_path: str,
    geometry: dict[str, Any],
    output_path: str,
    geometry_crs: str,
) -> str:
    with rasterio_module.open(dem_path) as src:
        dem_crs = str(src.crs)
        clip_geom = shape(geometry)
        if dem_crs != geometry_crs:
            from pyproj import Transformer
            from shapely.ops import transform as shapely_transform

            transformer = Transformer.from_crs(geometry_crs, dem_crs, always_xy=True)
            clip_geom = shapely_transform(transformer.transform, clip_geom)
        out_image, out_transform = rasterio_mask_fn(
            src, [mapping(clip_geom)], crop=True
        )
        profile = src.profile.copy()
        profile.update(
            height=out_image.shape[1], width=out_image.shape[2], transform=out_transform
        )
    ensure_parent_dir(output_path)
    with rasterio_module.open(output_path, "w", **profile) as dst:
        dst.write(out_image)
    return output_path


def clip_bbox_impl(
    *,
    rasterio_module,
    rasterio_mask_fn,
    ensure_parent_dir,
    bbox,
    dem_path: str,
    output_path: str,
) -> str:
    from shapely.geometry import box

    geom = box(*bbox)
    with rasterio_module.open(dem_path) as src:
        out_image, out_transform = rasterio_mask_fn(src, [mapping(geom)], crop=True)
        out_meta = src.meta.copy()
        out_meta.update(
            {
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
            }
        )
    ensure_parent_dir(output_path)
    with rasterio_module.open(output_path, "w", **out_meta) as dst:
        dst.write(out_image)
    return output_path


def classify_terrain_arrays(
    *,
    ref_shape,
    valid,
    legacy_mode: bool,
    hand,
    flow_acc,
    twi,
    valid_percentile,
    terreno_consts: dict[str, int],
) -> np.ndarray:
    if legacy_mode:
        classified = np.full(ref_shape, terreno_consts["plano_seco"], dtype=np.uint8)
        if twi is not None:
            classified[valid & (twi >= valid_percentile(twi, valid, 50))] = (
                terreno_consts["plano_humedo"]
            )
        if flow_acc is not None:
            classified[valid & (flow_acc > 1000)] = terreno_consts["drenaje_activo"]
            classified[valid & (flow_acc > 5000)] = terreno_consts["acumulacion"]
        return classified

    classified = np.full(ref_shape, terreno_consts["sin_riesgo"], dtype=np.uint8)
    fa_p99 = valid_percentile(flow_acc, valid, 99)
    twi_p55 = valid_percentile(twi, valid, 55)
    twi_p35 = valid_percentile(twi, valid, 35)
    if hand is not None and twi is not None:
        medio_mask = valid & (hand < 1.5) & (twi > twi_p35)
        classified[medio_mask] = terreno_consts["riesgo_medio"]
        alto_mask = valid & (hand < 0.8) & (twi > twi_p55)
        classified[alto_mask] = terreno_consts["riesgo_alto"]
    if flow_acc is not None and hand is not None:
        drenaje_mask = valid & (flow_acc > fa_p99) & (hand < 1.0)
        classified[drenaje_mask] = terreno_consts["drenaje_natural"]
    return classified
