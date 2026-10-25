"""GEO-3 regression: zonal stats must honor each raster's own nodata tag.

``compute_zonal_stats`` hardcoded ``nodata=-32768`` for EVERY raster, but
``classify_terrain`` writes uint8 with nodata=255 (processing.py) and
composites are written with nodata=None. On a terrain_class raster the 255
fill was counted as a legitimate maximum; on composites the override matched
nothing (uint8 cannot hold -32768).

The fix passes ``src.nodata`` through and keeps -32768 ONLY as a fallback for
float16/float32 rasters with no embedded nodata tag — historical float terrain
products whose fill value was never declared in metadata. These tests pin all
three behaviours.
"""

from __future__ import annotations

import numpy as np
import rasterio
from affine import Affine
from shapely.geometry import box

from app.domains.geo.zonal_stats import compute_zonal_stats

_CRS = "EPSG:32720"
_TRANSFORM = Affine(10.0, 0.0, 500_000.0, 0.0, -10.0, 7_000_000.0)
_SIZE = 4  # 4x4 cells, all covered by the zone below
_ZONE = {
    "id": "z1",
    "name": "whole-raster",
    # GeoJSON box over the entire raster extent, in the raster's own CRS.
    "geometry": box(500_000.0, 7_000_000.0 - 40.0, 500_000.0 + 40.0, 7_000_000.0).__geo_interface__,
}


def _write_raster(tmp_path, data: np.ndarray, nodata) -> str:
    path = tmp_path / f"raster_{data.dtype.str}_{str(nodata).replace('-', 'm')}.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs=_CRS,
        transform=_TRANSFORM,
        nodata=nodata,
    ) as dst:
        dst.write(data, 1)
    return str(path)


def test_uint8_terrain_class_fill_255_is_excluded(tmp_path) -> None:
    """RED pre-fix: nodata=-32768 counted the 255 fill, so max was 255."""
    data = np.arange(1, _SIZE * _SIZE + 1, dtype=np.uint8).reshape(_SIZE, _SIZE)
    data[0, 0] = 255  # was 1
    data[_SIZE - 1, _SIZE - 1] = 255  # was 16
    raster_path = _write_raster(tmp_path, data, nodata=255)

    results = compute_zonal_stats([_ZONE], raster_path, ["min", "max", "count"], geometry_crs=_CRS)

    assert results[0]["max"] == 15  # pre-fix: 255
    assert results[0]["min"] == 2  # pre-fix: 1 masked cell counted as 255 anyway
    assert results[0]["count"] == _SIZE * _SIZE - 2  # pre-fix: 16


def test_float32_without_nodata_tag_keeps_the_legacy_fill(tmp_path) -> None:
    """The documented fallback: undeclared float terrain fill stays masked."""
    data = np.array(
        [
            [10.0, 20.0, 30.0, 40.0],
            [50.0, -32768.0, 60.0, 70.0],
            [80.0, 90.0, -32768.0, 100.0],
            [1.0, 2.0, 3.0, 4.0],
        ],
        dtype=np.float32,
    )
    raster_path = _write_raster(tmp_path, data, nodata=None)

    results = compute_zonal_stats([_ZONE], raster_path, ["max", "count"], geometry_crs=_CRS)

    assert results[0]["max"] == 100.0
    assert results[0]["count"] == _SIZE * _SIZE - 2


def test_uint8_composite_style_masks_nothing(tmp_path) -> None:
    """Composites (nodata=None, uint8): every pixel is data, zeros included."""
    data = np.arange(0, _SIZE * _SIZE, dtype=np.uint8).reshape(_SIZE, _SIZE)
    raster_path = _write_raster(tmp_path, data, nodata=None)

    results = compute_zonal_stats([_ZONE], raster_path, ["min", "max", "count"], geometry_crs=_CRS)

    assert results[0]["min"] == 0
    assert results[0]["max"] == 15
    assert results[0]["count"] == _SIZE * _SIZE
