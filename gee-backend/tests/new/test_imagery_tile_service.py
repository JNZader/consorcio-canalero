"""HTTP contract of the standalone tile service (geo-worker).

The database and the bytes cache are the only collaborators stubbed here; the
raster path runs against real GeoTIFFs written to ``tmp_path``.

``rio-tiler`` lives in ``requirements-geo.txt`` (the geo-worker image), not in
the backend venv, so importing ``tile_service`` fails on a plain dev install.
When it is absent we register an import-only shim: the terrain-RGB,
categorical, zona-clip, caching and error branches never touch rio-tiler and
stay fully covered, while the continuous-colormap branch — which is rio-tiler
behaviour — is skipped instead of being asserted against a fake.
"""

from __future__ import annotations

import io
import json
import sys
import uuid
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from PIL import Image as PILImage
from rasterio.transform import from_bounds

try:  # pragma: no cover — depends on the installed requirement set
    import rio_tiler  # noqa: F401

    HAS_RIO_TILER = True
except ImportError:  # pragma: no cover
    HAS_RIO_TILER = False

    class _TileOutsideBounds(Exception):
        pass

    class _UnavailableReader:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("rio-tiler is not installed in this environment")

    _root = ModuleType("rio_tiler")
    _io = ModuleType("rio_tiler.io")
    _io.Reader = _UnavailableReader
    _errors = ModuleType("rio_tiler.errors")
    _errors.TileOutsideBounds = _TileOutsideBounds
    _colormap = ModuleType("rio_tiler.colormap")
    _colormap.cmap = None
    _root.io, _root.errors, _root.colormap = _io, _errors, _colormap
    sys.modules.setdefault("rio_tiler", _root)
    sys.modules.setdefault("rio_tiler.io", _io)
    sys.modules.setdefault("rio_tiler.errors", _errors)
    sys.modules.setdefault("rio_tiler.colormap", _colormap)

needs_rio_tiler = pytest.mark.skipif(
    not HAS_RIO_TILER, reason="rio-tiler (requirements-geo.txt) is not installed"
)

from app.domains.geo import tile_service  # noqa: E402
from app.domains.geo.tile_service_support import (  # noqa: E402
    WEB_MERCATOR_HALF_WORLD,
    ZONA_CLIP_GEOJSON_ENV,
    _zona_geometry_3857,
    get_elevation_baseline,
)

RASTER_WEST, RASTER_SOUTH = -62.80, -32.70
RASTER_EAST, RASTER_NORTH = -62.60, -32.50
ZOOM = 11


class StubBytesCache:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.gets: list[str] = []
        self.sets: list[str] = []

    def get(self, key: str):
        self.gets.append(key)
        return self.store.get(key)

    def set(self, key: str, value: bytes, ttl_seconds: int | None = None):
        self.sets.append(key)
        self.store[key] = value


@pytest.fixture
def cache(monkeypatch) -> StubBytesCache:
    stub = StubBytesCache()
    monkeypatch.setattr("app.core.cache.get_bytes_cache", lambda: stub)
    return stub


@pytest.fixture(autouse=True)
def isolated_zona(tmp_path, monkeypatch):
    """No zona geojson by default → tiles render unclipped."""
    _zona_geometry_3857.cache_clear()
    monkeypatch.setenv(ZONA_CLIP_GEOJSON_ENV, str(tmp_path / "absent.geojson"))
    get_elevation_baseline.cache_clear()
    yield
    _zona_geometry_3857.cache_clear()
    get_elevation_baseline.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(tile_service.app)


def _write_raster(path, data: np.ndarray, dtype: str, nodata=None) -> str:
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


def _layer(path: str, tipo: str = "dem_raw", metadata_extra=None):
    return SimpleNamespace(archivo_path=path, tipo=tipo, metadata_extra=metadata_extra)


def _serve(monkeypatch, layer) -> None:
    monkeypatch.setattr(tile_service, "_get_layer", lambda layer_id: layer)


