"""GEE analysis submission must validate before persistence and compensate dispatch failures."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.domains.geo.models import EstadoGeoJob, TipoAnalisisGee
from app.domains.geo.router_misc_support import submit_gee_analysis_impl


@pytest.mark.parametrize(
    "start_date,end_date",
    [
        ("not-a-date", "2026-07-18"),
        ("2026-07-19", "2026-07-18"),
    ],
)
def test_invalid_dates_are_rejected_before_analysis_is_persisted(start_date, end_date) -> None:
    payload = SimpleNamespace(
        tipo=TipoAnalisisGee.SAR_TEMPORAL.value,
        parametros={"start_date": start_date, "end_date": end_date, "scale": 100},
    )
    db = MagicMock()
    repo = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        submit_gee_analysis_impl(payload, db, repo)

    assert exc_info.value.status_code == 422
    repo.create_analisis.assert_not_called()
    db.commit.assert_not_called()


def test_broker_dispatch_failure_marks_persisted_analysis_failed() -> None:
    analysis = SimpleNamespace(id=uuid.uuid4())
    payload = SimpleNamespace(
        tipo=TipoAnalisisGee.SAR_TEMPORAL.value,
        parametros={"start_date": "2026-07-01", "end_date": "2026-07-18", "scale": 100},
    )
    db = MagicMock()
    repo = MagicMock()
    repo.create_analisis.return_value = analysis

    with patch(
        "app.domains.geo.gee_tasks.sar_temporal_task.delay",
        side_effect=ConnectionError("broker unavailable"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            submit_gee_analysis_impl(payload, db, repo)

    assert exc_info.value.status_code == 503
    assert db.commit.call_count == 2
    repo.update_analisis_status.assert_called_once()
    update_kwargs = repo.update_analisis_status.call_args.kwargs
    assert update_kwargs["estado"] == EstadoGeoJob.FAILED
    assert "encolar" in update_kwargs["error"].lower()
