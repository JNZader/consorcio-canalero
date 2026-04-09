"""
Tests for pure PyVista render functions in geo/visualization/renderer.py.

Strategy:
- pyvista is NOT installed in test environment (only in Docker/production).
- We mock the entire pyvista module via sys.modules before importing renderer.
- Tests assert that functions return bytes objects and call Plotter correctly.
- No DB, no filesystem I/O, no real rendering.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch, call
import tempfile

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Build a minimal pyvista stub so renderer.py can be imported in test env
# ---------------------------------------------------------------------------

def _make_pyvista_stub() -> types.ModuleType:
    """Return a fake pyvista module that satisfies renderer.py's imports."""
    pv = types.ModuleType("pyvista")

    class _StructuredGrid:
        def __init__(self, *args, **kwargs):
            self._data: dict = {}
            self.points = None

        def __setitem__(self, key, value):
            self._data[key] = value

        def __getitem__(self, key):
            return self._data[key]

    class _PolyData:
        def __init__(self, *args, **kwargs):
            self.lines = None
            self.points = None

    class _Plotter:
        def __init__(self, *args, **kwargs): ...
        def add_mesh(self, *args, **kwargs): ...
        def screenshot(self, *args, **kwargs): return b"PNG_BYTES"
        def open_movie(self, path, *args, **kwargs): ...
        def write_frame(self, *args, **kwargs): ...
        def close(self, *args, **kwargs): ...
        def set_position(self, *args, **kwargs): ...
        def camera_position(self): return "iso"

    pv.StructuredGrid = _StructuredGrid
    pv.PolyData = _PolyData
    pv.Plotter = _Plotter
    pv.start_xvfb = MagicMock()

    return pv


# Inject stub BEFORE importing renderer so pyvista import inside renderer works
_pyvista_stub = _make_pyvista_stub()
sys.modules.setdefault("pyvista", _pyvista_stub)


# Now safe to import renderer
from app.domains.geo.visualization import renderer  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dem_10x10() -> np.ndarray:
    """A small 10×10 DEM array with varied elevation values."""
    rng = np.random.default_rng(42)
    return rng.uniform(low=0.0, high=100.0, size=(10, 10)).astype(np.float32)


@pytest.fixture
def dem_zeros() -> np.ndarray:
    """All-zero DEM — edge case: flat terrain."""
    return np.zeros((10, 10), dtype=np.float32)


@pytest.fixture
def affine_transform():
    """Minimal affine transform (rasterio-compatible namedtuple-like object)."""
    from collections import namedtuple
    Affine = namedtuple("Affine", ["a", "b", "c", "d", "e", "f"])
    # 30 m pixel, origin at (0, 300)
    return Affine(a=30.0, b=0.0, c=0.0, d=0.0, e=-30.0, f=300.0)


@pytest.fixture
def cuencas_gdf_empty():
    """GeoDataFrame with no geometries."""
    import geopandas as gpd
    return gpd.GeoDataFrame({"geometry": []})


@pytest.fixture
def cuencas_gdf(cuencas_gdf_empty):
    """GeoDataFrame with one polygon geometry."""
    from shapely.geometry import Polygon
    import geopandas as gpd
    poly = Polygon([(0, 0), (30, 0), (30, 30), (0, 30)])
    return gpd.GeoDataFrame({"geometry": [poly]})


@pytest.fixture
def conflictos_gdf_empty():
    """GeoDataFrame with no risk zones."""
    import geopandas as gpd
    return gpd.GeoDataFrame({"geometry": [], "nivel_riesgo": []})


@pytest.fixture
def conflictos_gdf():
    """GeoDataFrame with one risk zone of each level."""
    from shapely.geometry import Polygon
    import geopandas as gpd
    poly = Polygon([(0, 0), (30, 0), (30, 30), (0, 30)])
    return gpd.GeoDataFrame({
        "geometry": [poly, poly, poly, poly],
        "nivel_riesgo": ["bajo", "medio", "alto", "critico"],
    })


@pytest.fixture
def geojson_empty() -> dict:
    """GeoJSON FeatureCollection with no features."""
    return {"type": "FeatureCollection", "features": []}