def _covering_tile(zoom: int = ZOOM) -> tuple[int, int]:
    from pyproj import Transformer

    to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x_m, y_m = to_3857.transform((RASTER_WEST + RASTER_EAST) / 2, (RASTER_SOUTH + RASTER_NORTH) / 2)
    span = (WEB_MERCATOR_HALF_WORLD * 2.0) / (2**zoom)
    return (
        int((x_m + WEB_MERCATOR_HALF_WORLD) // span),
        int((WEB_MERCATOR_HALF_WORLD - y_m) // span),
    )


def _url(layer_id, x: int, y: int, z: int = ZOOM, **params) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"/tiles/{layer_id}/{z}/{x}/{y}.png" + (f"?{query}" if query else "")


LAYER_ID = uuid.uuid4()


# ── health ─────────────────────────────────────────────────────────────────


def test_health_endpoint(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "geo-tile-service"}


# ── error paths ────────────────────────────────────────────────────────────


def test_unknown_layer_is_404(client, cache, monkeypatch) -> None:
    _serve(monkeypatch, None)

    response = client.get(_url(LAYER_ID, 0, 0))

    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


def test_missing_file_on_disk_is_404(client, cache, monkeypatch, tmp_path) -> None:
    _serve(monkeypatch, _layer(str(tmp_path / "gone.tif")))

    response = client.get(_url(LAYER_ID, 0, 0))

    assert response.status_code == 404
    assert "Archivo" in response.json()["detail"]


def test_terrain_rgb_is_rejected_for_non_elevation_layers(
    client, cache, monkeypatch, tmp_path
) -> None:
    path = _write_raster(tmp_path / "classes.tif", np.full((32, 32), 1), "uint8", nodata=255)
    _serve(monkeypatch, _layer(path, tipo="terrain_class"))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y, encoding="terrain-rgb"))

    assert response.status_code == 422
    assert "elevacion" in response.json()["detail"]


def test_cog_path_from_metadata_wins_over_archivo_path(
    client, cache, monkeypatch, tmp_path
) -> None:
    cog = _write_raster(tmp_path / "dem_cog.tif", np.full((64, 64), 120.0), "float32")
    layer = _layer("/does/not/exist.tif", metadata_extra={"cog_path": cog})
    _serve(monkeypatch, layer)
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y, encoding="terrain-rgb"))

    assert response.status_code == 200


# ── terrain-rgb ────────────────────────────────────────────────────────────


def test_terrain_rgb_tile_renders_a_png(client, cache, monkeypatch, tmp_path) -> None:
    path = _write_raster(tmp_path / "dem.tif", np.full((64, 64), 120.0), "float32")
    _serve(monkeypatch, _layer(path))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y, encoding="terrain-rgb"))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-cache"] == "MISS"
    image = PILImage.open(io.BytesIO(response.content))
    assert image.size == (256, 256)


def test_terrain_rgb_outside_the_raster_returns_a_flat_tile(
    client, cache, monkeypatch, tmp_path
) -> None:
    path = _write_raster(tmp_path / "dem.tif", np.full((64, 64), 120.0), "float32")
    _serve(monkeypatch, _layer(path))

    response = client.get(_url(LAYER_ID, 0, 0, z=5, encoding="terrain-rgb"))

    assert response.status_code == 200
    pixels = np.asarray(PILImage.open(io.BytesIO(response.content)).convert("RGB"))
    r, g, b = (int(v) for v in pixels[0, 0])
    assert -10000 + (r * 65536 + g * 256 + b) * 0.1 == pytest.approx(0.0, abs=0.05)


def test_terrain_rgb_with_smoothing_still_returns_a_256_tile(
    client, cache, monkeypatch, tmp_path
) -> None:
    data = np.full((128, 128), 120.0, dtype=np.float32)
    data[64, 64] = 160.0
    path = _write_raster(tmp_path / "dem.tif", data, "float32")
    _serve(monkeypatch, _layer(path))
    x, y = _covering_tile()

    response = client.get(
        _url(LAYER_ID, x, y, encoding="terrain-rgb", terrain_smoothing="despike_med")
    )

    assert response.status_code == 200
    assert PILImage.open(io.BytesIO(response.content)).size == (256, 256)


# ── categorical ────────────────────────────────────────────────────────────


def test_categorical_tile_outside_bounds_is_204(client, cache, monkeypatch, tmp_path) -> None:
    path = _write_raster(tmp_path / "classes.tif", np.full((32, 32), 1), "uint8", nodata=255)
    _serve(monkeypatch, _layer(path, tipo="terrain_class"))

    response = client.get(_url(LAYER_ID, 0, 0, z=5))

    assert response.status_code == 204


