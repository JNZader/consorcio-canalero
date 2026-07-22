"""PostgreSQL-ready coverage for atomic AnalisisGeo/outbox submission."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from app.domains.geo.models import AnalisisGeo, EstadoGeoJob, TipoAnalisisGee
from app.domains.geo.repository import GeoRepository
from app.domains.geo.router_misc_support import submit_gee_analysis_impl
from app.shared.celery_outbox import CeleryTaskKey, CeleryTaskOutbox


pytestmark = pytest.mark.integration


def _factory(test_engine):
    return sessionmaker(bind=test_engine, expire_on_commit=False)


def _payload(tipo: TipoAnalisisGee | str, parametros: dict):
    return SimpleNamespace(
        tipo=tipo.value if isinstance(tipo, TipoAnalisisGee) else tipo,
        parametros=parametros,
    )


def _cleanup(
    factory,
    *,
    analysis_id: uuid.UUID | None,
    celery_task_id: uuid.UUID,
) -> None:
    with factory() as db:
        db.execute(
            delete(CeleryTaskOutbox).where(CeleryTaskOutbox.celery_task_id == str(celery_task_id))
        )
        if analysis_id is not None:
            db.execute(delete(AnalisisGeo).where(AnalisisGeo.id == analysis_id))
        db.commit()


def test_submission_persists_analysis_and_outbox_atomically_before_broker_probe(
    test_engine,
) -> None:
    factory = _factory(test_engine)
    task_id = uuid.UUID("77777777-7777-4777-8777-777777777777")
    outbox_id = uuid.UUID("88888888-8888-4888-8888-888888888888")
    analysis_id: uuid.UUID | None = None

    try:
        with factory() as db:
            real_commit = db.commit
            with (
                patch(
                    "app.domains.geo.router_misc_support.uuid.uuid4",
                    side_effect=[task_id, outbox_id],
                ),
                patch.object(db, "commit", wraps=real_commit) as commit,
                patch(
                    "app.domains.geo.router_misc_support.try_publish_celery_task",
                    return_value=False,
                ) as publish,
            ):
                analysis = submit_gee_analysis_impl(
                    _payload(
                        TipoAnalisisGee.CUSTOM,
                        {
                            "start_date": "2026-07-01",
                            "end_date": "2026-07-18",
                            "method": "optical_only",
                        },
                    ),
                    db,
                    GeoRepository(),
                )
            analysis_id = analysis.id
            commit.assert_called_once_with()
            publish.assert_called_once_with(outbox_id)

        with factory() as db:
            stored_analysis = db.get(AnalisisGeo, analysis_id)
            intent = db.scalar(
                select(CeleryTaskOutbox).where(CeleryTaskOutbox.celery_task_id == str(task_id))
            )

            assert stored_analysis is not None
            assert stored_analysis.estado == EstadoGeoJob.PENDING
            assert stored_analysis.celery_task_id == str(task_id)
            assert intent is not None
            assert intent.id == outbox_id
            assert intent.task_key == CeleryTaskKey.ANALYZE_FLOOD.value
            assert intent.task_kwargs == {
                "start_date_str": "2026-07-01",
                "end_date_str": "2026-07-18",
                "method": "optical_only",
                "analisis_id": str(analysis_id),
            }
            assert intent.published_at is None
    finally:
        _cleanup(factory, analysis_id=analysis_id, celery_task_id=task_id)


def test_commit_failure_rolls_back_analysis_and_outbox(test_engine) -> None:
    factory = _factory(test_engine)
    task_id = uuid.UUID("99999999-9999-4999-8999-999999999999")
    outbox_id = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    try:
        with factory() as db:
            real_rollback = db.rollback
            with (
                patch(
                    "app.domains.geo.router_misc_support.uuid.uuid4",
                    side_effect=[task_id, outbox_id],
                ),
                patch.object(db, "commit", side_effect=RuntimeError("commit failed")),
                patch.object(db, "rollback", wraps=real_rollback) as rollback,
                patch("app.domains.geo.router_misc_support.try_publish_celery_task") as publish,
            ):
                with pytest.raises(RuntimeError, match="commit failed"):
                    submit_gee_analysis_impl(
                        _payload(
                            TipoAnalisisGee.SAR_TEMPORAL,
                            {
                                "start_date": "2026-07-01",
                                "end_date": "2026-07-18",
                                "scale": 100,
                            },
                        ),
                        db,
                        GeoRepository(),
                    )

            rollback.assert_called_once_with()
            publish.assert_not_called()

        with factory() as db:
            assert (
                db.scalar(select(AnalisisGeo).where(AnalisisGeo.celery_task_id == str(task_id)))
                is None
            )
            assert (
                db.scalar(
                    select(CeleryTaskOutbox).where(CeleryTaskOutbox.celery_task_id == str(task_id))
                )
                is None
            )
    finally:
        _cleanup(factory, analysis_id=None, celery_task_id=task_id)


def test_invalid_type_fails_before_any_database_write(test_engine) -> None:
    factory = _factory(test_engine)
    with factory() as db:
        with pytest.raises(HTTPException) as exc_info:
            submit_gee_analysis_impl(
                _payload("not-an-analysis", {}),
                db,
                GeoRepository(),
            )

        assert exc_info.value.status_code == 422
        assert not db.new
        assert not db.dirty
        assert not db.deleted