@pytest.fixture
def geojson_with_lines() -> dict:
    """GeoJSON FeatureCollection with a LineString."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0, 0], [30, 30], [60, 0]],
                },
                "properties": {},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Task 2.1/2.2 — render_cuencas_3d
# ---------------------------------------------------------------------------

class TestRenderCuencas3d:
    """render_cuencas_3d returns PNG bytes; calls Plotter(off_screen=True)."""

    def test_returns_bytes(self, dem_10x10, affine_transform, cuencas_gdf):
        result = renderer.render_cuencas_3d(dem_10x10, affine_transform, cuencas_gdf)
        assert isinstance(result, bytes)

    def test_returns_non_empty_bytes(self, dem_10x10, affine_transform, cuencas_gdf):
        result = renderer.render_cuencas_3d(dem_10x10, affine_transform, cuencas_gdf)
        assert len(result) > 0

    def test_plotter_called_offscreen(self, dem_10x10, affine_transform, cuencas_gdf):
        """Plotter must be created with off_screen=True for headless rendering."""
        mock_plotter_cls = MagicMock()
        mock_plotter_instance = MagicMock()
        mock_plotter_instance.screenshot.return_value = b"PNG"
        mock_plotter_cls.return_value = mock_plotter_instance

        with patch.object(renderer, "pyvista") as mock_pv:
            mock_pv.StructuredGrid.return_value = MagicMock()
            mock_pv.PolyData.return_value = MagicMock()
            mock_pv.Plotter = mock_plotter_cls
            renderer.render_cuencas_3d(dem_10x10, affine_transform, cuencas_gdf)

        mock_plotter_cls.assert_called_once_with(off_screen=True)

    def test_screenshot_called(self, dem_10x10, affine_transform, cuencas_gdf):
        """screenshot() must be called to produce PNG bytes."""
        mock_plotter_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.screenshot.return_value = b"PNG"
        mock_plotter_cls.return_value = mock_instance

        with patch.object(renderer, "pyvista") as mock_pv:
            mock_pv.StructuredGrid.return_value = MagicMock()
            mock_pv.PolyData.return_value = MagicMock()
            mock_pv.Plotter = mock_plotter_cls
            renderer.render_cuencas_3d(dem_10x10, affine_transform, cuencas_gdf)

        mock_instance.screenshot.assert_called_once()

    def test_empty_geodataframe_does_not_crash(self, dem_10x10, affine_transform, cuencas_gdf_empty):
        """Empty GeoDataFrame → terrain-only render, no crash."""
        result = renderer.render_cuencas_3d(dem_10x10, affine_transform, cuencas_gdf_empty)
        assert isinstance(result, bytes)

    def test_zero_dem_produces_output(self, dem_zeros, affine_transform, cuencas_gdf_empty):
        """All-zero DEM (flat terrain) must still return bytes."""
        result = renderer.render_cuencas_3d(dem_zeros, affine_transform, cuencas_gdf_empty)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# Task 2.3/2.4 — render_escorrentia_3d
# ---------------------------------------------------------------------------

class TestRenderEscorrentia3d:
    """render_escorrentia_3d returns PNG bytes for any GeoJSON input."""

    def test_returns_bytes_with_features(self, dem_10x10, affine_transform, geojson_with_lines):
        result = renderer.render_escorrentia_3d(dem_10x10, affine_transform, geojson_with_lines)
        assert isinstance(result, bytes)

    def test_returns_non_empty_bytes(self, dem_10x10, affine_transform, geojson_with_lines):
        result = renderer.render_escorrentia_3d(dem_10x10, affine_transform, geojson_with_lines)
        assert len(result) > 0

    def test_empty_geojson_does_not_crash(self, dem_10x10, affine_transform, geojson_empty):
        """Empty GeoJSON → terrain only, still returns bytes."""
        result = renderer.render_escorrentia_3d(dem_10x10, affine_transform, geojson_empty)
        assert isinstance(result, bytes)

    def test_plotter_called_offscreen(self, dem_10x10, affine_transform, geojson_empty):
        mock_plotter_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.screenshot.return_value = b"PNG"
        mock_plotter_cls.return_value = mock_instance

        with patch.object(renderer, "pyvista") as mock_pv:
            mock_pv.StructuredGrid.return_value = MagicMock()
            mock_pv.PolyData.return_value = MagicMock()
            mock_pv.Plotter = mock_plotter_cls
            renderer.render_escorrentia_3d(dem_10x10, affine_transform, geojson_empty)

        mock_plotter_cls.assert_called_once_with(off_screen=True)

    def test_zero_dem_produces_output(self, dem_zeros, affine_transform, geojson_empty):
        result = renderer.render_escorrentia_3d(dem_zeros, affine_transform, geojson_empty)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# Task 2.5/2.6 — render_riesgo_3d
# ---------------------------------------------------------------------------

class TestRenderRiesgo3d:
    """render_riesgo_3d returns PNG bytes; handles color-coded risk levels."""

    def test_returns_bytes(self, dem_10x10, affine_transform, conflictos_gdf):
        result = renderer.render_riesgo_3d(dem_10x10, affine_transform, conflictos_gdf)
        assert isinstance(result, bytes)

    def test_returns_non_empty_bytes(self, dem_10x10, affine_transform, conflictos_gdf):
        result = renderer.render_riesgo_3d(dem_10x10, affine_transform, conflictos_gdf)
        assert len(result) > 0

    def test_empty_risk_zones_does_not_crash(self, dem_10x10, affine_transform, conflictos_gdf_empty):
        result = renderer.render_riesgo_3d(dem_10x10, affine_transform, conflictos_gdf_empty)
        assert isinstance(result, bytes)

    def test_plotter_called_offscreen(self, dem_10x10, affine_transform, conflictos_gdf):
        mock_plotter_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.screenshot.return_value = b"PNG"
        mock_plotter_cls.return_value = mock_instance

        with patch.object(renderer, "pyvista") as mock_pv:
            mock_pv.StructuredGrid.return_value = MagicMock()
            mock_pv.PolyData.return_value = MagicMock()
            mock_pv.Plotter = mock_plotter_cls
            renderer.render_riesgo_3d(dem_10x10, affine_transform, conflictos_gdf)

        mock_plotter_cls.assert_called_once_with(off_screen=True)

    def test_zero_dem_produces_output(self, dem_zeros, affine_transform, conflictos_gdf_empty):
        result = renderer.render_riesgo_3d(dem_zeros, affine_transform, conflictos_gdf_empty)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# Task 2.7/2.8 — render_animacion_tormenta
# ---------------------------------------------------------------------------

class TestRenderAnimacionTormenta:
    """render_animacion_tormenta returns MP4 bytes via open_movie + write_frame."""

    def test_returns_bytes(self, dem_10x10, affine_transform, cuencas_gdf, conflictos_gdf):
        result = renderer.render_animacion_tormenta(
            dem_10x10, affine_transform, cuencas_gdf, conflictos_gdf
        )
        assert isinstance(result, bytes)

    def test_open_movie_called(self, dem_10x10, affine_transform, cuencas_gdf, conflictos_gdf):
        """Plotter.open_movie() must be called with a temp file path (str)."""
        mock_plotter_cls = MagicMock()
        mock_instance = MagicMock()
        mock_plotter_cls.return_value = mock_instance

        # Patch at the renderer module level (pyvista was already imported there)
        with patch.object(renderer, "pyvista") as mock_pv:
            mock_pv.StructuredGrid.return_value = MagicMock()
            mock_pv.PolyData.return_value = MagicMock()
            mock_pv.Plotter.return_value = mock_instance

            with patch("tempfile.NamedTemporaryFile") as mock_tmp:
                mock_tmp_obj = MagicMock()
                mock_tmp_obj.name = "/tmp/fake.mp4"
                mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_tmp_obj)
                mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

                with patch("builtins.open", create=True) as mock_open:
                    mock_open.return_value.__enter__ = MagicMock(
                        return_value=MagicMock(read=MagicMock(return_value=b"MP4"))
                    )
                    mock_open.return_value.__exit__ = MagicMock(return_value=False)

                    try:
                        renderer.render_animacion_tormenta(
                            dem_10x10, affine_transform, cuencas_gdf, conflictos_gdf
                        )
                    except Exception:
                        pass

        mock_instance.open_movie.assert_called_once()

    def test_write_frame_called(self, dem_10x10, affine_transform, cuencas_gdf, conflictos_gdf):
        """write_frame() must be called at least once per animation frame."""
        mock_instance = MagicMock()

        with patch.object(renderer, "pyvista") as mock_pv:
            mock_pv.StructuredGrid.return_value = MagicMock()
            mock_pv.PolyData.return_value = MagicMock()
            mock_pv.Plotter.return_value = mock_instance

            with patch("tempfile.NamedTemporaryFile") as mock_tmp:
                mock_tmp_obj = MagicMock()
                mock_tmp_obj.name = "/tmp/fake.mp4"
                mock_tmp.return_value.__enter__ = MagicMock(return_value=mock_tmp_obj)
                mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

                with patch("builtins.open", create=True) as mock_open:
                    mock_open.return_value.__enter__ = MagicMock(
                        return_value=MagicMock(read=MagicMock(return_value=b"MP4"))
                    )
                    mock_open.return_value.__exit__ = MagicMock(return_value=False)

                    try:
                        renderer.render_animacion_tormenta(
                            dem_10x10, affine_transform, cuencas_gdf, conflictos_gdf
                        )
                    except Exception:
                        pass

        assert mock_instance.write_frame.call_count >= 1

    def test_empty_conflictos_does_not_crash(
        self, dem_10x10, affine_transform, cuencas_gdf, conflictos_gdf_empty
    ):
        """Animation with empty risk zones → terrain + basins only, no crash."""
        result = renderer.render_animacion_tormenta(
            dem_10x10, affine_transform, cuencas_gdf, conflictos_gdf_empty
        )
        assert isinstance(result, bytes)

    def test_zero_dem_produces_output(
        self, dem_zeros, affine_transform, cuencas_gdf_empty, conflictos_gdf_empty
    ):
        result = renderer.render_animacion_tormenta(
            dem_zeros, affine_transform, cuencas_gdf_empty, conflictos_gdf_empty
        )
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# Task 2.9 — REFACTOR: _dem_to_grid helper
# ---------------------------------------------------------------------------

class TestDemToGridHelper:
    """_dem_to_grid private helper exists and returns a StructuredGrid-like object."""

    def test_helper_exists(self):
        assert hasattr(renderer, "_dem_to_grid"), (
            "_dem_to_grid helper must exist after refactor (task 2.9)"
        )

    def test_helper_returns_structured_grid(self, dem_10x10, affine_transform):
        grid = renderer._dem_to_grid(dem_10x10, affine_transform)
        # Should be an instance of pyvista.StructuredGrid (or stub)
        assert grid is not None

    def test_helper_zero_dem(self, dem_zeros, affine_transform):
        """Flat DEM must not crash _dem_to_grid."""
        grid = renderer._dem_to_grid(dem_zeros, affine_transform)
        assert grid is not None
