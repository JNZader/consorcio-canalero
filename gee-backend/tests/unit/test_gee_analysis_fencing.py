from __future__ import annotations

import sys
import uuid
from unittest.mock import MagicMock, call, patch

import pytest

from app.domains.geo.gee_tasks import (
    _update_tracking,
    analyze_flood_task,
    sar_temporal_task,
    supervised_classification_task,
)
from app.domains.geo.models import EstadoGeoJob
from app.domains.geo.repository import GeoRepository


def _runner(task):
    return getattr(task, "run", task)


WORKER_CASES = (
    pytest.param(
        analyze_flood_task,
        {
            "start_date_str": "2026-07-01",
            "end_date_str": "2026-07-18",
            "method": "fusion",
        },
        "build_flood_analysis_result",
        {},
        id="flood",
    ),
    pytest.param(
        supervised_classification_task,
        {
            "start_date_str": "2026-07-01",
            "end_date_str": "2026-07-18",
        },
        "build_classification_result",
        {},
        id="classification",
    ),
    pytest.param(
        sar_temporal_task,
        {
            "start_date_str": "2026-07-01",
            "end_date_str": "2026-07-18",
            "scale": 100,
        },
        "build_sar_temporal_result",
        {"image_count": 1, "status": "completed"},
        id="sar-temporal",
    ),
)


def test_repository_analisis_compare_and_set_reports_single_atomic_claim() -> None:
    db = MagicMock()
    db.execute.return_value.rowcount = 1
    repo = GeoRepository()

    assert repo.update_analisis_status_if_current(
        db,
        uuid.uuid4(),
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )

    db.execute.return_value.rowcount = 0
    assert not repo.update_analisis_status_if_current(
        db,
        uuid.uuid4(),
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )


def test_update_tracking_selects_analisis_cas_without_progress() -> None:
    db = MagicMock()
    repo = MagicMock()
    repo.update_analisis_status_if_current.return_value = True
    deps = {
        "SessionLocal": MagicMock(return_value=db),
        "EstadoGeoJob": EstadoGeoJob,
        "repo": repo,
    }
    analisis_id = str(uuid.uuid4())

    with patch("app.domains.geo.gee_tasks._get_deps", return_value=deps):
        assert _update_tracking(
            analisis_id=analisis_id,
            job_id=None,
            expected_estado=EstadoGeoJob.RUNNING,
            estado=EstadoGeoJob.COMPLETED,
            progreso=100,
            resultado={"ok": True},
        )

    repo.update_analisis_status_if_current.assert_called_once_with(
        db,
        uuid.UUID(analisis_id),
        expected_estado=EstadoGeoJob.RUNNING,
        estado=EstadoGeoJob.COMPLETED,
        resultado={"ok": True},
        error=None,
    )
    repo.update_job_status_if_current.assert_not_called()
    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_update_tracking_selects_geojob_cas_with_progress() -> None:
    db = MagicMock()
    repo = MagicMock()
    repo.update_job_status_if_current.return_value = True
    deps = {
        "SessionLocal": MagicMock(return_value=db),
        "EstadoGeoJob": EstadoGeoJob,
        "repo": repo,
    }
    job_id = str(uuid.uuid4())

    with patch("app.domains.geo.gee_tasks._get_deps", return_value=deps):
        assert _update_tracking(
            analisis_id=None,
            job_id=job_id,
            expected_estado=EstadoGeoJob.RUNNING,
            estado=EstadoGeoJob.COMPLETED,
            progreso=100,
            resultado={"ok": True},
        )

    repo.update_job_status_if_current.assert_called_once_with(
        db,
        uuid.UUID(job_id),
        expected_estado=EstadoGeoJob.RUNNING,
        estado=EstadoGeoJob.COMPLETED,
        progreso=100,
        resultado={"ok": True},
        error=None,
    )
    repo.update_analisis_status_if_current.assert_not_called()
    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_update_tracking_rejects_both_ids_before_opening_session() -> None:
    with patch("app.domains.geo.gee_tasks._get_deps") as get_deps:
        with pytest.raises(ValueError, match="mutually exclusive"):
            _update_tracking(
                analisis_id=str(uuid.uuid4()),
                job_id=str(uuid.uuid4()),
                expected_estado=EstadoGeoJob.PENDING,
                estado=EstadoGeoJob.RUNNING,
            )

    get_deps.assert_not_called()


@pytest.mark.parametrize(("task", "kwargs", "_builder_name", "_result"), WORKER_CASES)
def test_failed_claim_exits_each_worker_before_gee(
    task,
    kwargs,
    _builder_name,
    _result,
) -> None:
    analisis_id = str(uuid.uuid4())
    deps = {"EstadoGeoJob": EstadoGeoJob}

    with (
        patch("app.domains.geo.gee_tasks._get_deps", return_value=deps),
        patch("app.domains.geo.gee_tasks._update_tracking", return_value=False) as transition,
        patch("app.domains.geo.gee_tasks._get_gee") as get_gee,
    ):
        result = _runner(task)(**kwargs, analisis_id=analisis_id)

    assert result == {"status": "skipped", "analisis_id": analisis_id}
    transition.assert_called_once_with(
        analisis_id=analisis_id,
        job_id=None,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )
    get_gee.assert_not_called()


