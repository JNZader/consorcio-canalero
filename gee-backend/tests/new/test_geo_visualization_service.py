"""
Tests for VisualizationService — orchestration layer for 3D terrain rendering.

Strategy:
- rasterio is mocked via patch() — no real DEM files needed.
- renderer module functions are mocked — no PyVista calls.
- DB session is a MagicMock — service does not hit DB in Phase 3 simplified impl
  (GDFs are empty by default; real DB wiring is a future task).
- HTTPException(404) is raised when the DEM path does not exist.

TDD cycle: RED → GREEN → REFACTOR per task 3.1–3.6.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Stub pyvista so renderer.py can be imported (same pattern as renderer tests)
# ---------------------------------------------------------------------------

def _make_pyvista_stub() -> types.ModuleType:
    pv = types.ModuleType("pyvista")

    class _StructuredGrid:
        def __init__(self, *args, **kwargs):
            self._data: dict = {}

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

    pv.StructuredGrid = _StructuredGrid
    pv.PolyData = _PolyData
    pv.Plotter = _Plotter
    pv.start_xvfb = MagicMock()
    return pv


sys.modules.setdefault("pyvista", _make_pyvista_stub())

# Now safe to import the service
from app.domains.geo.visualization.service import VisualizationService  # noqa: E402
from app.domains.geo.visualization import renderer as _renderer_module  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Mock DB session — service receives it but simplified impl ignores it."""
    return MagicMock()


@pytest.fixture
def dem_path_existing(tmp_path) -> Path:
    """A real temp file that acts as a DEM (rasterio is mocked; content irrelevant)."""
    p = tmp_path / "dem.tif"
    p.write_bytes(b"FAKE_DEM")
    return p


@pytest.fixture
def dem_path_missing(tmp_path) -> Path:
    """A path that does NOT exist on disk."""
    return tmp_path / "does_not_exist.tif"


@pytest.fixture
def mock_rasterio_dataset(dem_path_existing) -> MagicMock:
    """Return a mock that behaves like rasterio.open() context manager."""
    elevation = np.ones((10, 10), dtype=np.float32) * 42.0

    from collections import namedtuple
    Affine = namedtuple("Affine", ["a", "b", "c", "d", "e", "f"])
    transform = Affine(a=30.0, b=0.0, c=0.0, d=0.0, e=-30.0, f=300.0)

    dataset = MagicMock()
    dataset.read.return_value = elevation
    dataset.transform = transform
    dataset.__enter__ = MagicMock(return_value=dataset)
    dataset.__exit__ = MagicMock(return_value=False)
    return dataset


@pytest.fixture
def service() -> VisualizationService:
    return VisualizationService()


# ---------------------------------------------------------------------------
# Task 3.1 / 3.2 — render_cuencas calls renderer with correct numpy array
# ---------------------------------------------------------------------------

class TestRenderCuencas:
    """VisualizationService.render_cuencas — TDD tasks 3.1 & 3.2."""

    def test_returns_bytes(self, service, db, dem_path_existing, mock_rasterio_dataset):
        """render_cuencas must return bytes (the PNG from the renderer)."""
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch.object(
                _renderer_module, "render_cuencas_3d", return_value=b"PNG_BYTES"
            ):
                result = service.render_cuencas(db, dem_path_existing)

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_calls_renderer_with_numpy_array(
        self, service, db, dem_path_existing, mock_rasterio_dataset
    ):
        """render_cuencas must call render_cuencas_3d with the DEM numpy array."""
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch.object(
                _renderer_module, "render_cuencas_3d", return_value=b"PNG_BYTES"
            ) as mock_render:
                service.render_cuencas(db, dem_path_existing)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        # First positional arg is the elevation array
        elevation_arg = call_args[0][0]
        assert isinstance(elevation_arg, np.ndarray)

    def test_calls_rasterio_with_given_dem_path(
        self, service, db, dem_path_existing, mock_rasterio_dataset
    ):
        """rasterio.open must be called with the exact dem_path provided."""
        with patch("rasterio.open", return_value=mock_rasterio_dataset) as mock_rio:
            with patch.object(
                _renderer_module, "render_cuencas_3d", return_value=b"PNG_BYTES"
            ):
                service.render_cuencas(db, dem_path_existing)

        mock_rio.assert_called_once_with(dem_path_existing)

    def test_renderer_return_value_is_propagated(
        self, service, db, dem_path_existing, mock_rasterio_dataset
    ):
        """render_cuencas must return exactly what render_cuencas_3d returns."""
        expected = b"EXPECTED_PNG"
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch.object(
                _renderer_module, "render_cuencas_3d", return_value=expected
            ):
                result = service.render_cuencas(db, dem_path_existing)

        assert result == expected


# ---------------------------------------------------------------------------
# Task 3.3 / 3.4 — HTTPException(404) when DEM does not exist
# ---------------------------------------------------------------------------

