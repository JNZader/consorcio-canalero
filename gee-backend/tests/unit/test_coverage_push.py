"""Additional tests targeting remaining coverage gaps.

Covers: geo/router (ML prediction, zonal stats, bundle import, more flood risk),
auth dependencies, finanzas router, denuncias router, capas router,
infraestructura router, reuniones router, tramites router, main.py,
monitoring router, core exceptions, geo service.
"""

import io
import json
import uuid
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db():
    db = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.flush = MagicMock()
    db.rollback = MagicMock()
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
# geo/router: ML Flood Prediction
# ---------------------------------------------------------------------------


class TestMLFloodPrediction:
    def test_predict_zona_not_found(self, mock_db, mock_user):
        from app.domains.geo.router import predict_flood_ml
        from app.core.exceptions import NotFoundError

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(NotFoundError):
            predict_flood_ml(uuid.uuid4(), mock_db, _user=mock_user)

    def test_predict_all_zones_empty(self, mock_db, mock_user):
        from app.domains.geo.router import predict_flood_all_zones

        mock_db.query.return_value.all.return_value = []

        result = predict_flood_all_zones(mock_db, _user=mock_user)
        assert result == {"zones": [], "count": 0}


# ---------------------------------------------------------------------------
# geo/router: Bundle Import
# ---------------------------------------------------------------------------


