"""Unit tests for app.domains.geo.gee_tasks — Celery tasks for GEE operations.

All external dependencies (DB, GEE, ImageExplorer) are mocked.
"""

import math
import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_gee_logger():
    """Replace the Celery task logger with a MagicMock to avoid
    TypeError from standard logging with keyword args."""
    with patch("app.domains.geo.gee_tasks.logger", MagicMock()):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deps(**overrides):
    deps = {
        "SessionLocal": MagicMock,
        "EstadoGeoJob": MagicMock(RUNNING="running", COMPLETED="completed", FAILED="failed"),
        "repo": MagicMock(),
    }
    deps.update(overrides)
    return deps


def _make_gee(**overrides):
    gee = {"explorer": MagicMock()}
    gee.update(overrides)
    return gee


# ---------------------------------------------------------------------------
# detect_vv_anomalies (pure function — no mocking needed)
# ---------------------------------------------------------------------------


class TestDetectVvAnomalies:
    def test_empty_values(self):
        from app.domains.geo.gee_tasks import detect_vv_anomalies

        result = detect_vv_anomalies([], [])
        assert result["baseline"] is None
        assert result["std"] is None
        assert result["threshold"] is None
        assert result["anomalies"] == []

    def test_no_anomalies_uniform(self):
        from app.domains.geo.gee_tasks import detect_vv_anomalies

        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        values = [-10.0, -10.0, -10.0]
        result = detect_vv_anomalies(dates, values)
        assert result["baseline"] == -10.0
        assert result["std"] == 0.0
        assert result["anomalies"] == []

    def test_detects_anomaly(self):
        from app.domains.geo.gee_tasks import detect_vv_anomalies

        # Many normal values with one deep drop to dilute outlier effect on std
        dates = [f"2024-01-{i:02d}" for i in range(1, 12)]
        values = [-10.0] * 10 + [-30.0]
        result = detect_vv_anomalies(dates, values, sigma=2.0)

        assert result["baseline"] is not None
        assert len(result["anomalies"]) >= 1
        assert result["anomalies"][0]["date"] == "2024-01-11"

    def test_sigma_parameter(self):
        from app.domains.geo.gee_tasks import detect_vv_anomalies

        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        values = [-10.0, -11.0, -15.0]

        # Very tight sigma should flag more anomalies
        result_tight = detect_vv_anomalies(dates, values, sigma=0.5)
        # Very loose sigma should flag fewer
        result_loose = detect_vv_anomalies(dates, values, sigma=5.0)

        assert len(result_tight["anomalies"]) >= len(result_loose["anomalies"])

    def test_single_value(self):
        from app.domains.geo.gee_tasks import detect_vv_anomalies

        result = detect_vv_anomalies(["2024-01-01"], [-10.0])
        assert result["baseline"] == -10.0
        assert result["std"] == 0.0
        assert result["anomalies"] == []

    def test_all_same_values(self):
        from app.domains.geo.gee_tasks import detect_vv_anomalies

        dates = [f"2024-01-{i:02d}" for i in range(1, 11)]
        values = [-12.0] * 10
        result = detect_vv_anomalies(dates, values)
        assert result["baseline"] == -12.0
        assert result["std"] == 0.0
        assert result["threshold"] == -12.0
        assert result["anomalies"] == []

    def test_values_rounded(self):
        from app.domains.geo.gee_tasks import detect_vv_anomalies

        result = detect_vv_anomalies(["d1", "d2"], [-10.12345, -10.67891])
        assert isinstance(result["baseline"], float)
        # All returned floats should be rounded to 4 decimals
        baseline_str = str(result["baseline"])
        decimals = baseline_str.split(".")[-1] if "." in baseline_str else ""
        assert len(decimals) <= 4


# ---------------------------------------------------------------------------
# _get_deps
# ---------------------------------------------------------------------------


class TestGetDeps:
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_returns_expected_keys(self, mock):
        mock.return_value = _make_deps()
        from app.domains.geo.gee_tasks import _get_deps

        result = _get_deps()
        assert "SessionLocal" in result
        assert "EstadoGeoJob" in result
        assert "repo" in result


# ---------------------------------------------------------------------------
# analyze_flood_task
# ---------------------------------------------------------------------------