class TestDemNotFound:
    """VisualizationService raises HTTPException(404) for missing DEM — task 3.3/3.4."""

    def test_render_cuencas_raises_404_when_dem_missing(
        self, service, db, dem_path_missing
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.render_cuencas(db, dem_path_missing)
        assert exc_info.value.status_code == 404

    def test_render_escorrentia_raises_404_when_dem_missing(
        self, service, db, dem_path_missing
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.render_escorrentia(db, dem_path_missing)
        assert exc_info.value.status_code == 404

    def test_render_riesgo_raises_404_when_dem_missing(
        self, service, db, dem_path_missing
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.render_riesgo(db, dem_path_missing)
        assert exc_info.value.status_code == 404

    def test_render_animacion_raises_404_when_dem_missing(
        self, service, db, dem_path_missing
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.render_animacion(db, dem_path_missing, fecha="2025-03-15")
        assert exc_info.value.status_code == 404

    def test_404_detail_contains_path(self, service, db, dem_path_missing):
        """The 404 message should mention the missing path."""
        with pytest.raises(HTTPException) as exc_info:
            service.render_cuencas(db, dem_path_missing)
        assert str(dem_path_missing) in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# Task 3.5 — render_escorrentia, render_riesgo, render_animacion
# ---------------------------------------------------------------------------

class TestRenderEscorrentia:
    """VisualizationService.render_escorrentia — task 3.5."""

    def test_returns_bytes(self, service, db, dem_path_existing, mock_rasterio_dataset):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch.object(
                _renderer_module, "render_escorrentia_3d", return_value=b"PNG_ESCORRENTIA"
            ):
                result = service.render_escorrentia(db, dem_path_existing)

        assert isinstance(result, bytes)

    def test_calls_renderer(self, service, db, dem_path_existing, mock_rasterio_dataset):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch.object(
                _renderer_module, "render_escorrentia_3d", return_value=b"PNG"
            ) as mock_render:
                service.render_escorrentia(db, dem_path_existing)

        mock_render.assert_called_once()

    def test_calls_rasterio_with_dem_path(
        self, service, db, dem_path_existing, mock_rasterio_dataset
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset) as mock_rio:
            with patch.object(
                _renderer_module, "render_escorrentia_3d", return_value=b"PNG"
            ):
                service.render_escorrentia(db, dem_path_existing)

        mock_rio.assert_called_once_with(dem_path_existing)


class TestRenderRiesgo:
    """VisualizationService.render_riesgo — task 3.5."""

    def test_returns_bytes(self, service, db, dem_path_existing, mock_rasterio_dataset):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch.object(
                _renderer_module, "render_riesgo_3d", return_value=b"PNG_RIESGO"
            ):
                result = service.render_riesgo(db, dem_path_existing)

        assert isinstance(result, bytes)

    def test_calls_renderer(self, service, db, dem_path_existing, mock_rasterio_dataset):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch.object(
                _renderer_module, "render_riesgo_3d", return_value=b"PNG"
            ) as mock_render:
                service.render_riesgo(db, dem_path_existing)

        mock_render.assert_called_once()

    def test_calls_rasterio_with_dem_path(
        self, service, db, dem_path_existing, mock_rasterio_dataset
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset) as mock_rio:
            with patch.object(
                _renderer_module, "render_riesgo_3d", return_value=b"PNG"
            ):
                service.render_riesgo(db, dem_path_existing)

        mock_rio.assert_called_once_with(dem_path_existing)


class TestRenderAnimacion:
    """VisualizationService.render_animacion — task 3.5."""

    def test_returns_bytes(self, service, db, dem_path_existing, mock_rasterio_dataset):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch.object(
                _renderer_module, "render_animacion_tormenta", return_value=b"MP4_BYTES"
            ):
                result = service.render_animacion(db, dem_path_existing, fecha="2025-03-15")

        assert isinstance(result, bytes)

    def test_calls_renderer(self, service, db, dem_path_existing, mock_rasterio_dataset):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch.object(
                _renderer_module, "render_animacion_tormenta", return_value=b"MP4"
            ) as mock_render:
                service.render_animacion(db, dem_path_existing, fecha="2025-03-15")

        mock_render.assert_called_once()

    def test_calls_rasterio_with_dem_path(
        self, service, db, dem_path_existing, mock_rasterio_dataset
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset) as mock_rio:
            with patch.object(
                _renderer_module, "render_animacion_tormenta", return_value=b"MP4"
            ):
                service.render_animacion(db, dem_path_existing, fecha="2025-03-15")

        mock_rio.assert_called_once_with(dem_path_existing)


# ---------------------------------------------------------------------------
# Task 3.6 — REFACTOR: _load_dem private helper exists and is used
# ---------------------------------------------------------------------------

class TestLoadDemHelper:
    """VisualizationService._load_dem helper — task 3.6."""

    def test_load_dem_helper_exists(self, service):
        """_load_dem must exist as a private method after refactor."""
        assert hasattr(service, "_load_dem"), (
            "_load_dem helper must exist after refactor (task 3.6)"
        )

    def test_load_dem_returns_tuple(self, service, dem_path_existing, mock_rasterio_dataset):
        """_load_dem must return (elevation_array, transform) tuple."""
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            result = service._load_dem(dem_path_existing)

        assert isinstance(result, tuple)
        assert len(result) == 2
        elevation, transform = result
        assert isinstance(elevation, np.ndarray)

    def test_load_dem_raises_404_when_missing(self, service, dem_path_missing):
        """_load_dem must raise HTTPException(404) when path does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            service._load_dem(dem_path_missing)
        assert exc_info.value.status_code == 404
