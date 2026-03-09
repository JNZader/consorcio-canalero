from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.services import gee_analysis_tasks


def test_analyze_flood_task_runs_classification_with_parsed_dates():
    monitoring = MagicMock()
    monitoring.classify_parcels.return_value = {"ok": True}

    with patch.object(gee_analysis_tasks, "get_monitoring_service", return_value=monitoring):
        result = gee_analysis_tasks.analyze_flood_task.run(
            "2026-01-01",
            "2026-01-10",
            "fusion",
        )

    assert result == {"ok": True}
    monitoring.classify_parcels.assert_called_once_with(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 10),
        layer_name="zona",
    )


def test_analyze_flood_task_re_raises_errors():
    monitoring = MagicMock()
    monitoring.classify_parcels.side_effect = RuntimeError("gee error")

    with patch.object(gee_analysis_tasks, "get_monitoring_service", return_value=monitoring):
        with pytest.raises(RuntimeError, match="gee error"):
            gee_analysis_tasks.analyze_flood_task.run(
                "2026-01-01",
                "2026-01-10",
            )


def test_supervised_classification_task_runs_cuenca_classification():
    monitoring = MagicMock()
    monitoring.classify_parcels_by_cuenca.return_value = {"cuencas": {"norte": {}}}

    with patch.object(gee_analysis_tasks, "get_monitoring_service", return_value=monitoring):
        result = gee_analysis_tasks.supervised_classification_task.run(
            "2026-02-01",
            "2026-02-28",
        )

    assert result["cuencas"] == {"norte": {}}
    monitoring.classify_parcels_by_cuenca.assert_called_once_with(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )


def test_supervised_classification_task_re_raises_errors():
    monitoring = MagicMock()
    monitoring.classify_parcels_by_cuenca.side_effect = ValueError("bad range")

    with patch.object(gee_analysis_tasks, "get_monitoring_service", return_value=monitoring):
        with pytest.raises(ValueError, match="bad range"):
            gee_analysis_tasks.supervised_classification_task.run(
                "2026-02-01",
                "2026-02-28",
            )
