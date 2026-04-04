"""Unit tests for gee_service.py — GEE service, ImageExplorer, and utility functions.

Mocks ee (Earth Engine) completely. No real GEE calls.
"""

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_gee_state():
    """Reset the module-level lazy-init state between tests."""
    import app.domains.geo.gee_service as mod

    mod._gee_initialized = False
    mod._gee_init_error = None


@pytest.fixture(autouse=True)
def reset_gee():
    _reset_gee_state()
    yield
    _reset_gee_state()


# ---------------------------------------------------------------------------
# _ensure_initialized
# ---------------------------------------------------------------------------


class TestEnsureInitialized:
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_already_initialized_returns_immediately(self, mock_settings, mock_ee):
        import app.domains.geo.gee_service as mod

        mod._gee_initialized = True
        mod._ensure_initialized()
        mock_ee.Initialize.assert_not_called()

    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_raises_if_previous_init_failed(self, mock_settings, mock_ee):
        import app.domains.geo.gee_service as mod

        mod._gee_init_error = "some error"
        with pytest.raises(RuntimeError, match="GEE no disponible"):
            mod._ensure_initialized()

    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_init_with_key_file(self, mock_settings, mock_ee, tmp_path):
        import app.domains.geo.gee_service as mod

        key_file = tmp_path / "key.json"
        key_file.write_text('{"client_email": "test@test.com"}')
        mock_settings.gee_key_file_path = str(key_file)
        mock_settings.gee_project_id = "test-project"
        mock_settings.gee_service_account_key = None

        mod._ensure_initialized()

        assert mod._gee_initialized is True
        mock_ee.ServiceAccountCredentials.assert_called_once()
        mock_ee.Initialize.assert_called_once()

    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_init_with_json_env_var(self, mock_settings, mock_ee):
        import app.domains.geo.gee_service as mod

        mock_settings.gee_key_file_path = None
        mock_settings.gee_service_account_key = json.dumps(
            {"client_email": "test@sa.iam.gserviceaccount.com"}
        )
        mock_settings.gee_project_id = "test-project"

        mod._ensure_initialized()

        assert mod._gee_initialized is True
        mock_ee.ServiceAccountCredentials.assert_called_once()

    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_init_with_default_auth(self, mock_settings, mock_ee):
        import app.domains.geo.gee_service as mod

        mock_settings.gee_key_file_path = None
        mock_settings.gee_service_account_key = None
        mock_settings.gee_project_id = "test-project"

        mod._ensure_initialized()

        assert mod._gee_initialized is True
        mock_ee.Initialize.assert_called_once_with(project="test-project")

    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_init_failure_stores_error(self, mock_settings, mock_ee):
        import app.domains.geo.gee_service as mod

        mock_settings.gee_key_file_path = None
        mock_settings.gee_service_account_key = None
        mock_settings.gee_project_id = "test-project"
        mock_ee.Initialize.side_effect = Exception("network error")

        with pytest.raises(ValueError, match="No se pudo inicializar GEE"):
            mod._ensure_initialized()

        assert mod._gee_init_error == "network error"

    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_key_file_not_exists_falls_through(self, mock_settings, mock_ee):
        import app.domains.geo.gee_service as mod

        mock_settings.gee_key_file_path = "/nonexistent/key.json"
        mock_settings.gee_service_account_key = None
        mock_settings.gee_project_id = "test-project"

        mod._ensure_initialized()

        # Falls through to default auth
        assert mod._gee_initialized is True


class TestIsInitialized:
    def test_returns_false_by_default(self):
        from app.domains.geo.gee_service import is_initialized

        assert is_initialized() is False

    def test_returns_true_after_init(self):
        import app.domains.geo.gee_service as mod

        mod._gee_initialized = True
        assert mod.is_initialized() is True


# ---------------------------------------------------------------------------
# GEEService
# ---------------------------------------------------------------------------


