"""Tests for monitoring/service.py — cover uncovered methods.

Lines missed: file operations, channel incorporation, dashboard stats,
sugerencia CRUD orchestration, analysis methods.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.domains.monitoring.service import MonitoringService


@pytest.fixture
def mock_repo():
    return MagicMock()


@pytest.fixture
def service(mock_repo):
    return MonitoringService(repository=mock_repo)


# ---------------------------------------------------------------------------
# Path resolution and file I/O helpers (lines 32-128)
# ---------------------------------------------------------------------------


class TestResolveExistingPath:
    def test_returns_first_existing(self, service, tmp_path):
        existing = tmp_path / "test.geojson"
        existing.write_text("{}")
        result = service._resolve_existing_path((existing, Path("/nonexistent")))
        assert result == existing

    def test_returns_none_when_none_exist(self, service):
        result = service._resolve_existing_path(
            (Path("/does/not/exist1"), Path("/does/not/exist2"))
        )
        assert result is None


class TestLoadFeatureCollection:
    def test_valid_file(self, service, tmp_path):
        fc_file = tmp_path / "canales.geojson"
        fc_file.write_text(
            json.dumps({"type": "FeatureCollection", "features": []})
        )
        result = service._load_feature_collection(fc_file)
        assert result["type"] == "FeatureCollection"
        assert result["features"] == []

    def test_not_feature_collection_raises(self, service, tmp_path):
        fc_file = tmp_path / "bad.geojson"
        fc_file.write_text(json.dumps({"type": "Feature"}))
        with pytest.raises(HTTPException) as exc_info:
            service._load_feature_collection(fc_file)
        assert exc_info.value.status_code == 500


class TestWriteFeatureCollection:
    def test_writes_and_replaces(self, service, tmp_path):
        target = tmp_path / "output.geojson"
        payload = {"type": "FeatureCollection", "features": []}
        service._write_feature_collection(target, payload)
        assert target.exists()
        content = json.loads(target.read_text())
        assert content["type"] == "FeatureCollection"

    def test_creates_parent_dirs(self, service, tmp_path):
        target = tmp_path / "subdir" / "nested" / "output.geojson"
        payload = {"type": "FeatureCollection", "features": []}
        service._write_feature_collection(target, payload)
        assert target.exists()


class TestBuildChannelFeatures:
    def test_filters_linestrings(self, service):
        sugerencia = SimpleNamespace(
            id=uuid.uuid4(),
            titulo="Canal Test",
            geometry={
                "features": [
                    {
                        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                        "properties": {"name": "Canal 1"},
                    },
                    {
                        "geometry": {"type": "Point", "coordinates": [0, 0]},
                        "properties": {},
                    },
                ]
            },
        )
        features = service._build_channel_features_from_sugerencia(sugerencia)
        assert len(features) == 1
        assert features[0]["properties"]["source"] == "sugerencia_incorporada"

    def test_empty_geometry(self, service):
        sugerencia = SimpleNamespace(
            id=uuid.uuid4(),
            titulo="Empty",
            geometry={"features": []},
        )
        features = service._build_channel_features_from_sugerencia(sugerencia)
        assert features == []

    def test_uses_sugerencia_titulo_as_fallback(self, service):
        sugerencia = SimpleNamespace(
            id=uuid.uuid4(),
            titulo="Fallback Name",
            geometry={
                "features": [
                    {
                        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                        "properties": {},
                    }
                ]
            },
        )
        features = service._build_channel_features_from_sugerencia(sugerencia)
        assert features[0]["properties"]["name"] == "Fallback Name"


class TestPersistIncorporatedChannel:
    def test_backend_not_found_raises(self, service):
        with patch.object(service, "_resolve_existing_path", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                service._persist_incorporated_channel(
                    SimpleNamespace(id=uuid.uuid4(), geometry={"features": []})
                )
            assert exc_info.value.status_code == 500

    def test_appends_new_features(self, service, tmp_path):
        backend_file = tmp_path / "canales.geojson"
        backend_file.write_text(
            json.dumps({"type": "FeatureCollection", "features": []})
        )

        sugerencia = SimpleNamespace(
            id=uuid.uuid4(),
            titulo="New Canal",
            geometry={
                "features": [
                    {
                        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                        "properties": {},
                    }
                ]
            },
        )

        with patch.object(
            service,
            "_resolve_existing_path",
            side_effect=[backend_file, None],  # backend found, frontend not
        ):
            service._persist_incorporated_channel(sugerencia)

        updated = json.loads(backend_file.read_text())
        assert len(updated["features"]) == 1

    def test_skips_if_already_present(self, service, tmp_path):
        sug_id = uuid.uuid4()
        backend_file = tmp_path / "canales.geojson"
        backend_file.write_text(
            json.dumps({
                "type": "FeatureCollection",
                "features": [
                    {"properties": {"sugerencia_id": str(sug_id)}}
                ],
            })
        )

        sugerencia = SimpleNamespace(
            id=sug_id,
            titulo="Existing",
            geometry={"features": []},
        )

        with patch.object(service, "_resolve_existing_path", return_value=backend_file):
            service._persist_incorporated_channel(sugerencia)

        # Should still have just 1 feature
        updated = json.loads(backend_file.read_text())
        assert len(updated["features"]) == 1


class TestGetPersistedSugerenciaIds:
    def test_returns_ids(self, service, tmp_path):
        backend_file = tmp_path / "canales.geojson"
        backend_file.write_text(
            json.dumps({
                "type": "FeatureCollection",
                "features": [
                    {"properties": {"sugerencia_id": "abc-123"}},
                    {"properties": {}},  # no sugerencia_id
                ],
            })
        )
        with patch.object(service, "_resolve_existing_path", return_value=backend_file):
            ids = service._get_persisted_sugerencia_ids()
        assert "abc-123" in ids
        assert len(ids) == 1

    def test_returns_empty_when_no_file(self, service):
        with patch.object(service, "_resolve_existing_path", return_value=None):
            assert service._get_persisted_sugerencia_ids() == set()


# ---------------------------------------------------------------------------
# Sugerencia CRUD orchestration (lines 132-200)
# ---------------------------------------------------------------------------


class TestSugerenciaService:
    def test_get_sugerencia_found(self, service, mock_repo):
        sug = SimpleNamespace(id=uuid.uuid4(), titulo="Test")
        mock_repo.get_sugerencia_by_id.return_value = sug
        result = service.get_sugerencia(MagicMock(), sug.id)
        assert result.titulo == "Test"

    def test_get_sugerencia_not_found(self, service, mock_repo):
        mock_repo.get_sugerencia_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            service.get_sugerencia(MagicMock(), uuid.uuid4())
        assert exc_info.value.status_code == 404

    def test_list_sugerencias(self, service, mock_repo):
        mock_repo.get_all_sugerencias.return_value = ([], 0)
        items, total = service.list_sugerencias(MagicMock())
        assert total == 0

    def test_create_sugerencia(self, service, mock_repo):
        db = MagicMock()
        data = MagicMock()
        sug = SimpleNamespace(id=uuid.uuid4())
        mock_repo.create_sugerencia.return_value = sug
        result = service.create_sugerencia(db, data)
        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    def test_update_sugerencia_found(self, service, mock_repo):
        db = MagicMock()
        sug = SimpleNamespace(id=uuid.uuid4())
        mock_repo.update_sugerencia.return_value = sug
        result = service.update_sugerencia(db, sug.id, MagicMock())
        db.commit.assert_called_once()

    def test_update_sugerencia_not_found(self, service, mock_repo):
        mock_repo.update_sugerencia.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            service.update_sugerencia(MagicMock(), uuid.uuid4(), MagicMock())
        assert exc_info.value.status_code == 404

    def test_get_sugerencias_stats(self, service, mock_repo):
        mock_repo.get_sugerencias_stats.return_value = {"total": 10}
        result = service.get_sugerencias_stats(MagicMock())
        assert result["total"] == 10

    def test_get_proxima_reunion(self, service, mock_repo):
        mock_repo.get_proxima_reunion.return_value = []
        result = service.get_proxima_reunion(MagicMock())
        assert result == []


class TestIncorporateSugerencia:
    def test_no_geometry_raises(self, service, mock_repo):
        sug = SimpleNamespace(id=uuid.uuid4(), titulo="Test", geometry=None)
        mock_repo.get_sugerencia_by_id.return_value = sug
        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            service.incorporate_sugerencia_as_channel(db, sug.id)
        assert exc_info.value.status_code == 400

    def test_success(self, service, mock_repo):
        sug = SimpleNamespace(
            id=uuid.uuid4(),
            titulo="Canal",
            geometry={"features": []},
            estado="nueva",
            respuesta=None,
        )
        mock_repo.get_sugerencia_by_id.return_value = sug
        db = MagicMock()
        with patch.object(service, "_persist_incorporated_channel"):
            result = service.incorporate_sugerencia_as_channel(db, sug.id)
        assert result.estado == "implementada"
        db.commit.assert_called_once()


class TestGetIncorporatedChannelFeatureCollection:
    def test_returns_unpersisted_features(self, service, mock_repo):
        sug = SimpleNamespace(
            id=uuid.uuid4(),
            titulo="Canal 1",
            geometry={
                "features": [
                    {
                        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                        "properties": {},
                    }
                ]
            },
        )
        mock_repo.get_incorporated_channel_suggestions.return_value = [sug]
        with patch.object(service, "_get_persisted_sugerencia_ids", return_value=set()):
            result = service.get_incorporated_channel_feature_collection(MagicMock())
        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 1

    def test_skips_already_persisted(self, service, mock_repo):
        sug_id = uuid.uuid4()
        sug = SimpleNamespace(
            id=sug_id,
            titulo="Canal",
            geometry={
                "features": [
                    {
                        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                        "properties": {},
                    }
                ]
            },
        )
        mock_repo.get_incorporated_channel_suggestions.return_value = [sug]
        with patch.object(
            service,
            "_get_persisted_sugerencia_ids",
            return_value={str(sug_id)},
        ):
            result = service.get_incorporated_channel_feature_collection(MagicMock())
        assert len(result["features"]) == 0


# ---------------------------------------------------------------------------
# Analysis methods (lines 237-267)
# ---------------------------------------------------------------------------


class TestAnalysisMethods:
    def test_get_analysis_found(self, service, mock_repo):
        analysis = SimpleNamespace(id=uuid.uuid4())
        mock_repo.get_analysis_by_id.return_value = analysis
        result = service.get_analysis(MagicMock(), analysis.id)
        assert result.id == analysis.id

    def test_get_analysis_not_found(self, service, mock_repo):
        mock_repo.get_analysis_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            service.get_analysis(MagicMock(), uuid.uuid4())
        assert exc_info.value.status_code == 404

    def test_list_analyses(self, service, mock_repo):
        mock_repo.get_analysis_history.return_value = ([], 0)
        items, total = service.list_analyses(MagicMock())
        assert total == 0

    def test_save_analysis(self, service, mock_repo):
        db = MagicMock()
        analysis = SimpleNamespace(id=uuid.uuid4())
        mock_repo.save_analysis.return_value = analysis
        result = service.save_analysis(db, {"tipo": "ndvi"})
        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    def test_get_dashboard_stats(self, service, mock_repo):
        mock_repo.get_dashboard_stats.return_value = {"total": 5}
        result = service.get_dashboard_stats(MagicMock())
        assert result["total"] == 5
