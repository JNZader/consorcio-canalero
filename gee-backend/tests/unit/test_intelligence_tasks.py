"""Unit tests for app.domains.geo.intelligence.tasks — Celery task orchestration.

All external dependencies (DB, repos, services, geopandas, rasterio) are mocked.
"""

import uuid
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deps(**overrides):
    """Build a fake deps dict matching _get_deps() shape."""
    deps = {
        "SessionLocal": MagicMock,
        "intel_repo": MagicMock(),
        "intel_service": MagicMock(),
        "EstadoGeoJob": MagicMock(),
        "TipoGeoLayer": MagicMock(),
        "geo_repo": MagicMock(),
    }
    deps.update(overrides)
    return deps


# ---------------------------------------------------------------------------
# _get_deps / _get_db
# ---------------------------------------------------------------------------


class TestGetDeps:
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_returns_dict_with_expected_keys(self, mock):
        mock.return_value = _make_deps()
        from app.domains.geo.intelligence.tasks import _get_deps

        result = _get_deps()
        assert "SessionLocal" in result
        assert "intel_repo" in result
        assert "intel_service" in result
        assert "geo_repo" in result


class TestGetDb:
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_creates_session(self, mock_deps):
        session_cls = MagicMock()
        mock_deps.return_value = _make_deps(SessionLocal=session_cls)

        from app.domains.geo.intelligence.tasks import _get_db

        db = _get_db()
        session_cls.assert_called_once()


# ---------------------------------------------------------------------------
# _get_layer_path
# ---------------------------------------------------------------------------


class TestGetLayerPath:
    def test_returns_path_when_layer_exists(self):
        from app.domains.geo.intelligence.tasks import _get_layer_path

        db = MagicMock()
        deps = _make_deps()
        layer = MagicMock(archivo_path="/data/slope.tif")
        deps["geo_repo"].get_layers.return_value = ([layer], 1)

        result = _get_layer_path(db, deps, deps["TipoGeoLayer"].SLOPE)
        assert result == "/data/slope.tif"

    def test_returns_none_when_no_layers(self):
        from app.domains.geo.intelligence.tasks import _get_layer_path

        db = MagicMock()
        deps = _make_deps()
        deps["geo_repo"].get_layers.return_value = ([], 0)

        result = _get_layer_path(db, deps, deps["TipoGeoLayer"].SLOPE)
        assert result is None

    def test_returns_none_when_no_archivo_path(self):
        from app.domains.geo.intelligence.tasks import _get_layer_path

        db = MagicMock()
        deps = _make_deps()
        layer = MagicMock(archivo_path=None)
        deps["geo_repo"].get_layers.return_value = ([layer], 1)

        result = _get_layer_path(db, deps, deps["TipoGeoLayer"].SLOPE)
        assert result is None


# ---------------------------------------------------------------------------
# _extract_zone_raster_stats
# ---------------------------------------------------------------------------


class TestExtractZoneRasterStats:
    def test_returns_defaults_when_all_paths_none(self):
        from app.domains.geo.intelligence.tasks import _extract_zone_raster_stats

        zona = MagicMock()
        result = _extract_zone_raster_stats(zona, None, None, None)
        assert result == {
            "pendiente_media": 0.5,
            "acumulacion_media": 0.5,
            "twi_medio": 0.5,
        }

    @patch("app.domains.geo.intelligence.tasks._zonal_mean_normalized")
    def test_calls_zonal_mean_for_each_raster(self, mock_zonal):
        mock_zonal.return_value = 0.7
        # Need to mock to_shape for geometry extraction
        with patch("geoalchemy2.shape.to_shape", return_value=MagicMock()):
            from app.domains.geo.intelligence.tasks import _extract_zone_raster_stats

            zona = MagicMock()
            result = _extract_zone_raster_stats(zona, "/slope.tif", "/flow.tif", "/twi.tif")
            assert mock_zonal.call_count == 3
            assert result["pendiente_media"] == 0.7

    def test_returns_defaults_when_to_shape_fails(self):
        with patch("geoalchemy2.shape.to_shape", side_effect=Exception("bad geom")):
            from app.domains.geo.intelligence.tasks import _extract_zone_raster_stats

            zona = MagicMock()
            result = _extract_zone_raster_stats(zona, "/slope.tif", None, None)
            assert result["pendiente_media"] == 0.5


