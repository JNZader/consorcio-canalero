"""Common filesystem/raster helpers for terrain processing."""

from __future__ import annotations

import json
from typing import Any

import numpy as np


def ensure_parent_dir_impl(*, path_cls, output_path: str) -> None:
    path_cls(output_path).parent.mkdir(parents=True, exist_ok=True)


def read_single_band_impl(
    *, rasterio_module, raster_path: str
) -> tuple[np.ndarray, float | None, Any, dict[str, Any], Any]:
    with rasterio_module.open(raster_path) as src:
        return (
            src.read(1),
            src.nodata,
            src.transform,
            src.meta.copy(),
            src.crs,
        )


def write_single_band_impl(
    *,
    rasterio_module,
    ensure_parent_dir,
    output_path: str,
    data: np.ndarray,
    meta: dict[str, Any],
) -> str:
    ensure_parent_dir(output_path)
    with rasterio_module.open(output_path, "w", **meta) as dst:
        dst.write(data, 1)
    return output_path


def copy_if_projected_impl(
    *, shutil_module, input_path: str, output_path: str, src
) -> bool:
    if src.crs and src.crs.is_projected:
        shutil_module.copy2(input_path, output_path)
        return True
    return False


def compute_utm_crs_impl(*, bounds) -> str:
    center_lon = (bounds.left + bounds.right) / 2
    center_lat = (bounds.top + bounds.bottom) / 2
    zone = int((center_lon + 180) / 6) + 1
    epsg = 32600 + zone if center_lat >= 0 else 32700 + zone
    return f"EPSG:{epsg}"


def write_feature_collection_impl(
    *,
    ensure_parent_dir,
    output_path: str,
    features: list[dict[str, Any]],
    crs_name: str,
) -> str:
    geojson = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": crs_name}},
        "features": features,
    }
    ensure_parent_dir(output_path)
    with open(output_path, "w") as f:
        json.dump(geojson, f)
    return output_path


def load_optional_raster_impl(
    *, path_cls, rasterio_module, path: str | None
) -> tuple[np.ndarray | None, float | None]:
    if path is None or not path_cls(path).exists():
        return None, None
    with rasterio_module.open(path) as src:
        return src.read(1).astype(np.float64), src.nodata


def valid_percentile_impl(
    *, np_module, data: np.ndarray | None, valid_mask: np.ndarray, percentile: float
) -> float:
    if data is None:
        return 0.0
    vals = data[valid_mask]
    return float(np_module.percentile(vals, percentile)) if vals.size > 0 else 0.0


def resolve_classify_terrain_inputs_impl(
    *,
    path_cls,
    filled_dem_path: str | None,
    output_dir: str | None,
    hand_path: str | None,
    tpi_path: str | None,
    flow_acc_path: str | None,
    twi_path: str | None,
    slope_path: str | None,
    output_path: str | None,
) -> tuple[bool, str, str, str | None, str | None, str | None]:
    legacy_call = (
        slope_path is not None
        or output_path is not None
        or (
            filled_dem_path is not None
            and output_dir is not None
            and hand_path is not None
            and tpi_path is not None
            and flow_acc_path is None
            and twi_path is None
        )
    )
    if legacy_call:
        slope_input = slope_path or filled_dem_path
        twi_input = twi_path or output_dir
        flow_acc_input = flow_acc_path or hand_path
        resolved_output = output_path or tpi_path
        if (
            slope_input is None
            or twi_input is None
            or flow_acc_input is None
            or resolved_output is None
        ):
            raise ValueError(
                "Legacy classify_terrain call requires slope, TWI, flow_acc, and output paths"
            )
        return True, slope_input, resolved_output, None, flow_acc_input, twi_input

    if filled_dem_path is None or output_dir is None:
        raise ValueError(
            "Current classify_terrain call requires filled_dem_path and output_dir"
        )
    return (
        False,
        filled_dem_path,
        str(path_cls(output_dir) / "terrain_class.tif"),
        hand_path,
        flow_acc_path,
        twi_path,
    )