class TestGEEService:
    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_constructor_initializes_assets(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import GEEService

        mock_settings.gee_project_id = "test-proj"
        svc = GEEService()

        assert mock_ee.FeatureCollection.call_count >= 3  # zona, caminos, canales

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_canales_fallback_on_exception(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import GEEService

        mock_settings.gee_project_id = "test-proj"
        call_count = 0

        def side_effect(path):
            nonlocal call_count
            call_count += 1
            if "canales" in str(path):
                raise Exception("not found")
            return MagicMock()

        mock_ee.FeatureCollection.side_effect = side_effect
        svc = GEEService()
        # Should not raise; canales falls back to empty

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_dem_download_url(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import GEEService

        mock_settings.gee_project_id = "test-proj"
        svc = GEEService()

        mock_image = MagicMock()
        mock_image.clip.return_value = mock_image
        mock_image.getDownloadURL.return_value = "https://example.com/dem.tif"
        mock_collection = MagicMock()
        mock_collection.select.return_value.mosaic.return_value = mock_image
        mock_ee.ImageCollection.return_value = mock_collection

        result = svc.get_dem_download_url(scale=30)

        assert result["download_url"] == "https://example.com/dem.tif"
        assert result["scale"] == 30
        assert result["crs"] == "EPSG:4326"

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sentinel2_tiles_no_images(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import GEEService

        mock_settings.gee_project_id = "test-proj"
        svc = GEEService()

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 0
        mock_ee.ImageCollection.return_value = mock_collection

        result = svc.get_sentinel2_tiles(date(2025, 1, 1), date(2025, 1, 31))

        assert "error" in result

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sentinel2_tiles_success(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import GEEService

        mock_settings.gee_project_id = "test-proj"
        svc = GEEService()

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 5
        mock_mosaic = MagicMock()
        mock_mosaic.clip.return_value = mock_mosaic
        mock_fetcher = MagicMock()
        mock_fetcher.url_format = "https://tiles/{z}/{x}/{y}"
        mock_mosaic.getMapId.return_value = {"tile_fetcher": mock_fetcher}
        mock_collection.mosaic.return_value = mock_mosaic
        mock_ee.ImageCollection.return_value = mock_collection

        result = svc.get_sentinel2_tiles(date(2025, 1, 1), date(2025, 1, 31))

        assert "tile_url" in result
        assert result["imagenes_disponibles"] == 5


# ---------------------------------------------------------------------------
# get_layer_geojson / get_available_layers
# ---------------------------------------------------------------------------


class TestLayerFunctions:
    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_layer_geojson_valid(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import get_layer_geojson

        mock_settings.gee_project_id = "test-proj"
        mock_fc = MagicMock()
        mock_fc.getInfo.return_value = {"type": "FeatureCollection", "features": []}
        mock_ee.FeatureCollection.return_value = mock_fc

        result = get_layer_geojson("zona")
        assert result["type"] == "FeatureCollection"

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_layer_geojson_invalid_name(self, mock_settings, mock_init):
        from app.domains.geo.gee_service import get_layer_geojson

        mock_settings.gee_project_id = "test-proj"
        with pytest.raises(ValueError, match="no encontrada"):
            get_layer_geojson("nonexistent_layer")

    def test_get_available_layers_returns_list(self):
        from app.domains.geo.gee_service import get_available_layers

        layers = get_available_layers()
        assert isinstance(layers, list)
        assert len(layers) == 6
        ids = [l["id"] for l in layers]
        assert "zona" in ids
        assert "caminos" in ids


# ---------------------------------------------------------------------------
# Consorcios camineros functions
# ---------------------------------------------------------------------------


class TestConsorciosFunctions:
    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_consorcios_camineros(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import get_consorcios_camineros

        mock_settings.gee_project_id = "test-proj"
        mock_fc = MagicMock()
        mock_fc.getInfo.return_value = {
            "features": [
                {"properties": {"ccn": "Consorcio A", "ccc": "CA", "lzn": 10.5}},
                {"properties": {"ccn": "Consorcio A", "ccc": "CA", "lzn": 5.2}},
                {"properties": {"ccn": "Consorcio B", "ccc": "CB", "lzn": "bad"}},
            ]
        }
        mock_ee.FeatureCollection.return_value = mock_fc

        result = get_consorcios_camineros()

        assert len(result) == 2
        ca = next(c for c in result if c["nombre"] == "Consorcio A")
        assert ca["tramos"] == 2
        assert ca["longitud_total_km"] == pytest.approx(15.7)

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_caminos_by_consorcio(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import get_caminos_by_consorcio

        mock_settings.gee_project_id = "test-proj"
        mock_fc = MagicMock()
        mock_filtered = MagicMock()
        mock_filtered.getInfo.return_value = {"features": [{"id": 1}]}
        mock_fc.filter.return_value = mock_filtered
        mock_ee.FeatureCollection.return_value = mock_fc

        result = get_caminos_by_consorcio("CA")
        assert len(result["features"]) == 1

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_caminos_by_consorcio_fallback_upper(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import get_caminos_by_consorcio

        mock_settings.gee_project_id = "test-proj"
        mock_fc = MagicMock()

        # First filter returns empty, second returns data
        mock_filtered_empty = MagicMock()
        mock_filtered_empty.getInfo.return_value = {"features": []}
        mock_filtered_with_data = MagicMock()
        mock_filtered_with_data.getInfo.return_value = {"features": [{"id": 1}]}
        mock_fc.filter.side_effect = [mock_filtered_empty, mock_filtered_with_data]
        mock_ee.FeatureCollection.return_value = mock_fc

        result = get_caminos_by_consorcio("ca")
        assert len(result["features"]) == 1

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_caminos_by_consorcio_nombre(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import get_caminos_by_consorcio_nombre

        mock_settings.gee_project_id = "test-proj"
        mock_fc = MagicMock()
        mock_filtered = MagicMock()
        mock_filtered.getInfo.return_value = {"features": [{"id": 1}]}
        mock_fc.filter.return_value = mock_filtered
        mock_ee.FeatureCollection.return_value = mock_fc

        result = get_caminos_by_consorcio_nombre("Consorcio A")
        assert len(result["features"]) == 1

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_caminos_con_colores(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import get_caminos_con_colores

        mock_settings.gee_project_id = "test-proj"
        mock_fc = MagicMock()
        mock_fc.getInfo.return_value = {
            "features": [
                {"properties": {"ccn": "C1", "ccc": "CC1", "lzn": 10}},
                {"properties": {"ccn": "C2", "ccc": "CC2", "lzn": 20}},
                {"properties": {"ccn": "C1", "ccc": "CC1", "lzn": 5}},
            ]
        }
        mock_ee.FeatureCollection.return_value = mock_fc

        result = get_caminos_con_colores()

        assert result["type"] == "FeatureCollection"
        assert result["metadata"]["total_tramos"] == 3
        assert result["metadata"]["total_consorcios"] == 2
        assert len(result["consorcios"]) == 2
        # Colors should be assigned
        for f in result["features"]:
            assert "color" in f["properties"]

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_estadisticas_consorcios(self, mock_settings, mock_ee, mock_init):
        from app.domains.geo.gee_service import get_estadisticas_consorcios

        mock_settings.gee_project_id = "test-proj"
        mock_fc = MagicMock()
        mock_fc.getInfo.return_value = {
            "features": [
                {"properties": {"ccn": "C1", "ccc": "CC1", "lzn": 10, "hct": "primaria", "rst": "tierra"}},
                {"properties": {"ccn": "C1", "ccc": "CC1", "lzn": 5, "hct": "secundaria", "rst": "ripio"}},
                {"properties": {"ccn": "C2", "ccc": "CC2", "lzn": 8, "hct": "primaria", "rst": "tierra"}},
            ]
        }
        mock_ee.FeatureCollection.return_value = mock_fc

        result = get_estadisticas_consorcios()

        assert result["totales"]["consorcios"] == 2
        assert result["totales"]["tramos"] == 3
        c1 = next(c for c in result["consorcios"] if c["nombre"] == "C1")
        assert len(c1["por_jerarquia"]) == 2
        assert len(c1["por_superficie"]) == 2


# ---------------------------------------------------------------------------
# ImageExplorer
# ---------------------------------------------------------------------------


class TestImageExplorer:
    def _make_explorer(self, mock_ee, mock_settings):
        """Create an ImageExplorer with mocked dependencies."""
        from app.domains.geo.gee_service import ImageExplorer

        mock_settings.gee_project_id = "test-proj"
        return ImageExplorer()

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_available_dates_sentinel2(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_agg = MagicMock()
        mock_agg.map.return_value = mock_agg
        mock_agg.distinct.return_value = mock_agg
        mock_agg.sort.return_value = mock_agg
        mock_agg.getInfo.return_value = ["2025-06-01", "2025-06-05"]
        mock_collection.aggregate_array.return_value = mock_agg
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_available_dates(2025, 6, sensor="sentinel2")

        assert result["sensor"] == "sentinel2"
        assert result["total"] == 2
        assert "2025-06-01" in result["dates"]

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_available_dates_sentinel1(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_agg = MagicMock()
        mock_agg.map.return_value = mock_agg
        mock_agg.distinct.return_value = mock_agg
        mock_agg.sort.return_value = mock_agg
        mock_agg.getInfo.return_value = ["2025-06-03"]
        mock_collection.aggregate_array.return_value = mock_agg
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_available_dates(2025, 6, sensor="sentinel1")

        assert result["sensor"] == "sentinel1"
        assert result["total"] == 1

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_available_dates_empty(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_agg = MagicMock()
        mock_agg.map.return_value = mock_agg
        mock_agg.distinct.return_value = mock_agg
        mock_agg.sort.return_value = mock_agg
        mock_agg.getInfo.return_value = None
        mock_collection.aggregate_array.return_value = mock_agg
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_available_dates(2025, 6)

        assert result["dates"] == []
        assert result["total"] == 0

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sentinel2_image_no_images(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 0
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_sentinel2_image(date(2025, 6, 15))

        assert "error" in result
        assert "sugerencia" in result

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sentinel2_image_rgb(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        # Build a chain that supports both the filter chain and the map/mosaic chain
        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 3
        # map() for cloud masking returns a new collection
        mock_masked = MagicMock()
        mock_collection.map.return_value = mock_masked
        mock_agg = MagicMock()
        mock_agg.map.return_value = mock_agg
        mock_agg.distinct.return_value = mock_agg
        mock_agg.getInfo.return_value = ["2025-06-15"]
        mock_collection.aggregate_array.return_value = mock_agg

        mock_composite = MagicMock()
        mock_composite.clip.return_value = mock_composite
        mock_masked.mosaic.return_value = mock_composite

        mock_fetcher = MagicMock()
        mock_fetcher.url_format = "https://tiles/{z}/{x}/{y}"
        mock_composite.getMapId.return_value = {"tile_fetcher": mock_fetcher}

        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_sentinel2_image(date(2025, 6, 15), visualization="rgb")

        assert result["tile_url"] == "https://tiles/{z}/{x}/{y}"
        assert result["sensor"] == "Sentinel-2"
        assert result["visualization"] == "rgb"

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sentinel2_image_ndwi_index(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 2
        mock_masked = MagicMock()
        mock_collection.map.return_value = mock_masked
        mock_agg = MagicMock()
        mock_agg.map.return_value = mock_agg
        mock_agg.distinct.return_value = mock_agg
        mock_agg.getInfo.return_value = ["2025-06-15"]
        mock_collection.aggregate_array.return_value = mock_agg

        mock_composite = MagicMock()
        mock_composite.clip.return_value = mock_composite
        mock_masked.mosaic.return_value = mock_composite

        mock_index = MagicMock()
        mock_index.rename.return_value = mock_index
        mock_composite.normalizedDifference.return_value = mock_index

        mock_fetcher = MagicMock()
        mock_fetcher.url_format = "https://tiles/{z}/{x}/{y}"
        mock_index.getMapId.return_value = {"tile_fetcher": mock_fetcher}

        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_sentinel2_image(date(2025, 6, 15), visualization="ndwi")

        assert result["visualization"] == "ndwi"

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sentinel2_image_toa_old_date(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 1
        mock_agg = MagicMock()
        mock_agg.map.return_value = mock_agg
        mock_agg.distinct.return_value = mock_agg
        mock_agg.getInfo.return_value = ["2018-06-15"]
        mock_collection.aggregate_array.return_value = mock_agg

        mock_composite = MagicMock()
        mock_composite.clip.return_value = mock_composite
        mock_collection.mosaic.return_value = mock_composite

        mock_fetcher = MagicMock()
        mock_fetcher.url_format = "https://tiles/{z}/{x}/{y}"
        mock_composite.getMapId.return_value = {"tile_fetcher": mock_fetcher}
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_sentinel2_image(date(2018, 6, 15))

        assert result["collection"] == "COPERNICUS/S2_HARMONIZED"

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sentinel1_image_no_images(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 0
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_sentinel1_image(date(2025, 6, 15))

        assert "error" in result

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sentinel1_image_vv(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 2
        mock_collection.select.return_value = mock_collection
        mock_agg = MagicMock()
        mock_agg.map.return_value = mock_agg
        mock_agg.distinct.return_value = mock_agg
        mock_agg.getInfo.return_value = ["2025-06-10"]
        mock_collection.aggregate_array.return_value = mock_agg

        mock_mosaic = MagicMock()
        mock_mosaic.clip.return_value = mock_mosaic
        mock_collection.select.return_value.mosaic.return_value = mock_mosaic

        mock_fetcher = MagicMock()
        mock_fetcher.url_format = "https://tiles/{z}/{x}/{y}"
        mock_mosaic.getMapId.return_value = {"tile_fetcher": mock_fetcher}
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_sentinel1_image(date(2025, 6, 15), visualization="vv")

        assert result["sensor"] == "Sentinel-1"

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sentinel1_image_vv_flood(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 1
        mock_collection.select.return_value = mock_collection
        mock_agg = MagicMock()
        mock_agg.map.return_value = mock_agg
        mock_agg.distinct.return_value = mock_agg
        mock_agg.getInfo.return_value = ["2025-06-10"]
        mock_collection.aggregate_array.return_value = mock_agg

        mock_mosaic = MagicMock()
        mock_mosaic.clip.return_value = mock_mosaic
        mock_flood = MagicMock()
        mock_flood.selfMask.return_value = mock_flood
        mock_mosaic.lt.return_value = mock_flood
        mock_collection.select.return_value.mosaic.return_value = mock_mosaic

        mock_fetcher = MagicMock()
        mock_fetcher.url_format = "https://tiles/{z}/{x}/{y}"
        mock_flood.getMapId.return_value = {"tile_fetcher": mock_fetcher}
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_sentinel1_image(date(2025, 6, 15), visualization="vv_flood")

        assert "Deteccion de agua" in result["visualization_description"]

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_flood_comparison(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        # Mock get_sentinel2_image to return simple results
        explorer.get_sentinel2_image = MagicMock(
            return_value={"tile_url": "https://tiles", "sensor": "Sentinel-2"}
        )

        result = explorer.get_flood_comparison(
            flood_date=date(2025, 6, 15),
            normal_date=date(2025, 1, 15),
        )

        assert result["flood_date"] == "2025-06-15"
        assert result["normal_date"] == "2025-01-15"
        assert "flood_detection" in result
        assert "flood_rgb" in result
        assert "normal_rgb" in result

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sar_time_series_no_images(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.select.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 0
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_sar_time_series(date(2025, 1, 1), date(2025, 6, 1))

        assert result["image_count"] == 0
        assert "warning" in result

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_sar_time_series_with_data(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_collection.select.return_value = mock_collection
        mock_collection.size.return_value.getInfo.return_value = 3

        mock_features = MagicMock()
        mock_features.getInfo.return_value = {
            "features": [
                {"properties": {"date": "2025-01-10", "vv_mean": -12.5}},
                {"properties": {"date": "2025-02-15", "vv_mean": -14.2}},
                {"properties": {"date": "2025-03-20", "vv_mean": None}},
            ]
        }
        mock_collection.map.return_value = mock_features
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_sar_time_series(date(2025, 1, 1), date(2025, 6, 1))

        assert result["image_count"] == 2  # None vv_mean is excluded
        assert len(result["dates"]) == 2
        assert len(result["vv_mean"]) == 2

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_available_visualizations(self, mock_settings, mock_ee, mock_init):
        explorer = self._make_explorer(mock_ee, mock_settings)

        result = explorer.get_available_visualizations()

        assert isinstance(result, list)
        assert len(result) == 7  # 7 presets
        ids = [v["id"] for v in result]
        assert "rgb" in ids
        assert "ndvi" in ids
        assert "inundacion" in ids

    @patch("app.domains.geo.gee_service._ensure_initialized")
    @patch("app.domains.geo.gee_service.ee")
    @patch("app.domains.geo.gee_service.settings")
    def test_get_available_dates_pre_2019(self, mock_settings, mock_ee, mock_init):
        """Pre-2019 should use TOA collection."""
        explorer = self._make_explorer(mock_ee, mock_settings)

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value = mock_collection
        mock_collection.filter.return_value = mock_collection
        mock_agg = MagicMock()
        mock_agg.map.return_value = mock_agg
        mock_agg.distinct.return_value = mock_agg
        mock_agg.sort.return_value = mock_agg
        mock_agg.getInfo.return_value = ["2018-06-01"]
        mock_collection.aggregate_array.return_value = mock_agg
        mock_ee.ImageCollection.return_value = mock_collection

        result = explorer.get_available_dates(2018, 6, sensor="sentinel2")

        assert result["year"] == 2018
        # Verify ImageCollection was called with TOA collection
        mock_ee.ImageCollection.assert_called_with("COPERNICUS/S2_HARMONIZED")
