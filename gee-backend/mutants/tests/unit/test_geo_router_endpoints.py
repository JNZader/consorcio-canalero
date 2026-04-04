"""Unit tests for geo router — new endpoints (flood events, ML training, rainfall).

Uses direct function calls with mocked dependencies instead of TestClient
to avoid bootstrapping the full app (DB, Redis, middleware).
"""

import sys
import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db():
    db = MagicMock()
    return db


@pytest.fixture()
def mock_repo():
    return MagicMock()


# ---------------------------------------------------------------------------
# POST /flood-events
# ---------------------------------------------------------------------------


class TestCreateFloodEvent:
    def _import_handler(self):
        from app.domains.geo.router import create_flood_event
        return create_flood_event

    def _make_payload(self, labels=None):
        from app.domains.geo.schemas import FloodEventCreate, FloodLabelCreate

        zona_id = uuid.uuid4()
        if labels is None:
            labels = [FloodLabelCreate(zona_id=zona_id, is_flooded=True)]
        return FloodEventCreate(
            event_date=date(2025, 6, 15),
            description="Test flood",
            labels=labels,
        )

    @pytest.mark.asyncio
    async def test_rejects_duplicate_zona_ids(self, mock_db, mock_repo):
        handler = self._import_handler()
        from app.domains.geo.schemas import FloodLabelCreate

        zona_id = uuid.uuid4()
        payload = self._make_payload(labels=[
            FloodLabelCreate(zona_id=zona_id, is_flooded=True),
            FloodLabelCreate(zona_id=zona_id, is_flooded=False),
        ])

        with pytest.raises(HTTPException) as exc_info:
            await handler(payload, mock_db, mock_repo, _user=MagicMock())

        assert exc_info.value.status_code == 422
        assert "duplicada" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejects_missing_zona_ids(self, mock_db, mock_repo):
        handler = self._import_handler()

        payload = self._make_payload()
        zona_id = payload.labels[0].zona_id

        # Mock the query chain to return no existing zonas
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            await handler(payload, mock_db, mock_repo, _user=MagicMock())

        assert exc_info.value.status_code == 422
        assert "no encontradas" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.domains.geo.router.asyncio")
    async def test_rejects_duplicate_event_date(self, mock_asyncio, mock_db, mock_repo):
        handler = self._import_handler()
        payload = self._make_payload()
        zona_id = payload.labels[0].zona_id

        # Zona exists
        zona_row = MagicMock()
        zona_row.id = zona_id
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [zona_row]
        mock_db.query.return_value = mock_query

        # But event date already exists — mock the FloodEventModel query
        with patch("app.domains.geo.router.FloodEventModel", create=True) as MockModel:
            mock_event_query = MagicMock()
            mock_event_query.filter.return_value.first.return_value = MagicMock()  # existing event

            # Second call to db.query is for FloodEventModel
            mock_db.query.side_effect = [mock_query, mock_event_query]

            with pytest.raises(HTTPException) as exc_info:
                await handler(payload, mock_db, mock_repo, _user=MagicMock())

            assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# GET /flood-events
# ---------------------------------------------------------------------------


class TestListFloodEvents:
    def test_returns_formatted_list(self, mock_db, mock_repo):
        from app.domains.geo.router import list_flood_events
        from datetime import datetime

        mock_repo.list_flood_events.return_value = [
            {
                "id": uuid.uuid4(),
                "event_date": date(2025, 6, 15),
                "description": "Flood 1",
                "label_count": 3,
                "created_at": datetime(2025, 6, 15, 12, 0),
            },
        ]

        result = list_flood_events(mock_db, mock_repo, _user=MagicMock())

        assert len(result) == 1
        assert result[0]["description"] == "Flood 1"
        assert result[0]["label_count"] == 3

    def test_returns_empty_list(self, mock_db, mock_repo):
        from app.domains.geo.router import list_flood_events

        mock_repo.list_flood_events.return_value = []

        result = list_flood_events(mock_db, mock_repo, _user=MagicMock())

        assert result == []


# ---------------------------------------------------------------------------
# GET /flood-events/{event_id}
# ---------------------------------------------------------------------------


class TestGetFloodEvent:
    def test_returns_event_with_labels(self, mock_db, mock_repo):
        from app.domains.geo.router import get_flood_event
        from datetime import datetime

        event_id = uuid.uuid4()
        label = MagicMock()
        label.id = uuid.uuid4()
        label.zona_id = uuid.uuid4()
        label.is_flooded = True
        label.ndwi_value = 0.35
        label.extracted_features = {"ndwi": 0.35}

        event = MagicMock()
        event.id = event_id
        event.event_date = date(2025, 6, 15)
        event.description = "Test"
        event.satellite_source = "S2"
        event.labels = [label]
        event.created_at = datetime(2025, 6, 15, 12, 0)
        event.updated_at = datetime(2025, 6, 15, 12, 0)

        mock_repo.get_flood_event_by_id.return_value = event

        result = get_flood_event(event_id, mock_db, mock_repo, _user=MagicMock())

        assert result["id"] == str(event_id)
        assert len(result["labels"]) == 1

    def test_raises_404_when_not_found(self, mock_db, mock_repo):
        from app.domains.geo.router import get_flood_event

        mock_repo.get_flood_event_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_flood_event(uuid.uuid4(), mock_db, mock_repo, _user=MagicMock())

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /flood-events/{event_id}
# ---------------------------------------------------------------------------


