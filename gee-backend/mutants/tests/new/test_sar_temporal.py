"""
Tests for SAR Temporal Analysis feature.

Tests:
- detect_vv_anomalies() pure function with various inputs
- sar_temporal_task Celery task registration
- SAR_TEMPORAL enum value exists
"""

import math

import pytest

from app.domains.geo.gee_tasks import detect_vv_anomalies
from app.domains.geo.models import TipoAnalisisGee


# ── Enum ──────────────────────────────────────────


class TestSarTemporalEnum:
    """Verify SAR_TEMPORAL enum value exists."""

    def test_sar_temporal_in_tipo_analisis(self):
        assert TipoAnalisisGee.SAR_TEMPORAL.value == "sar_temporal"

    def test_sar_temporal_is_string_enum(self):
        assert isinstance(TipoAnalisisGee.SAR_TEMPORAL, str)
        assert TipoAnalisisGee.SAR_TEMPORAL == "sar_temporal"


# ── detect_vv_anomalies ──────────────────────────


class TestDetectVvAnomalies:
    """Test the pure anomaly detection function."""

    def test_empty_input_returns_nulls(self):
        result = detect_vv_anomalies(dates=[], vv_values=[])
        assert result["baseline"] is None
        assert result["std"] is None
        assert result["threshold"] is None
        assert result["anomalies"] == []

    def test_normal_range_no_anomalies(self):
        """All values within normal range should produce zero anomalies."""
        dates = ["2025-01-01", "2025-01-13", "2025-01-25", "2025-02-06"]
        vv_values = [-12.0, -11.5, -12.5, -11.8]

        result = detect_vv_anomalies(dates, vv_values)

        assert result["baseline"] is not None
        assert result["std"] is not None
        assert result["threshold"] is not None
        assert result["anomalies"] == []

        # Verify stats
        expected_baseline = sum(vv_values) / len(vv_values)
        assert abs(result["baseline"] - expected_baseline) < 0.01

    def test_single_anomaly_detected(self):
        """One extreme outlier below threshold should be flagged."""
        # With many normal values and one extreme outlier, the outlier
        # should still fall below baseline - 2*std.
        dates = [
            "2025-01-01", "2025-01-13", "2025-01-25", "2025-02-06",
            "2025-02-18", "2025-03-02", "2025-03-14", "2025-03-26",
            "2025-04-07", "2025-04-19",
        ]
        # 9 normal values around -12 dB, 1 extreme outlier at -22 dB
        vv_values = [-12.0, -11.5, -12.5, -11.8, -12.2, -11.9, -12.3, -11.7, -12.1, -22.0]

        result = detect_vv_anomalies(dates, vv_values)

        assert len(result["anomalies"]) >= 1
        anomaly_dates = [a["date"] for a in result["anomalies"]]
        assert "2025-04-19" in anomaly_dates

    def test_all_identical_no_anomalies(self):
        """All identical values → std=0, threshold=baseline, no anomalies."""
        dates = ["2025-01-01", "2025-01-13", "2025-01-25"]
        vv_values = [-12.0, -12.0, -12.0]

        result = detect_vv_anomalies(dates, vv_values)

        assert result["baseline"] == -12.0
        assert result["std"] == 0.0
        assert result["threshold"] == -12.0
        assert result["anomalies"] == []

    def test_all_values_are_anomalies(self):
        """If all values are way below a hypothetical baseline, none are anomalies
        because baseline adjusts to the data."""
        dates = ["2025-01-01", "2025-01-13", "2025-01-25"]
        vv_values = [-20.0, -20.0, -20.0]

        result = detect_vv_anomalies(dates, vv_values)

        # All identical → std=0 → threshold=baseline → no anomalies
        assert result["anomalies"] == []

    def test_custom_sigma(self):
        """Using sigma=1 should detect more anomalies than sigma=2."""
        dates = ["2025-01-01", "2025-01-13", "2025-01-25", "2025-02-06"]
        vv_values = [-12.0, -11.5, -12.5, -14.5]

        result_sigma2 = detect_vv_anomalies(dates, vv_values, sigma=2.0)
        result_sigma1 = detect_vv_anomalies(dates, vv_values, sigma=1.0)

        assert len(result_sigma1["anomalies"]) >= len(result_sigma2["anomalies"])

    def test_single_value_no_anomalies(self):
        """Single value → std=0, no anomalies possible."""
        result = detect_vv_anomalies(["2025-01-01"], [-12.0])
        assert result["baseline"] == -12.0
        assert result["std"] == 0.0
        assert result["anomalies"] == []

    def test_result_structure(self):
        """Verify the return dict has all required keys."""
        dates = ["2025-01-01", "2025-01-13"]
        vv_values = [-12.0, -11.5]

        result = detect_vv_anomalies(dates, vv_values)

        assert "baseline" in result
        assert "std" in result
        assert "threshold" in result
        assert "anomalies" in result
        assert isinstance(result["anomalies"], list)

    def test_anomaly_contains_date_and_vv(self):
        """Each anomaly entry must have 'date' and 'vv' keys."""
        dates = [
            "2025-01-01", "2025-01-13", "2025-01-25", "2025-02-06",
            "2025-02-18", "2025-03-02", "2025-03-14", "2025-03-26",
            "2025-04-07", "2025-04-19",
        ]
        vv_values = [-12.0, -11.5, -12.5, -11.8, -12.2, -11.9, -12.3, -11.7, -12.1, -25.0]

        result = detect_vv_anomalies(dates, vv_values)

        assert len(result["anomalies"]) > 0
        for anomaly in result["anomalies"]:
            assert "date" in anomaly
            assert "vv" in anomaly
            assert isinstance(anomaly["date"], str)
            assert isinstance(anomaly["vv"], float)

    def test_threshold_is_baseline_minus_2_std(self):
        """Verify threshold = baseline - 2*std."""
        dates = ["2025-01-01", "2025-01-13", "2025-01-25", "2025-02-06"]
        vv_values = [-12.0, -11.0, -13.0, -10.0]

        result = detect_vv_anomalies(dates, vv_values)

        expected_threshold = result["baseline"] - 2 * result["std"]
        assert abs(result["threshold"] - expected_threshold) < 0.01


# ── Celery task registration ──────────────────────


class TestSarTemporalTaskRegistration:
    """Verify sar_temporal_task is properly registered as Celery task."""

    def test_task_is_celery_task(self):
        from app.domains.geo.gee_tasks import sar_temporal_task

        assert hasattr(sar_temporal_task, "delay")
        assert hasattr(sar_temporal_task, "apply_async")

    def test_task_name(self):
        from app.domains.geo.gee_tasks import sar_temporal_task

        assert sar_temporal_task.name == "gee.sar_temporal"

    def test_detect_vv_anomalies_is_importable(self):
        """Verify the pure function is importable from gee_tasks."""
        from app.domains.geo.gee_tasks import detect_vv_anomalies

        assert callable(detect_vv_anomalies)