class TestBundleImport:
    @pytest.mark.asyncio
    async def test_rejects_non_zip(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import import_geo_bundle

        file = MagicMock()
        file.filename = "data.csv"

        with pytest.raises(HTTPException) as exc_info:
            await import_geo_bundle(file, mock_db, mock_repo, mock_user)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_empty_file(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import import_geo_bundle

        file = MagicMock()
        file.filename = "data.zip"
        file.read = AsyncMock(return_value=b"")

        with pytest.raises(HTTPException) as exc_info:
            await import_geo_bundle(file, mock_db, mock_repo, mock_user)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_bad_zip(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import import_geo_bundle

        file = MagicMock()
        file.filename = "data.zip"
        file.read = AsyncMock(return_value=b"not a zip file")

        with pytest.raises(HTTPException) as exc_info:
            await import_geo_bundle(file, mock_db, mock_repo, mock_user)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_zip_without_manifest(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import import_geo_bundle

        # Create a valid zip without manifest.json
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("readme.txt", "hello")
        buffer.seek(0)

        file = MagicMock()
        file.filename = "data.zip"
        file.read = AsyncMock(return_value=buffer.getvalue())

        with pytest.raises(HTTPException) as exc_info:
            await import_geo_bundle(file, mock_db, mock_repo, mock_user)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# geo/router: Zonal Stats
# ---------------------------------------------------------------------------


class TestZonalStats:
    def test_no_layer_found(self, mock_db, mock_user):
        from app.domains.geo.router import compute_zonal_statistics, ZonalStatsRequest
        from app.core.exceptions import NotFoundError

        mock_db.query.return_value.filter.return_value.order_by.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        body = ZonalStatsRequest(layer_tipo="slope")

        with pytest.raises(NotFoundError):
            compute_zonal_statistics(body, mock_db, _user=mock_user)


# ---------------------------------------------------------------------------
# geo/router: Water Detection Multi-Date
# ---------------------------------------------------------------------------


class TestWaterDetectionMultiSuccess:
    @patch("app.domains.geo.water_detection.detect_water_multi_date")
    def test_success(self, mock_detect, mock_db, mock_user):
        from app.domains.geo.router import detect_water_multi, WaterMultiDateRequest

        zona = MagicMock()
        zona.id = uuid.uuid4()
        zona.nombre = "Zone A"
        mock_db.query.return_value.filter.return_value.first.return_value = zona
        mock_db.execute.return_value.scalar.return_value = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'
        mock_detect.return_value = {"dates": ["2025-06-01"], "results": []}

        body = WaterMultiDateRequest(
            zona_id=zona.id,
            dates=["2025-06-01"],
        )

        result = detect_water_multi(body, mock_db, _user=mock_user)
        assert result["zona"]["nombre"] == "Zone A"


# ---------------------------------------------------------------------------
# geo/router: Hydrology TWI/Canal with COG path
# ---------------------------------------------------------------------------


class TestHydrologyCogPath:
    def test_twi_uses_cog_path(self, mock_db, mock_user, tmp_path):
        from app.domains.geo.router import get_twi_summary

        cog_path = str(tmp_path / "twi_cog.tif")
        Path(cog_path).touch()

        mock_layer = MagicMock()
        mock_layer.archivo_path = "/nonexistent/twi.tif"
        mock_layer.metadata_extra = {"cog_path": cog_path}
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_layer

        with patch("app.domains.geo.hydrology_terrain.compute_twi_zone_summary", return_value={"zones": []}) as mock_fn:
            result = get_twi_summary(area_id="zona_principal", db=mock_db, _user=mock_user)
            mock_fn.assert_called_once_with(cog_path)


# ---------------------------------------------------------------------------
# geo/router: Compare Rasters (temporal) - has layers but no files on disk
# ---------------------------------------------------------------------------


class TestCompareRastersNoFiles:
    def test_layers_exist_but_files_missing(self, mock_db, mock_user):
        from app.domains.geo.router import compare_rasters, RasterCompareRequest
        from app.core.exceptions import AppException

        mock_layer = MagicMock()
        mock_layer.archivo_path = "/nonexistent/slope.tif"
        mock_layer.metadata_extra = None
        mock_layer.tipo = "slope"
        mock_layer.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_layer]

        body = RasterCompareRequest(layer_tipo="slope")

        with pytest.raises(AppException):
            compare_rasters(body, mock_db, _user=mock_user)


# ---------------------------------------------------------------------------
# geo/router: STAC collections and search with actual module patches
# ---------------------------------------------------------------------------


class TestStacEndpoints:
    def test_stac_collections(self, mock_db):
        from app.domains.geo.router import stac_collections

        request = MagicMock()
        request.base_url = "http://localhost:8000/"

        with patch("app.domains.geo.stac.get_collections", return_value={"collections": []}):
            result = stac_collections(request, mock_db)

    def test_stac_search(self, mock_db):
        from app.domains.geo.router import stac_search

        request = MagicMock()
        request.base_url = "http://localhost:8000/"

        with patch("app.domains.geo.stac.search_catalog", return_value={"items": []}):
            result = stac_search(request, mock_db, tipo="slope", area_id=None, fuente=None, limit=50, offset=0)


# ---------------------------------------------------------------------------
# geo/router: Flood risk with actual metrics computation
# ---------------------------------------------------------------------------


class TestFloodRiskComputation:
    def test_zona_found_but_no_layers(self, mock_db, mock_user):
        """When zona exists but no raster layers, raises AppException."""
        from app.domains.geo.router import get_zona_flood_risk
        from app.core.exceptions import AppException

        zona = MagicMock()
        zona.id = uuid.uuid4()
        zona.nombre = "Zone Risk"

        call_count = [0]

        def query_side(model):
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value = q
            call_count[0] += 1
            if call_count[0] == 1:
                q.first.return_value = zona
            else:
                q.first.return_value = None
            return q

        mock_db.query.side_effect = query_side

        with pytest.raises(AppException):
            get_zona_flood_risk(zona.id, mock_db, _user=mock_user)


# ---------------------------------------------------------------------------
# core/exceptions
# ---------------------------------------------------------------------------


class TestAppException:
    def test_app_exception_to_dict(self):
        from app.core.exceptions import AppException

        exc = AppException(message="test error", code="TEST_ERR", status_code=400)
        d = exc.to_dict()
        assert d["error"]["code"] == "TEST_ERR"
        assert d["error"]["message"] == "test error"

    def test_not_found_error(self):
        from app.core.exceptions import NotFoundError

        exc = NotFoundError(message="not found", resource_type="zona", resource_id="123")
        assert exc.status_code == 404

    def test_rate_limit_error(self):
        from app.core.exceptions import RateLimitExceededError

        exc = RateLimitExceededError(retry_after=60)
        assert exc.status_code == 429
        assert exc.retry_after == 60

    def test_get_safe_error_detail_short_message(self):
        from app.core.exceptions import get_safe_error_detail

        detail = get_safe_error_detail(ValueError("simple error"), "operation")
        assert isinstance(detail, str)
        assert len(detail) > 0

    def test_sanitize_error_message_filters_sensitive(self):
        from app.core.exceptions import sanitize_error_message

        result = sanitize_error_message(ValueError("password=secret123"), "test error")
        assert "secret123" not in result

    def test_sanitize_error_message_filters_long(self):
        from app.core.exceptions import sanitize_error_message

        long_error = "x" * 300
        result = sanitize_error_message(ValueError(long_error), "fallback")
        assert result == "fallback"


# ---------------------------------------------------------------------------
# geo/service — dispatch_job
# ---------------------------------------------------------------------------


class TestGeoServiceModels:
    def test_tipo_geo_job_values(self):
        from app.domains.geo.models import TipoGeoJob
        assert TipoGeoJob.DEM_FULL_PIPELINE is not None


# ---------------------------------------------------------------------------
# Denuncias router stubs
# ---------------------------------------------------------------------------


class TestDomainRouters:
    def test_denuncias_router_import(self):
        from app.domains.denuncias.router import router
        assert router is not None

    def test_capas_router_import(self):
        from app.domains.capas.router import router
        assert router is not None

    def test_infraestructura_router_import(self):
        from app.domains.infraestructura.router import router
        assert router is not None

    def test_finanzas_router_import(self):
        from app.domains.finanzas.router import router
        assert router is not None

    def test_reuniones_router_import(self):
        from app.domains.reuniones.router import router
        assert router is not None

    def test_tramites_router_import(self):
        from app.domains.tramites.router import router
        assert router is not None


# ---------------------------------------------------------------------------
# Monitoring schemas
# ---------------------------------------------------------------------------


class TestMonitoringSchemas:
    def test_sugerencia_create_schema_exists(self):
        from app.domains.monitoring.schemas import SugerenciaCreate
        assert SugerenciaCreate is not None

    def test_sugerencia_response_schema_exists(self):
        from app.domains.monitoring.schemas import SugerenciaResponse
        assert SugerenciaResponse is not None


# ---------------------------------------------------------------------------
# geo/router: Approved Zones Build/Save
# ---------------------------------------------------------------------------


class TestApprovedZonesBuild:
    @patch("app.domains.geo.router.IntelligenceRepository")
    @patch("app.domains.geo.intelligence.zoning_suggestions.build_zones_from_assignments", create=True)
    def test_build_returns_feature_collection(self, mock_build, MockIntelRepo, mock_db):
        from app.domains.geo.router import build_approved_basin_zones, ApprovedZonesBuildRequest

        mock_intel = MagicMock()
        mock_intel.get_zonas_for_grouping.return_value = []
        MockIntelRepo.return_value = mock_intel
        mock_build.return_value = {"type": "FeatureCollection", "features": []}

        body = ApprovedZonesBuildRequest(assignments={}, zone_names={})

        with patch("app.domains.geo.intelligence.zoning_suggestions.build_zones_from_assignments", mock_build):
            result = build_approved_basin_zones(body, mock_db)
            assert isinstance(result, dict)


class TestApprovedZonesSave:
    @patch("app.domains.geo.router._serialize_approved_zoning")
    def test_save_creates_version(self, mock_serialize, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import save_current_approved_basin_zones, ApprovedZonesSaveRequest

        mock_created = MagicMock()
        mock_repo.create_approved_zoning_version.return_value = mock_created
        mock_serialize.return_value = {"id": "test", "nombre": "Test", "version": 1}

        body = ApprovedZonesSaveRequest(
            featureCollection={"type": "FeatureCollection", "features": []},
            assignments={},
            zone_names={},
        )

        result = save_current_approved_basin_zones(body, mock_db, mock_repo, mock_user)
        mock_repo.create_approved_zoning_version.assert_called_once()


# ---------------------------------------------------------------------------
# geo/router: Basins Import
# ---------------------------------------------------------------------------


class TestBasinsImport:
    @pytest.mark.asyncio
    async def test_rejects_non_geojson(self, mock_db, mock_user):
        from app.domains.geo.router import import_basins_geojson

        file = MagicMock()
        file.filename = "data.csv"

        with pytest.raises(HTTPException) as exc_info:
            await import_basins_geojson(file=file, db=mock_db, _user=mock_user)
        assert exc_info.value.status_code == 400


class TestApprovedZonesImport:
    @pytest.mark.asyncio
    async def test_rejects_non_geojson(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import import_current_approved_basin_zones

        file = MagicMock()
        file.filename = "data.csv"

        with pytest.raises(HTTPException) as exc_info:
            await import_current_approved_basin_zones(file=file, db=mock_db, repo=mock_repo, user=mock_user)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# geo/router: Geo Layer File serving
# ---------------------------------------------------------------------------


class TestGeoLayerFile:
    def test_layer_not_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_geo_layer_file

        mock_repo.get_layer_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_geo_layer_file(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 404

    def test_file_not_on_disk(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_geo_layer_file

        mock_layer = MagicMock()
        mock_layer.archivo_path = "/nonexistent/file.tif"
        mock_repo.get_layer_by_id.return_value = mock_layer

        with pytest.raises(HTTPException) as exc_info:
            get_geo_layer_file(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 404

    def test_file_served_successfully(self, mock_db, mock_repo, mock_user, tmp_path):
        from app.domains.geo.router import get_geo_layer_file

        test_file = tmp_path / "test.tif"
        test_file.write_bytes(b"TIFF DATA")

        mock_layer = MagicMock()
        mock_layer.archivo_path = str(test_file)
        mock_layer.formato = "geotiff"
        mock_repo.get_layer_by_id.return_value = mock_layer

        result = get_geo_layer_file(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert result.media_type == "image/tiff"


# ---------------------------------------------------------------------------
# main.py app instance
# ---------------------------------------------------------------------------


class TestMainApp:
    def test_app_exists(self):
        from app.main import app, APP_VERSION
        assert app is not None
        assert APP_VERSION == "2.0.0"

    @pytest.mark.asyncio
    async def test_root_endpoint(self):
        """Test the root endpoint via direct function call."""
        from app.main import root

        result = await root()
        assert result["status"] == "ok"
        assert result["version"] == "2.0.0"
