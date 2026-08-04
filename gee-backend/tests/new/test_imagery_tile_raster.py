"""Raster tile maths: mercator bounds, terrain-RGB encoding, smoothing, PNGs.

All pure numpy/rasterio — no service, no database.
"""

from __future__ import annotations

import io
import math

import numpy as np
import pytest
import rasterio
from PIL import Image as PILImage
from rasterio.transform import from_bounds

from app.domains.geo.tile_service_support import (
    CATEGORICAL_COLORS,
    TERRAIN_NODATA_FEATHER_PX,
    TERRAIN_SMOOTHING_METHODS,
    WEB_MERCATOR_HALF_WORLD,
    bounds_intersect,
    crop_center,
    encode_terrain_rgb,
    feather_nodata_elevation,
    get_elevation_baseline,
    read_categorical_tile,
    read_elevation_tile,
    render_categorical_png,
    render_flat_terrain_rgb_png,
    render_terrain_rgb_png,
    smooth_elevation_tile,
    tile_bounds_3857,
)


# ── tile_bounds_3857 ───────────────────────────────────────────────────────


def test_tile_bounds_at_zoom_zero_cover_the_whole_world() -> None:
    left, bottom, right, top = tile_bounds_3857(0, 0, 0)

    assert left == pytest.approx(-WEB_MERCATOR_HALF_WORLD)
    assert right == pytest.approx(WEB_MERCATOR_HALF_WORLD)
    assert top == pytest.approx(WEB_MERCATOR_HALF_WORLD)
    assert bottom == pytest.approx(-WEB_MERCATOR_HALF_WORLD)


def test_tile_bounds_children_tile_the_parent() -> None:
    parent = tile_bounds_3857(0, 0, 0)
    top_left = tile_bounds_3857(0, 0, 1)
    bottom_right = tile_bounds_3857(1, 1, 1)

    assert top_left[0] == pytest.approx(parent[0])
    assert top_left[3] == pytest.approx(parent[3])
    assert bottom_right[2] == pytest.approx(parent[2])
    assert bottom_right[1] == pytest.approx(parent[1])
    assert top_left[2] == pytest.approx(bottom_right[0])


def test_tile_bounds_are_square_at_every_zoom() -> None:
    for zoom in range(0, 15):
        left, bottom, right, top = tile_bounds_3857(3 % max(1, 2**zoom), 1, zoom)
        assert (right - left) == pytest.approx(top - bottom)
        assert (right - left) == pytest.approx(WEB_MERCATOR_HALF_WORLD * 2 / (2**zoom))


# ── bounds_intersect ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((0, 0, 10, 10), (5, 5, 15, 15), True),
        ((0, 0, 10, 10), (10, 0, 20, 10), False),  # touching edges do not count
        ((0, 0, 10, 10), (11, 11, 20, 20), False),
        ((0, 0, 10, 10), (2, 2, 4, 4), True),  # fully contained
        ((0, 0, 10, 10), (-5, -5, 1, 1), True),
        ((0, 0, 10, 10), (0, -20, 10, 0), False),
    ],
)
def test_bounds_intersect(a, b, expected: bool) -> None:
    assert bounds_intersect(a, b) is expected
    assert bounds_intersect(b, a) is expected


# ── terrain-RGB encoding ───────────────────────────────────────────────────


@pytest.mark.parametrize("elevation", [0.0, 1.0, 123.4, -10.0, 8848.0])
def test_terrain_rgb_roundtrips_to_the_original_elevation(elevation: float) -> None:
    encoded = encode_terrain_rgb(np.full((2, 2), elevation, dtype=np.float32))

    r, g, b = (int(encoded[i][0, 0]) for i in range(3))
    decoded = -10000 + ((r * 256 * 256 + g * 256 + b) * 0.1)

    assert decoded == pytest.approx(elevation, abs=0.05)


def test_terrain_rgb_clips_out_of_range_elevations() -> None:
    encoded = encode_terrain_rgb(np.array([[-99999.0, 1e9]], dtype=np.float64))

    assert encoded.shape == (3, 1, 2)
    assert encoded.dtype == np.uint8


def test_render_terrain_rgb_png_produces_a_decodable_rgb_image() -> None:
    data = np.full((8, 8), 42.0, dtype=np.float32)

    png = render_terrain_rgb_png(data, np.ones((8, 8), dtype=bool))

    image = PILImage.open(io.BytesIO(png))
    assert image.format == "PNG"
    assert image.mode == "RGB"
    assert image.size == (8, 8)