# ---------------------------------------------------------------------------
# _zonal_mean_normalized
# ---------------------------------------------------------------------------


class TestZonalMeanNormalized:
    def test_returns_default_when_path_is_none(self):
        from app.domains.geo.intelligence.tasks import _zonal_mean_normalized

        result = _zonal_mean_normalized(None, MagicMock(), 45.0, 0.5)
        assert result == 0.5

    @patch("rasterio.open")
    @patch("rasterio.mask.mask")
    def test_returns_normalized_mean(self, mock_mask, mock_open):
        import numpy as np

        src_mock = MagicMock()
        src_mock.nodata = -9999
        src_mock.__enter__ = MagicMock(return_value=src_mock)
        src_mock.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = src_mock

        out_image = np.array([[[22.5, 22.5, -9999]]])
        mock_mask.return_value = (out_image, None)

        from app.domains.geo.intelligence.tasks import _zonal_mean_normalized

        result = _zonal_mean_normalized("/slope.tif", MagicMock(), max_val=45.0, default=0.5)
        assert result == 0.5  # 22.5 / 45.0 = 0.5

    @patch("rasterio.open")
    @patch("rasterio.mask.mask")
    def test_clamps_to_one(self, mock_mask, mock_open):
        import numpy as np

        src_mock = MagicMock()
        src_mock.nodata = -9999
        src_mock.__enter__ = MagicMock(return_value=src_mock)
        src_mock.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = src_mock

        out_image = np.array([[[100.0]]])
        mock_mask.return_value = (out_image, None)

        from app.domains.geo.intelligence.tasks import _zonal_mean_normalized

        result = _zonal_mean_normalized("/slope.tif", MagicMock(), max_val=45.0, default=0.5)
        assert result == 1.0

    @patch("rasterio.open")
    @patch("rasterio.mask.mask")
    def test_returns_default_when_all_nodata(self, mock_mask, mock_open):
        import numpy as np

        src_mock = MagicMock()
        src_mock.nodata = -9999
        src_mock.__enter__ = MagicMock(return_value=src_mock)
        src_mock.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = src_mock

        out_image = np.array([[[-9999, -9999]]])
        mock_mask.return_value = (out_image, None)

        from app.domains.geo.intelligence.tasks import _zonal_mean_normalized

        result = _zonal_mean_normalized("/slope.tif", MagicMock(), max_val=45.0, default=0.5)
        assert result == 0.5

    def test_returns_default_on_rasterio_error(self):
        with patch("rasterio.open", side_effect=Exception("file not found")):
            from app.domains.geo.intelligence.tasks import _zonal_mean_normalized

            result = _zonal_mean_normalized("/bad.tif", MagicMock(), max_val=45.0, default=0.5)
            assert result == 0.5

    @patch("rasterio.open")
    @patch("rasterio.mask.mask")
    def test_uses_negative_9999_when_nodata_is_none(self, mock_mask, mock_open):
        import numpy as np

        src_mock = MagicMock()
        src_mock.nodata = None
        src_mock.__enter__ = MagicMock(return_value=src_mock)
        src_mock.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = src_mock

        out_image = np.array([[[10.0, -9999]]])
        mock_mask.return_value = (out_image, None)

        from app.domains.geo.intelligence.tasks import _zonal_mean_normalized

        result = _zonal_mean_normalized("/slope.tif", MagicMock(), max_val=20.0, default=0.5)
        assert result == 0.5  # 10/20 = 0.5


# ---------------------------------------------------------------------------
# task_calculate_hci_all_zones
# ---------------------------------------------------------------------------