class TestDeleteFloodEvent:
    def test_returns_204_on_success(self, mock_db, mock_repo):
        from app.domains.geo.router import delete_flood_event

        mock_repo.delete_flood_event.return_value = True

        result = delete_flood_event(uuid.uuid4(), mock_db, mock_repo, _user=MagicMock())

        assert result.status_code == 204
        mock_db.commit.assert_called_once()

    def test_raises_404_when_not_found(self, mock_db, mock_repo):
        from app.domains.geo.router import delete_flood_event

        mock_repo.delete_flood_event.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            delete_flood_event(uuid.uuid4(), mock_db, mock_repo, _user=MagicMock())

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /ml/flood-prediction/train
# ---------------------------------------------------------------------------


class TestTrainFloodModel:
    @patch("app.domains.geo.router.shutil")
    def test_raises_400_when_insufficient_labels(self, mock_shutil, mock_db, mock_repo):
        from app.domains.geo.router import train_flood_model

        mock_repo.get_labels_with_features.return_value = [MagicMock()] * 3  # < 5

        with pytest.raises(HTTPException) as exc_info:
            train_flood_model(mock_db, mock_repo, _user=MagicMock())

        assert exc_info.value.status_code == 400
        assert "al menos 5" in exc_info.value.detail.lower()

    @patch("app.domains.geo.router.shutil")
    def test_returns_training_result_on_success(self, mock_shutil, mock_db, mock_repo):
        from app.domains.geo.router import train_flood_model

        # 5 labels with features
        labels = []
        for i in range(5):
            lbl = MagicMock()
            lbl.extracted_features = {"ndwi": 0.3 + i * 0.05}
            lbl.is_flooded = i % 2 == 0
            labels.append(lbl)
        mock_repo.get_labels_with_features.return_value = labels

        mock_model = MagicMock()
        mock_model.weights = {"ndwi": 0.5}
        mock_model.train_from_events.return_value = {
            "events": 5,
            "epochs": 100,
            "initial_loss": 0.7,
            "final_loss": 0.1,
            "weights": {"ndwi": 0.8},
            "bias": -0.2,
        }

        mock_flood_model_cls = MagicMock()
        mock_flood_model_cls.load.return_value = mock_model

        mock_model_path = MagicMock()
        mock_model_path.parent.mkdir = MagicMock()
        mock_model_path.exists.return_value = False

        with patch.dict("sys.modules", {
            "app.domains.geo.ml.flood_prediction": MagicMock(
                FloodModel=mock_flood_model_cls,
                MODEL_PATH=mock_model_path,
            ),
        }):
            result = train_flood_model(mock_db, mock_repo, _user=MagicMock())

        assert result.events_used == 5
        assert result.final_loss == 0.1


# ---------------------------------------------------------------------------
# POST /rainfall/backfill
# ---------------------------------------------------------------------------


class TestTriggerRainfallBackfill:
    def test_returns_202_with_job_id(self, mock_db):
        from app.domains.geo.schemas import BackfillRequest
        from app.domains.geo.router import trigger_rainfall_backfill

        payload = BackfillRequest(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )

        mock_celery_task = MagicMock()
        mock_celery_task.delay.return_value = MagicMock(id="celery-task-123")

        mock_tasks_module = MagicMock()
        mock_tasks_module.rainfall_backfill = mock_celery_task

        with patch.dict("sys.modules", {"app.domains.geo.tasks": mock_tasks_module}):
            result = trigger_rainfall_backfill(payload, mock_db, _user=MagicMock())

        assert result["status"] == "accepted"
        assert result["job_id"] == "celery-task-123"


# ---------------------------------------------------------------------------
# GET /rainfall/zones/{zone_id}
# ---------------------------------------------------------------------------


class TestGetRainfallForZone:
    def test_returns_records(self, mock_db, mock_repo):
        from app.domains.geo.router import get_rainfall_for_zone

        zone_id = uuid.uuid4()
        record = MagicMock()
        record.date = date(2025, 1, 15)
        record.precipitation_mm = 22.5
        record.source = "CHIRPS"

        mock_repo.get_rainfall_by_zone.return_value = [record]

        result = get_rainfall_for_zone(
            zone_id, start=None, end=None,
            db=mock_db, repo=mock_repo, _user=MagicMock(),
        )

        assert result["count"] == 1
        assert result["records"][0]["precipitation_mm"] == 22.5


# ---------------------------------------------------------------------------
# GET /rainfall/summary
# ---------------------------------------------------------------------------


