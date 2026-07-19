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
    publication_error = ConnectionError("broker unavailable")

    with patch(
        "app.domains.geo.gee_tasks.sar_temporal_task.delay",
        side_effect=publication_error,
    ):
        with pytest.raises(HTTPException) as exc_info:
            submit_gee_analysis_impl(payload, db, repo)

    assert exc_info.value.status_code == 503
    assert exc_info.value.__cause__ is publication_error
    assert db.commit.call_count == 2
    repo.update_analisis_status_if_current.assert_called_once_with(
        db,
        analysis.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.FAILED,
        error="No se pudo encolar el análisis GEE; reintente más tarde",
    )
    repo.update_analisis_metadata.assert_not_called()
    db.rollback.assert_not_called()


def test_repository_compensation_failure_never_masks_broker_error() -> None:
    analysis = SimpleNamespace(id=uuid.uuid4(), estado=EstadoGeoJob.PENDING)
    payload = SimpleNamespace(
        tipo=TipoAnalisisGee.SAR_TEMPORAL.value,
        parametros={"start_date": "2026-07-01", "end_date": "2026-07-18", "scale": 100},
    )
    db = MagicMock()
    repo = MagicMock()
    repo.create_analisis.return_value = analysis
    persistence_error = RuntimeError("database unavailable")
    repo.update_analisis_status_if_current.side_effect = persistence_error
    publication_error = ConnectionError("broker unavailable")

    def publish(*_args, **_kwargs):
        analysis.estado = EstadoGeoJob.RUNNING
        raise publication_error

    with (
        patch(
            "app.domains.geo.gee_tasks.sar_temporal_task.delay",
            side_effect=publish,
        ),
        patch("app.domains.geo.router_misc_support.logger") as logger,
        pytest.raises(HTTPException) as exc_info,
    ):
        submit_gee_analysis_impl(payload, db, repo)

    assert exc_info.value.status_code == 503
    assert exc_info.value.__cause__ is publication_error
    assert analysis.estado == EstadoGeoJob.RUNNING
    assert db.commit.call_count == 1
    db.rollback.assert_called_once_with()
    repo.update_analisis_metadata.assert_not_called()
    logger.exception.assert_called_once_with(
        "gee_analysis.publication_failure_persist_failed",
        analisis_id=str(analysis.id),
        publication_error=str(publication_error),
        persistence_error=str(persistence_error),
    )


def test_compensation_commit_failure_never_masks_broker_error() -> None:
    analysis = SimpleNamespace(id=uuid.uuid4(), estado=EstadoGeoJob.PENDING)
    payload = SimpleNamespace(
        tipo=TipoAnalisisGee.SAR_TEMPORAL.value,
        parametros={"start_date": "2026-07-01", "end_date": "2026-07-18", "scale": 100},
    )
    db = MagicMock()
    repo = MagicMock()
    repo.create_analisis.return_value = analysis
    repo.update_analisis_status_if_current.return_value = True
    persistence_error = RuntimeError("commit failed")
    db.commit.side_effect = [None, persistence_error]
    publication_error = ConnectionError("broker unavailable")

    def publish(*_args, **_kwargs):
        analysis.estado = EstadoGeoJob.RUNNING
        raise publication_error

    with (
        patch(
            "app.domains.geo.gee_tasks.sar_temporal_task.delay",
            side_effect=publish,
        ),
        patch("app.domains.geo.router_misc_support.logger") as logger,
        pytest.raises(HTTPException) as exc_info,
    ):
        submit_gee_analysis_impl(payload, db, repo)

    assert exc_info.value.status_code == 503
    assert exc_info.value.__cause__ is publication_error
    assert analysis.estado == EstadoGeoJob.RUNNING
    assert db.commit.call_count == 2
    db.rollback.assert_called_once_with()
    repo.update_analisis_metadata.assert_not_called()
    logger.exception.assert_called_once_with(
        "gee_analysis.publication_failure_persist_failed",
        analisis_id=str(analysis.id),
        publication_error=str(publication_error),
        persistence_error=str(persistence_error),
    )


def test_ambiguous_publish_failure_does_not_overwrite_fast_running_analysis() -> None:
    analysis = SimpleNamespace(id=uuid.uuid4(), estado=EstadoGeoJob.PENDING)
    payload = SimpleNamespace(
        tipo=TipoAnalisisGee.SAR_TEMPORAL.value,
        parametros={"start_date": "2026-07-01", "end_date": "2026-07-18", "scale": 100},
    )
    db = MagicMock()
    repo = MagicMock()
    repo.create_analisis.return_value = analysis
    repo.update_analisis_status_if_current.return_value = False

    def publish(*_args, **_kwargs):
        analysis.estado = EstadoGeoJob.RUNNING
        raise ConnectionError("broker result was ambiguous")

    with patch(
        "app.domains.geo.gee_tasks.sar_temporal_task.delay",
        side_effect=publish,
    ):
        with pytest.raises(HTTPException) as exc_info:
            submit_gee_analysis_impl(payload, db, repo)

    assert exc_info.value.status_code == 503
    assert analysis.estado == EstadoGeoJob.RUNNING
    repo.update_analisis_status_if_current.assert_called_once_with(
        db,
        analysis.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.FAILED,
        error="No se pudo encolar el análisis GEE; reintente más tarde",
    )
    repo.update_analisis_metadata.assert_not_called()


def test_fast_worker_state_survives_unconditional_task_metadata_update() -> None:
    analysis = SimpleNamespace(id=uuid.uuid4(), estado=EstadoGeoJob.PENDING)
    payload = SimpleNamespace(
        tipo=TipoAnalisisGee.SAR_TEMPORAL.value,
        parametros={"start_date": "2026-07-01", "end_date": "2026-07-18", "scale": 100},
    )
    db = MagicMock()
    repo = MagicMock()
    repo.create_analisis.return_value = analysis
    task = SimpleNamespace(id="gee-analysis-deterministic-id")

    def publish(*_args, **_kwargs):
        analysis.estado = EstadoGeoJob.RUNNING
        return task

    with patch(
        "app.domains.geo.gee_tasks.sar_temporal_task.delay",
        side_effect=publish,
    ):
        returned = submit_gee_analysis_impl(payload, db, repo)

    assert returned is analysis
    assert analysis.estado == EstadoGeoJob.RUNNING
    repo.update_analisis_metadata.assert_called_once_with(
        db,
        analysis.id,
        celery_task_id=task.id,
    )
    repo.update_analisis_status_if_current.assert_not_called()
    assert db.commit.call_count == 2
