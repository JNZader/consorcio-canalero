"""
Tests for VisualizationService — orchestration layer for 3D terrain rendering.

Strategy:
- GeoRepository is mocked — _get_layer_path is tested via repo mock.
- rasterio is mocked via patch() — no real DEM files needed.
- renderer module functions are mocked — no PyVista calls.
- calculation functions (generar_zonificacion, simular_escorrentia,
  detectar_puntos_conflicto) are mocked — no WhiteboxTools or real rasters.
- DB session is a MagicMock.
- HTTPException(404) is raised when repo returns no layer for a given type.

TDD cycle: RED → GREEN → REFACTOR per task 3.1–3.6 (updated for DB-layer wiring).
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
from app.domains.geo.models import TipoGeoLayer  # noqa: E402

# Patch target path for calculation functions (lazy-imported inside service
# methods, so we patch the source module, not the consumer).
_CALC_MODULE = "app.domains.geo.intelligence.calculations"
_REPO_MODULE = "app.domains.geo.visualization.service.GeoRepository"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_layer(path: str) -> MagicMock:
    """Return a mock GeoLayer with the given archivo_path."""
    layer = MagicMock()
    layer.archivo_path = path
    return layer


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Mock DB session."""
    return MagicMock()


@pytest.fixture
def dem_path(tmp_path) -> str:
    """A real temp file that acts as a DEM (rasterio is mocked; content irrelevant)."""
    p = tmp_path / "dem.tif"
    p.write_bytes(b"FAKE_DEM")
    return str(p)


@pytest.fixture
def flow_acc_path(tmp_path) -> str:
    p = tmp_path / "flow_acc.tif"
    p.write_bytes(b"FAKE_FLOW_ACC")
    return str(p)


@pytest.fixture
def flow_dir_path(tmp_path) -> str:
    p = tmp_path / "flow_dir.tif"
    p.write_bytes(b"FAKE_FLOW_DIR")
    return str(p)


@pytest.fixture
def slope_path(tmp_path) -> str:
    p = tmp_path / "slope.tif"
    p.write_bytes(b"FAKE_SLOPE")
    return str(p)


@pytest.fixture
def mock_rasterio_dataset() -> MagicMock:
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
    return gpd.GeoDataFrame({"geometry": []})


@pytest.fixture
def empty_conflictos_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"geometry": [], "nivel_riesgo": []})


@pytest.fixture
def sample_escorrentia_geojson() -> dict:
    return {"type": "FeatureCollection", "features": []}


@pytest.fixture
def service() -> VisualizationService:
    return VisualizationService()


# ---------------------------------------------------------------------------
# _get_layer_path helper tests
# ---------------------------------------------------------------------------

class TestGetLayerPath:
    """VisualizationService._get_layer_path — DB-based layer resolution."""

    def test_returns_path_from_repo_when_no_area_id(self, service, db):
        """Without area_id, uses get_layers and returns archivo_path."""
        fake_layer = _make_fake_layer("/data/dem.tif")
        with patch(_REPO_MODULE) as MockRepo:
            MockRepo.return_value.get_layers.return_value = ([fake_layer], 1)
            path = service._get_layer_path(db, TipoGeoLayer.DEM_RAW)

        assert path == "/data/dem.tif"

    def test_returns_path_from_repo_when_area_id_given(self, service, db):
        """With area_id, uses get_layer_by_tipo_and_area."""
        fake_layer = _make_fake_layer("/data/dem_area1.tif")
        with patch(_REPO_MODULE) as MockRepo:
            MockRepo.return_value.get_layer_by_tipo_and_area.return_value = fake_layer
            path = service._get_layer_path(db, TipoGeoLayer.DEM_RAW, area_id="area-1")

        assert path == "/data/dem_area1.tif"

    def test_raises_404_when_no_layers_found(self, service, db):
        """Raises HTTPException(404) when get_layers returns empty list."""
        with patch(_REPO_MODULE) as MockRepo:
            MockRepo.return_value.get_layers.return_value = ([], 0)
            with pytest.raises(HTTPException) as exc_info:
                service._get_layer_path(db, TipoGeoLayer.DEM_RAW)

        assert exc_info.value.status_code == 404

    def test_raises_404_when_area_layer_not_found(self, service, db):
        """Raises HTTPException(404) when get_layer_by_tipo_and_area returns None."""
        with patch(_REPO_MODULE) as MockRepo:
            MockRepo.return_value.get_layer_by_tipo_and_area.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                service._get_layer_path(db, TipoGeoLayer.DEM_RAW, area_id="missing-area")

        assert exc_info.value.status_code == 404

    def test_404_detail_contains_tipo(self, service, db):
        """404 detail message must mention the layer type."""
        with patch(_REPO_MODULE) as MockRepo:
            MockRepo.return_value.get_layers.return_value = ([], 0)
            with pytest.raises(HTTPException) as exc_info:
                service._get_layer_path(db, TipoGeoLayer.FLOW_ACC)

        assert "flow_acc" in exc_info.value.detail