def test_categorical_tile_renders_rgba(client, cache, monkeypatch, tmp_path) -> None:
    path = _write_raster(tmp_path / "classes.tif", np.full((32, 32), 1), "uint8", nodata=255)
    _serve(monkeypatch, _layer(path, tipo="terrain_class"))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y))

    assert response.status_code == 200
    rgba = np.asarray(PILImage.open(io.BytesIO(response.content)).convert("RGBA"))
    assert rgba[..., 3].max() == 255


def test_categorical_tile_is_clipped_to_the_zona(client, cache, monkeypatch, tmp_path) -> None:
    """Without the clip the overlay bled over the whole processing bbox."""
    path = _write_raster(tmp_path / "classes.tif", np.full((32, 32), 1), "uint8", nodata=255)
    _serve(monkeypatch, _layer(path, tipo="terrain_class"))
    x, y = _covering_tile()

    unclipped = client.get(_url(LAYER_ID, x, y))
    assert np.asarray(PILImage.open(io.BytesIO(unclipped.content))).max() > 0

    # Now point the zona at a polygon far away: everything must be masked out.
    far_zona = tmp_path / "zona.geojson"
    far_zona.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-58.5, -34.7],
                            [-58.4, -34.7],
                            [-58.4, -34.6],
                            [-58.5, -34.6],
                            [-58.5, -34.7],
                        ]
                    ],
                },
            }
        )
    )
    monkeypatch.setenv(ZONA_CLIP_GEOJSON_ENV, str(far_zona))
    _zona_geometry_3857.cache_clear()
    cache.store.clear()

    clipped = client.get(_url(LAYER_ID, x, y))

    rgba = np.asarray(PILImage.open(io.BytesIO(clipped.content)).convert("RGBA"))
    assert rgba[..., 3].max() == 0


def test_hidden_classes_are_transparent(client, cache, monkeypatch, tmp_path) -> None:
    path = _write_raster(tmp_path / "classes.tif", np.full((32, 32), 1), "uint8", nodata=255)
    _serve(monkeypatch, _layer(path, tipo="terrain_class"))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y, hide_classes="1"))

    rgba = np.asarray(PILImage.open(io.BytesIO(response.content)).convert("RGBA"))
    assert rgba[..., 3].max() == 0


def test_invalid_hide_classes_does_not_break_the_tile(client, cache, monkeypatch, tmp_path) -> None:
    path = _write_raster(tmp_path / "classes.tif", np.full((32, 32), 1), "uint8", nodata=255)
    _serve(monkeypatch, _layer(path, tipo="terrain_class"))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y, hide_classes="uno,dos"))

    assert response.status_code == 200


# ── continuous ─────────────────────────────────────────────────────────────


@needs_rio_tiler
def test_continuous_tile_outside_bounds_is_204(client, cache, monkeypatch, tmp_path) -> None:
    path = _write_raster(tmp_path / "twi.tif", np.full((32, 32), 10.0), "float32")
    _serve(monkeypatch, _layer(path, tipo="twi"))

    response = client.get(_url(LAYER_ID, 0, 0, z=5))

    assert response.status_code == 204


@needs_rio_tiler
def test_continuous_tile_renders_with_the_default_colormap(
    client, cache, monkeypatch, tmp_path
) -> None:
    path = _write_raster(tmp_path / "twi.tif", np.full((64, 64), 10.0), "float32")
    _serve(monkeypatch, _layer(path, tipo="twi"))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


@needs_rio_tiler
def test_continuous_tile_falls_back_when_the_colormap_is_unknown(
    client, cache, monkeypatch, tmp_path
) -> None:
    path = _write_raster(tmp_path / "twi.tif", np.full((64, 64), 10.0), "float32")
    _serve(monkeypatch, _layer(path, tipo="twi"))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y, colormap="no-such-colormap"))

    assert response.status_code == 200


@needs_rio_tiler
def test_log_scaled_layer_renders(client, cache, monkeypatch, tmp_path) -> None:
    data = np.linspace(1, 5000, 64 * 64, dtype=np.float32).reshape(64, 64)
    path = _write_raster(tmp_path / "flowacc.tif", data, "float32")
    _serve(monkeypatch, _layer(path, tipo="flow_acc"))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y))

    assert response.status_code == 200


