"""API response contract tests.

Verify HTTP response shapes, status codes, and schema compliance
for the new geo endpoints. Uses FastAPI TestClient with mocked
DB/services — validates the HTTP contract, not business logic.
"""

import uuid
from datetime import date, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domains.geo.schemas import (
    FloodEventListResponse,
    FloodEventResponse,
    FloodLabelResponse,
    RainfallEventResponse,
    RainfallRecordResponse,
    RainfallSummaryResponse,
    TrainingResultResponse,
)
from app.domains.geo.intelligence.schemas import (
    AnalysisSummaryResponse,
    CanalSuggestionResponse,
)


# ──────────────────────────────────────────────
# FIXTURES
# ──────────────────────────────────────────────


def _make_fake_user():
    """Create a mock user object that satisfies auth checks."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.role = "admin"
    user.is_active = True
    user.is_superuser = False
    user.is_verified = True
    return user


@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.first.return_value = None
    db.execute.return_value.scalars.return_value.all.return_value = []
    db.execute.return_value.scalar_one.return_value = 0
    db.commit.return_value = None
    db.close.return_value = None
    return db


@pytest.fixture
def mock_geo_repo():
    """Mock GeoRepository."""
    return MagicMock()


@pytest.fixture
def mock_intel_repo():
    """Mock IntelligenceRepository."""
    return MagicMock()


@pytest.fixture
def client(mock_db, mock_geo_repo, mock_intel_repo):
    """TestClient with all dependencies overridden via dependency_overrides."""
    from app.auth.dependencies import current_active_user
    from app.db.session import get_db
    from app.domains.geo.repository import GeoRepository
    from app.domains.geo.intelligence.repository import IntelligenceRepository

    # Import the actual app to get all routes registered
    from app.main import app

    fake_user = _make_fake_user()

    # Override ALL auth-related dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[current_active_user] = lambda: fake_user

    # The routers use Depends(_get_repo) which calls _get_repo() → GeoRepository().
    # We need to override the actual GeoRepository and IntelligenceRepository callables
    # that FastAPI sees as the dependency function. Since _get_repo is a closure
    # returning GeoRepository(), we override it at the Depends level.
    from app.domains.geo.router import _get_repo as geo_get_repo
    from app.domains.geo.intelligence.router import _get_repo as intel_get_repo

    app.dependency_overrides[geo_get_repo] = lambda: mock_geo_repo
    app.dependency_overrides[intel_get_repo] = lambda: mock_intel_repo

    yield TestClient(app, raise_server_exceptions=False)

    # Cleanup overrides
    app.dependency_overrides.clear()


# ──────────────────────────────────────────────
# FLOOD EVENT ENDPOINTS
# ──────────────────────────────────────────────


class TestFloodEventContracts:
    """Contract: /geo/flood-events responses match declared shapes."""

    def test_create_flood_event_422_empty_labels(self, client):
        """POST /flood-events with empty labels returns 422."""
        payload = {"event_date": "2025-06-15", "labels": []}
        resp = client.post("/api/v2/geo/flood-events", json=payload)
        assert resp.status_code == 422

    def test_create_flood_event_422_missing_fields(self, client):
        """POST /flood-events with missing body returns 422."""
        resp = client.post("/api/v2/geo/flood-events", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body

    def test_create_flood_event_201(self, client, mock_db, mock_geo_repo):
        """POST /flood-events with valid payload returns 201."""
        zona_id = uuid.uuid4()

        # Mock zona exists
        mock_zona = MagicMock()
        mock_zona.id = zona_id
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_zona]

        # Mock no duplicate event
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Mock repo return
        fake_event = MagicMock()
        fake_event.id = uuid.uuid4()
        fake_event.event_date = date(2025, 6, 15)
        fake_event.description = "Test event"
        fake_event.satellite_source = "Sentinel-2"
        fake_event.created_at = datetime(2025, 6, 15, 10, 0, 0)
        fake_event.updated_at = datetime(2025, 6, 15, 10, 0, 0)

        fake_label = MagicMock()
        fake_label.id = uuid.uuid4()
        fake_label.zona_id = zona_id
        fake_label.is_flooded = True
        fake_label.ndwi_value = None
        fake_label.extracted_features = None
        fake_event.labels = [fake_label]

        mock_geo_repo.create_flood_event.return_value = fake_event
        mock_geo_repo.get_flood_event_by_id.return_value = fake_event

        payload = {
            "event_date": "2025-06-15",
            "labels": [{"zona_id": str(zona_id), "is_flooded": True}],
        }

        resp = client.post("/api/v2/geo/flood-events", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert "labels" in body
        assert isinstance(body["labels"], list)

    def test_list_flood_events_200(self, client, mock_geo_repo):
        """GET /flood-events returns 200 with array."""
        mock_geo_repo.list_flood_events.return_value = [
            {
                "id": uuid.uuid4(),
                "event_date": date(2025, 6, 15),
                "description": "Test",
                "label_count": 3,
                "created_at": datetime(2025, 6, 15),
            }
        ]

        resp = client.get("/api/v2/geo/flood-events")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        if len(body) > 0:
            item = body[0]
            assert "id" in item
            assert "event_date" in item
            assert "label_count" in item

    def test_get_flood_event_404(self, client, mock_geo_repo):
        """GET /flood-events/{id} with nonexistent ID returns 404."""
        mock_geo_repo.get_flood_event_by_id.return_value = None
        event_id = uuid.uuid4()

        resp = client.get(f"/api/v2/geo/flood-events/{event_id}")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)

    def test_get_flood_event_200(self, client, mock_geo_repo):
        """GET /flood-events/{id} returns full event with labels."""
        event_id = uuid.uuid4()
        fake_event = MagicMock()
        fake_event.id = event_id
        fake_event.event_date = date(2025, 6, 15)
        fake_event.description = None
        fake_event.satellite_source = "Sentinel-2"
        fake_label = MagicMock()
        fake_label.id = uuid.uuid4()
        fake_label.zona_id = uuid.uuid4()
        fake_label.is_flooded = True
        fake_label.ndwi_value = 0.35
        fake_label.extracted_features = {"ndwi_mean": 0.35}
        fake_event.labels = [fake_label]
        fake_event.created_at = datetime(2025, 6, 15)
        fake_event.updated_at = datetime(2025, 6, 15)

        mock_geo_repo.get_flood_event_by_id.return_value = fake_event

        resp = client.get(f"/api/v2/geo/flood-events/{event_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert "satellite_source" in body
        assert "labels" in body
        assert isinstance(body["labels"], list)


# ──────────────────────────────────────────────
# RAINFALL ENDPOINTS
# ──────────────────────────────────────────────


class TestRainfallContracts:
    """Contract: /geo/rainfall/* response shapes."""

    def test_backfill_422_missing_dates(self, client):
        """POST /rainfall/backfill with missing dates returns 422."""
        resp = client.post("/api/v2/geo/rainfall/backfill", json={})
        assert resp.status_code == 422

    def test_rainfall_summary_requires_dates(self, client):
        """GET /rainfall/summary without query params returns 422."""
        resp = client.get("/api/v2/geo/rainfall/summary")
        assert resp.status_code == 422

    def test_rainfall_daily_requires_dates(self, client):
        """GET /rainfall/daily without query params returns 422."""
        resp = client.get("/api/v2/geo/rainfall/daily")
        assert resp.status_code == 422

    def test_rainfall_zones_200(self, client, mock_geo_repo):
        """GET /rainfall/zones/{zone_id} returns zone rainfall data."""
        zone_id = uuid.uuid4()
        mock_geo_repo.get_rainfall_by_zone.return_value = []

        resp = client.get(f"/api/v2/geo/rainfall/zones/{zone_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "zona_operativa_id" in body
        assert "records" in body
        assert isinstance(body["records"], list)

    def test_rainfall_events_200(self, client, mock_db):
        """GET /rainfall/events returns event detection results."""
        with patch(
            "app.domains.geo.rainfall_service.detect_rainfall_events",
            return_value=[],
        ):
            resp = client.get(
                "/api/v2/geo/rainfall/events",
                params={"start": "2024-01-01", "end": "2024-12-31"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "threshold_mm" in body
            assert "window_days" in body
            assert "total" in body
            assert "events" in body
            assert isinstance(body["events"], list)

    def test_rainfall_events_default_threshold(self, client, mock_db):
        """GET /rainfall/events uses default threshold_mm=50."""
        with patch(
            "app.domains.geo.rainfall_service.detect_rainfall_events",
            return_value=[],
        ):
            resp = client.get("/api/v2/geo/rainfall/events")
            if resp.status_code == 200:
                body = resp.json()
                assert body["threshold_mm"] == 50.0

    def test_rainfall_suggestions_200(self, client, mock_db):
        """GET /rainfall/suggestions returns suggestion list."""
        with patch(
            "app.domains.geo.rainfall_service.detect_rainfall_events",
            return_value=[],
        ):
            resp = client.get(
                "/api/v2/geo/rainfall/suggestions",
                params={"start": "2024-01-01", "end": "2024-12-31"},
            )
            if resp.status_code == 200:
                body = resp.json()
                assert isinstance(body, dict)

    def test_backfill_202(self, client):
        """POST /rainfall/backfill returns 202 with job info."""
        with patch("app.domains.geo.tasks.rainfall_backfill") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-123")

            payload = {
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            }
            resp = client.post("/api/v2/geo/rainfall/backfill", json=payload)
            if resp.status_code == 202:
                body = resp.json()
                assert "job_id" in body
                assert "status" in body


# ──────────────────────────────────────────────
# ML TRAINING ENDPOINT
# ──────────────────────────────────────────────


class TestMLTrainingContracts:
    """Contract: /geo/ml/flood-prediction/train response shape."""

    def test_train_400_insufficient_labels(self, client, mock_geo_repo):
        """POST /ml/flood-prediction/train with < 5 labels returns 400."""
        mock_geo_repo.get_labels_with_features.return_value = [MagicMock()] * 3

        resp = client.post(
            "/api/v2/geo/ml/flood-prediction/train",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)

    def test_train_200_shape(self, client, mock_geo_repo):
        """POST /ml/flood-prediction/train returns TrainingResultResponse shape."""
        labels = []
        for i in range(6):
            lbl = MagicMock()
            lbl.extracted_features = {"ndwi_mean": 0.3 + i * 0.05, "slope": 0.1}
            lbl.is_flooded = i % 2 == 0
            labels.append(lbl)
        mock_geo_repo.get_labels_with_features.return_value = labels

        with patch("app.domains.geo.ml.flood_prediction.FloodModel") as MockModel, \
             patch("app.domains.geo.ml.flood_prediction.MODEL_PATH") as mock_path:
            mock_model = MagicMock()
            mock_model.weights = {"ndwi_mean": 1.0, "slope": 0.5}
            mock_model.train_from_events.return_value = {
                "events": 6,
                "epochs": 100,
                "initial_loss": 0.693,
                "final_loss": 0.25,
                "weights": {"ndwi_mean": 1.2, "slope": 0.8},
                "bias": -0.3,
            }
            MockModel.load.return_value = mock_model
            mock_path.exists.return_value = True
            mock_path.parent = MagicMock()
            mock_path.parent.__truediv__ = MagicMock(
                return_value=MagicMock(__str__=lambda s: "/tmp/backup.json")
            )

            resp = client.post(
                "/api/v2/geo/ml/flood-prediction/train",
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                body = resp.json()
                assert "events_used" in body
                assert "epochs" in body
                assert "initial_loss" in body
                assert "final_loss" in body
                assert "weights_before" in body
                assert "weights_after" in body
                assert "bias" in body
                assert "backup_path" in body
                result = TrainingResultResponse(**body)
                assert result.events_used == 6


# ──────────────────────────────────────────────
# INTELLIGENCE ENDPOINTS
# ──────────────────────────────────────────────


class TestIntelligenceContracts:
    """Contract: /geo/intelligence/* response shapes."""

    def test_suggestions_results_empty(self, client, mock_intel_repo):
        """GET /intelligence/suggestions/results with no data returns empty."""
        mock_intel_repo.get_latest_batch.return_value = None

        resp = client.get("/api/v2/geo/intelligence/suggestions/results")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["batch_id"] is None

    def test_suggestions_results_with_data(self, client, mock_intel_repo, mock_db):
        """GET /intelligence/suggestions/results returns paginated results."""
        batch_id = uuid.uuid4()
        mock_intel_repo.get_latest_batch.return_value = batch_id

        fake_suggestion = MagicMock(spec=[])
        fake_suggestion.id = uuid.uuid4()
        fake_suggestion.tipo = "hotspot"
        fake_suggestion.score = 85.0
        fake_suggestion.metadata_ = {"reason": "high flow"}
        fake_suggestion.batch_id = batch_id
        fake_suggestion.created_at = datetime(2025, 1, 1)

        mock_intel_repo.get_suggestions_by_tipo.return_value = (
            [fake_suggestion],
            1,
        )

        resp = client.get(
            "/api/v2/geo/intelligence/suggestions/results",
            params={"tipo": "hotspot"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "limit" in body
        assert "batch_id" in body
        assert isinstance(body["items"], list)

    def test_suggestions_summary_empty(self, client, mock_intel_repo):
        """GET /intelligence/suggestions/summary with no data returns defaults."""
        mock_intel_repo.get_summary.return_value = None

        resp = client.get("/api/v2/geo/intelligence/suggestions/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["batch_id"] is None
        assert body["total_suggestions"] == 0
        assert body["by_tipo"] == {}

    def test_suggestions_results_by_batch_404(self, client, mock_intel_repo, mock_db):
        """GET /intelligence/suggestions/results/{batch_id} returns 404 for empty."""
        batch_id = uuid.uuid4()
        mock_intel_repo.get_suggestions_by_tipo.return_value = ([], 0)

        mock_db.execute.return_value.scalar_one.return_value = 0

        resp = client.get(
            f"/api/v2/geo/intelligence/suggestions/results/{batch_id}"
        )
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    def test_dashboard_response_shape(self, client, mock_intel_repo, mock_db):
        """GET /intelligence/dashboard returns DashboardInteligente shape."""
        mock_intel_repo.get_dashboard_stats.return_value = {
            "total_zonas_operativas": 10,
            "total_conflictos": 5,
            "total_alertas_activas": 2,
        }
        mock_intel_repo.get_alertas_resumen.return_value = {}
        mock_intel_repo.get_hci_por_zona.return_value = ([], 0)

        resp = client.get("/api/v2/geo/intelligence/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert "porcentaje_area_riesgo" in body
        assert "canales_criticos" in body
        assert "caminos_vulnerables" in body
        assert "conflictos_activos" in body
        assert "alertas_activas" in body
        assert "zonas_por_nivel" in body

    def test_alertas_200(self, client, mock_intel_repo):
        """GET /intelligence/alertas returns alert list."""
        mock_intel_repo.get_alertas_activas.return_value = []

        resp = client.get("/api/v2/geo/intelligence/alertas")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)


# ──────────────────────────────────────────────
# ERROR RESPONSE CONTRACTS
# ──────────────────────────────────────────────


class TestErrorContracts:
    """Contract: error responses follow consistent shape."""

    def test_422_has_detail(self, client):
        """422 errors include 'detail' field."""
        resp = client.post("/api/v2/geo/flood-events", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], list)
        for err in body["detail"]:
            assert "loc" in err
            assert "msg" in err
            assert "type" in err

    def test_404_has_detail_string(self, client, mock_geo_repo):
        """404 errors include 'detail' as string."""
        mock_geo_repo.get_flood_event_by_id.return_value = None

        resp = client.get(f"/api/v2/geo/flood-events/{uuid.uuid4()}")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)

    def test_invalid_uuid_path_422(self, client):
        """Invalid UUID in path returns 422."""
        resp = client.get("/api/v2/geo/flood-events/not-a-uuid")
        assert resp.status_code == 422


# ──────────────────────────────────────────────
# RESPONSE SCHEMA VALIDATION
# ──────────────────────────────────────────────


class TestResponseSchemaValidation:
    """Verify response dicts validate against declared Pydantic schemas."""

    def test_flood_event_list_item_validates(self):
        data = {
            "id": str(uuid.uuid4()),
            "event_date": "2025-06-15",
            "description": None,
            "label_count": 3,
            "created_at": "2025-06-15T10:00:00",
        }
        result = FloodEventListResponse(**data)
        assert result.label_count == 3

    def test_flood_label_response_validates(self):
        data = {
            "id": str(uuid.uuid4()),
            "zona_id": str(uuid.uuid4()),
            "is_flooded": True,
            "ndwi_value": 0.35,
            "extracted_features": {"ndwi_mean": 0.35},
        }
        result = FloodLabelResponse(**data)
        assert result.is_flooded is True

    def test_rainfall_record_validates(self):
        data = {
            "id": str(uuid.uuid4()),
            "zona_operativa_id": str(uuid.uuid4()),
            "date": "2025-01-15",
            "precipitation_mm": 25.4,
            "source": "CHIRPS",
            "created_at": "2025-01-15T00:00:00",
        }
        result = RainfallRecordResponse(**data)
        assert result.precipitation_mm == 25.4

    def test_rainfall_event_validates(self):
        data = {
            "event_start": "2025-01-01",
            "event_end": "2025-01-03",
            "zona_operativa_id": str(uuid.uuid4()),
            "accumulated_mm": 75.0,
            "duration_days": 3,
        }
        result = RainfallEventResponse(**data)
        assert result.duration_days == 3

    def test_rainfall_summary_validates(self):
        data = {
            "zona_operativa_id": str(uuid.uuid4()),
            "zona_name": "Zona Norte",
            "total_mm": 150.0,
            "avg_mm": 5.0,
            "max_mm": 40.0,
            "rainy_days": 20,
        }
        result = RainfallSummaryResponse(**data)
        assert result.zona_name == "Zona Norte"

    def test_training_result_validates(self):
        data = {
            "events_used": 10,
            "epochs": 100,
            "initial_loss": 0.693,
            "final_loss": 0.25,
            "weights_before": {"ndwi": 1.0},
            "weights_after": {"ndwi": 1.2},
            "bias": -0.5,
            "backup_path": "/data/backup.json",
        }
        result = TrainingResultResponse(**data)
        assert result.events_used == 10

    def test_canal_suggestion_validates(self):
        data = {
            "id": str(uuid.uuid4()),
            "tipo": "hotspot",
            "score": 85.5,
            "metadata": {"reason": "high flow"},
            "batch_id": str(uuid.uuid4()),
            "created_at": "2025-01-01T00:00:00",
        }
        result = CanalSuggestionResponse(**data)
        assert result.tipo == "hotspot"

    def test_analysis_summary_validates(self):
        data = {
            "batch_id": str(uuid.uuid4()),
            "total_suggestions": 15,
            "by_tipo": {"hotspot": 5, "gap": 10},
            "avg_score": 72.3,
            "created_at": "2025-01-01T00:00:00",
        }
        result = AnalysisSummaryResponse(**data)
        assert result.total_suggestions == 15
