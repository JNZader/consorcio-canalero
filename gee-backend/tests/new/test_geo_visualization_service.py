"""
Tests for VisualizationService — orchestration layer for 3D terrain rendering.

Strategy:
- rasterio is mocked via patch() — no real DEM files needed.
- renderer module functions are mocked — no PyVista calls.
- calculation functions (generar_zonificacion, simular_escorrentia,
  detectar_puntos_conflicto) are mocked — no WhiteboxTools or real rasters.
- DB session is a MagicMock — service receives it but does not hit DB.
- HTTPException(404) is raised when the DEM path does not exist.

TDD cycle: RED → GREEN → REFACTOR per task 3.1–3.6 (updated for real wiring).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
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

# Patch target paths for calculation functions
_CALC_MODULE = "app.domains.geo.visualization.service"


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
def flow_acc_path_existing(tmp_path) -> Path:
    """A real temp file for flow accumulation raster."""
    p = tmp_path / "flow_acc.tif"
    p.write_bytes(b"FAKE_FLOW_ACC")
    return p


@pytest.fixture
def flow_dir_path_existing(tmp_path) -> Path:
    """A real temp file for flow direction raster."""
    p = tmp_path / "flow_dir.tif"
    p.write_bytes(b"FAKE_FLOW_DIR")
    return p


@pytest.fixture
def slope_path_existing(tmp_path) -> Path:
    """A real temp file for slope raster."""
    p = tmp_path / "slope.tif"
    p.write_bytes(b"FAKE_SLOPE")
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
def empty_cuencas_gdf() -> gpd.GeoDataFrame:
    """Empty GeoDataFrame as returned by generar_zonificacion when no basins found."""
    return gpd.GeoDataFrame({"geometry": []})


@pytest.fixture
def empty_conflictos_gdf() -> gpd.GeoDataFrame:
    """Empty GeoDataFrame as returned by detectar_puntos_conflicto when no conflicts."""
    return gpd.GeoDataFrame({"geometry": [], "nivel_riesgo": []})


@pytest.fixture
def sample_escorrentia_geojson() -> dict:
    """Minimal GeoJSON dict as returned by simular_escorrentia."""
    return {"type": "FeatureCollection", "features": []}


@pytest.fixture
def service() -> VisualizationService:
    return VisualizationService()


# ---------------------------------------------------------------------------
# Task 3.1 / 3.2 — render_cuencas calls generar_zonificacion + renderer
# ---------------------------------------------------------------------------

class TestRenderCuencas:
    """VisualizationService.render_cuencas — updated with real wiring."""

    def test_returns_bytes(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        mock_rasterio_dataset, empty_cuencas_gdf,
    ):
        """render_cuencas must return bytes (the PNG from the renderer)."""
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                with patch.object(
                    _renderer_module, "render_cuencas_3d", return_value=b"PNG_BYTES"
                ):
                    result = service.render_cuencas(db, dem_path_existing, flow_acc_path_existing)

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_calls_generar_zonificacion(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        mock_rasterio_dataset, empty_cuencas_gdf,
    ):
        """render_cuencas must call generar_zonificacion with correct paths."""
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(
                f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf
            ) as mock_gen:
                with patch.object(
                    _renderer_module, "render_cuencas_3d", return_value=b"PNG"
                ):
                    service.render_cuencas(db, dem_path_existing, flow_acc_path_existing)

        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args
        # dem_path and flow_acc_path must be passed (positional or keyword)
        args, kwargs = call_kwargs
        all_args = list(args) + list(kwargs.values())
        assert str(dem_path_existing) in [str(a) for a in all_args]
        assert str(flow_acc_path_existing) in [str(a) for a in all_args]

    def test_calls_renderer_with_numpy_array(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        mock_rasterio_dataset, empty_cuencas_gdf,
    ):
        """render_cuencas must call render_cuencas_3d with the DEM numpy array."""
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                with patch.object(
                    _renderer_module, "render_cuencas_3d", return_value=b"PNG_BYTES"
                ) as mock_render:
                    service.render_cuencas(db, dem_path_existing, flow_acc_path_existing)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        elevation_arg = call_args[0][0]
        assert isinstance(elevation_arg, np.ndarray)

    def test_renderer_return_value_is_propagated(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        mock_rasterio_dataset, empty_cuencas_gdf,
    ):
        """render_cuencas must return exactly what render_cuencas_3d returns."""
        expected = b"EXPECTED_PNG"
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                with patch.object(
                    _renderer_module, "render_cuencas_3d", return_value=expected
                ):
                    result = service.render_cuencas(db, dem_path_existing, flow_acc_path_existing)

        assert result == expected


# ---------------------------------------------------------------------------
# Task 3.3 / 3.4 — HTTPException(404) when DEM does not exist
# ---------------------------------------------------------------------------

class TestDemNotFound:
    """VisualizationService raises HTTPException(404) for missing DEM."""

    def test_render_cuencas_raises_404_when_dem_missing(
        self, service, db, dem_path_missing, flow_acc_path_existing
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.render_cuencas(db, dem_path_missing, flow_acc_path_existing)
        assert exc_info.value.status_code == 404

    def test_render_escorrentia_raises_404_when_dem_missing(
        self, service, db, dem_path_missing, flow_dir_path_existing, flow_acc_path_existing
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.render_escorrentia(
                db, dem_path_missing, flow_dir_path_existing, flow_acc_path_existing
            )
        assert exc_info.value.status_code == 404

    def test_render_riesgo_raises_404_when_dem_missing(
        self, service, db, dem_path_missing, flow_acc_path_existing, slope_path_existing
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.render_riesgo(db, dem_path_missing, flow_acc_path_existing, slope_path_existing)
        assert exc_info.value.status_code == 404

    def test_render_animacion_raises_404_when_dem_missing(
        self, service, db, dem_path_missing, flow_acc_path_existing, slope_path_existing
    ):
        with pytest.raises(HTTPException) as exc_info:
            service.render_animacion(db, dem_path_missing, flow_acc_path_existing, slope_path_existing)
        assert exc_info.value.status_code == 404

    def test_404_detail_contains_path(self, service, db, dem_path_missing, flow_acc_path_existing):
        """The 404 message should mention the missing path."""
        with pytest.raises(HTTPException) as exc_info:
            service.render_cuencas(db, dem_path_missing, flow_acc_path_existing)
        assert str(dem_path_missing) in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# Task 3.5 — render_escorrentia wires simular_escorrentia
# ---------------------------------------------------------------------------

class TestRenderEscorrentia:
    """VisualizationService.render_escorrentia — wired with simular_escorrentia."""

    def test_returns_bytes(
        self, service, db, dem_path_existing, flow_dir_path_existing,
        flow_acc_path_existing, mock_rasterio_dataset, sample_escorrentia_geojson,
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(
                f"{_CALC_MODULE}.simular_escorrentia",
                return_value=sample_escorrentia_geojson,
            ):
                with patch.object(
                    _renderer_module, "render_escorrentia_3d", return_value=b"PNG_ESCORRENTIA"
                ):
                    result = service.render_escorrentia(
                        db, dem_path_existing, flow_dir_path_existing, flow_acc_path_existing
                    )

        assert isinstance(result, bytes)

    def test_calls_simular_escorrentia_with_correct_params(
        self, service, db, dem_path_existing, flow_dir_path_existing,
        flow_acc_path_existing, mock_rasterio_dataset, sample_escorrentia_geojson,
    ):
        """simular_escorrentia must be called with flow paths and punto_inicio."""
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(
                f"{_CALC_MODULE}.simular_escorrentia",
                return_value=sample_escorrentia_geojson,
            ) as mock_sim:
                with patch.object(
                    _renderer_module, "render_escorrentia_3d", return_value=b"PNG"
                ):
                    service.render_escorrentia(
                        db, dem_path_existing, flow_dir_path_existing, flow_acc_path_existing,
                        lon=-63.0, lat=-31.0, lluvia_mm=50.0,
                    )

        mock_sim.assert_called_once()
        args, kwargs = mock_sim.call_args
        all_kwargs = {**dict(zip(["flow_dir_path", "flow_acc_path", "punto_inicio", "lluvia_mm"], args)), **kwargs}
        # punto_inicio must be (lon, lat)
        punto = all_kwargs.get("punto_inicio") or args[2]
        assert punto == (-63.0, -31.0)

    def test_calls_renderer(
        self, service, db, dem_path_existing, flow_dir_path_existing,
        flow_acc_path_existing, mock_rasterio_dataset, sample_escorrentia_geojson,
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(
                f"{_CALC_MODULE}.simular_escorrentia",
                return_value=sample_escorrentia_geojson,
            ):
                with patch.object(
                    _renderer_module, "render_escorrentia_3d", return_value=b"PNG"
                ) as mock_render:
                    service.render_escorrentia(
                        db, dem_path_existing, flow_dir_path_existing, flow_acc_path_existing
                    )

        mock_render.assert_called_once()

    def test_passes_geojson_to_renderer(
        self, service, db, dem_path_existing, flow_dir_path_existing,
        flow_acc_path_existing, mock_rasterio_dataset,
    ):
        """The GeoJSON dict returned by simular_escorrentia must go to the renderer."""
        sentinel_geojson = {"type": "FeatureCollection", "features": [{"sentinel": True}]}
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(f"{_CALC_MODULE}.simular_escorrentia", return_value=sentinel_geojson):
                with patch.object(
                    _renderer_module, "render_escorrentia_3d", return_value=b"PNG"
                ) as mock_render:
                    service.render_escorrentia(
                        db, dem_path_existing, flow_dir_path_existing, flow_acc_path_existing
                    )

        call_args = mock_render.call_args[0]
        # Third positional arg is the geojson dict
        assert call_args[2] == sentinel_geojson


# ---------------------------------------------------------------------------
# Task 3.5 — render_riesgo wires detectar_puntos_conflicto
# ---------------------------------------------------------------------------

class TestRenderRiesgo:
    """VisualizationService.render_riesgo — wired with detectar_puntos_conflicto."""

    def test_returns_bytes(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        slope_path_existing, mock_rasterio_dataset, empty_conflictos_gdf,
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(
                f"{_CALC_MODULE}.detectar_puntos_conflicto",
                return_value=empty_conflictos_gdf,
            ):
                with patch.object(
                    _renderer_module, "render_riesgo_3d", return_value=b"PNG_RIESGO"
                ):
                    result = service.render_riesgo(
                        db, dem_path_existing, flow_acc_path_existing, slope_path_existing
                    )

        assert isinstance(result, bytes)

    def test_calls_detectar_puntos_conflicto(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        slope_path_existing, mock_rasterio_dataset, empty_conflictos_gdf,
    ):
        """detectar_puntos_conflicto must be called with flow_acc and slope paths."""
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(
                f"{_CALC_MODULE}.detectar_puntos_conflicto",
                return_value=empty_conflictos_gdf,
            ) as mock_detect:
                with patch.object(
                    _renderer_module, "render_riesgo_3d", return_value=b"PNG"
                ):
                    service.render_riesgo(
                        db, dem_path_existing, flow_acc_path_existing, slope_path_existing
                    )

        mock_detect.assert_called_once()
        args, kwargs = mock_detect.call_args
        all_str_args = [str(a) for a in list(args) + list(kwargs.values())]
        assert str(flow_acc_path_existing) in all_str_args
        assert str(slope_path_existing) in all_str_args

    def test_calls_renderer(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        slope_path_existing, mock_rasterio_dataset, empty_conflictos_gdf,
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(
                f"{_CALC_MODULE}.detectar_puntos_conflicto",
                return_value=empty_conflictos_gdf,
            ):
                with patch.object(
                    _renderer_module, "render_riesgo_3d", return_value=b"PNG"
                ) as mock_render:
                    service.render_riesgo(
                        db, dem_path_existing, flow_acc_path_existing, slope_path_existing
                    )

        mock_render.assert_called_once()


# ---------------------------------------------------------------------------
# Task 3.5 — render_animacion uses both generar_zonificacion + detectar
# ---------------------------------------------------------------------------

class TestRenderAnimacion:
    """VisualizationService.render_animacion — wired with both calc functions."""

    def test_returns_bytes(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        slope_path_existing, mock_rasterio_dataset, empty_cuencas_gdf, empty_conflictos_gdf,
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                with patch(
                    f"{_CALC_MODULE}.detectar_puntos_conflicto",
                    return_value=empty_conflictos_gdf,
                ):
                    with patch.object(
                        _renderer_module, "render_animacion_tormenta", return_value=b"MP4_BYTES"
                    ):
                        result = service.render_animacion(
                            db, dem_path_existing, flow_acc_path_existing, slope_path_existing
                        )

        assert isinstance(result, bytes)

    def test_calls_generar_zonificacion(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        slope_path_existing, mock_rasterio_dataset, empty_cuencas_gdf, empty_conflictos_gdf,
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(
                f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf
            ) as mock_gen:
                with patch(
                    f"{_CALC_MODULE}.detectar_puntos_conflicto",
                    return_value=empty_conflictos_gdf,
                ):
                    with patch.object(
                        _renderer_module, "render_animacion_tormenta", return_value=b"MP4"
                    ):
                        service.render_animacion(
                            db, dem_path_existing, flow_acc_path_existing, slope_path_existing
                        )

        mock_gen.assert_called_once()

    def test_calls_detectar_puntos_conflicto(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        slope_path_existing, mock_rasterio_dataset, empty_cuencas_gdf, empty_conflictos_gdf,
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                with patch(
                    f"{_CALC_MODULE}.detectar_puntos_conflicto",
                    return_value=empty_conflictos_gdf,
                ) as mock_detect:
                    with patch.object(
                        _renderer_module, "render_animacion_tormenta", return_value=b"MP4"
                    ):
                        service.render_animacion(
                            db, dem_path_existing, flow_acc_path_existing, slope_path_existing
                        )

        mock_detect.assert_called_once()

    def test_calls_renderer(
        self, service, db, dem_path_existing, flow_acc_path_existing,
        slope_path_existing, mock_rasterio_dataset, empty_cuencas_gdf, empty_conflictos_gdf,
    ):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                with patch(
                    f"{_CALC_MODULE}.detectar_puntos_conflicto",
                    return_value=empty_conflictos_gdf,
                ):
                    with patch.object(
                        _renderer_module, "render_animacion_tormenta", return_value=b"MP4"
                    ) as mock_render:
                        service.render_animacion(
                            db, dem_path_existing, flow_acc_path_existing, slope_path_existing
                        )

        mock_render.assert_called_once()


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


# ---------------------------------------------------------------------------
# Calculation imports in service — smoke test
# ---------------------------------------------------------------------------

class TestServiceImports:
    """Verify calculation functions are importable from the service module."""

    def test_service_module_imports_generar_zonificacion(self):
        import app.domains.geo.visualization.service as svc_mod
        assert hasattr(svc_mod, "generar_zonificacion"), (
            "service.py must import generar_zonificacion from calculations"
        )

    def test_service_module_imports_simular_escorrentia(self):
        import app.domains.geo.visualization.service as svc_mod
        assert hasattr(svc_mod, "simular_escorrentia"), (
            "service.py must import simular_escorrentia from calculations"
        )

    def test_service_module_imports_detectar_puntos_conflicto(self):
        import app.domains.geo.visualization.service as svc_mod
        assert hasattr(svc_mod, "detectar_puntos_conflicto"), (
            "service.py must import detectar_puntos_conflicto from calculations"
        )
