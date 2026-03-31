from __future__ import annotations

import importlib
import io
import math
import sys
import types

import numpy as np
import pytest
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.transform import from_origin


@pytest.fixture
def tile_service_module():
    """Import tile_service with a minimal rio-tiler stub for unit tests."""
    rio_tiler = types.ModuleType("rio_tiler")
    rio_tiler_io = types.ModuleType("rio_tiler.io")
    rio_tiler_errors = types.ModuleType("rio_tiler.errors")

    class DummyReader:  # pragma: no cover - only used to satisfy imports
        pass

    class DummyTileOutsideBounds(Exception):
        pass

    rio_tiler_io.Reader = DummyReader
    rio_tiler_errors.TileOutsideBounds = DummyTileOutsideBounds

    sys.modules["rio_tiler"] = rio_tiler
    sys.modules["rio_tiler.io"] = rio_tiler_io
    sys.modules["rio_tiler.errors"] = rio_tiler_errors

    module_name = "app.domains.geo.tile_service"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _lonlat_to_xyz(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    lat_rad = math.radians(lat)
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def test_render_categorical_png_maps_classes_and_hides_selected(tile_service_module):
    raw = np.array([[0, 1, 2], [3, 4, 255]], dtype=np.uint8)
    mask = np.array([[255, 255, 255], [255, 255, 0]], dtype=np.uint8)

    png = tile_service_module._render_categorical_png(
        raw,
        mask,
        tile_service_module.CATEGORICAL_COLORS["terrain_class"],
        hidden_classes={1, 3},
    )

    rgba = np.array(Image.open(io.BytesIO(png)).convert("RGBA"))

    assert tuple(rgba[0, 0]) == (76, 175, 80, 180)
    assert tuple(rgba[0, 1]) == (30, 136, 229, 0)
    assert tuple(rgba[0, 2]) == (211, 47, 47, 255)
    assert tuple(rgba[1, 0]) == (255, 143, 0, 0)
    assert tuple(rgba[1, 1]) == (0, 0, 0, 0)
    assert tuple(rgba[1, 2]) == (0, 0, 0, 0)


def test_read_categorical_tile_preserves_class_4_from_utm_raster(tmp_path, tile_service_module):
    tif_path = tmp_path / "terrain_class.tif"

    data = np.full((512, 512), 4, dtype=np.uint8)
    data[:80, :80] = 0
    data[80:160, 80:160] = 1
    data[160:240, 160:240] = 2
    data[240:320, 240:320] = 3
    data[0:16, 496:512] = 255

    transform = from_origin(360000, 6400000, 10, 10)
    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="uint8",
        crs="EPSG:32720",
        transform=transform,
        nodata=255,
    ) as dst:
        dst.write(data, 1)

    center_easting = 360000 + (data.shape[1] * 10) / 2
    center_northing = 6400000 - (data.shape[0] * 10) / 2
    lon, lat = Transformer.from_crs("EPSG:32720", "EPSG:4326", always_xy=True).transform(
        center_easting,
        center_northing,
    )
    x, y = _lonlat_to_xyz(lon, lat, z=14)

    tile = tile_service_module._read_categorical_tile(tif_path, x, y, 14, tilesize=256)

    assert tile is not None
    raw, mask = tile
    assert raw.shape == (256, 256)
    assert mask.shape == (256, 256)
    assert mask.dtype == np.uint8
    assert 4 in np.unique(raw)
    assert np.count_nonzero(raw == 4) > 0
    assert np.all(mask[raw == 255] == 0)


def test_read_elevation_tile_and_render_terrain_rgb_png_keep_256_dimensions(
    tmp_path,
    tile_service_module,
):
    tif_path = tmp_path / "dem_raw.tif"

    data = np.linspace(100.0, 130.0, num=512 * 512, dtype=np.float32).reshape(512, 512)
    data[0:16, 496:512] = -9999.0

    transform = from_origin(360000, 6400000, 10, 10)
    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:32720",
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)

    center_easting = 360000 + (data.shape[1] * 10) / 2
    center_northing = 6400000 - (data.shape[0] * 10) / 2
    lon, lat = Transformer.from_crs("EPSG:32720", "EPSG:4326", always_xy=True).transform(
        center_easting,
        center_northing,
    )
    x, y = _lonlat_to_xyz(lon, lat, z=14)

    tile = tile_service_module._read_elevation_tile(tif_path, x, y, 14, tilesize=256)

    assert tile is not None
    elevation, valid_mask = tile
    assert elevation.shape == (256, 256)
    assert valid_mask.shape == (256, 256)
    assert valid_mask.dtype == np.bool_

    png = tile_service_module._render_terrain_rgb_png(elevation, valid_mask)
    rendered = np.array(Image.open(io.BytesIO(png)).convert("RGBA"))

    assert rendered.shape == (256, 256, 4)
    assert rendered.dtype == np.uint8