@pytest.mark.parametrize(("task", "kwargs", "builder_name", "builder_result"), WORKER_CASES)
def test_duplicate_delivery_with_same_future_task_id_executes_worker_once(
    task,
    kwargs,
    builder_name,
    builder_result,
) -> None:
    analisis_id = str(uuid.uuid4())
    task_kwargs = {**kwargs, "analisis_id": analisis_id}
    deterministic_task_id = f"gee-analysis:{analisis_id}"
    deps = {"EstadoGeoJob": EstadoGeoJob}
    explorer = MagicMock()

    with (
        patch("app.domains.geo.gee_tasks._get_deps", return_value=deps),
        patch(
            "app.domains.geo.gee_tasks._update_tracking",
            side_effect=[True, True, False],
        ) as transition,
        patch(
            "app.domains.geo.gee_tasks._get_gee",
            return_value={"explorer": explorer},
        ) as get_gee,
        patch(
            f"app.domains.geo.gee_tasks.{builder_name}",
            return_value=dict(builder_result),
        ) as builder,
        patch.dict(sys.modules, {"ee": MagicMock()}),
    ):
        first = task.apply(kwargs=task_kwargs, task_id=deterministic_task_id)
        duplicate = task.apply(kwargs=task_kwargs, task_id=deterministic_task_id)

    assert first.successful()
    assert first.get()["status"] == "completed"
    assert duplicate.successful()
    assert duplicate.get() == {"status": "skipped", "analisis_id": analisis_id}
    assert transition.call_count == 3
    assert transition.call_args_list[0] == call(
        analisis_id=analisis_id,
        job_id=None,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )
    completion_call = transition.call_args_list[1]
    assert completion_call.kwargs["expected_estado"] == EstadoGeoJob.RUNNING
    assert completion_call.kwargs["estado"] == EstadoGeoJob.COMPLETED
    assert transition.call_args_list[2] == transition.call_args_list[0]
    get_gee.assert_called_once()
    builder.assert_called_once()


@pytest.mark.parametrize(("task", "kwargs", "builder_name", "_builder_result"), WORKER_CASES)
def test_worker_failure_write_requires_running(
    task,
    kwargs,
    builder_name,
    _builder_result,
) -> None:
    analisis_id = str(uuid.uuid4())
    deps = {"EstadoGeoJob": EstadoGeoJob}
    failure = RuntimeError("GEE failed")

    with (
        patch("app.domains.geo.gee_tasks._get_deps", return_value=deps),
        patch(
            "app.domains.geo.gee_tasks._update_tracking",
            side_effect=[True, True],
        ) as transition,
        patch(
            "app.domains.geo.gee_tasks._get_gee",
            return_value={"explorer": MagicMock()},
        ),
        patch(
            f"app.domains.geo.gee_tasks.{builder_name}",
            side_effect=failure,
        ),
        patch.dict(sys.modules, {"ee": MagicMock()}),
    ):
        with pytest.raises(RuntimeError, match="GEE failed"):
            _runner(task)(**kwargs, analisis_id=analisis_id)

    assert transition.call_count == 2
    assert transition.call_args_list[0] == call(
        analisis_id=analisis_id,
        job_id=None,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )
    failure_call = transition.call_args_list[1]
    assert failure_call.kwargs["expected_estado"] == EstadoGeoJob.RUNNING
    assert failure_call.kwargs["estado"] == EstadoGeoJob.FAILED
    assert "RuntimeError: GEE failed" in failure_call.kwargs["error"]


@pytest.mark.parametrize(
    ("task", "kwargs"),
    (
        pytest.param(
            analyze_flood_task,
            {
                "start_date_str": "2026-07-01",
                "end_date_str": "2026-07-18",
                "method": "fusion",
            },
            id="flood",
        ),
        pytest.param(
            supervised_classification_task,
            {
                "start_date_str": "2026-07-01",
                "end_date_str": "2026-07-18",
            },
            id="classification",
        ),
    ),
)
def test_job_id_only_worker_uses_existing_geojob_claim(task, kwargs) -> None:
    job_id = str(uuid.uuid4())
    deps = {"EstadoGeoJob": EstadoGeoJob}

    with (
        patch("app.domains.geo.gee_tasks._get_deps", return_value=deps),
        patch("app.domains.geo.gee_tasks._update_tracking", return_value=False) as transition,
        patch("app.domains.geo.gee_tasks._get_gee") as get_gee,
    ):
        result = _runner(task)(**kwargs, job_id=job_id)

    assert result == {"status": "skipped", "job_id": job_id}
    transition.assert_called_once_with(
        analisis_id=None,
        job_id=job_id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )
    get_gee.assert_not_called()