@needs_rio_tiler
def test_hidden_ranges_render_through_the_manual_path(client, cache, monkeypatch, tmp_path) -> None:
    data = np.full((64, 64), 8.0, dtype=np.float32)
    path = _write_raster(tmp_path / "twi.tif", data, "float32")
    _serve(monkeypatch, _layer(path, tipo="twi"))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y, hide_ranges="0"))

    assert response.status_code == 200
    rgba = np.asarray(PILImage.open(io.BytesIO(response.content)).convert("RGBA"))
    # Range 0 of twi is 6–9 → every pixel (8.0) must be transparent.
    assert rgba[..., 3].max() == 0


# ── caching ────────────────────────────────────────────────────────────────


def test_second_request_is_served_from_cache(client, cache, monkeypatch, tmp_path) -> None:
    path = _write_raster(tmp_path / "dem.tif", np.full((64, 64), 120.0), "float32")
    _serve(monkeypatch, _layer(path))
    x, y = _covering_tile()

    first = client.get(_url(LAYER_ID, x, y, encoding="terrain-rgb"))
    second = client.get(_url(LAYER_ID, x, y, encoding="terrain-rgb"))

    assert first.headers["x-cache"] == "MISS"
    assert second.headers["x-cache"] == "HIT"
    assert first.content == second.content


def test_cache_key_is_order_independent_for_set_style_params(
    client, cache, monkeypatch, tmp_path
) -> None:
    path = _write_raster(tmp_path / "classes.tif", np.full((32, 32), 1), "uint8", nodata=255)
    _serve(monkeypatch, _layer(path, tipo="terrain_class"))
    x, y = _covering_tile()

    client.get(_url(LAYER_ID, x, y, hide_classes="1,2"))
    second = client.get(_url(LAYER_ID, x, y, hide_classes="2,1"))

    assert second.headers["x-cache"] == "HIT"
    assert len(cache.store) == 1


@needs_rio_tiler
def test_cache_key_separates_different_render_parameters(
    client, cache, monkeypatch, tmp_path
) -> None:
    path = _write_raster(tmp_path / "twi.tif", np.full((64, 64), 10.0), "float32")
    _serve(monkeypatch, _layer(path, tipo="twi"))
    x, y = _covering_tile()

    client.get(_url(LAYER_ID, x, y))
    client.get(_url(LAYER_ID, x, y, colormap="viridis"))

    assert len(cache.store) == 2


def test_invalid_hide_ranges_does_not_break_the_tile(client, cache, monkeypatch, tmp_path) -> None:
    path = _write_raster(tmp_path / "classes.tif", np.full((32, 32), 1), "uint8", nodata=255)
    _serve(monkeypatch, _layer(path, tipo="terrain_class"))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y, hide_ranges="a,b"))

    assert response.status_code == 200


# ── precip_normal + per-request rescale ────────────────────────────────────


@needs_rio_tiler
def test_precip_normal_tile_renders_with_default_colormap(
    client, cache, monkeypatch, tmp_path
) -> None:
    path = _write_raster(tmp_path / "precip_anual.tif", np.full((64, 64), 900.0), "float32")
    _serve(monkeypatch, _layer(path, tipo="precip_normal"))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


@needs_rio_tiler
def test_continuous_tile_uses_per_request_rescale(client, cache, monkeypatch, tmp_path) -> None:
    path = _write_raster(tmp_path / "precip_monthly.tif", np.full((64, 64), 50.0), "float32")
    _serve(monkeypatch, _layer(path, tipo="precip_normal"))
    x, y = _covering_tile()

    default_response = client.get(_url(LAYER_ID, x, y))
    override_response = client.get(_url(LAYER_ID, x, y, rescale_min=0, rescale_max=200))

    assert default_response.status_code == 200
    assert override_response.status_code == 200
    assert default_response.content != override_response.content


@needs_rio_tiler
def test_cache_key_separates_rescale_params(client, cache, monkeypatch, tmp_path) -> None:
    path = _write_raster(tmp_path / "precip.tif", np.full((64, 64), 100.0), "float32")
    _serve(monkeypatch, _layer(path, tipo="precip_normal"))
    x, y = _covering_tile()

    client.get(_url(LAYER_ID, x, y))
    client.get(_url(LAYER_ID, x, y, rescale_min=0, rescale_max=200))

    assert len(cache.store) == 2


