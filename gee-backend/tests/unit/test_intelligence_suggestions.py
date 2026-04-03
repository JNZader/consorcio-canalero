"""Unit tests for app.domains.geo.intelligence.suggestions — full analysis orchestration."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.domains.geo.intelligence.suggestions import (
    _gap_severity_to_score,
    _to_suggestion,
    run_full_analysis,
)


# ---------------------------------------------------------------------------
# Helper: _gap_severity_to_score
# ---------------------------------------------------------------------------


class TestGapSeverityToScore:
    def test_critico_returns_95(self):
        assert _gap_severity_to_score("critico") == 95.0

    def test_alto_returns_75(self):
        assert _gap_severity_to_score("alto") == 75.0

    def test_moderado_returns_50(self):
        assert _gap_severity_to_score("moderado") == 50.0

    def test_unknown_defaults_to_50(self):
        assert _gap_severity_to_score("bajo") == 50.0
        assert _gap_severity_to_score("") == 50.0


# ---------------------------------------------------------------------------
# Helper: _to_suggestion
# ---------------------------------------------------------------------------


class TestToSuggestion:
    def test_basic_structure(self):
        batch = uuid.uuid4()
        result = _to_suggestion(batch, "hotspot", 85.0, {"key": "val"})

        assert result["tipo"] == "hotspot"
        assert result["score"] == 85.0
        assert result["batch_id"] is batch
        assert result["metadata_"] == {"key": "val"}
        assert result["geometry"] is None

    def test_geometry_dict_is_converted(self):
        batch = uuid.uuid4()
        geojson = {
            "type": "Point",
            "coordinates": [-62.5, -32.5],
        }
        result = _to_suggestion(batch, "gap", 50.0, {"geometry": geojson, "extra": 1})

        assert result["geometry"] is not None
        assert "geometry" not in result["metadata_"]
        assert result["metadata_"]["extra"] == 1

    def test_invalid_geometry_yields_none(self):
        batch = uuid.uuid4()
        result = _to_suggestion(batch, "gap", 50.0, {"geometry": "not-a-geom"})
        assert result["geometry"] is None


# ---------------------------------------------------------------------------
# Orchestration: run_full_analysis
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    db.execute.return_value.all.return_value = []
    db.execute.return_value.scalar_one.return_value = 0
    return db


class TestRunFullAnalysis:
    """Tests for the run_full_analysis orchestrator."""

    @patch("app.domains.geo.intelligence.suggestions.IntelligenceRepository")
    @patch("app.domains.geo.intelligence.suggestions.GeoRepository")
    @patch("app.domains.geo.intelligence.suggestions._load_canal_geometries", return_value=[])
    @patch("app.domains.geo.intelligence.suggestions._get_layer_path", return_value=None)
    @patch("app.domains.geo.intelligence.suggestions._load_zones", return_value=[])
    @patch("app.domains.geo.intelligence.suggestions._load_hci_scores", return_value={})
    @patch("app.domains.geo.intelligence.suggestions._load_conflict_counts", return_value={})
    def test_returns_empty_when_no_data(
        self, _conflicts, _hci, _zones, _layer, _canals, _geo_repo, _intel_repo, mock_db
    ):
        result = run_full_analysis(mock_db)

        assert "batch_id" in result
        assert isinstance(result["batch_id"], uuid.UUID)
        assert result["total_suggestions"] == 0
        assert result["by_tipo"] == {}

    @patch("app.domains.geo.intelligence.suggestions.IntelligenceRepository")
    @patch("app.domains.geo.intelligence.suggestions.GeoRepository")
    @patch("app.domains.geo.intelligence.suggestions._load_canal_geometries")
    @patch("app.domains.geo.intelligence.suggestions._get_layer_path")
    @patch("app.domains.geo.intelligence.suggestions._load_zones", return_value=[])
    @patch("app.domains.geo.intelligence.suggestions._load_hci_scores", return_value={})
    @patch("app.domains.geo.intelligence.suggestions._load_conflict_counts", return_value={})
    @patch("app.domains.geo.intelligence.suggestions.rank_canal_hotspots")
    def test_hotspots_called_when_data_available(
        self, mock_hotspots, _conflicts, _hci, _zones, mock_layer, mock_canals,
        _geo_repo, mock_intel_repo, mock_db,
    ):
        mock_canals.return_value = [{"id": 1, "geometry": {"type": "LineString", "coordinates": []}}]
        mock_layer.return_value = "/some/flow_acc.tif"
        mock_hotspots.return_value = [
            {"score": 90.0, "segment_index": 0, "flow_acc_mean": 100.0},
        ]
        mock_intel_repo.return_value.insert_suggestions_batch.return_value = 1

        result = run_full_analysis(mock_db)

        mock_hotspots.assert_called_once()
        assert result["total_suggestions"] >= 1
        assert "hotspot" in result["by_tipo"]

    @patch("app.domains.geo.intelligence.suggestions.IntelligenceRepository")
    @patch("app.domains.geo.intelligence.suggestions.GeoRepository")
    @patch("app.domains.geo.intelligence.suggestions._load_canal_geometries")
    @patch("app.domains.geo.intelligence.suggestions._get_layer_path", return_value="/path.tif")
    @patch("app.domains.geo.intelligence.suggestions._load_zones", return_value=[])
    @patch("app.domains.geo.intelligence.suggestions._load_hci_scores", return_value={})
    @patch("app.domains.geo.intelligence.suggestions._load_conflict_counts", return_value={})
    @patch("app.domains.geo.intelligence.suggestions.rank_canal_hotspots", side_effect=RuntimeError("boom"))
    def test_hotspot_error_does_not_crash(
        self, _hotspots, _conflicts, _hci, _zones, _layer, mock_canals,
        _geo_repo, mock_intel_repo, mock_db,
    ):
        mock_canals.return_value = [{"id": 1, "geometry": {}}]
        mock_intel_repo.return_value.insert_suggestions_batch.return_value = 0

        result = run_full_analysis(mock_db)
        # Should not raise — error is caught internally
        assert result["total_suggestions"] == 0

    @patch("app.domains.geo.intelligence.suggestions.IntelligenceRepository")
    @patch("app.domains.geo.intelligence.suggestions.GeoRepository")
    @patch("app.domains.geo.intelligence.suggestions._load_canal_geometries", return_value=[])
    @patch("app.domains.geo.intelligence.suggestions._get_layer_path", return_value=None)
    @patch("app.domains.geo.intelligence.suggestions._load_zones", return_value=[])
    @patch("app.domains.geo.intelligence.suggestions._load_hci_scores", return_value={})
    @patch("app.domains.geo.intelligence.suggestions._load_conflict_counts", return_value={})
    def test_batch_id_is_uuid(
        self, _conflicts, _hci, _zones, _layer, _canals, _geo_repo, _intel_repo, mock_db
    ):
        result = run_full_analysis(mock_db)
        assert isinstance(result["batch_id"], uuid.UUID)

    @patch("app.domains.geo.intelligence.suggestions.IntelligenceRepository")
    @patch("app.domains.geo.intelligence.suggestions.GeoRepository")
    @patch("app.domains.geo.intelligence.suggestions._load_canal_geometries")
    @patch("app.domains.geo.intelligence.suggestions._get_layer_path")
    @patch("app.domains.geo.intelligence.suggestions._load_zones")
    @patch("app.domains.geo.intelligence.suggestions._load_hci_scores")
    @patch("app.domains.geo.intelligence.suggestions._load_conflict_counts")
    @patch("app.domains.geo.intelligence.suggestions.rank_canal_hotspots")
    @patch("app.domains.geo.intelligence.suggestions.detect_coverage_gaps")
    @patch("app.domains.geo.intelligence.suggestions.suggest_canal_routes")
    def test_gaps_and_routes_called_when_data_present(
        self, mock_routes, mock_gaps, mock_hotspots,
        _conflicts, _hci, mock_zones, mock_layer, mock_canals,
        _geo_repo, mock_intel_repo, mock_db,
    ):
        canals = [{"id": 1, "geometry": {}}]
        mock_canals.return_value = canals
        mock_layer.return_value = "/path.tif"
        mock_zones.return_value = [{"id": "z1", "geometry": {}}]
        _hci.return_value = {"z1": 0.8}
        _conflicts.return_value = {}
        mock_hotspots.return_value = []
        mock_gaps.return_value = [{"severity": "alto"}]
        mock_routes.return_value = [{"status": "ok", "estimated_cost": 500.0}]
        mock_intel_repo.return_value.insert_suggestions_batch.return_value = 2

        result = run_full_analysis(mock_db)

        mock_gaps.assert_called_once()
        mock_routes.assert_called_once()
        assert "gap" in result["by_tipo"]
        assert "route" in result["by_tipo"]

    @patch("app.domains.geo.intelligence.suggestions.IntelligenceRepository")
    @patch("app.domains.geo.intelligence.suggestions.GeoRepository")
    @patch("app.domains.geo.intelligence.suggestions._load_canal_geometries")
    @patch("app.domains.geo.intelligence.suggestions._get_layer_path", return_value="/path.tif")
    @patch("app.domains.geo.intelligence.suggestions._load_zones", return_value=[])
    @patch("app.domains.geo.intelligence.suggestions._load_hci_scores")
    @patch("app.domains.geo.intelligence.suggestions._load_conflict_counts")
    @patch("app.domains.geo.intelligence.suggestions.rank_canal_hotspots", return_value=[])
    @patch("app.domains.geo.intelligence.suggestions.compute_maintenance_priority")
    def test_maintenance_called_when_scores_present(
        self, mock_maint, _hotspots, mock_conflicts, mock_hci,
        _zones, _layer, mock_canals, _geo_repo, mock_intel_repo, mock_db,
    ):
        mock_canals.return_value = [{"id": 1, "geometry": {}}]
        mock_hci.return_value = {"z1": 0.5}
        mock_conflicts.return_value = {0: 3}
        mock_maint.return_value = [{"composite_score": 0.85, "node_id": 0}]
        mock_intel_repo.return_value.insert_suggestions_batch.return_value = 1

        result = run_full_analysis(mock_db)

        mock_maint.assert_called_once()
        assert "maintenance" in result["by_tipo"]

    @patch("app.domains.geo.intelligence.suggestions.IntelligenceRepository")
    @patch("app.domains.geo.intelligence.suggestions.GeoRepository")
    @patch("app.domains.geo.intelligence.suggestions._load_canal_geometries")
    @patch("app.domains.geo.intelligence.suggestions._get_layer_path", return_value="/path.tif")
    @patch("app.domains.geo.intelligence.suggestions._load_zones", return_value=[])
    @patch("app.domains.geo.intelligence.suggestions._load_hci_scores", return_value={})
    @patch("app.domains.geo.intelligence.suggestions._load_conflict_counts", return_value={})
    @patch("app.domains.geo.intelligence.suggestions.rank_canal_hotspots", return_value=[])
    def test_persistence_called_when_suggestions_exist(
        self, _hotspots, _conflicts, _hci, _zones, _layer, mock_canals,
        _geo_repo, mock_intel_repo, mock_db,
    ):
        # Mock betweenness_centrality imported inside the function via the routing module
        with patch(
            "app.domains.geo.routing.betweenness_centrality",
            return_value=[{"node_id": 1, "centrality": 0.9}],
        ):
            mock_canals.return_value = [{"id": 1, "geometry": {}}]
            mock_intel_repo_inst = mock_intel_repo.return_value
            mock_intel_repo_inst.insert_suggestions_batch.return_value = 1

            result = run_full_analysis(mock_db)

            mock_intel_repo_inst.insert_suggestions_batch.assert_called_once()
            mock_db.commit.assert_called()
            assert result["total_suggestions"] >= 1