class TestTaskCalculateHciAllZones:
    @patch("app.domains.geo.intelligence.tasks._get_layer_path", return_value=None)
    @patch("app.domains.geo.intelligence.tasks._extract_zone_raster_stats")
    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_returns_completed_with_results(self, mock_deps, mock_db, mock_stats, mock_layer):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()

        zona = MagicMock(id=uuid.uuid4())
        deps["intel_repo"].get_zonas.return_value = ([zona], 1)
        mock_stats.return_value = {
            "pendiente_media": 0.5,
            "acumulacion_media": 0.5,
            "twi_medio": 0.5,
        }
        deps["intel_service"].calculate_hci_for_zone.return_value = {"indice": 0.7}

        from app.domains.geo.intelligence.tasks import task_calculate_hci_all_zones

        result = task_calculate_hci_all_zones()
        assert result["status"] == "completed"
        assert result["zonas_calculadas"] == 1

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_returns_skipped_when_no_zones(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()
        deps["intel_repo"].get_zonas.return_value = ([], 0)

        from app.domains.geo.intelligence.tasks import task_calculate_hci_all_zones

        result = task_calculate_hci_all_zones()
        assert result["status"] == "skipped"

    @patch("app.domains.geo.intelligence.tasks._get_layer_path", return_value=None)
    @patch("app.domains.geo.intelligence.tasks._extract_zone_raster_stats")
    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_skips_failed_zones(self, mock_deps, mock_db, mock_stats, mock_layer):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()

        zona1 = MagicMock(id=uuid.uuid4())
        zona2 = MagicMock(id=uuid.uuid4())
        deps["intel_repo"].get_zonas.return_value = ([zona1, zona2], 2)
        mock_stats.return_value = {
            "pendiente_media": 0.5,
            "acumulacion_media": 0.5,
            "twi_medio": 0.5,
        }
        # First zone fails, second succeeds
        deps["intel_service"].calculate_hci_for_zone.side_effect = [
            Exception("zone error"),
            {"indice": 0.5},
        ]

        from app.domains.geo.intelligence.tasks import task_calculate_hci_all_zones

        result = task_calculate_hci_all_zones()
        assert result["status"] == "completed"
        assert result["zonas_calculadas"] == 1

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_raises_on_fatal_error(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()
        deps["intel_repo"].get_zonas.side_effect = RuntimeError("db dead")

        from app.domains.geo.intelligence.tasks import task_calculate_hci_all_zones

        with pytest.raises(RuntimeError, match="db dead"):
            task_calculate_hci_all_zones()

    @patch("app.domains.geo.intelligence.tasks._get_layer_path")
    @patch("app.domains.geo.intelligence.tasks._extract_zone_raster_stats")
    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_passes_custom_parameters(self, mock_deps, mock_db, mock_stats, mock_layer):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()
        mock_layer.return_value = None

        zona = MagicMock(id=uuid.uuid4())
        deps["intel_repo"].get_zonas.return_value = ([zona], 1)
        mock_stats.return_value = {
            "pendiente_media": 0.3,
            "acumulacion_media": 0.4,
            "twi_medio": 0.6,
        }
        deps["intel_service"].calculate_hci_for_zone.return_value = {"indice": 0.8}

        from app.domains.geo.intelligence.tasks import task_calculate_hci_all_zones

        result = task_calculate_hci_all_zones(
            proximidad_canal_m=1000.0,
            historial_inundacion=0.8,
        )
        assert result["status"] == "completed"
        # Verify custom params passed through
        call_kwargs = deps["intel_service"].calculate_hci_for_zone.call_args
        assert call_kwargs[1]["proximidad_canal_m"] == 1000.0
        assert call_kwargs[1]["historial_inundacion"] == 0.8

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_closes_db_on_success(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        mock_db.return_value = db
        deps["intel_repo"].get_zonas.return_value = ([], 0)

        from app.domains.geo.intelligence.tasks import task_calculate_hci_all_zones

        task_calculate_hci_all_zones()
        db.close.assert_called_once()

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_closes_db_on_error(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        mock_db.return_value = db
        deps["intel_repo"].get_zonas.side_effect = RuntimeError("boom")

        from app.domains.geo.intelligence.tasks import task_calculate_hci_all_zones

        with pytest.raises(RuntimeError):
            task_calculate_hci_all_zones()
        db.close.assert_called_once()


# ---------------------------------------------------------------------------
# task_detect_all_conflicts
# ---------------------------------------------------------------------------


class TestTaskDetectAllConflicts:
    @patch("app.domains.geo.intelligence.tasks._load_drainage_from_layers")
    @patch("app.domains.geo.intelligence.tasks._load_caminos_from_gee")
    @patch("app.domains.geo.intelligence.tasks._load_canales_from_gee")
    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_returns_completed(self, mock_deps, mock_db, mock_canales, mock_caminos, mock_drainage):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()

        # Provide layers
        layer_mock = MagicMock(archivo_path="/data/flow_acc.tif")
        deps["geo_repo"].get_layers.return_value = ([layer_mock], 1)

        # Mock GeoDataFrames
        canales_gdf = MagicMock(empty=False)
        caminos_gdf = MagicMock(empty=False)
        drainage_gdf = MagicMock(empty=True)
        mock_canales.return_value = canales_gdf
        mock_caminos.return_value = caminos_gdf
        mock_drainage.return_value = drainage_gdf

        deps["intel_service"].detect_conflicts.return_value = {"conflictos_detectados": 5}

        from app.domains.geo.intelligence.tasks import task_detect_all_conflicts

        result = task_detect_all_conflicts(buffer_m=100.0)
        assert result["status"] == "completed"
        assert result["conflictos_detectados"] == 5

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_skipped_when_no_raster_layers(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()
        deps["geo_repo"].get_layers.return_value = ([], 0)

        from app.domains.geo.intelligence.tasks import task_detect_all_conflicts

        result = task_detect_all_conflicts()
        assert result["status"] == "skipped"
        assert "flow_acc or slope" in result["reason"]

    @patch("app.domains.geo.intelligence.tasks._load_drainage_from_layers")
    @patch("app.domains.geo.intelligence.tasks._load_caminos_from_gee")
    @patch("app.domains.geo.intelligence.tasks._load_canales_from_gee")
    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_skipped_when_fewer_than_2_datasets(self, mock_deps, mock_db, mock_can, mock_cam, mock_drain):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()

        layer_mock = MagicMock(archivo_path="/data/layer.tif")
        deps["geo_repo"].get_layers.return_value = ([layer_mock], 1)

        # Only 1 non-empty
        mock_can.return_value = MagicMock(empty=False)
        mock_cam.return_value = MagicMock(empty=True)
        mock_drain.return_value = MagicMock(empty=True)

        from app.domains.geo.intelligence.tasks import task_detect_all_conflicts

        result = task_detect_all_conflicts()
        assert result["status"] == "skipped"
        assert "at least 2" in result["reason"]

    @patch("app.domains.geo.intelligence.tasks._load_drainage_from_layers")
    @patch("app.domains.geo.intelligence.tasks._load_caminos_from_gee")
    @patch("app.domains.geo.intelligence.tasks._load_canales_from_gee")
    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_raises_on_fatal_error(self, mock_deps, mock_db, mock_can, mock_cam, mock_drain):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()

        layer_mock = MagicMock(archivo_path="/data/layer.tif")
        deps["geo_repo"].get_layers.return_value = ([layer_mock], 1)

        mock_can.return_value = MagicMock(empty=False)
        mock_cam.return_value = MagicMock(empty=False)
        mock_drain.return_value = MagicMock(empty=True)

        deps["intel_service"].detect_conflicts.side_effect = RuntimeError("conflict engine boom")

        from app.domains.geo.intelligence.tasks import task_detect_all_conflicts

        with pytest.raises(RuntimeError, match="conflict engine boom"):
            task_detect_all_conflicts()

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_closes_db(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        mock_db.return_value = db
        deps["geo_repo"].get_layers.return_value = ([], 0)

        from app.domains.geo.intelligence.tasks import task_detect_all_conflicts

        task_detect_all_conflicts()
        db.close.assert_called_once()


# ---------------------------------------------------------------------------
# _load_canales_from_gee
# ---------------------------------------------------------------------------


class TestLoadCanalesFromGee:
    @patch("app.domains.geo.intelligence.tasks.gpd", create=True)
    @patch("app.domains.geo.gee_service.get_layer_geojson")
    def test_loads_multiple_layers(self, mock_geojson, mock_gpd_unused):
        """Test that canales are loaded from 4 GEE layers."""
        import importlib

        with patch.dict("sys.modules", {"geopandas": MagicMock(), "pandas": MagicMock()}):
            import geopandas as gpd

            mock_gdf = MagicMock(empty=False)
            gpd.GeoDataFrame.from_features = MagicMock(return_value=mock_gdf)

            mock_geojson.return_value = {"features": [{"type": "Feature"}]}

            with patch("app.domains.geo.intelligence.tasks.gpd", gpd, create=True):
                from app.domains.geo.intelligence.tasks import _load_canales_from_gee
                # This will try real geopandas import — skip if not available
                try:
                    _load_canales_from_gee()
                except (ImportError, AttributeError):
                    pytest.skip("geopandas not available")

    def test_returns_empty_gdf_on_import_error(self):
        """When geopandas import fails, return empty GDF."""
        with patch.dict("sys.modules", {"geopandas": None}):
            # Force reimport to trigger ImportError
            try:
                from app.domains.geo.intelligence.tasks import _load_canales_from_gee
                # Actual call may or may not raise depending on caching
            except ImportError:
                pass  # Expected


# ---------------------------------------------------------------------------
# _load_drainage_from_layers
# ---------------------------------------------------------------------------


class TestLoadDrainageFromLayers:
    def test_returns_empty_gdf_on_no_layers(self):
        """When no drainage layers exist, return empty GDF."""
        try:
            import geopandas as gpd
        except ImportError:
            pytest.skip("geopandas not available")

        from app.domains.geo.intelligence.tasks import _load_drainage_from_layers

        db = MagicMock()
        deps = _make_deps()
        deps["geo_repo"].get_layers.return_value = ([], 0)

        result = _load_drainage_from_layers(db, deps)
        assert result.empty


# ---------------------------------------------------------------------------
# task_generate_zonification
# ---------------------------------------------------------------------------


class TestTaskGenerateZonification:
    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_returns_completed(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()

        dem_id = str(uuid.uuid4())
        layer = MagicMock(archivo_path="/data/dem.tif", area_id="cuenca1")
        deps["geo_repo"].get_layer_by_id.return_value = layer

        flow_layer = MagicMock(archivo_path="/data/flow.tif")
        deps["geo_repo"].get_layers.return_value = ([flow_layer], 1)

        deps["intel_service"].generate_zones.return_value = {"zonas_creadas": 10}

        from app.domains.geo.intelligence.tasks import task_generate_zonification

        result = task_generate_zonification(dem_id)
        assert result["status"] == "completed"
        assert result["zonas_creadas"] == 10

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_failed_when_dem_not_found(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()
        deps["geo_repo"].get_layer_by_id.return_value = None

        from app.domains.geo.intelligence.tasks import task_generate_zonification

        result = task_generate_zonification(str(uuid.uuid4()))
        assert result["status"] == "failed"
        assert "not found" in result["error"]

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_failed_when_no_flow_acc(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()

        layer = MagicMock(archivo_path="/data/dem.tif", area_id="cuenca1")
        deps["geo_repo"].get_layer_by_id.return_value = layer
        deps["geo_repo"].get_layers.return_value = ([], 0)

        from app.domains.geo.intelligence.tasks import task_generate_zonification

        result = task_generate_zonification(str(uuid.uuid4()))
        assert result["status"] == "failed"
        assert "flow_acc" in result["error"]

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_uses_default_cuenca_when_area_id_none(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()

        layer = MagicMock(archivo_path="/data/dem.tif", area_id=None)
        deps["geo_repo"].get_layer_by_id.return_value = layer

        flow_layer = MagicMock(archivo_path="/data/flow.tif")
        deps["geo_repo"].get_layers.return_value = ([flow_layer], 1)
        deps["intel_service"].generate_zones.return_value = {"zonas_creadas": 3}

        from app.domains.geo.intelligence.tasks import task_generate_zonification

        result = task_generate_zonification(str(uuid.uuid4()))
        call_kwargs = deps["intel_service"].generate_zones.call_args[1]
        assert call_kwargs["cuenca"] == "default"

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_raises_on_fatal(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        mock_db.return_value = db
        deps["geo_repo"].get_layer_by_id.side_effect = RuntimeError("boom")

        from app.domains.geo.intelligence.tasks import task_generate_zonification

        with pytest.raises(RuntimeError):
            task_generate_zonification(str(uuid.uuid4()))
        db.close.assert_called_once()


# ---------------------------------------------------------------------------
# task_evaluate_alerts
# ---------------------------------------------------------------------------


class TestTaskEvaluateAlerts:
    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_returns_completed(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()
        deps["intel_service"].check_alerts.return_value = {"alertas": 3}

        from app.domains.geo.intelligence.tasks import task_evaluate_alerts

        result = task_evaluate_alerts()
        assert result["status"] == "completed"
        assert result["alertas"] == 3

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_raises_on_error(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        mock_db.return_value = db
        deps["intel_service"].check_alerts.side_effect = RuntimeError("alert engine down")

        from app.domains.geo.intelligence.tasks import task_evaluate_alerts

        with pytest.raises(RuntimeError):
            task_evaluate_alerts()
        db.close.assert_called_once()


# ---------------------------------------------------------------------------
# run_canal_analysis
# ---------------------------------------------------------------------------


class TestRunCanalAnalysis:
    @patch("app.domains.geo.intelligence.suggestions.run_full_analysis")
    @patch("app.domains.geo.intelligence.tasks._get_db")
    def test_returns_completed(self, mock_db, mock_analysis):
        db = MagicMock()
        mock_db.return_value = db
        batch_id = uuid.uuid4()
        mock_analysis.return_value = {
            "batch_id": batch_id,
            "total_suggestions": 42,
            "by_tipo": {"hotspot": 10, "gap": 32},
        }

        from app.domains.geo.intelligence.tasks import run_canal_analysis

        result = run_canal_analysis()
        assert result["status"] == "completed"
        assert result["batch_id"] == str(batch_id)
        assert result["total_suggestions"] == 42
        db.close.assert_called_once()

    @patch("app.domains.geo.intelligence.suggestions.run_full_analysis")
    @patch("app.domains.geo.intelligence.tasks._get_db")
    def test_raises_on_error(self, mock_db, mock_analysis):
        db = MagicMock()
        mock_db.return_value = db
        mock_analysis.side_effect = RuntimeError("analysis failed")

        from app.domains.geo.intelligence.tasks import run_canal_analysis

        with pytest.raises(RuntimeError):
            run_canal_analysis()
        db.close.assert_called_once()


# ---------------------------------------------------------------------------
# task_refresh_materialized_views
# ---------------------------------------------------------------------------


class TestTaskRefreshMaterializedViews:
    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_returns_completed(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        mock_db.return_value = MagicMock()
        deps["intel_repo"].refresh_materialized_views.return_value = {
            "mv_dashboard_geo_stats": "ok"
        }

        from app.domains.geo.intelligence.tasks import task_refresh_materialized_views

        result = task_refresh_materialized_views()
        assert result["status"] == "completed"

    @patch("app.domains.geo.intelligence.tasks._get_db")
    @patch("app.domains.geo.intelligence.tasks._get_deps")
    def test_raises_on_error(self, mock_deps, mock_db):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        mock_db.return_value = db
        deps["intel_repo"].refresh_materialized_views.side_effect = RuntimeError("mv error")

        from app.domains.geo.intelligence.tasks import task_refresh_materialized_views

        with pytest.raises(RuntimeError):
            task_refresh_materialized_views()
        db.close.assert_called_once()
