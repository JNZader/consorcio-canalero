"""Comprehensive tests for geo/router.py — all endpoint groups.

Uses direct function calls with mocked dependencies instead of TestClient
to avoid bootstrapping the full app (DB, Redis, middleware).

Coverage target: ~40+ tests covering jobs, layers, basins, GEE, STAC,
water detection, flood prediction, hydrology, temporal, and flood risk.
"""

import json
import uuid
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from fastapi import HTTPException, UploadFile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db():
    db = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.flush = MagicMock()
    return db


@pytest.fixture()
def mock_repo():
    return MagicMock()


@pytest.fixture()
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.nombre = "Admin"
    user.apellido = "Test"
    user.email = "admin@test.com"
    return user


# ---------------------------------------------------------------------------
# HELPER: _validate_geojson_filename
# ---------------------------------------------------------------------------


class TestValidateGeojsonFilename:
    def _import(self):
        from app.domains.geo.router import _validate_geojson_filename
        return _validate_geojson_filename

    def test_accepts_geojson_extension(self):
        fn = self._import()
        fn("test.geojson")  # no exception

    def test_accepts_json_extension(self):
        fn = self._import()
        fn("test.json")  # no exception

    def test_rejects_none_filename(self):
        fn = self._import()
        with pytest.raises(HTTPException) as exc_info:
            fn(None)
        assert exc_info.value.status_code == 400

    def test_rejects_empty_filename(self):
        fn = self._import()
        with pytest.raises(HTTPException) as exc_info:
            fn("")
        assert exc_info.value.status_code == 400

    def test_rejects_invalid_extension(self):
        fn = self._import()
        with pytest.raises(HTTPException) as exc_info:
            fn("test.csv")
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# HELPER: _read_geojson_upload
# ---------------------------------------------------------------------------


class TestReadGeojsonUpload:
    def _import(self):
        from app.domains.geo.router import _read_geojson_upload
        return _read_geojson_upload

    def test_accepts_valid_feature_collection(self):
        fn = self._import()
        payload = {"type": "FeatureCollection", "features": []}
        result = fn(json.dumps(payload).encode("utf-8"))
        assert result["type"] == "FeatureCollection"

    def test_rejects_empty_content(self):
        fn = self._import()
        with pytest.raises(HTTPException) as exc_info:
            fn(b"")
        assert exc_info.value.status_code == 400

    def test_rejects_invalid_json(self):
        fn = self._import()
        with pytest.raises(HTTPException) as exc_info:
            fn(b"not-json-data")
        assert exc_info.value.status_code == 400

    def test_rejects_non_feature_collection(self):
        fn = self._import()
        payload = {"type": "Feature", "geometry": {}}
        with pytest.raises(HTTPException) as exc_info:
            fn(json.dumps(payload).encode("utf-8"))
        assert exc_info.value.status_code == 400

    def test_rejects_missing_features_list(self):
        fn = self._import()
        payload = {"type": "FeatureCollection", "features": "not-a-list"}
        with pytest.raises(HTTPException) as exc_info:
            fn(json.dumps(payload).encode("utf-8"))
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# HELPER: _extract_source_properties
# ---------------------------------------------------------------------------


class TestExtractSourceProperties:
    def _import(self):
        from app.domains.geo.router import _extract_source_properties
        return _extract_source_properties

    def test_returns_source_properties_when_present(self):
        fn = self._import()
        props = {"source_properties": {"zone_id": "z1", "name": "Zone 1"}}
        result = fn(props)
        assert result == {"zone_id": "z1", "name": "Zone 1"}

    def test_returns_props_when_no_source_properties(self):
        fn = self._import()
        props = {"zone_id": "z1", "name": "Zone 1"}
        result = fn(props)
        assert result == props

    def test_returns_empty_for_none(self):
        fn = self._import()
        assert fn(None) == {}

    def test_returns_empty_for_non_dict(self):
        fn = self._import()
        assert fn("string") == {}


# ---------------------------------------------------------------------------
# HELPER: _get_user_display_name
# ---------------------------------------------------------------------------