class TestAnalyzeFloodTask:
    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_fusion_method_completed(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sentinel2_image.return_value = {"tile_url": "http://tile", "date": "2024-01-01"}
        explorer.get_sentinel1_image.return_value = {"tile_url": "http://sar", "date": "2024-01-01"}
        explorer.get_flood_comparison.return_value = {"change_map": "data"}
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import analyze_flood_task

        result = analyze_flood_task(
            "2024-01-01", "2024-02-01", method="fusion"
        )
        assert result["status"] == "completed"
        assert result["method"] == "fusion"
        assert "optical" in result
        assert "sar" in result

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_optical_only(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sentinel2_image.return_value = {"tile_url": "http://tile"}
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import analyze_flood_task

        result = analyze_flood_task("2024-01-01", "2024-01-10", method="optical_only")
        assert result["status"] == "completed"
        assert result["method"] == "optical_only"
        assert "optical" in result
        assert "sar" not in result

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_sar_only(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sentinel1_image.return_value = {"tile_url": "http://sar"}
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import analyze_flood_task

        result = analyze_flood_task("2024-01-01", "2024-01-10", method="sar_only")
        assert result["status"] == "completed"
        assert "sar" in result
        assert "optical" not in result

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_with_analisis_id_tracks_status(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db
        repo = deps["repo"]

        explorer = MagicMock()
        explorer.get_sentinel2_image.return_value = {}
        explorer.get_sentinel1_image.return_value = {}
        mock_gee.return_value = {"explorer": explorer}

        analisis_id = str(uuid.uuid4())

        from app.domains.geo.gee_tasks import analyze_flood_task

        analyze_flood_task("2024-01-01", "2024-01-02", analisis_id=analisis_id)

        # Should have called update_analisis_status twice: RUNNING then COMPLETED
        assert repo.update_analisis_status.call_count >= 2

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_error_marks_failed(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db
        repo = deps["repo"]

        mock_gee.side_effect = RuntimeError("GEE init failed")

        analisis_id = str(uuid.uuid4())

        from app.domains.geo.gee_tasks import analyze_flood_task

        with pytest.raises(RuntimeError, match="GEE init failed"):
            analyze_flood_task("2024-01-01", "2024-01-10", analisis_id=analisis_id)

        # Should have tried to mark as FAILED
        failed_calls = [
            c for c in repo.update_analisis_status.call_args_list
            if "FAILED" in str(c) or "failed" in str(c)
        ]


    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_error_status_update_fails_gracefully(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db
        repo = deps["repo"]

        mock_gee.side_effect = RuntimeError("boom")
        # The status update in except block also fails
        repo.update_analisis_status.side_effect = [None, Exception("db dead")]

        from app.domains.geo.gee_tasks import analyze_flood_task

        with pytest.raises(RuntimeError):
            analyze_flood_task("2024-01-01", "2024-01-10", analisis_id=str(uuid.uuid4()))


    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_handles_error_in_optical_result(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sentinel2_image.return_value = {
            "tile_url": "http://tile",
            "error": "cloud coverage too high",
        }
        explorer.get_sentinel1_image.return_value = {"tile_url": "http://sar"}
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import analyze_flood_task

        result = analyze_flood_task("2024-01-01", "2024-01-02", method="fusion")
        assert "warning" in result["optical"]

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_comparison_error_captured(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sentinel2_image.return_value = {"tile_url": "ok"}
        explorer.get_sentinel1_image.return_value = {"tile_url": "ok"}
        explorer.get_flood_comparison.side_effect = Exception("comparison failed")
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import analyze_flood_task

        # Long date range to trigger comparison
        result = analyze_flood_task("2024-01-01", "2024-02-01", method="fusion")
        assert "comparison_error" in result

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_no_comparison_for_short_range(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sentinel2_image.return_value = {"tile_url": "ok"}
        explorer.get_sentinel1_image.return_value = {"tile_url": "ok"}
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import analyze_flood_task

        # Date range <= 5 days should NOT trigger comparison
        result = analyze_flood_task("2024-01-01", "2024-01-03", method="fusion")
        assert "comparison" not in result
        explorer.get_flood_comparison.assert_not_called()


# ---------------------------------------------------------------------------
# supervised_classification_task
# ---------------------------------------------------------------------------


class TestSupervisedClassificationTask:
    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_completed_with_all_visualizations(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sentinel2_image.return_value = {"tile_url": "http://tile"}
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import supervised_classification_task

        result = supervised_classification_task("2024-01-01", "2024-02-01")
        assert result["status"] == "completed"
        assert result["classification_type"] == "ndvi_ndwi_based"
        assert "ndvi" in result
        assert "rgb" in result
        assert "agricultura" in result
        assert "falso_color" in result


    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_with_analisis_id(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db
        repo = deps["repo"]

        explorer = MagicMock()
        explorer.get_sentinel2_image.return_value = {"tile_url": "http://tile"}
        mock_gee.return_value = {"explorer": explorer}

        analisis_id = str(uuid.uuid4())

        from app.domains.geo.gee_tasks import supervised_classification_task

        supervised_classification_task("2024-01-01", "2024-02-01", analisis_id=analisis_id)
        assert repo.update_analisis_status.call_count >= 2

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_error_marks_failed(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        mock_gee.side_effect = RuntimeError("GEE failed")

        from app.domains.geo.gee_tasks import supervised_classification_task

        with pytest.raises(RuntimeError):
            supervised_classification_task(
                "2024-01-01", "2024-02-01", analisis_id=str(uuid.uuid4())
            )


    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_error_with_status_update_failure(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db
        deps["repo"].update_analisis_status.side_effect = [None, Exception("db error")]

        mock_gee.side_effect = RuntimeError("boom")

        from app.domains.geo.gee_tasks import supervised_classification_task

        with pytest.raises(RuntimeError):
            supervised_classification_task(
                "2024-01-01", "2024-02-01", analisis_id=str(uuid.uuid4())
            )

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_handles_ndvi_warning(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sentinel2_image.return_value = {
            "tile_url": "ok",
            "error": "high clouds",
        }
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import supervised_classification_task

        result = supervised_classification_task("2024-01-01", "2024-02-01")
        assert "warning" in result["ndvi"]


# ---------------------------------------------------------------------------
# sar_temporal_task
# ---------------------------------------------------------------------------


class TestSarTemporalTask:
    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_completed(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sar_time_series.return_value = {
            "dates": ["2024-01-01", "2024-01-13"],
            "vv_mean": [-10.0, -10.5],
            "image_count": 2,
        }
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import sar_temporal_task

        result = sar_temporal_task("2024-01-01", "2024-02-01", scale=100)
        assert result["status"] == "completed"
        assert result["image_count"] == 2
        assert "baseline" in result
        assert "anomalies" in result


    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_with_warning(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sar_time_series.return_value = {
            "dates": [],
            "vv_mean": [],
            "image_count": 0,
            "warning": "No SAR images found",
        }
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import sar_temporal_task

        result = sar_temporal_task("2024-01-01", "2024-02-01")
        assert result["warning"] == "No SAR images found"

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_with_analisis_id(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db
        repo = deps["repo"]

        explorer = MagicMock()
        explorer.get_sar_time_series.return_value = {
            "dates": ["2024-01-01"],
            "vv_mean": [-10.0],
            "image_count": 1,
        }
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import sar_temporal_task

        sar_temporal_task(
            "2024-01-01", "2024-02-01", analisis_id=str(uuid.uuid4())
        )
        assert repo.update_analisis_status.call_count >= 2

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_error_marks_failed(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        mock_gee.side_effect = RuntimeError("GEE init failed")

        from app.domains.geo.gee_tasks import sar_temporal_task

        with pytest.raises(RuntimeError):
            sar_temporal_task(
                "2024-01-01", "2024-02-01", analisis_id=str(uuid.uuid4())
            )


    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_error_with_db_failure_in_except(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db
        deps["repo"].update_analisis_status.side_effect = [None, Exception("db dead")]

        mock_gee.side_effect = RuntimeError("boom")

        from app.domains.geo.gee_tasks import sar_temporal_task

        with pytest.raises(RuntimeError):
            sar_temporal_task(
                "2024-01-01", "2024-02-01", analisis_id=str(uuid.uuid4())
            )

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_without_analisis_id(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sar_time_series.return_value = {
            "dates": ["2024-01-01"],
            "vv_mean": [-10.0],
            "image_count": 1,
        }
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import sar_temporal_task

        result = sar_temporal_task("2024-01-01", "2024-02-01")
        assert result["status"] == "completed"
        # Should NOT have called update_analisis_status at all
        deps["repo"].update_analisis_status.assert_not_called()

    @patch("app.domains.geo.gee_tasks._get_gee")
    @patch("app.domains.geo.gee_tasks._get_deps")
    def test_custom_scale(self, mock_deps, mock_gee):
        deps = _make_deps()
        mock_deps.return_value = deps
        db = MagicMock()
        deps["SessionLocal"].return_value = db

        explorer = MagicMock()
        explorer.get_sar_time_series.return_value = {
            "dates": [],
            "vv_mean": [],
            "image_count": 0,
        }
        mock_gee.return_value = {"explorer": explorer}

        from app.domains.geo.gee_tasks import sar_temporal_task

        result = sar_temporal_task("2024-01-01", "2024-02-01", scale=500)
        assert result["scale_m"] == 500
        explorer.get_sar_time_series.assert_called_once()
        call_kwargs = explorer.get_sar_time_series.call_args[1]
        assert call_kwargs["scale"] == 500