# ── nodata feathering (vertical-curtain fix) ───────────────────────────────


def _decode_terrain_png(png: bytes) -> np.ndarray:
    """Decode a terrain-RGB PNG back into elevations."""
    pixels = np.asarray(PILImage.open(io.BytesIO(png)).convert("RGB")).astype(np.float64)
    return -10000.0 + ((pixels[..., 0] * 65536.0 + pixels[..., 1] * 256.0 + pixels[..., 2]) * 0.1)


def test_feather_leaves_a_fully_valid_tile_untouched() -> None:
    data = np.linspace(0.0, 50.0, 64, dtype=np.float32).reshape(8, 8)

    feathered = feather_nodata_elevation(data, np.ones((8, 8), dtype=bool))

    assert np.array_equal(feathered, data)


def test_feather_of_a_fully_invalid_tile_is_the_baseline_plane() -> None:
    data = np.full((8, 8), 33.0, dtype=np.float32)

    feathered = feather_nodata_elevation(data, np.zeros((8, 8), dtype=bool))

    assert np.array_equal(feathered, np.zeros((8, 8), dtype=np.float32))


def test_feather_ramps_the_nodata_side_down_instead_of_cliffing_to_zero() -> None:
    """The regression this fixes: nodata used to snap to the baseline (0.0),
    which is a full-relief vertical wall at the edge of the DEM recorte."""
    width = 4 * TERRAIN_NODATA_FEATHER_PX
    data = np.full((8, width), 100.0, dtype=np.float32)
    valid = np.zeros((8, width), dtype=bool)
    valid[:, : width // 2] = True  # left half valid, right half nodata

    feathered = feather_nodata_elevation(data, valid)

    row = feathered[0]
    edge = width // 2
    # No cliff: the first nodata column is within one ramp step of the terrain.
    step = 100.0 / TERRAIN_NODATA_FEATHER_PX
    assert row[edge] == pytest.approx(100.0 - step, abs=0.01)
    # Monotonically non-increasing, and the far field is the baseline plane —
    # the same value tiles fully outside the DEM are rendered with.
    assert np.all(np.diff(row[edge:]) <= 1e-6)
    assert row[edge + TERRAIN_NODATA_FEATHER_PX] == pytest.approx(0.0, abs=1e-6)
    assert row[-1] == pytest.approx(0.0, abs=1e-6)
    # Every consecutive step in the ramp stays small (no abrupt jump anywhere).
    assert float(np.max(np.abs(np.diff(row)))) <= step + 0.01
    # Valid pixels are never touched.
    assert np.array_equal(feathered[:, :edge], data[:, :edge])


def test_rendered_terrain_tile_feathers_its_nodata_border() -> None:
    size = 2 * TERRAIN_NODATA_FEATHER_PX
    data = np.full((size, size), 60.0, dtype=np.float32)
    valid = np.zeros((size, size), dtype=bool)
    valid[:, : size // 2] = True

    elevations = _decode_terrain_png(render_terrain_rgb_png(data, valid))

    edge = size // 2
    assert elevations[0, edge - 1] == pytest.approx(60.0, abs=0.05)
    # Used to be exactly 0.0 (the curtain); now it steps down gradually.
    assert elevations[0, edge] > 50.0
    assert elevations[0, -1] == pytest.approx(0.0, abs=0.05)


def test_render_terrain_rgb_png_rejects_a_fully_invalid_tile() -> None:
    with pytest.raises(ValueError):
        render_terrain_rgb_png(np.zeros((4, 4), dtype=np.float32), np.zeros((4, 4), dtype=bool))


def test_flat_terrain_tile_decodes_to_the_requested_elevation() -> None:
    png = render_flat_terrain_rgb_png(tilesize=16, elevation=12.5)

    pixels = np.asarray(PILImage.open(io.BytesIO(png)).convert("RGB"))
    r, g, b = (int(v) for v in pixels[0, 0])
    decoded = -10000 + ((r * 65536 + g * 256 + b) * 0.1)

    assert pixels.shape == (16, 16, 3)
    assert decoded == pytest.approx(12.5, abs=0.05)


# ── crop_center ────────────────────────────────────────────────────────────


def test_crop_center_removes_the_halo_on_every_side() -> None:
    arr = np.arange(100).reshape(10, 10)

    cropped = crop_center(arr, 2)

    assert cropped.shape == (6, 6)
    assert cropped[0, 0] == arr[2, 2]


@pytest.mark.parametrize("buffer_px", [0, -1])
def test_crop_center_is_a_noop_without_a_buffer(buffer_px: int) -> None:
    arr = np.arange(9).reshape(3, 3)

    assert crop_center(arr, buffer_px) is arr


# ── smooth_elevation_tile ──────────────────────────────────────────────────


def _spiky_tile(size: int = 32) -> tuple[np.ndarray, np.ndarray]:
    elevation = np.full((size, size), 100.0, dtype=np.float32)
    elevation[size // 2, size // 2] = 110.0  # a 10 m tree/building spike
    return elevation, np.ones((size, size), dtype=bool)


@pytest.mark.parametrize("method", [None, "", "none"])
def test_smoothing_disabled_returns_the_input_untouched(method) -> None:
    elevation, valid = _spiky_tile()

    result = smooth_elevation_tile(elevation, valid, method)

    assert result is elevation


def test_unknown_method_degrades_to_the_raw_tile() -> None:
    elevation, valid = _spiky_tile()

    result = smooth_elevation_tile(elevation, valid, "median-9000")

    assert result is elevation


@pytest.mark.parametrize("method", TERRAIN_SMOOTHING_METHODS)
def test_every_advertised_method_removes_the_spike(method: str) -> None:
    elevation, valid = _spiky_tile()

    result = smooth_elevation_tile(elevation, valid, method)

    assert result.shape == elevation.shape
    assert result[16, 16] == pytest.approx(100.0, abs=0.01)
    assert result.dtype == np.float32


def test_despike_legacy_alias_matches_the_medium_preset() -> None:
    elevation, valid = _spiky_tile()

    legacy = smooth_elevation_tile(elevation.copy(), valid, "despike15")
    current = smooth_elevation_tile(elevation.copy(), valid, "despike_med")

    assert np.array_equal(legacy, current)


def test_despike_preserves_negative_features() -> None:
    """Despiking targets positive artefacts; a ditch must survive."""
    elevation = np.full((32, 32), 100.0, dtype=np.float32)
    elevation[:, 15:17] = 97.0  # a channel
    valid = np.ones((32, 32), dtype=bool)

    result = smooth_elevation_tile(elevation, valid, "despike_high")

    assert result[16, 15] < 99.0


def test_smoothing_leaves_invalid_pixels_as_they_were() -> None:
    elevation = np.full((32, 32), 100.0, dtype=np.float32)
    elevation[0, 0] = np.nan
    valid = np.ones((32, 32), dtype=bool)
    valid[0, 0] = False

    result = smooth_elevation_tile(elevation, valid, "median5")

    assert math.isnan(float(result[0, 0]))
    assert result[16, 16] == pytest.approx(100.0)


def test_smoothing_a_fully_invalid_tile_returns_the_input() -> None:
    elevation = np.full((8, 8), np.nan, dtype=np.float32)

    result = smooth_elevation_tile(elevation, np.zeros((8, 8), dtype=bool), "median3")

    assert result is elevation


def test_smoothing_a_buffered_tile_samples_only_the_center() -> None:
    """The halo can straddle the COG edge; using it would tint the tile."""
    size = 256 + 2 * 8
    elevation = np.full((size, size), 100.0, dtype=np.float32)
    valid = np.ones((size, size), dtype=bool)
    # Halo comes from a totally different elevation regime and is invalid.
    elevation[:8, :] = 900.0
    valid[:8, :] = False

    result = smooth_elevation_tile(elevation, valid, "median5")

    center = crop_center(result, 8)
    assert center.shape == (256, 256)
    assert float(center.max()) == pytest.approx(100.0, abs=0.5)


# ── categorical rendering ──────────────────────────────────────────────────


def test_categorical_png_paints_the_configured_colours() -> None:
    raw = np.array([[0, 1], [2, 3]], dtype=np.uint8)
    mask = np.full((2, 2), 255, dtype=np.uint8)
    colors = CATEGORICAL_COLORS["terrain_class"]

    png = render_categorical_png(raw, mask, colors)

    rgba = np.asarray(PILImage.open(io.BytesIO(png)).convert("RGBA"))
    assert tuple(rgba[0, 0]) == colors[0]
    assert tuple(rgba[1, 1]) == colors[3]


def test_categorical_png_leaves_nodata_transparent() -> None:
    raw = np.array([[1, 1]], dtype=np.uint8)
    mask = np.array([[255, 0]], dtype=np.uint8)

    png = render_categorical_png(raw, mask, CATEGORICAL_COLORS["terrain_class"])

    rgba = np.asarray(PILImage.open(io.BytesIO(png)).convert("RGBA"))
    assert rgba[0, 0, 3] == 255
    assert rgba[0, 1, 3] == 0


def test_categorical_png_hides_requested_classes() -> None:
    raw = np.array([[1, 2]], dtype=np.uint8)
    mask = np.full((1, 2), 255, dtype=np.uint8)

    png = render_categorical_png(raw, mask, CATEGORICAL_COLORS["terrain_class"], {2})

    rgba = np.asarray(PILImage.open(io.BytesIO(png)).convert("RGBA"))
    assert rgba[0, 0, 3] == 255
    assert rgba[0, 1, 3] == 0


# ── reading real GeoTIFFs ──────────────────────────────────────────────────

RASTER_WEST, RASTER_SOUTH = -62.80, -32.70
RASTER_EAST, RASTER_NORTH = -62.60, -32.50


def _write_raster(path, data: np.ndarray, dtype, nodata=None) -> str:
    transform = from_bounds(
        RASTER_WEST, RASTER_SOUTH, RASTER_EAST, RASTER_NORTH, data.shape[1], data.shape[0]
    )
    profile = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": dtype,
        "crs": "EPSG:4326",
        "transform": transform,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(dtype), 1)
    return str(path)


def _tile_covering_raster(zoom: int = 11) -> tuple[int, int]:
    from pyproj import Transformer

    to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x_m, y_m = to_3857.transform((RASTER_WEST + RASTER_EAST) / 2, (RASTER_SOUTH + RASTER_NORTH) / 2)
    span = (WEB_MERCATOR_HALF_WORLD * 2.0) / (2**zoom)
    return (
        int((x_m + WEB_MERCATOR_HALF_WORLD) // span),
        int((WEB_MERCATOR_HALF_WORLD - y_m) // span),
    )


def test_read_elevation_tile_returns_none_outside_the_raster(tmp_path) -> None:
    path = _write_raster(tmp_path / "dem.tif", np.full((64, 64), 120.0), "float32")

    assert read_elevation_tile(path, 0, 0, 5) is None


def test_read_elevation_tile_reads_the_covered_tile(tmp_path) -> None:
    path = _write_raster(tmp_path / "dem.tif", np.full((64, 64), 120.0), "float32")
    x, y = _tile_covering_raster()

    tile, valid = read_elevation_tile(path, x, y, 11)

    assert tile.shape == (256, 256)
    assert valid.any()
    assert float(np.nanmax(tile)) == pytest.approx(120.0, abs=0.01)


def test_read_elevation_tile_with_a_buffer_returns_a_padded_window(tmp_path) -> None:
    path = _write_raster(tmp_path / "dem.tif", np.full((64, 64), 120.0), "float32")
    x, y = _tile_covering_raster()

    tile, valid = read_elevation_tile(path, x, y, 11, buffer_px=8)

    assert tile.shape == (256 + 16, 256 + 16)
    assert valid.shape == tile.shape
    assert crop_center(tile, 8).shape == (256, 256)


def test_read_categorical_tile_returns_none_outside_the_raster(tmp_path) -> None:
    path = _write_raster(tmp_path / "classes.tif", np.full((64, 64), 2), "uint8", nodata=255)

    assert read_categorical_tile(path, 0, 0, 5) is None


def test_read_categorical_tile_uses_nearest_neighbour_class_values(tmp_path) -> None:
    data = np.full((64, 64), 2, dtype=np.uint8)
    data[:32, :] = 1
    path = _write_raster(tmp_path / "classes.tif", data, "uint8", nodata=255)
    x, y = _tile_covering_raster()

    raw, mask = read_categorical_tile(path, x, y, 11)

    assert raw.shape == (256, 256)
    assert set(np.unique(raw)).issubset({1, 2, 255})
    assert mask[raw != 255].min() == 255


def test_elevation_baseline_is_the_raster_minimum(tmp_path) -> None:
    data = np.full((32, 32), 130.0, dtype=np.float32)
    data[0, 0] = 101.5
    path = _write_raster(tmp_path / "baseline.tif", data, "float32")

    get_elevation_baseline.cache_clear()
    assert get_elevation_baseline(path) == pytest.approx(101.5)


def test_elevation_baseline_of_an_all_nodata_raster_is_zero(tmp_path) -> None:
    path = _write_raster(
        tmp_path / "empty.tif", np.full((16, 16), -9999.0), "float32", nodata=-9999.0
    )

    get_elevation_baseline.cache_clear()
    assert get_elevation_baseline(path) == 0.0