class TestGetUserDisplayName:
    def _import(self):
        from app.domains.geo.router import _get_user_display_name
        return _get_user_display_name

    def test_returns_none_for_none_id(self, mock_db):
        fn = self._import()
        assert fn(mock_db, None) is None

    def test_returns_none_if_user_not_found(self, mock_db):
        fn = self._import()
        mock_db.get.return_value = None
        assert fn(mock_db, uuid.uuid4()) is None

    def test_returns_full_name(self, mock_db):
        fn = self._import()
        user = MagicMock()
        user.nombre = "Juan"
        user.apellido = "Perez"
        user.email = "juan@test.com"
        mock_db.get.return_value = user
        assert fn(mock_db, uuid.uuid4()) == "Juan Perez"

    def test_returns_email_when_no_name(self, mock_db):
        fn = self._import()
        user = MagicMock()
        user.nombre = ""
        user.apellido = ""
        user.email = "juan@test.com"
        mock_db.get.return_value = user
        assert fn(mock_db, uuid.uuid4()) == "juan@test.com"


# ---------------------------------------------------------------------------
# JOBS ENDPOINTS
# ---------------------------------------------------------------------------


class TestSubmitGeoJob:
    @patch("app.domains.geo.router.dispatch_job")
    def test_submit_creates_job(self, mock_dispatch, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import submit_geo_job
        from app.domains.geo.schemas import GeoJobCreate

        mock_job = MagicMock()
        mock_job.id = uuid.uuid4()
        mock_dispatch.return_value = mock_job

        payload = GeoJobCreate(tipo="dem_pipeline", parametros={"area_id": "test"})
        result = submit_geo_job(payload, mock_db, mock_repo, _user=mock_user)
        assert result == mock_job
        mock_dispatch.assert_called_once()


class TestListGeoJobs:
    def test_list_returns_paginated(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import list_geo_jobs

        mock_repo.get_jobs.return_value = ([], 0)
        result = list_geo_jobs(
            page=1, limit=20, estado=None, tipo=None,
            db=mock_db, repo=mock_repo, _user=mock_user,
        )
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["items"] == []


class TestGetGeoJob:
    def test_returns_job_when_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_geo_job

        job_id = uuid.uuid4()
        mock_job = MagicMock()
        mock_repo.get_job_by_id.return_value = mock_job
        result = get_geo_job(job_id, mock_db, mock_repo, _user=mock_user)
        assert result == mock_job

    def test_raises_404_when_not_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_geo_job

        mock_repo.get_job_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            get_geo_job(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# LAYERS ENDPOINTS
# ---------------------------------------------------------------------------


class TestListGeoLayers:
    def test_list_returns_paginated(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import list_geo_layers

        mock_repo.get_layers.return_value = ([], 0)
        result = list_geo_layers(
            page=1, limit=20, tipo=None, fuente=None, area_id=None,
            db=mock_db, repo=mock_repo, _user=mock_user,
        )
        assert result["total"] == 0
        assert result["items"] == []


class TestListPublicGeoLayers:
    def test_returns_empty_for_disallowed_type(self, mock_db, mock_repo):
        from app.domains.geo.router import list_public_geo_layers

        result = list_public_geo_layers(
            page=1, limit=20, tipo="secret_type", fuente=None, area_id=None,
            db=mock_db, repo=mock_repo,
        )
        assert result["items"] == []
        assert result["total"] == 0

    def test_filters_to_allowed_types(self, mock_db, mock_repo):
        from app.domains.geo.router import list_public_geo_layers

        mock_layer = MagicMock()
        mock_layer.tipo = "dem_raw"
        mock_layer.id = uuid.uuid4()
        mock_layer.nombre = "DEM"
        mock_layer.fuente = "gee"
        mock_layer.formato = "geotiff"
        mock_layer.area_id = None
        mock_layer.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_repo.get_layers.return_value = ([mock_layer], 1)

        result = list_public_geo_layers(
            page=1, limit=20, tipo="dem_raw", fuente=None, area_id=None,
            db=mock_db, repo=mock_repo,
        )
        assert len(result["items"]) == 1


class TestGetGeoLayer:
    def test_returns_layer_when_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_geo_layer

        layer_id = uuid.uuid4()
        mock_layer = MagicMock()
        mock_repo.get_layer_by_id.return_value = mock_layer
        result = get_geo_layer(layer_id, mock_db, mock_repo, _user=mock_user)
        assert result == mock_layer

    def test_raises_404_when_not_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_geo_layer

        mock_repo.get_layer_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            get_geo_layer(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 404


class TestGetGeoLayerFile:
    def test_raises_404_when_layer_not_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_geo_layer_file

        mock_repo.get_layer_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            get_geo_layer_file(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 404

    def test_raises_404_when_file_missing(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_geo_layer_file

        mock_layer = MagicMock()
        mock_layer.archivo_path = "/nonexistent/path/file.tif"
        mock_repo.get_layer_by_id.return_value = mock_layer

        with pytest.raises(HTTPException) as exc_info:
            get_geo_layer_file(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# DEM PIPELINE
# ---------------------------------------------------------------------------


class TestTriggerDemPipeline:
    @patch("app.domains.geo.router.dispatch_job")
    def test_trigger_returns_response(self, mock_dispatch, mock_db, mock_user):
        from app.domains.geo.router import trigger_dem_pipeline
        from app.domains.geo.schemas import DemPipelineRequest

        mock_job = MagicMock()
        mock_job.id = uuid.uuid4()
        mock_job.tipo = "dem_full_pipeline"
        mock_job.estado = "pendiente"
        mock_dispatch.return_value = mock_job

        result = trigger_dem_pipeline(DemPipelineRequest(), mock_db, _user=mock_user)
        assert result.job_id == mock_job.id


# ---------------------------------------------------------------------------
# TILE PROXY
# ---------------------------------------------------------------------------


class TestProxyTile:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._get_tile_client")
    @patch("app.config.settings")
    async def test_returns_204_on_connect_error(self, mock_settings, mock_get_client):
        from app.domains.geo.router import proxy_tile
        import httpx

        mock_settings.geo_worker_tile_url = "http://geo-worker:8001"
        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("fail")
        mock_get_client.return_value = client

        result = await proxy_tile(uuid.uuid4(), 1, 1, 1)
        assert result.status_code == 204

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._get_tile_client")
    @patch("app.config.settings")
    async def test_returns_204_on_upstream_error(self, mock_settings, mock_get_client):
        from app.domains.geo.router import proxy_tile

        mock_settings.geo_worker_tile_url = "http://geo-worker:8001"
        client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        client.get.return_value = mock_response
        mock_get_client.return_value = client

        result = await proxy_tile(uuid.uuid4(), 1, 1, 1)
        assert result.status_code == 204

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._get_tile_client")
    @patch("app.config.settings")
    async def test_returns_tile_on_success(self, mock_settings, mock_get_client):
        from app.domains.geo.router import proxy_tile

        mock_settings.geo_worker_tile_url = "http://geo-worker:8001"
        client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"PNG_DATA"
        client.get.return_value = mock_response
        mock_get_client.return_value = client

        result = await proxy_tile(uuid.uuid4(), 1, 1, 1)
        assert result.media_type == "image/png"


# ---------------------------------------------------------------------------
# BASINS
# ---------------------------------------------------------------------------


class TestGetBasins:
    @patch("app.domains.geo.router.IntelligenceRepository")
    def test_returns_feature_collection_unadjusted(self, MockIntelRepo, mock_db):
        from app.domains.geo.router import get_basins

        mock_repo = MagicMock()
        mock_repo.get_zonas_as_geojson.return_value = {
            "type": "FeatureCollection",
            "features": [],
            "metadata": {},
        }
        MockIntelRepo.return_value = mock_repo

        result = get_basins(
            bbox=None, tolerance=0.001, limit=500, cuenca=None,
            adjusted=False, db=mock_db,
        )
        assert result["type"] == "FeatureCollection"

    @patch("app.domains.geo.router.IntelligenceRepository")
    def test_invalid_bbox_raises_422(self, MockIntelRepo, mock_db):
        from app.domains.geo.router import get_basins

        with pytest.raises(HTTPException) as exc_info:
            get_basins(
                bbox="invalid,bbox", tolerance=0.001, limit=500,
                cuenca=None, adjusted=False, db=mock_db,
            )
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# APPROVED ZONES
# ---------------------------------------------------------------------------


class TestApprovedZones:
    def test_get_current_returns_none_when_empty(self, mock_db, mock_repo):
        from app.domains.geo.router import get_current_approved_basin_zones

        mock_repo.get_active_approved_zoning.return_value = None
        result = get_current_approved_basin_zones(
            cuenca=None, db=mock_db, repo=mock_repo,
        )
        assert result is None

    def test_delete_current_calls_clear(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import clear_current_approved_basin_zones

        mock_repo.clear_active_approved_zoning.return_value = 1
        result = clear_current_approved_basin_zones(
            cuenca=None, db=mock_db, repo=mock_repo, _user=mock_user,
        )
        assert result["deleted"] == 1
        mock_db.commit.assert_called_once()

    def test_history_returns_list(self, mock_db, mock_repo):
        from app.domains.geo.router import list_approved_basin_zone_history

        mock_repo.list_approved_zonings.return_value = []
        result = list_approved_basin_zone_history(
            cuenca=None, limit=20, db=mock_db, repo=mock_repo,
        )
        assert result == []

    def test_restore_raises_404_when_not_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import restore_approved_basin_zone_version

        mock_repo.get_approved_zoning_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            restore_approved_basin_zone_version(
                zoning_id=uuid.uuid4(), db=mock_db, repo=mock_repo, user=mock_user,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# STAC CATALOG
# ---------------------------------------------------------------------------


class TestStacCatalog:
    def test_stac_root_returns_catalog(self):
        from app.domains.geo.router import stac_root

        request = MagicMock()
        request.base_url = "http://localhost:8000/"

        result = stac_root(request)
        assert result["type"] == "Catalog"
        assert result["stac_version"] == "1.0.0"
        assert len(result["links"]) == 3

    @patch("app.domains.geo.router.layer_to_stac_item", create=True)
    def test_stac_item_raises_404_when_not_found(self, mock_fn, mock_db):
        from app.domains.geo.router import stac_item
        from app.core.exceptions import NotFoundError

        mock_db.query.return_value.filter.return_value.first.return_value = None
        request = MagicMock()
        request.base_url = "http://localhost:8000/"

        with pytest.raises(NotFoundError):
            stac_item(uuid.uuid4(), request, mock_db)


# ---------------------------------------------------------------------------
# GEE ROUTER — list_gee_layers
# ---------------------------------------------------------------------------


class TestGeeRouter:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._lazy_gee_service")
    async def test_list_gee_layers(self, mock_lazy):
        from app.domains.geo.router import list_gee_layers

        mock_lazy.return_value = {
            "get_available_layers": lambda: [{"name": "test"}],
        }
        result = await list_gee_layers()
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_get_available_visualizations(self):
        from app.domains.geo.router import get_available_visualizations

        result = await get_available_visualizations()
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_get_historic_floods(self):
        from app.domains.geo.router import get_historic_floods

        result = await get_historic_floods()
        body = json.loads(result.body)
        assert "floods" in body
        assert body["total"] >= 1

    @pytest.mark.asyncio
    async def test_get_historic_flood_tiles_not_found(self):
        from app.domains.geo.router import get_historic_flood_tiles
        from app.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await get_historic_flood_tiles("nonexistent_flood_id")


# ---------------------------------------------------------------------------
# GEE ANALYSIS CRUD
# ---------------------------------------------------------------------------


class TestGeeAnalysisCrud:
    def test_list_gee_analyses(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import list_gee_analyses

        mock_repo.get_analisis_list.return_value = ([], 0)
        result = list_gee_analyses(
            page=1, limit=20, tipo=None, estado=None,
            db=mock_db, repo=mock_repo, _user=mock_user,
        )
        assert result["total"] == 0

    def test_get_gee_analysis_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_gee_analysis

        mock_analisis = MagicMock()
        mock_repo.get_analisis_by_id.return_value = mock_analisis
        result = get_gee_analysis(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert result == mock_analisis

    def test_get_gee_analysis_not_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_gee_analysis

        mock_repo.get_analisis_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            get_gee_analysis(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# ML MODEL INFO
# ---------------------------------------------------------------------------


class TestMlModelInfo:
    @patch("app.domains.geo.ml.water_segmentation.UNetStrategy")
    @patch("app.domains.geo.ml.flood_prediction.FloodModel")
    def test_returns_model_info(self, MockFloodModel, MockUNet):
        from app.domains.geo.router import get_ml_model_info

        mock_model = MagicMock()
        mock_model.version = "default-v0"
        mock_model.weights = {}
        mock_model.bias = 0.0
        MockFloodModel.load.return_value = mock_model

        mock_unet = MagicMock()
        mock_unet.model_available = False
        mock_unet.MODEL_DIR = Path("/tmp")
        mock_unet.MODEL_FILE = "unet.pth"
        MockUNet.return_value = mock_unet

        result = get_ml_model_info()
        assert "flood_prediction" in result
        assert "water_segmentation" in result


# ---------------------------------------------------------------------------
# HISTORIC FLOODS DATA
# ---------------------------------------------------------------------------


class TestHistoricFloodsData:
    def test_historic_floods_list_is_not_empty(self):
        from app.domains.geo.router import HISTORIC_FLOODS

        assert len(HISTORIC_FLOODS) > 0
        for flood in HISTORIC_FLOODS:
            assert "id" in flood
            assert "date" in flood
            assert "name" in flood


# ---------------------------------------------------------------------------
# SCHEMAS / REQUEST MODELS
# ---------------------------------------------------------------------------


class TestRequestModels:
    def test_water_detection_request_validation(self):
        from app.domains.geo.router import WaterDetectionRequest

        req = WaterDetectionRequest(
            zona_id=uuid.uuid4(),
            target_date="2025-06-15",
            days_window=15,
            cloud_cover_max=20,
        )
        assert req.days_window == 15

    def test_water_multi_date_request_validation(self):
        from app.domains.geo.router import WaterMultiDateRequest

        req = WaterMultiDateRequest(
            zona_id=uuid.uuid4(),
            dates=["2025-06-01", "2025-06-15"],
            cloud_cover_max=20,
        )
        assert len(req.dates) == 2

    def test_zonal_stats_request_defaults(self):
        from app.domains.geo.router import ZonalStatsRequest

        req = ZonalStatsRequest(layer_tipo="slope")
        assert req.zona_source == "zonas_operativas"
        assert req.area_id is None

    def test_ndwi_trend_request_validation(self):
        from app.domains.geo.router import NdwiTrendRequest

        req = NdwiTrendRequest(
            zona_id=uuid.uuid4(),
            start_date="2025-01-01",
            end_date="2025-06-01",
            cloud_cover_max=30,
        )
        assert req.cloud_cover_max == 30

    def test_raster_compare_request_defaults(self):
        from app.domains.geo.router import RasterCompareRequest

        req = RasterCompareRequest(layer_tipo="twi")
        assert req.zona_id is None

    def test_approved_zones_save_request(self):
        from app.domains.geo.router import ApprovedZonesSaveRequest

        req = ApprovedZonesSaveRequest(
            featureCollection={"type": "FeatureCollection", "features": []},
            assignments={},
            zone_names={},
        )
        assert req.nombre == "Zonificación Consorcio aprobada"

    def test_approved_zones_build_request(self):
        from app.domains.geo.router import ApprovedZonesBuildRequest

        req = ApprovedZonesBuildRequest()
        assert req.assignments == {}
        assert req.cuenca is None

    def test_import_canals_request(self):
        from app.domains.geo.router import ImportCanalsRequest

        req = ImportCanalsRequest(geojson_paths=["/path/to/file.geojson"])
        assert req.rebuild_topology is True

    def test_geo_json_import_response(self):
        from app.domains.geo.router import GeoJsonImportResponse

        resp = GeoJsonImportResponse(
            importedCount=5,
            replacedCount=3,
            featureType="zonas_operativas",
        )
        assert resp.imported_count == 5

    def test_geo_bundle_import_response(self):
        from app.domains.geo.router import GeoBundleImportResponse

        resp = GeoBundleImportResponse(
            vectorsImported={"zonas": 10},
            layersImported=3,
            bundleName="test.zip",
        )
        assert resp.layers_imported == 3

    def test_approved_zones_response(self):
        from app.domains.geo.router import ApprovedZonesResponse

        resp = ApprovedZonesResponse(
            id="abc-123",
            nombre="Test",
            version=1,
            featureCollection={"type": "FeatureCollection", "features": []},
            approvedAt="2025-01-01T00:00:00",
        )
        assert resp.version == 1