# ---------------------------------------------------------------------------
# render_cuencas tests
# ---------------------------------------------------------------------------

class TestRenderCuencas:
    """VisualizationService.render_cuencas — DB layer lookup + rendering."""

    def _patch_repo(self, dem_path: str, flow_acc_path: str):
        """Context manager factory that patches GeoRepository for cuencas."""
        def _repo_side_effect(*args, tipo_filter=None, **kwargs):
            mapping = {
                TipoGeoLayer.DEM_RAW: ([_make_fake_layer(dem_path)], 1),
                TipoGeoLayer.FLOW_ACC: ([_make_fake_layer(flow_acc_path)], 1),
            }
            return mapping.get(tipo_filter, ([], 0))

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_layers.side_effect = _repo_side_effect
        return mock_repo_instance

    def test_returns_bytes(
        self, service, db, dem_path, flow_acc_path,
        mock_rasterio_dataset, empty_cuencas_gdf,
    ):
        repo_instance = self._patch_repo(dem_path, flow_acc_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                    with patch.object(
                        _renderer_module, "render_cuencas_3d", return_value=b"PNG_BYTES"
                    ):
                        result = service.render_cuencas(db)

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_calls_generar_zonificacion(
        self, service, db, dem_path, flow_acc_path,
        mock_rasterio_dataset, empty_cuencas_gdf,
    ):
        repo_instance = self._patch_repo(dem_path, flow_acc_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(
                    f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf
                ) as mock_gen:
                    with patch.object(
                        _renderer_module, "render_cuencas_3d", return_value=b"PNG"
                    ):
                        service.render_cuencas(db)

        mock_gen.assert_called_once()

    def test_calls_renderer_with_numpy_array(
        self, service, db, dem_path, flow_acc_path,
        mock_rasterio_dataset, empty_cuencas_gdf,
    ):
        repo_instance = self._patch_repo(dem_path, flow_acc_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                    with patch.object(
                        _renderer_module, "render_cuencas_3d", return_value=b"PNG_BYTES"
                    ) as mock_render:
                        service.render_cuencas(db)

        mock_render.assert_called_once()
        elevation_arg = mock_render.call_args[0][0]
        assert isinstance(elevation_arg, np.ndarray)

    def test_renderer_return_value_is_propagated(
        self, service, db, dem_path, flow_acc_path,
        mock_rasterio_dataset, empty_cuencas_gdf,
    ):
        expected = b"EXPECTED_PNG"
        repo_instance = self._patch_repo(dem_path, flow_acc_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                    with patch.object(
                        _renderer_module, "render_cuencas_3d", return_value=expected
                    ):
                        result = service.render_cuencas(db)

        assert result == expected

    def test_uses_area_id_for_lookup(self, service, db, dem_path, flow_acc_path):
        """When area_id is provided, repo.get_layer_by_tipo_and_area is called."""
        fake_dem = _make_fake_layer(dem_path)
        fake_flow_acc = _make_fake_layer(flow_acc_path)

        def _by_tipo_and_area(db_, tipo, area_id):
            if tipo == TipoGeoLayer.DEM_RAW:
                return fake_dem
            if tipo == TipoGeoLayer.FLOW_ACC:
                return fake_flow_acc
            return None

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_layer_by_tipo_and_area.side_effect = _by_tipo_and_area

        with patch(_REPO_MODULE, return_value=mock_repo_instance):
            with patch("rasterio.open") as mock_rio:
                ds = MagicMock()
                ds.read.return_value = np.ones((5, 5))
                ds.transform = MagicMock()
                ds.__enter__ = MagicMock(return_value=ds)
                ds.__exit__ = MagicMock(return_value=False)
                mock_rio.return_value = ds
                with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=gpd.GeoDataFrame()):
                    with patch.object(_renderer_module, "render_cuencas_3d", return_value=b"PNG"):
                        service.render_cuencas(db, area_id="test-area")

        mock_repo_instance.get_layer_by_tipo_and_area.assert_called()


# ---------------------------------------------------------------------------
# 404 when no layers found in DB
# ---------------------------------------------------------------------------

class TestLayerNotFoundRaises404:
    """HTTPException(404) is raised when the DB has no matching layer."""

    def test_render_cuencas_raises_404_when_no_dem(self, service, db):
        with patch(_REPO_MODULE) as MockRepo:
            MockRepo.return_value.get_layers.return_value = ([], 0)
            with pytest.raises(HTTPException) as exc_info:
                service.render_cuencas(db)
        assert exc_info.value.status_code == 404

    def test_render_escorrentia_raises_404_when_no_layer(self, service, db):
        with patch(_REPO_MODULE) as MockRepo:
            MockRepo.return_value.get_layers.return_value = ([], 0)
            with pytest.raises(HTTPException) as exc_info:
                service.render_escorrentia(db)
        assert exc_info.value.status_code == 404

    def test_render_riesgo_raises_404_when_no_layer(self, service, db):
        with patch(_REPO_MODULE) as MockRepo:
            MockRepo.return_value.get_layers.return_value = ([], 0)
            with pytest.raises(HTTPException) as exc_info:
                service.render_riesgo(db)
        assert exc_info.value.status_code == 404

    def test_render_animacion_raises_404_when_no_layer(self, service, db):
        with patch(_REPO_MODULE) as MockRepo:
            MockRepo.return_value.get_layers.return_value = ([], 0)
            with pytest.raises(HTTPException) as exc_info:
                service.render_animacion(db)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# render_escorrentia tests
# ---------------------------------------------------------------------------

class TestRenderEscorrentia:
    """VisualizationService.render_escorrentia — DB lookup + simular_escorrentia."""

    def _patch_repo(self, dem_path: str, flow_dir_path: str, flow_acc_path: str):
        def _repo_side_effect(*args, tipo_filter=None, **kwargs):
            mapping = {
                TipoGeoLayer.FLOW_DIR: ([_make_fake_layer(flow_dir_path)], 1),
                TipoGeoLayer.FLOW_ACC: ([_make_fake_layer(flow_acc_path)], 1),
                TipoGeoLayer.DEM_RAW: ([_make_fake_layer(dem_path)], 1),
            }
            return mapping.get(tipo_filter, ([], 0))

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_layers.side_effect = _repo_side_effect
        return mock_repo_instance

    def test_returns_bytes(
        self, service, db, dem_path, flow_dir_path, flow_acc_path,
        mock_rasterio_dataset, sample_escorrentia_geojson,
    ):
        repo_instance = self._patch_repo(dem_path, flow_dir_path, flow_acc_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(
                    f"{_CALC_MODULE}.simular_escorrentia",
                    return_value=sample_escorrentia_geojson,
                ):
                    with patch.object(
                        _renderer_module, "render_escorrentia_3d", return_value=b"PNG_ESCORRENTIA"
                    ):
                        result = service.render_escorrentia(db)

        assert isinstance(result, bytes)

    def test_calls_simular_escorrentia_with_correct_params(
        self, service, db, dem_path, flow_dir_path, flow_acc_path,
        mock_rasterio_dataset, sample_escorrentia_geojson,
    ):
        repo_instance = self._patch_repo(dem_path, flow_dir_path, flow_acc_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(
                    f"{_CALC_MODULE}.simular_escorrentia",
                    return_value=sample_escorrentia_geojson,
                ) as mock_sim:
                    with patch.object(
                        _renderer_module, "render_escorrentia_3d", return_value=b"PNG"
                    ):
                        service.render_escorrentia(db, lon=-63.0, lat=-31.0, lluvia_mm=50.0)

        mock_sim.assert_called_once()
        args, kwargs = mock_sim.call_args
        all_kwargs = {**dict(zip(["flow_dir_path", "flow_acc_path", "punto_inicio", "lluvia_mm"], args)), **kwargs}
        punto = all_kwargs.get("punto_inicio") or (args[2] if len(args) > 2 else None)
        assert punto == (-63.0, -31.0)

    def test_passes_geojson_to_renderer(
        self, service, db, dem_path, flow_dir_path, flow_acc_path,
        mock_rasterio_dataset,
    ):
        sentinel_geojson = {"type": "FeatureCollection", "features": [{"sentinel": True}]}
        repo_instance = self._patch_repo(dem_path, flow_dir_path, flow_acc_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(f"{_CALC_MODULE}.simular_escorrentia", return_value=sentinel_geojson):
                    with patch.object(
                        _renderer_module, "render_escorrentia_3d", return_value=b"PNG"
                    ) as mock_render:
                        service.render_escorrentia(db)

        call_args = mock_render.call_args[0]
        assert call_args[2] == sentinel_geojson


# ---------------------------------------------------------------------------
# render_riesgo tests
# ---------------------------------------------------------------------------

class TestRenderRiesgo:
    """VisualizationService.render_riesgo — DB lookup + detectar_puntos_conflicto."""

    def _patch_repo(self, dem_path: str, flow_acc_path: str, slope_path: str):
        def _repo_side_effect(*args, tipo_filter=None, **kwargs):
            mapping = {
                TipoGeoLayer.DEM_RAW: ([_make_fake_layer(dem_path)], 1),
                TipoGeoLayer.FLOW_ACC: ([_make_fake_layer(flow_acc_path)], 1),
                TipoGeoLayer.SLOPE: ([_make_fake_layer(slope_path)], 1),
            }
            return mapping.get(tipo_filter, ([], 0))

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_layers.side_effect = _repo_side_effect
        return mock_repo_instance

    def test_returns_bytes(
        self, service, db, dem_path, flow_acc_path, slope_path,
        mock_rasterio_dataset, empty_conflictos_gdf,
    ):
        repo_instance = self._patch_repo(dem_path, flow_acc_path, slope_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(
                    f"{_CALC_MODULE}.detectar_puntos_conflicto",
                    return_value=empty_conflictos_gdf,
                ):
                    with patch.object(
                        _renderer_module, "render_riesgo_3d", return_value=b"PNG_RIESGO"
                    ):
                        result = service.render_riesgo(db)

        assert isinstance(result, bytes)

    def test_calls_detectar_puntos_conflicto(
        self, service, db, dem_path, flow_acc_path, slope_path,
        mock_rasterio_dataset, empty_conflictos_gdf,
    ):
        repo_instance = self._patch_repo(dem_path, flow_acc_path, slope_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(
                    f"{_CALC_MODULE}.detectar_puntos_conflicto",
                    return_value=empty_conflictos_gdf,
                ) as mock_detect:
                    with patch.object(
                        _renderer_module, "render_riesgo_3d", return_value=b"PNG"
                    ):
                        service.render_riesgo(db)

        mock_detect.assert_called_once()
        args, kwargs = mock_detect.call_args
        all_str_args = [str(a) for a in list(args) + list(kwargs.values())]
        assert flow_acc_path in all_str_args
        assert slope_path in all_str_args

    def test_calls_renderer(
        self, service, db, dem_path, flow_acc_path, slope_path,
        mock_rasterio_dataset, empty_conflictos_gdf,
    ):
        repo_instance = self._patch_repo(dem_path, flow_acc_path, slope_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(
                    f"{_CALC_MODULE}.detectar_puntos_conflicto",
                    return_value=empty_conflictos_gdf,
                ):
                    with patch.object(
                        _renderer_module, "render_riesgo_3d", return_value=b"PNG"
                    ) as mock_render:
                        service.render_riesgo(db)

        mock_render.assert_called_once()


# ---------------------------------------------------------------------------
# render_animacion tests
# ---------------------------------------------------------------------------

class TestRenderAnimacion:
    """VisualizationService.render_animacion — DB lookup + both calc functions."""

    def _patch_repo(self, dem_path: str, flow_acc_path: str, slope_path: str):
        def _repo_side_effect(*args, tipo_filter=None, **kwargs):
            mapping = {
                TipoGeoLayer.DEM_RAW: ([_make_fake_layer(dem_path)], 1),
                TipoGeoLayer.FLOW_ACC: ([_make_fake_layer(flow_acc_path)], 1),
                TipoGeoLayer.SLOPE: ([_make_fake_layer(slope_path)], 1),
            }
            return mapping.get(tipo_filter, ([], 0))

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_layers.side_effect = _repo_side_effect
        return mock_repo_instance

    def test_returns_bytes(
        self, service, db, dem_path, flow_acc_path, slope_path,
        mock_rasterio_dataset, empty_cuencas_gdf, empty_conflictos_gdf,
    ):
        repo_instance = self._patch_repo(dem_path, flow_acc_path, slope_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                    with patch(
                        f"{_CALC_MODULE}.detectar_puntos_conflicto",
                        return_value=empty_conflictos_gdf,
                    ):
                        with patch.object(
                            _renderer_module, "render_animacion_tormenta", return_value=b"MP4_BYTES"
                        ):
                            result = service.render_animacion(db)

        assert isinstance(result, bytes)

    def test_calls_generar_zonificacion(
        self, service, db, dem_path, flow_acc_path, slope_path,
        mock_rasterio_dataset, empty_cuencas_gdf, empty_conflictos_gdf,
    ):
        repo_instance = self._patch_repo(dem_path, flow_acc_path, slope_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
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
                            service.render_animacion(db)

        mock_gen.assert_called_once()

    def test_calls_detectar_puntos_conflicto(
        self, service, db, dem_path, flow_acc_path, slope_path,
        mock_rasterio_dataset, empty_cuencas_gdf, empty_conflictos_gdf,
    ):
        repo_instance = self._patch_repo(dem_path, flow_acc_path, slope_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                    with patch(
                        f"{_CALC_MODULE}.detectar_puntos_conflicto",
                        return_value=empty_conflictos_gdf,
                    ) as mock_detect:
                        with patch.object(
                            _renderer_module, "render_animacion_tormenta", return_value=b"MP4"
                        ):
                            service.render_animacion(db)

        mock_detect.assert_called_once()

    def test_calls_renderer(
        self, service, db, dem_path, flow_acc_path, slope_path,
        mock_rasterio_dataset, empty_cuencas_gdf, empty_conflictos_gdf,
    ):
        repo_instance = self._patch_repo(dem_path, flow_acc_path, slope_path)
        with patch(_REPO_MODULE, return_value=repo_instance):
            with patch("rasterio.open", return_value=mock_rasterio_dataset):
                with patch(f"{_CALC_MODULE}.generar_zonificacion", return_value=empty_cuencas_gdf):
                    with patch(
                        f"{_CALC_MODULE}.detectar_puntos_conflicto",
                        return_value=empty_conflictos_gdf,
                    ):
                        with patch.object(
                            _renderer_module, "render_animacion_tormenta", return_value=b"MP4"
                        ) as mock_render:
                            service.render_animacion(db)

        mock_render.assert_called_once()


# ---------------------------------------------------------------------------
# _load_dem private helper tests
# ---------------------------------------------------------------------------

class TestLoadDemHelper:
    """VisualizationService._load_dem helper."""

    def test_load_dem_helper_exists(self, service):
        assert hasattr(service, "_load_dem")

    def test_load_dem_returns_tuple(self, service, dem_path, mock_rasterio_dataset):
        with patch("rasterio.open", return_value=mock_rasterio_dataset):
            result = service._load_dem(dem_path)

        assert isinstance(result, tuple)
        assert len(result) == 2
        elevation, transform = result
        assert isinstance(elevation, np.ndarray)

    def test_load_dem_raises_404_when_missing(self, service, tmp_path):
        missing = str(tmp_path / "does_not_exist.tif")
        with pytest.raises(HTTPException) as exc_info:
            service._load_dem(missing)
        assert exc_info.value.status_code == 404

    def test_load_dem_404_detail_contains_path(self, service, tmp_path):
        missing = str(tmp_path / "does_not_exist.tif")
        with pytest.raises(HTTPException) as exc_info:
            service._load_dem(missing)
        assert missing in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# Calculation imports smoke test
# ---------------------------------------------------------------------------

class TestServiceImports:
    """Verify module-level imports in the service module.

    Note: generar_zonificacion / simular_escorrentia / detectar_puntos_conflicto
    are intentionally LAZY-imported inside methods (commit 978efca) so the
    service module loads in environments without geopandas. Tests asserting
    they exist as module attributes were removed.
    """

    def test_service_module_imports_tipo_geo_layer(self):
        import app.domains.geo.visualization.service as svc_mod
        assert hasattr(svc_mod, "TipoGeoLayer")
