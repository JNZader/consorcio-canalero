"""Zona clip mask for visual raster tiles.

The pipeline GeoTIFFs cover the whole PROCESSING bbox, much larger than the
consorcio, so every visual overlay used to bleed over the province. This mask
clips the rendered tile to the zona outline — and must degrade gracefully to
``None`` (unclipped tiles) instead of 500-ing when the geojson is missing or
unreadable.

Runs against REAL rasterio/shapely/pyproj: the geometry maths is the point.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from pyproj import Transformer

from app.domains.geo.tile_service_support import (
    WEB_MERCATOR_HALF_WORLD,
    ZONA_CLIP_GEOJSON_ENV,
    _zona_geometry_3857,
    tile_bounds_3857,
    zona_clip_mask,
)

# A small square around Bell Ville (the consorcio's area), in lon/lat.
ZONA_WEST, ZONA_SOUTH = -62.72, -32.64
ZONA_EAST, ZONA_NORTH = -62.68, -32.60
ZOOM = 12

_TO_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


@pytest.fixture(autouse=True)
def clear_zona_cache():
    """``_zona_geometry_3857`` is ``lru_cache``d for the process lifetime."""
    _zona_geometry_3857.cache_clear()
    yield
    _zona_geometry_3857.cache_clear()


def _polygon(west: float, south: float, east: float, north: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]
        ],
    }


def _write_zona(tmp_path: Path, monkeypatch, payload: str | dict, name="zona.geojson") -> Path:
    path = tmp_path / name
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    monkeypatch.setenv(ZONA_CLIP_GEOJSON_ENV, str(path))
    return path


def _feature_collection() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "zona"},
                "geometry": _polygon(ZONA_WEST, ZONA_SOUTH, ZONA_EAST, ZONA_NORTH),
            }
        ],
    }


def _tile_for(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """XYZ tile index containing a lon/lat point."""
    x_m, y_m = _TO_3857.transform(lon, lat)
    span = (WEB_MERCATOR_HALF_WORLD * 2.0) / (2**zoom)
    return (
        int(math.floor((x_m + WEB_MERCATOR_HALF_WORLD) / span)),
        int(math.floor((WEB_MERCATOR_HALF_WORLD - y_m) / span)),
    )


def _pixel_for(lon: float, lat: float, x: int, y: int, z: int, tilesize: int = 256):
    """Row/col of a lon/lat point inside a tile, or None when outside."""
    x_m, y_m = _TO_3857.transform(lon, lat)
    west, south, east, north = tile_bounds_3857(x, y, z)
    col = int((x_m - west) / (east - west) * tilesize)
    row = int((north - y_m) / (north - south) * tilesize)
    if not (0 <= col < tilesize and 0 <= row < tilesize):
        return None
    return row, col


# ── happy path ─────────────────────────────────────────────────────────────


def test_mask_is_true_inside_and_false_outside_the_zona(tmp_path, monkeypatch) -> None:
    _write_zona(tmp_path, monkeypatch, _feature_collection())
    center_lon = (ZONA_WEST + ZONA_EAST) / 2
    center_lat = (ZONA_SOUTH + ZONA_NORTH) / 2
    x, y = _tile_for(center_lon, center_lat, ZOOM)

    mask = zona_clip_mask(x, y, ZOOM)

    assert mask is not None
    assert mask.shape == (256, 256)
    assert mask.dtype == bool
    inside = _pixel_for(center_lon, center_lat, x, y, ZOOM)
    assert inside is not None
    assert bool(mask[inside]) is True
    # The zona square (~4 km) is far smaller than a z12 tile (~9.8 km): the
    # tile necessarily straddles the outline.
    assert mask.any() and not mask.all()


def test_mask_is_false_for_a_pixel_outside_the_zona(tmp_path, monkeypatch) -> None:
    _write_zona(tmp_path, monkeypatch, _feature_collection())
    center_lon = (ZONA_WEST + ZONA_EAST) / 2
    center_lat = (ZONA_SOUTH + ZONA_NORTH) / 2
    x, y = _tile_for(center_lon, center_lat, ZOOM)
    west, south, east, north = tile_bounds_3857(x, y, ZOOM)

    mask = zona_clip_mask(x, y, ZOOM)

    # Whichever corner of the tile falls outside the small zona square.
    corners = [(0, 0), (0, 255), (255, 0), (255, 255)]
    assert any(not bool(mask[r, c]) for r, c in corners)
    assert (east - west) > 0 and (north - south) > 0


def test_mask_is_all_false_for_a_tile_that_misses_the_zona(tmp_path, monkeypatch) -> None:
    _write_zona(tmp_path, monkeypatch, _feature_collection())
    x, y = _tile_for(-58.4, -34.6, ZOOM)  # Buenos Aires, ~500 km away

    mask = zona_clip_mask(x, y, ZOOM)

    assert mask is not None
    assert not mask.any()


def test_mask_honours_a_custom_tilesize(tmp_path, monkeypatch) -> None:
    _write_zona(tmp_path, monkeypatch, _feature_collection())
    x, y = _tile_for(-62.70, -32.62, ZOOM)

    mask = zona_clip_mask(x, y, ZOOM, tilesize=64)

    assert mask.shape == (64, 64)


def test_mask_accepts_a_bare_feature_document(tmp_path, monkeypatch) -> None:
    _write_zona(
        tmp_path,
        monkeypatch,
        {
            "type": "Feature",
            "properties": {},
            "geometry": _polygon(ZONA_WEST, ZONA_SOUTH, ZONA_EAST, ZONA_NORTH),
        },
    )
    x, y = _tile_for(-62.70, -32.62, ZOOM)

    mask = zona_clip_mask(x, y, ZOOM)

    assert mask is not None
    assert mask.any()


def test_multiple_features_are_unioned(tmp_path, monkeypatch) -> None:
    _write_zona(
        tmp_path,
        monkeypatch,
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": _polygon(-62.72, -32.64, -62.70, -32.62),
                },
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": _polygon(-62.70, -32.62, -62.68, -32.60),
                },
            ],
        },
    )
    x, y = _tile_for(-62.71, -32.63, ZOOM)

    mask = zona_clip_mask(x, y, ZOOM)

    covered = np.count_nonzero(mask)
    assert covered > 0


def test_geometry_is_cached_across_calls(tmp_path, monkeypatch) -> None:
    path = _write_zona(tmp_path, monkeypatch, _feature_collection())

    first = _zona_geometry_3857()
    path.unlink()
    second = _zona_geometry_3857()

    assert first is second


# ── graceful degradation ───────────────────────────────────────────────────


def test_missing_file_degrades_to_no_mask(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(ZONA_CLIP_GEOJSON_ENV, str(tmp_path / "no-such-file.geojson"))

    assert _zona_geometry_3857() is None
    assert zona_clip_mask(1000, 2000, ZOOM) is None


def test_corrupt_geojson_degrades_to_no_mask(tmp_path, monkeypatch) -> None:
    _write_zona(tmp_path, monkeypatch, "{not really json")

    assert zona_clip_mask(1000, 2000, ZOOM) is None


def test_geojson_with_invalid_geometry_degrades_to_no_mask(tmp_path, monkeypatch) -> None:
    _write_zona(
        tmp_path,
        monkeypatch,
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon"}},
            ],
        },
    )

    assert zona_clip_mask(1000, 2000, ZOOM) is None


def test_geojson_without_features_degrades_to_no_mask(tmp_path, monkeypatch) -> None:
    _write_zona(tmp_path, monkeypatch, {"type": "FeatureCollection", "features": []})

    assert zona_clip_mask(1000, 2000, ZOOM) is None


def test_features_without_geometry_degrade_to_no_mask(tmp_path, monkeypatch) -> None:
    _write_zona(
        tmp_path,
        monkeypatch,
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": None}],
        },
    )

    assert zona_clip_mask(1000, 2000, ZOOM) is None


def test_path_pointing_to_a_directory_degrades_to_no_mask(tmp_path, monkeypatch) -> None:
    """Docker bind-mounts a DIRECTORY when the host file is missing."""
    directory = tmp_path / "zona_ampliada.geojson"
    directory.mkdir()
    monkeypatch.setenv(ZONA_CLIP_GEOJSON_ENV, str(directory))

    assert directory.exists()
    assert _zona_geometry_3857() is None
    assert zona_clip_mask(1000, 2000, ZOOM) is None
