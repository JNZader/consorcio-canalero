"""PostgreSQL-ready coverage for atomic GeoJob/outbox producer semantics."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from app.domains.geo.models import EstadoGeoJob, GeoJob, TipoGeoJob
from app.domains.geo.service import dispatch_job
from app.shared.celery_outbox import CeleryTaskKey, CeleryTaskOutbox


pytestmark = pytest.mark.integration


def _factory(test_engine):
    return sessionmaker(bind=test_engine, expire_on_commit=False)


def _cleanup(factory, *, job_id: uuid.UUID | None, celery_task_id: uuid.UUID) -> None:
    with factory() as db:
        db.execute(
            delete(CeleryTaskOutbox).where(CeleryTaskOutbox.celery_task_id == str(celery_task_id))
        )
        if job_id is not None:
            db.execute(delete(GeoJob).where(GeoJob.id == job_id))
        db.commit()


def test_dispatch_persists_job_and_outbox_atomically_before_broker_probe(test_engine) -> None:
    factory = _factory(test_engine)
    task_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    outbox_id = uuid.UUID("44444444-4444-4444-8444-444444444444")
    job_id: uuid.UUID | None = None

    try:
        with factory() as db:
            with (
                patch(
                    "app.domains.geo.service.uuid.uuid4",
                    side_effect=[task_id, outbox_id],
                ),
                patch(
                    "app.domains.geo.service.try_publish_celery_task",
                    return_value=False,
                ) as publish,
            ):
                job = dispatch_job(
                    db,
                    tipo=TipoGeoJob.SLOPE,
                    parametros={"dem_path": "dem.tif", "output_path": "slope.tif"},
                )
            job_id = job.id
            publish.assert_called_once_with(outbox_id)

        with factory() as db:
            stored_job = db.get(GeoJob, job_id)
            intent = db.scalar(
                select(CeleryTaskOutbox).where(CeleryTaskOutbox.celery_task_id == str(task_id))
            )

            assert stored_job is not None
            assert stored_job.estado == EstadoGeoJob.PENDING
            assert stored_job.celery_task_id == str(task_id)
            assert intent is not None
            assert intent.id == outbox_id
            assert intent.task_key == CeleryTaskKey.COMPUTE_SLOPE.value
            assert intent.task_kwargs == {
                "dem_path": "dem.tif",
                "output_path": "slope.tif",
                "job_id": str(job_id),
            }
            assert intent.published_at is None
    finally:
        _cleanup(factory, job_id=job_id, celery_task_id=task_id)


def test_commit_failure_rolls_back_both_job_and_outbox(test_engine) -> None:
    factory = _factory(test_engine)
    task_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    outbox_id = uuid.UUID("66666666-6666-4666-8666-666666666666")

    try:
        with factory() as db:
            real_rollback = db.rollback
            with (
                patch(
                    "app.domains.geo.service.uuid.uuid4",
                    side_effect=[task_id, outbox_id],
                ),
                patch.object(db, "commit", side_effect=RuntimeError("commit failed")),
                patch.object(db, "rollback", wraps=real_rollback) as rollback,
                patch("app.domains.geo.service.try_publish_celery_task") as publish,
            ):
                with pytest.raises(RuntimeError, match="commit failed"):
                    dispatch_job(
                        db,
                        tipo=TipoGeoJob.TWI,
                        parametros={"marker": "atomic-rollback"},
                    )

            rollback.assert_called_once_with()
            publish.assert_not_called()

        with factory() as db:
            assert db.scalar(select(GeoJob).where(GeoJob.celery_task_id == str(task_id))) is None
            assert (
                db.scalar(
                    select(CeleryTaskOutbox).where(CeleryTaskOutbox.celery_task_id == str(task_id))
                )
                is None
            )
    finally:
        _cleanup(factory, job_id=None, celery_task_id=task_id)


def test_unknown_type_fails_before_any_database_write(test_engine) -> None:
    factory = _factory(test_engine)
    with factory() as db:
        with pytest.raises(ValueError, match="Unsupported GeoJob type"):
            dispatch_job(db, tipo="not-a-geo-job", parametros={"marker": "unknown"})

        assert not db.new
        assert not db.dirty
        assert not db.deleted
