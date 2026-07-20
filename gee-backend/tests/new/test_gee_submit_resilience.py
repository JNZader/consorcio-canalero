"""Service-free coverage for durable AnalisisGeo outbox submission."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.domains.geo.models import EstadoGeoJob, TipoAnalisisGee
from app.domains.geo.router_misc_support import submit_gee_analysis_impl
from app.shared.celery_outbox import CeleryTaskKey


ANALYSIS_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
TASK_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
OUTBOX_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
START_DATE = "2026-07-01"
END_DATE = "2026-07-18"


def _payload(tipo: TipoAnalisisGee | str, parametros: dict | None = None):
    return SimpleNamespace(
        tipo=tipo.value if isinstance(tipo, TipoAnalisisGee) else tipo,
        parametros=parametros or {},
    )


def _analysis_from_create(_db, **kwargs):
    return SimpleNamespace(
        id=ANALYSIS_ID,
        tipo=kwargs["tipo"],
        fecha_analisis=kwargs["fecha_analisis"],
        parametros=kwargs["parametros"],
        usuario_id=kwargs["usuario_id"],
        estado=EstadoGeoJob.PENDING,
        celery_task_id=kwargs["celery_task_id"],
    )


def test_analysis_task_key_map_covers_every_family_exactly() -> None:
    from app.domains.geo.router_misc_support import _get_gee_task_key_map

    assert _get_gee_task_key_map() == {
        TipoAnalisisGee.FLOOD: CeleryTaskKey.ANALYZE_FLOOD,
        TipoAnalisisGee.VEGETATION: CeleryTaskKey.SUPERVISED_CLASSIFICATION,
        TipoAnalisisGee.CLASSIFICATION: CeleryTaskKey.SUPERVISED_CLASSIFICATION,
        TipoAnalisisGee.NDVI: CeleryTaskKey.SUPERVISED_CLASSIFICATION,
        TipoAnalisisGee.CUSTOM: CeleryTaskKey.ANALYZE_FLOOD,
        TipoAnalisisGee.SAR_TEMPORAL: CeleryTaskKey.SAR_TEMPORAL,
    }


@pytest.mark.parametrize(
    ("tipo", "parametros", "task_key", "expected_task_kwargs"),
    [
        (
            TipoAnalisisGee.FLOOD,
            {"start_date": START_DATE, "end_date": END_DATE, "method": "sar_only"},
            CeleryTaskKey.ANALYZE_FLOOD,
            {
                "start_date_str": START_DATE,
                "end_date_str": END_DATE,
                "method": "sar_only",
            },
        ),
        (
            TipoAnalisisGee.CUSTOM,
            {"start_date": START_DATE, "end_date": END_DATE, "method": "optical_only"},
            CeleryTaskKey.ANALYZE_FLOOD,
            {
                "start_date_str": START_DATE,
                "end_date_str": END_DATE,
                "method": "optical_only",
            },
        ),
        (
            TipoAnalisisGee.VEGETATION,
            {"start_date": START_DATE, "end_date": END_DATE},
            CeleryTaskKey.SUPERVISED_CLASSIFICATION,
            {"start_date_str": START_DATE, "end_date_str": END_DATE},
        ),
        (
            TipoAnalisisGee.CLASSIFICATION,
            {"start_date": START_DATE, "end_date": END_DATE},
            CeleryTaskKey.SUPERVISED_CLASSIFICATION,
            {"start_date_str": START_DATE, "end_date_str": END_DATE},
        ),
        (
            TipoAnalisisGee.NDVI,
            {"start_date": START_DATE, "end_date": END_DATE},
            CeleryTaskKey.SUPERVISED_CLASSIFICATION,
            {"start_date_str": START_DATE, "end_date_str": END_DATE},
        ),
        (
            TipoAnalisisGee.SAR_TEMPORAL,
            {"start_date": START_DATE, "end_date": END_DATE, "scale": 30},
            CeleryTaskKey.SAR_TEMPORAL,
            {"start_date_str": START_DATE, "end_date_str": END_DATE, "scale": 30},
        ),
    ],
)
def test_each_analysis_family_commits_exact_outbox_intent_once_before_publish(
    tipo: TipoAnalisisGee,
    parametros: dict,
    task_key: CeleryTaskKey,
    expected_task_kwargs: dict,
) -> None:
    events: list[str] = []
    db = MagicMock()
    db.commit.side_effect = lambda: events.append("commit")
    db.refresh.side_effect = lambda _analysis: events.append("refresh")
    repo = MagicMock()
    outbox = SimpleNamespace(id=OUTBOX_ID)

    def create_analysis(*args, **kwargs):
        events.append("create")
        return _analysis_from_create(*args, **kwargs)

    def enqueue_task(*_args, **_kwargs):
        events.append("enqueue")
        return outbox

    repo.create_analisis.side_effect = create_analysis
    with (
        patch("app.domains.geo.router_misc_support.uuid.uuid4", return_value=TASK_ID),
        patch(
            "app.domains.geo.router_misc_support.enqueue_celery_task",
            side_effect=enqueue_task,
        ) as enqueue,
        patch(
            "app.domains.geo.router_misc_support.try_publish_celery_task",
            side_effect=lambda _outbox_id: events.append("publish") or False,
        ) as publish,
    ):
        returned = submit_gee_analysis_impl(_payload(tipo, parametros), db, repo)

    assert returned.estado == EstadoGeoJob.PENDING
    assert returned.celery_task_id == str(TASK_ID)
    assert events == ["create", "enqueue", "commit", "refresh", "publish"]

    create_kwargs = repo.create_analisis.call_args.kwargs
    assert create_kwargs["tipo"] == tipo
    assert create_kwargs["parametros"] == parametros
    assert create_kwargs["usuario_id"] is None
    assert create_kwargs["celery_task_id"] == str(TASK_ID)
    assert isinstance(create_kwargs["fecha_analisis"], date)
    enqueue.assert_called_once_with(
        db,
        celery_task_id=TASK_ID,
        task_key=task_key,
        task_kwargs={**expected_task_kwargs, "analisis_id": str(ANALYSIS_ID)},
    )
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(returned)
    db.rollback.assert_not_called()
    publish.assert_called_once_with(OUTBOX_ID)
    repo.update_analisis_metadata.assert_not_called()
    repo.update_analisis_status_if_current.assert_not_called()


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        (_payload("not-an-analysis"), "Tipo invalido"),
        (
            _payload(
                TipoAnalisisGee.SAR_TEMPORAL,
                {"start_date": "not-a-date", "end_date": END_DATE, "scale": 100},
            ),
            "YYYY-MM-DD",
        ),
        (
            _payload(
                TipoAnalisisGee.FLOOD,
                {"start_date": "2026-07-19", "end_date": "2026-07-18"},
            ),
            "anterior",
        ),
        (
            _payload(
                TipoAnalisisGee.FLOOD,
                {"start_date": START_DATE, "end_date": END_DATE, "method": "invalid"},
            ),
            "method invalido",
        ),
        (
            _payload(
                TipoAnalisisGee.CUSTOM,
                {"start_date": START_DATE, "end_date": END_DATE, "method": []},
            ),
            "method invalido",
        ),
        (
            _payload(
                TipoAnalisisGee.SAR_TEMPORAL,
                {"start_date": START_DATE, "end_date": END_DATE, "scale": "invalid"},
            ),
            "scale debe ser un entero",
        ),
        (
            _payload(
                TipoAnalisisGee.SAR_TEMPORAL,
                {"start_date": START_DATE, "end_date": END_DATE, "scale": 0},
            ),
            "scale fuera de rango",
        ),
        (
            _payload(
                TipoAnalisisGee.SAR_TEMPORAL,
                {"start_date": START_DATE, "end_date": END_DATE, "scale": 10_001},
            ),
            "scale fuera de rango",
        ),
    ],
)
def test_invalid_submission_is_rejected_before_persistence(payload, detail: str) -> None:
    db = MagicMock()
    repo = MagicMock()
    with (
        patch("app.domains.geo.router_misc_support.enqueue_celery_task") as enqueue,
        patch("app.domains.geo.router_misc_support.try_publish_celery_task") as publish,
        pytest.raises(HTTPException) as exc_info,
    ):
        submit_gee_analysis_impl(payload, db, repo)

    assert exc_info.value.status_code == 422
    assert detail in str(exc_info.value.detail)
    repo.create_analisis.assert_not_called()
    enqueue.assert_not_called()
    db.commit.assert_not_called()
    publish.assert_not_called()


def test_missing_allowlist_mapping_fails_before_persistence() -> None:
    db = MagicMock()
    repo = MagicMock()
    with (
        patch("app.domains.geo.router_misc_support._get_gee_task_key_map", return_value={}),
        patch("app.domains.geo.router_misc_support.enqueue_celery_task") as enqueue,
        pytest.raises(RuntimeError, match="Unsupported GEE analysis task mapping"),
    ):
        submit_gee_analysis_impl(
            _payload(
                TipoAnalisisGee.FLOOD,
                {"start_date": START_DATE, "end_date": END_DATE},
            ),
            db,
            repo,
        )

    repo.create_analisis.assert_not_called()
    enqueue.assert_not_called()
    db.commit.assert_not_called()


def test_commit_failure_rolls_back_analysis_and_intent_without_publication() -> None:
    commit_error = RuntimeError("commit failed")
    db = MagicMock()
    db.commit.side_effect = commit_error
    repo = MagicMock()
    repo.create_analisis.side_effect = _analysis_from_create

    with (
        patch("app.domains.geo.router_misc_support.uuid.uuid4", return_value=TASK_ID),
        patch(
            "app.domains.geo.router_misc_support.enqueue_celery_task",
            return_value=SimpleNamespace(id=OUTBOX_ID),
        ) as enqueue,
        patch("app.domains.geo.router_misc_support.try_publish_celery_task") as publish,
        pytest.raises(RuntimeError) as raised,
    ):
        submit_gee_analysis_impl(
            _payload(
                TipoAnalisisGee.SAR_TEMPORAL,
                {"start_date": START_DATE, "end_date": END_DATE, "scale": 100},
            ),
            db,
            repo,
        )

    assert raised.value is commit_error
    enqueue.assert_called_once()
    db.rollback.assert_called_once_with()
    db.refresh.assert_not_called()
    publish.assert_not_called()
    repo.update_analisis_metadata.assert_not_called()
    repo.update_analisis_status_if_current.assert_not_called()


def test_rollback_failure_does_not_mask_commit_failure() -> None:
    commit_error = RuntimeError("commit failed")
    db = MagicMock()
    db.commit.side_effect = commit_error
    db.rollback.side_effect = RuntimeError("rollback failed")
    repo = MagicMock()
    repo.create_analisis.side_effect = _analysis_from_create

    with (
        patch("app.domains.geo.router_misc_support.uuid.uuid4", return_value=TASK_ID),
        patch(
            "app.domains.geo.router_misc_support.enqueue_celery_task",
            return_value=SimpleNamespace(id=OUTBOX_ID),
        ),
        patch("app.domains.geo.router_misc_support.try_publish_celery_task") as publish,
        pytest.raises(RuntimeError) as raised,
    ):
        submit_gee_analysis_impl(
            _payload(
                TipoAnalisisGee.CLASSIFICATION,
                {"start_date": START_DATE, "end_date": END_DATE},
            ),
            db,
            repo,
        )

    assert raised.value is commit_error
    publish.assert_not_called()


def test_broker_ambiguity_returns_durable_pending_without_compensation_or_503() -> None:
    db = MagicMock()
    repo = MagicMock()
    repo.create_analisis.side_effect = _analysis_from_create

    with (
        patch("app.domains.geo.router_misc_support.uuid.uuid4", return_value=TASK_ID),
        patch(
            "app.domains.geo.router_misc_support.enqueue_celery_task",
            return_value=SimpleNamespace(id=OUTBOX_ID),
        ),
        patch(
            "app.domains.geo.router_misc_support.try_publish_celery_task",
            side_effect=ConnectionError("broker password=secret"),
        ),
    ):
        returned = submit_gee_analysis_impl(
            _payload(
                TipoAnalisisGee.SAR_TEMPORAL,
                {"start_date": START_DATE, "end_date": END_DATE, "scale": 100},
            ),
            db,
            repo,
        )

    assert returned.estado == EstadoGeoJob.PENDING
    assert returned.celery_task_id == str(TASK_ID)
    db.commit.assert_called_once_with()
    repo.update_analisis_metadata.assert_not_called()
    repo.update_analisis_status_if_current.assert_not_called()