class TestGetRainfallSummary:
    def test_returns_enriched_summaries(self, mock_db, mock_repo):
        from app.domains.geo.router import get_rainfall_summary

        zona_id = uuid.uuid4()
        mock_repo.get_rainfall_summary.return_value = [
            {"zona_operativa_id": zona_id, "total_mm": 150.0},
        ]

        # Mock zone name lookup
        zona_row = MagicMock()
        zona_row.id = zona_id
        zona_row.nombre = "Zona Norte"
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [zona_row]
        mock_db.query.return_value = mock_query

        result = get_rainfall_summary(
            start=date(2025, 1, 1), end=date(2025, 6, 30),
            db=mock_db, repo=mock_repo, _user=MagicMock(),
        )

        assert result["start"] == "2025-01-01"
        assert len(result["zones"]) == 1
        assert result["zones"][0]["zona_name"] == "Zona Norte"


# ---------------------------------------------------------------------------
# GET /rainfall/daily
# ---------------------------------------------------------------------------


class TestGetRainfallDaily:
    def test_delegates_to_repo(self, mock_db, mock_repo):
        from app.domains.geo.router import get_rainfall_daily

        expected = [{"date": "2025-01-15", "max_mm": 40.0}]
        mock_repo.get_rainfall_daily_max.return_value = expected

        result = get_rainfall_daily(
            start=date(2025, 1, 1), end=date(2025, 1, 31),
            db=mock_db, repo=mock_repo, _user=MagicMock(),
        )

        assert result == expected


# ---------------------------------------------------------------------------
# GET /rainfall/events
# ---------------------------------------------------------------------------


class TestGetRainfallEvents:
    def test_returns_enriched_events(self, mock_db):
        from app.domains.geo.router import get_rainfall_events

        zona_id = uuid.uuid4()
        mock_detect = MagicMock(return_value=[
            {
                "zona_operativa_id": zona_id,
                "event_start": date(2025, 3, 10),
                "event_end": date(2025, 3, 12),
                "accumulated_mm": 85.0,
                "duration_days": 3,
            },
        ])

        zona_row = MagicMock()
        zona_row.id = zona_id
        zona_row.nombre = "Zona ML"
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [zona_row]
        mock_db.query.return_value = mock_query

        with patch("app.domains.geo.rainfall_service.detect_rainfall_events", mock_detect):
            result = get_rainfall_events(
                start=date(2025, 1, 1), end=date(2025, 6, 30),
                threshold_mm=50.0, window_days=3,
                db=mock_db, _user=MagicMock(),
            )

        assert result["total"] == 1
        assert result["events"][0]["accumulated_mm"] == 85.0
        assert result["events"][0]["zona_name"] == "Zona ML"


# ---------------------------------------------------------------------------
# GET /rainfall/suggestions
# ---------------------------------------------------------------------------


class TestGetRainfallSuggestions:
    def test_returns_suggestions_with_images(self, mock_db):
        from app.domains.geo.router import get_rainfall_suggestions

        zona_id = uuid.uuid4()
        mock_detect = MagicMock(return_value=[
            {
                "zona_operativa_id": zona_id,
                "event_start": date(2025, 3, 10),
                "event_end": date(2025, 3, 12),
                "accumulated_mm": 85.0,
                "duration_days": 3,
            },
        ])

        mock_suggest = MagicMock(return_value=[
            {"date": date(2025, 3, 15), "cloud_cover_pct": 12.0},
            {"date": date(2025, 3, 16), "cloud_cover_pct": 25.0},
        ])

        zona_row = MagicMock()
        zona_row.id = zona_id
        zona_row.nombre = "Zona ML"
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [zona_row]
        mock_db.query.return_value = mock_query

        with patch("app.domains.geo.rainfall_service.detect_rainfall_events", mock_detect), \
             patch("app.domains.geo.rainfall_service.suggest_images_for_event", mock_suggest):
            result = get_rainfall_suggestions(
                start=date(2025, 1, 1), end=date(2025, 6, 30),
                threshold_mm=50.0, window_days=3, days_after=5,
                db=mock_db, _user=MagicMock(),
            )

        assert len(result) >= 1

    def test_handles_gee_failure_gracefully(self, mock_db):
        from app.domains.geo.router import get_rainfall_suggestions

        zona_id = uuid.uuid4()
        mock_detect = MagicMock(return_value=[
            {
                "zona_operativa_id": zona_id,
                "event_start": date(2025, 3, 10),
                "event_end": date(2025, 3, 12),
                "accumulated_mm": 85.0,
                "duration_days": 3,
            },
        ])

        mock_suggest = MagicMock(side_effect=Exception("GEE down"))

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        with patch("app.domains.geo.rainfall_service.detect_rainfall_events", mock_detect), \
             patch("app.domains.geo.rainfall_service.suggest_images_for_event", mock_suggest):
            # Should not raise — GEE failure is handled gracefully
            result = get_rainfall_suggestions(
                start=date(2025, 1, 1), end=date(2025, 6, 30),
                threshold_mm=50.0, window_days=3, days_after=5,
                db=mock_db, _user=MagicMock(),
            )

        assert len(result) >= 1