# ── H1 hardening: bounded cache-key token + safe fallback ────────────────────


@needs_rio_tiler
def test_rescale_cache_key_uses_bounded_token_not_raw_float(
    client, cache, monkeypatch, tmp_path
) -> None:
    """The rescale portion of the cache key must be a bounded token, never the
    attacker-controlled float. Monthly -> 'r=m', annual -> 'r=a', none -> 'r=-'."""
    path = _write_raster(tmp_path / "precip.tif", np.full((64, 64), 100.0), "float32")
    _serve(monkeypatch, _layer(path, tipo="precip_normal"))
    x, y = _covering_tile()

    client.get(_url(LAYER_ID, x, y, rescale_min=0, rescale_max=200))
    annual_key = cache.sets[-1]
    client.get(_url(LAYER_ID, x, y, rescale_min=0, rescale_max=1800))
    client.get(_url(LAYER_ID, x, y))

    monthly_key, annual_key2, none_key = cache.sets[-3], cache.sets[-2], cache.sets[-1]
    for key in (monthly_key, annual_key2, none_key):
        assert "rmin=" not in key
        assert "rmax=" not in key
    assert ":r=m" in monthly_key
    assert ":r=a" in annual_key2
    assert ":r=-" in none_key
    # Distinct canonical ranges must not collide in the cache.
    assert monthly_key != annual_key2 != none_key


@needs_rio_tiler
def test_unsupported_rescale_falls_back_to_default_and_bounded_key(
    client, cache, monkeypatch, tmp_path
) -> None:
    """A rescale pair that is not canonical for the layer (e.g. a direct call
    that bypassed the proxy) must NOT be applied and must NOT reach the cache
    key as a raw float — it degrades to the default rendering with token '-'."""
    path = _write_raster(tmp_path / "precip.tif", np.full((64, 64), 100.0), "float32")
    _serve(monkeypatch, _layer(path, tipo="precip_normal"))
    x, y = _covering_tile()

    default_response = client.get(_url(LAYER_ID, x, y))
    cache.store.clear()  # Force the unsupported override through the cold-cache fallback.
    override_response = client.get(_url(LAYER_ID, x, y, rescale_min=0, rescale_max=100))

    assert default_response.status_code == 200
    assert override_response.status_code == 200
    # Falls back to the default render (no contrast change from an unsupported range).
    assert default_response.content == override_response.content
    # And the cache key never carries the unsupported float.
    assert ":r=-" in cache.sets[-1]
    assert "rmin=" not in cache.sets[-1]


@needs_rio_tiler
def test_no_override_renders_identically_to_annual_default(
    client, cache, monkeypatch, tmp_path
) -> None:
    """No-override preserves the existing default rendering: for precip_normal the
    default rescale IS (0, 1800), so omitting rescale must render identically to
    the explicit annual override."""
    path = _write_raster(tmp_path / "precip.tif", np.full((64, 64), 900.0), "float32")
    _serve(monkeypatch, _layer(path, tipo="precip_normal"))
    x, y = _covering_tile()

    no_override = client.get(_url(LAYER_ID, x, y))
    annual = client.get(_url(LAYER_ID, x, y, rescale_min=0, rescale_max=1800))

    assert no_override.status_code == 200
    assert annual.status_code == 200
    assert no_override.content == annual.content


# ── terrain-rgb fallbacks ──────────────────────────────────────────────────


def test_terrain_rgb_falls_back_to_a_flat_tile_when_every_pixel_is_nodata(
    client, cache, monkeypatch, tmp_path
) -> None:
    """``render_terrain_rgb_png`` raises on an all-invalid tile; the handler
    must answer with the flat tile instead of a 500."""
    path = _write_raster(
        tmp_path / "dem.tif", np.full((64, 64), -9999.0), "float32", nodata=-9999.0
    )
    _serve(monkeypatch, _layer(path))
    x, y = _covering_tile()

    response = client.get(_url(LAYER_ID, x, y, encoding="terrain-rgb"))

    assert response.status_code == 200
    pixels = np.asarray(PILImage.open(io.BytesIO(response.content)).convert("RGB"))
    r, g, b = (int(v) for v in pixels[0, 0])
    assert -10000 + (r * 65536 + g * 256 + b) * 0.1 == pytest.approx(0.0, abs=0.05)
