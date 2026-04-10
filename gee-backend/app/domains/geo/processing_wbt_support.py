"""Whitebox/vector/IO support helpers for terrain processing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import mapping, shape


def run_wbt_tool_impl(*, output_path: str, ensure_parent_dir, get_wbt, runner) -> str:
    ensure_parent_dir(output_path)
    runner(get_wbt(), output_path)
    return output_path


def remove_off_terrain_objects_impl(
    *,
    run_wbt_tool,
    dem_path: str,
    output_path: str,
    filter_size: int,
    slope_threshold: float,
) -> str:
    return run_wbt_tool(
        output_path,
        lambda wbt, path: wbt.remove_off_terrain_objects(
            dem_path,
            path,
            filter=filter_size,
            slope=slope_threshold,
        ),
    )


def fill_sinks_impl(*, run_wbt_tool, dem_path: str, output_path: str) -> str:
    return run_wbt_tool(
        output_path, lambda wbt, path: wbt.fill_depressions(dem_path, path)
    )


def compute_flow_direction_impl(
    *, run_wbt_tool, filled_dem_path: str, output_path: str
) -> str:
    return run_wbt_tool(
        output_path, lambda wbt, path: wbt.d8_pointer(filled_dem_path, path)
    )


def compute_flow_accumulation_impl(
    *, run_wbt_tool, flow_dir_path: str, output_path: str
) -> str:
    return run_wbt_tool(
        output_path,
        lambda wbt, path: wbt.d8_flow_accumulation(
            flow_dir_path, path, out_type="cells"
        ),
    )


def compute_profile_curvature_impl(
    *,
    path_cls,
    run_wbt_tool,
    filled_dem_path: str,
    output_dir: str,
) -> str:
    output_path = str(path_cls(output_dir) / "profile_curvature.tif")
    return run_wbt_tool(
        output_path, lambda wbt, path: wbt.profile_curvature(filled_dem_path, path)
    )


def compute_tpi_impl(
    *,
    path_cls,
    run_wbt_tool,
    filled_dem_path: str,
    output_dir: str,
    radius: int,
) -> str:
    output_path = str(path_cls(output_dir) / "tpi.tif")
    filterx = radius * 2 + 1
    filtery = radius * 2 + 1
    return run_wbt_tool(
        output_path,
        lambda wbt, path: wbt.dev_from_mean_elev(
            filled_dem_path,
            path,
            filterx=filterx,
            filtery=filtery,
        ),
    )


def compute_hand_impl(
    *,
    read_single_band,
    write_single_band,
    get_wbt,
    ensure_parent_dir,
    dem_path: str,
    flow_dir_path: str,
    flow_acc_path: str,
    output_path: str,
    drainage_threshold: int,
) -> str:
    import tempfile

    ensure_parent_dir(output_path)
    with tempfile.TemporaryDirectory() as tmpdir:
        drainage_raster = str(Path(tmpdir) / "drainage.tif")
        fa, nodata_fa, _, meta, _ = read_single_band(flow_acc_path)
        drainage = np.where(fa >= drainage_threshold, 1, 0).astype(np.int16)
        if nodata_fa is not None:
            drainage[fa == nodata_fa] = 0
        meta.update({"dtype": "int16", "count": 1, "nodata": 0, "driver": "GTiff"})
        write_single_band(drainage_raster, drainage, meta)
        get_wbt().elevation_above_stream(dem_path, drainage_raster, output_path)
    return output_path


def extract_drainage_network_impl(
    *,
    read_single_band,
    write_feature_collection,
    shapes_fn,
    flow_acc_path: str,
    threshold: int,
    output_path: str,
) -> str:
    fa, nodata, transform, _, crs = read_single_band(flow_acc_path)
    drainage_mask = fa > threshold
    if nodata is not None:
        drainage_mask &= fa != nodata
    drainage_binary = drainage_mask.astype(np.uint8)
    features = []
    for geom, value in shapes_fn(
        drainage_binary, mask=drainage_binary, transform=transform
    ):
        if value == 1:
            features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {"class": "drainage"},
                }
            )
    return write_feature_collection(
        output_path,
        features=features,
        crs_name=str(crs) if crs else "EPSG:4326",
    )


def vectorize_basins_impl(
    *,
    read_single_band,
    write_feature_collection,
    shapes_fn,
    flow_dir_path: str,
    output_raster_path: str,
    output_geojson_path: str,
    min_area_ha: float,
    get_wbt,
    ensure_parent_dir,
) -> str:
    ensure_parent_dir(output_raster_path)
    ensure_parent_dir(output_geojson_path)
    get_wbt().basins(flow_dir_path, output_raster_path)
    basin_data, basins_nodata, transform, _, crs = read_single_band(output_raster_path)
    need_reproject = crs and crs.is_projected
    if need_reproject:
        from pyproj import Transformer

        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    features: list[dict[str, Any]] = []
    for geom, basin_id in shapes_fn(basin_data, transform=transform):
        if basin_id == 0 or basin_id == basins_nodata:
            continue
        poly = shape(geom)
        if crs and crs.is_projected:
            area_m2 = poly.area
        else:
            centroid = poly.centroid
            lat_rad = np.radians(centroid.y)
            area_m2 = poly.area * 111_320.0 * (111_320.0 * np.cos(lat_rad))
        area_ha = area_m2 / 10_000.0
        if area_ha < min_area_ha:
            continue
        if need_reproject:
            from shapely.ops import transform as shapely_transform

            out_geom = mapping(shapely_transform(transformer.transform, poly))
        else:
            out_geom = geom
        features.append(
            {
                "type": "Feature",
                "geometry": out_geom,
                "properties": {"basin_id": int(basin_id), "area_ha": round(area_ha, 2)},
            }
        )
    return write_feature_collection(
        output_geojson_path, features=features, crs_name="EPSG:4326"
    )


def download_dem_impl(
    *,
    ee_module,
    requests_module,
    rasterio_module,
    ensure_parent_dir,
    zona_geometry: dict[str, Any],
    output_path: str,
    scale: int,
) -> str:
    dem = ee_module.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
    region = ee_module.Geometry(zona_geometry)
    clipped = dem.clip(region)
    url = clipped.getDownloadURL(
        {"format": "GEO_TIFF", "scale": scale, "region": region, "crs": "EPSG:4326"}
    )
    ensure_parent_dir(output_path)
    tmp_path = str(Path(output_path).with_suffix(".tmp.tif"))
    response = requests_module.get(url, stream=True, timeout=300)
    response.raise_for_status()
    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    with rasterio_module.open(tmp_path) as src:
        profile = src.profile.copy()
        profile.update(compress="deflate", predictor=2)
        with rasterio_module.open(output_path, "w", **profile) as dst:
            dst.write(src.read())
    Path(tmp_path).unlink(missing_ok=True)
    return output_path
