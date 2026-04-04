"""Final coverage push — targeting remaining uncovered lines in router.py
and other files.

Covers: flood events CRUD, rainfall endpoints, ML model info variations,
suggested zones, geo_layer file serving with geojson format,
GEE analysis submit with various tipos, and helper functions.
"""

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


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
# Flood Events CRUD
# ---------------------------------------------------------------------------


class TestFloodEventsList:
    def test_list_flood_events(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import list_flood_events

        mock_repo.list_flood_events.return_value = []
        result = list_flood_events(db=mock_db, repo=mock_repo, _user=mock_user)
        assert result == []

    def test_get_flood_event_not_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_flood_event
        mock_repo.get_flood_event_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            get_flood_event(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 404

    def test_get_flood_event_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import get_flood_event
        mock_event = MagicMock()
        mock_event.id = uuid.uuid4()
        mock_event.labels = []
        mock_repo.get_flood_event_by_id.return_value = mock_event

        result = get_flood_event(mock_event.id, mock_db, mock_repo, _user=mock_user)
        assert result is not None

    def test_delete_flood_event_not_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import delete_flood_event
        mock_repo.delete_flood_event.return_value = False
        with pytest.raises(HTTPException) as exc_info:
            delete_flood_event(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Rainfall endpoints
# ---------------------------------------------------------------------------


class TestRainfallSchemas:
    def test_backfill_request(self):
        from app.domains.geo.schemas import BackfillRequest

        req = BackfillRequest(start_date="2025-01-01", end_date="2025-06-01")
        assert req.start_date == date(2025, 1, 1)


# ---------------------------------------------------------------------------
# GEE Analysis Submit — different tipos
# ---------------------------------------------------------------------------


class TestGeeAnalysisSubmitVariousTipos:
    def _make_analisis(self, mock_repo):
        mock_analisis = MagicMock()
        mock_analisis.id = uuid.uuid4()
        mock_repo.create_analisis.return_value = mock_analisis
        return mock_analisis

    @patch("app.domains.geo.gee_tasks.sar_temporal_task")
    @patch("app.domains.geo.gee_tasks.analyze_flood_task")
    @patch("app.domains.geo.gee_tasks.supervised_classification_task")
    def test_submit_sar_temporal(self, mock_class, mock_flood, mock_sar, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import submit_gee_analysis
        from app.domains.geo.schemas import AnalisisGeoCreate

        mock_analisis = self._make_analisis(mock_repo)
        mock_sar.delay.return_value = MagicMock(id="celery-id")

        payload = AnalisisGeoCreate(
            tipo="sar_temporal",
            parametros={"start_date": "2025-01-01", "end_date": "2025-06-01", "scale": 100},
        )

        result = submit_gee_analysis(payload, mock_db, mock_repo, _user=mock_user)
        mock_sar.delay.assert_called_once()

    @patch("app.domains.geo.gee_tasks.sar_temporal_task")
    @patch("app.domains.geo.gee_tasks.analyze_flood_task")
    @patch("app.domains.geo.gee_tasks.supervised_classification_task")
    def test_submit_classification(self, mock_class, mock_flood, mock_sar, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import submit_gee_analysis
        from app.domains.geo.schemas import AnalisisGeoCreate

        mock_analisis = self._make_analisis(mock_repo)
        mock_class.delay.return_value = MagicMock(id="celery-id")

        payload = AnalisisGeoCreate(
            tipo="classification",
            parametros={"start_date": "2025-01-01", "end_date": "2025-06-01"},
        )

        result = submit_gee_analysis(payload, mock_db, mock_repo, _user=mock_user)
        mock_class.delay.assert_called_once()

    @patch("app.domains.geo.gee_tasks.sar_temporal_task")
    @patch("app.domains.geo.gee_tasks.analyze_flood_task")
    @patch("app.domains.geo.gee_tasks.supervised_classification_task")
    def test_submit_invalid_tipo(self, mock_class, mock_flood, mock_sar, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import submit_gee_analysis
        from app.domains.geo.schemas import AnalisisGeoCreate

        payload = AnalisisGeoCreate(
            tipo="invalid_tipo_xyz",
            parametros={},
        )

        with pytest.raises(HTTPException) as exc_info:
            submit_gee_analysis(payload, mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 422

    @patch("app.domains.geo.gee_tasks.sar_temporal_task")
    @patch("app.domains.geo.gee_tasks.analyze_flood_task")
    @patch("app.domains.geo.gee_tasks.supervised_classification_task")
    def test_submit_sar_invalid_dates(self, mock_class, mock_flood, mock_sar, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import submit_gee_analysis
        from app.domains.geo.schemas import AnalisisGeoCreate

        mock_analisis = self._make_analisis(mock_repo)

        payload = AnalisisGeoCreate(
            tipo="sar_temporal",
            parametros={"start_date": "2025-06-01", "end_date": "2025-01-01"},
        )

        with pytest.raises(HTTPException) as exc_info:
            submit_gee_analysis(payload, mock_db, mock_repo, _user=mock_user)
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# Suggested Zones
# ---------------------------------------------------------------------------


class TestSuggestedZonesDetail:
    @patch("app.domains.geo.router.IntelligenceRepository")
    def test_returns_empty_proposals(self, MockIntelRepo, mock_db):
        from app.domains.geo.router import get_suggested_basin_zones

        mock_repo_inst = MagicMock()
        mock_repo_inst.get_zonas_for_grouping.return_value = []
        MockIntelRepo.return_value = mock_repo_inst

        result = get_suggested_basin_zones(cuenca=None, db=mock_db)
        assert isinstance(result, dict)

    @patch("app.domains.geo.router.IntelligenceRepository")
    def test_with_cuenca_filter(self, MockIntelRepo, mock_db):
        from app.domains.geo.router import get_suggested_basin_zones

        mock_repo_inst = MagicMock()
        mock_repo_inst.get_zonas_for_grouping.return_value = []
        MockIntelRepo.return_value = mock_repo_inst

        result = get_suggested_basin_zones(cuenca="norte", db=mock_db)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Geo Layer File — geojson format
# ---------------------------------------------------------------------------


class TestGeoLayerFileFormats:
    def test_geojson_format(self, mock_db, mock_repo, mock_user, tmp_path):
        from app.domains.geo.router import get_geo_layer_file

        test_file = tmp_path / "test.geojson"
        test_file.write_text('{"type": "FeatureCollection"}')

        mock_layer = MagicMock()
        mock_layer.archivo_path = str(test_file)
        mock_layer.formato = "geojson"
        mock_repo.get_layer_by_id.return_value = mock_layer

        result = get_geo_layer_file(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert result.media_type == "application/geo+json"

    def test_unknown_format(self, mock_db, mock_repo, mock_user, tmp_path):
        from app.domains.geo.router import get_geo_layer_file

        test_file = tmp_path / "test.xyz"
        test_file.write_bytes(b"data")

        mock_layer = MagicMock()
        mock_layer.archivo_path = str(test_file)
        mock_layer.formato = "xyz"
        mock_repo.get_layer_by_id.return_value = mock_layer

        result = get_geo_layer_file(uuid.uuid4(), mock_db, mock_repo, _user=mock_user)
        assert result.media_type == "application/octet-stream"


# ---------------------------------------------------------------------------
# Helper functions from router
# ---------------------------------------------------------------------------


class TestRouterHelpers:
    def test_extract_source_properties(self):
        from app.domains.geo.router import _extract_source_properties

        feature = {
            "properties": {"nombre": "Test", "cuenca": "norte"}
        }
        result = _extract_source_properties(feature)
        assert isinstance(result, dict)

    def test_get_user_display_name_none_id(self, mock_db):
        from app.domains.geo.router import _get_user_display_name

        result = _get_user_display_name(mock_db, None)
        assert result is None

    def test_get_user_display_name_found(self, mock_db):
        from app.domains.geo.router import _get_user_display_name
        from types import SimpleNamespace

        user_obj = SimpleNamespace(nombre="John", apellido="Doe", email="john@test.com")
        mock_db.get.return_value = user_obj

        result = _get_user_display_name(mock_db, uuid.uuid4())
        assert "John" in result

    def test_get_user_display_name_not_found(self, mock_db):
        from app.domains.geo.router import _get_user_display_name

        mock_db.get.return_value = None

        result = _get_user_display_name(mock_db, uuid.uuid4())
        assert result is None

    def test_validate_geojson_filename_accepts_geojson(self):
        from app.domains.geo.router import _validate_geojson_filename
        _validate_geojson_filename("test.geojson")  # no exception

    def test_validate_geojson_filename_rejects_csv(self):
        from app.domains.geo.router import _validate_geojson_filename
        with pytest.raises(HTTPException):
            _validate_geojson_filename("test.csv")


# ---------------------------------------------------------------------------
# geo/routing.py — pure functions
# ---------------------------------------------------------------------------


class TestGeoRouting:
    def test_module_imports(self):
        """Verify geo routing module loads."""
        from app.domains.geo import routing
        assert routing is not None


# ---------------------------------------------------------------------------
# intelligence/zoning_suggestions
# ---------------------------------------------------------------------------


class TestZoningSuggestions:
    def test_module_imports(self):
        from app.domains.geo.intelligence import zoning_suggestions
        assert zoning_suggestions is not None


# ---------------------------------------------------------------------------
# intelligence/suggestions
# ---------------------------------------------------------------------------


class TestIntelligenceSuggestions:
    def test_module_imports(self):
        from app.domains.geo.intelligence import suggestions
        assert suggestions is not None


# ---------------------------------------------------------------------------
# geo/stac
# ---------------------------------------------------------------------------


class TestStacModule:
    def test_module_imports(self):
        from app.domains.geo import stac
        assert stac is not None


# ---------------------------------------------------------------------------
# ML flood prediction — pure model logic
# ---------------------------------------------------------------------------


class TestFloodPredictionModel:
    def test_predict_flood_for_zone(self):
        from app.domains.geo.ml.flood_prediction import predict_flood_for_zone

        features = {
            "zona_id": "test-1",
            "zona_name": "Test Zone",
            "hand_mean": 0.5,
            "hand_min": 0.1,
            "twi_mean": 12.0,
            "twi_max": 15.0,
            "slope_mean": 2.0,
            "flow_acc_max": 50000,
            "flow_acc_mean": 10000,
        }
        result = predict_flood_for_zone(features)
        assert "probability" in result
        assert "risk_level" in result
        assert 0 <= result["probability"] <= 1

    def test_predict_flood_empty_features(self):
        from app.domains.geo.ml.flood_prediction import predict_flood_for_zone

        features = {
            "zona_id": "test-1",
            "zona_name": "Test Zone",
        }
        result = predict_flood_for_zone(features)
        assert "probability" in result

    def test_flood_model_load(self):
        from app.domains.geo.ml.flood_prediction import FloodModel

        model = FloodModel.load()
        assert model is not None
        assert hasattr(model, "version")

    def test_zone_features(self):
        from app.domains.geo.ml.flood_prediction import ZoneFeatures

        features = ZoneFeatures(zona_id="z1", zona_name="Zone 1")
        assert features.zona_id == "z1"
        assert features.hand_mean == 0.0

    def test_flood_model_predict(self):
        from app.domains.geo.ml.flood_prediction import FloodModel, ZoneFeatures

        model = FloodModel.load()
        features = ZoneFeatures(
            zona_id="z1",
            zona_name="Zone 1",
            hand_mean=0.3,
            twi_mean=14.0,
            slope_mean=0.5,
            flow_acc_max=100000,
        )
        result = model.predict(features)
        assert "probability" in result
        assert "risk_level" in result


# ---------------------------------------------------------------------------
# geo/hydrology module
# ---------------------------------------------------------------------------


class TestHydrologyModule:
    def test_module_imports(self):
        from app.domains.geo import hydrology
        assert hydrology is not None


# ---------------------------------------------------------------------------
# geo/water_detection module
# ---------------------------------------------------------------------------


class TestWaterDetectionModule:
    def test_module_imports(self):
        from app.domains.geo import water_detection
        assert water_detection is not None


# ---------------------------------------------------------------------------
# geo/temporal module
# ---------------------------------------------------------------------------


class TestTemporalModule:
    def test_module_imports(self):
        from app.domains.geo import temporal
        assert temporal is not None


# ---------------------------------------------------------------------------
# core/exceptions — additional coverage
# ---------------------------------------------------------------------------


class TestExceptionsAdditional:
    def test_validation_error(self):
        from app.core.exceptions import ValidationError

        exc = ValidationError(message="invalid input", field="name")
        assert exc.status_code == 400

    def test_app_exception_with_details(self):
        from app.core.exceptions import AppException

        exc = AppException(
            message="test", code="TEST", status_code=500, details={"key": "val"},
        )
        d = exc.to_dict()
        assert d["error"]["details"]["key"] == "val"
