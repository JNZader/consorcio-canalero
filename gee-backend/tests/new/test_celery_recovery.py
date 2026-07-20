"""Regression tests for worker-loss delivery and stale geo-job recovery."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import uuid

from app.core.celery_app import celery_app
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401
from app.domains.geo.models import (
    AnalisisGeo,
    EstadoGeoJob,
    GeoJob,
    TipoAnalisisGee,
    TipoGeoJob,
)


def test_delivery_policy_is_scoped_and_timeouts_are_compatible() -> None:
    from app.core.celery_app import (
        CELERY_VISIBILITY_TIMEOUT_SECONDS,
        GEO_STALE_JOB_MINUTES,
        LONG_TASK_SOFT_TIME_LIMIT_SECONDS,
        LONG_TASK_TIME_LIMIT_SECONDS,
        RECOVERABLE_LONG_TASKS,
    )

    assert celery_app.conf.task_acks_late is False
    assert celery_app.conf.task_reject_on_worker_lost is False
    assert celery_app.conf.worker_prefetch_multiplier == 1

    annotations = celery_app.conf.task_annotations
    non_idempotent = {
        "geo.intelligence.calculate_hci_all",
        "geo.intelligence.detect_all_conflicts",
        "geo.intelligence.generate_zonification",
    }
    assert non_idempotent.isdisjoint(annotations)
    assert {
        "geo.process_dem_pipeline",
        "geo.run_full_dem_pipeline",
        "gee.analyze_flood",
        "gee.supervised_classification",
        "gee.sar_temporal",
    } <= RECOVERABLE_LONG_TASKS

    for task_name in RECOVERABLE_LONG_TASKS:
        policy = annotations[task_name]
        assert policy["acks_late"] is True
        assert policy["acks_on_failure_or_timeout"] is True
        assert policy["reject_on_worker_lost"] is True
        assert policy["soft_time_limit"] == LONG_TASK_SOFT_TIME_LIMIT_SECONDS
        assert policy["time_limit"] == LONG_TASK_TIME_LIMIT_SECONDS

    assert 600 < LONG_TASK_SOFT_TIME_LIMIT_SECONDS < LONG_TASK_TIME_LIMIT_SECONDS
    assert LONG_TASK_TIME_LIMIT_SECONDS < CELERY_VISIBILITY_TIMEOUT_SECONDS
    assert CELERY_VISIBILITY_TIMEOUT_SECONDS < GEO_STALE_JOB_MINUTES * 60
    assert celery_app.conf.broker_transport_options["visibility_timeout"] == (
        CELERY_VISIBILITY_TIMEOUT_SECONDS
    )


def test_reconcile_stale_geo_jobs_respects_outbox_publication_state(db) -> None:
    from app.domains.geo.reconciliation import reconcile_stale_geo_jobs
    from app.shared.celery_outbox import CeleryTaskKey, enqueue_celery_task

    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    stale_at = now - timedelta(hours=2)
    recent_at = now - timedelta(minutes=5)

    def add_outboxed_job(
        tipo: TipoGeoJob,
        *,
        estado: EstadoGeoJob = EstadoGeoJob.PENDING,
        published_at: datetime | None = None,
    ) -> GeoJob:
        task_id = uuid.uuid4()
        job = GeoJob(
            id=uuid.uuid4(),
            tipo=tipo,
            estado=estado,
            celery_task_id=str(task_id),
            updated_at=stale_at,
        )
        db.add(job)
        intent = enqueue_celery_task(
            db,
            celery_task_id=task_id,
            task_key=CeleryTaskKey.PROCESS_DEM_PIPELINE,
            task_kwargs={"job_id": str(job.id)},
        )
        intent.published_at = published_at
        return job

    def add_outboxed_analysis(
        tipo: TipoAnalisisGee,
        *,
        estado: EstadoGeoJob = EstadoGeoJob.PENDING,
        published_at: datetime | None = None,
    ) -> AnalisisGeo:
        task_id = uuid.uuid4()
        analysis = AnalisisGeo(
            id=uuid.uuid4(),
            tipo=tipo,
            fecha_analisis=date.today(),
            estado=estado,
            celery_task_id=str(task_id),
            updated_at=stale_at,
        )
        db.add(analysis)
        intent = enqueue_celery_task(
            db,
            celery_task_id=task_id,
            task_key=CeleryTaskKey.ANALYZE_FLOOD,
            task_kwargs={"analisis_id": str(analysis.id)},
        )
        intent.published_at = published_at
        return analysis

    unpublished = add_outboxed_job(TipoGeoJob.DEM_PIPELINE)
    recently_published = add_outboxed_job(
        TipoGeoJob.SLOPE,
        published_at=recent_at,
    )
    stale_published = add_outboxed_job(
        TipoGeoJob.ASPECT,
        published_at=stale_at,
    )
    stale_running = add_outboxed_job(
        TipoGeoJob.DEM_FULL_PIPELINE,
        estado=EstadoGeoJob.RUNNING,
    )
    legacy_pending = GeoJob(
        tipo=TipoGeoJob.TWI,
        estado=EstadoGeoJob.PENDING,
        updated_at=stale_at,
    )
    recent_pending = GeoJob(
        tipo=TipoGeoJob.HAND,
        estado=EstadoGeoJob.PENDING,
        updated_at=recent_at,
    )
    completed_job = GeoJob(
        tipo=TipoGeoJob.FLOW_ACC,
        estado=EstadoGeoJob.COMPLETED,
        updated_at=stale_at,
    )
    unpublished_analysis = add_outboxed_analysis(TipoAnalisisGee.FLOOD)
    recently_published_analysis = add_outboxed_analysis(
        TipoAnalisisGee.CLASSIFICATION,
        published_at=recent_at,
    )
    stale_published_analysis = add_outboxed_analysis(
        TipoAnalisisGee.CUSTOM,
        published_at=stale_at,
    )
    stale_running_analysis = add_outboxed_analysis(
        TipoAnalisisGee.SAR_TEMPORAL,
        estado=EstadoGeoJob.RUNNING,
    )
    legacy_pending_analysis = AnalisisGeo(
        tipo=TipoAnalisisGee.VEGETATION,
        fecha_analisis=date.today(),
        estado=EstadoGeoJob.PENDING,
        updated_at=stale_at,
    )
    recent_pending_analysis = AnalisisGeo(
        tipo=TipoAnalisisGee.NDVI,
        fecha_analisis=date.today(),
        estado=EstadoGeoJob.PENDING,
        updated_at=recent_at,
    )
    completed_analysis = AnalisisGeo(
        tipo=TipoAnalisisGee.CLASSIFICATION,
        fecha_analisis=date.today(),
        estado=EstadoGeoJob.COMPLETED,
        updated_at=stale_at,
    )
    db.add_all(
        [
            legacy_pending,
            recent_pending,
            completed_job,
            legacy_pending_analysis,
            recent_pending_analysis,
            completed_analysis,
        ]
    )
    db.flush()

    reconciled = reconcile_stale_geo_jobs(
        db,
        now=now,
        stale_after=timedelta(minutes=90),
    )
    db.flush()
    for tracker in (
        unpublished,
        recently_published,
        stale_published,
        stale_running,
        legacy_pending,
        recent_pending,
        completed_job,
        unpublished_analysis,
        recently_published_analysis,
        stale_published_analysis,
        stale_running_analysis,
        legacy_pending_analysis,
        recent_pending_analysis,
        completed_analysis,
    ):
        db.refresh(tracker)

    assert reconciled == {"geo_jobs": 3, "gee_analyses": 3}
    assert unpublished.estado == EstadoGeoJob.PENDING
    assert recently_published.estado == EstadoGeoJob.PENDING
    assert stale_running.estado == EstadoGeoJob.FAILED
    assert "stale" in (stale_running.error or "").lower()
    assert recent_pending.estado == EstadoGeoJob.PENDING
    assert completed_job.estado == EstadoGeoJob.COMPLETED

    assert stale_published.estado == EstadoGeoJob.FAILED
    assert "stale" in (stale_published.error or "").lower()
    assert legacy_pending.estado == EstadoGeoJob.FAILED
    assert "stale" in (legacy_pending.error or "").lower()

    assert unpublished_analysis.estado == EstadoGeoJob.PENDING
    assert recently_published_analysis.estado == EstadoGeoJob.PENDING
    assert recent_pending_analysis.estado == EstadoGeoJob.PENDING
    assert completed_analysis.estado == EstadoGeoJob.COMPLETED

    assert stale_published_analysis.estado == EstadoGeoJob.FAILED
    assert "stale" in (stale_published_analysis.error or "").lower()
    assert stale_running_analysis.estado == EstadoGeoJob.FAILED
    assert "stale" in (stale_running_analysis.error or "").lower()
    assert legacy_pending_analysis.estado == EstadoGeoJob.FAILED
    assert "stale" in (legacy_pending_analysis.error or "").lower()


def test_reconciliation_terminalizes_worker_loss_and_fences_redelivery(db) -> None:
    from app.domains.geo.reconciliation import reconcile_stale_geo_jobs
    from app.domains.geo.repository import GeoRepository
    from app.shared.celery_outbox import CeleryTaskKey, enqueue_celery_task

    repo = GeoRepository()
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    task_id = uuid.uuid4()
    orphaned = GeoJob(
        id=uuid.uuid4(),
        tipo=TipoGeoJob.DEM_FULL_PIPELINE,
        estado=EstadoGeoJob.RUNNING,
        celery_task_id=str(task_id),
        parametros={"area_id": "worker-loss"},
        updated_at=now - timedelta(hours=2),
    )
    db.add(orphaned)
    intent = enqueue_celery_task(
        db,
        celery_task_id=task_id,
        task_key=CeleryTaskKey.RUN_FULL_DEM_PIPELINE,
        task_kwargs={"area_id": "worker-loss", "job_id": str(orphaned.id)},
    )
    intent.published_at = now - timedelta(minutes=5)
    db.flush()

    reconciled = reconcile_stale_geo_jobs(
        db,
        now=now,
        stale_after=timedelta(minutes=90),
    )
    db.flush()
    db.refresh(orphaned)

    assert reconciled["geo_jobs"] == 1
    assert orphaned.estado == EstadoGeoJob.FAILED
    reconciled_error = orphaned.error
    assert "stale" in (reconciled_error or "").lower()

    # A late-ack redelivery cannot re-claim the terminalized tracker.
    assert not repo.update_job_status_if_current(
        db,
        orphaned.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )
    # Nor can the lost worker overwrite reconciliation if it returns late.
    assert not repo.update_job_status_if_current(
        db,
        orphaned.id,
        expected_estado=EstadoGeoJob.RUNNING,
        estado=EstadoGeoJob.COMPLETED,
        resultado={"late": True},
    )
    assert not repo.update_job_status_if_current(
        db,
        orphaned.id,
        expected_estado=EstadoGeoJob.RUNNING,
        estado=EstadoGeoJob.FAILED,
        error="late worker error",
    )
    db.refresh(orphaned)
    assert orphaned.estado == EstadoGeoJob.FAILED
    assert orphaned.error == reconciled_error
    assert orphaned.resultado is None


def test_geo_job_claim_cannot_resurrect_a_reconciled_job(db) -> None:
    from app.domains.geo.reconciliation import reconcile_stale_geo_jobs
    from app.domains.geo.repository import GeoRepository

    repo = GeoRepository()
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)

    fresh = repo.create_job(
        db,
        tipo=TipoGeoJob.DEM_PIPELINE,
        parametros={"area_id": "fresh"},
    )
    stale = GeoJob(
        tipo=TipoGeoJob.DEM_FULL_PIPELINE,
        estado=EstadoGeoJob.PENDING,
        parametros={"area_id": "stale"},
        updated_at=now - timedelta(hours=2),
    )
    db.add(stale)
    db.flush()

    assert repo.update_job_status_if_current(
        db,
        fresh.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )
    assert not repo.update_job_status_if_current(
        db,
        fresh.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )

    reconciled = reconcile_stale_geo_jobs(
        db,
        now=now,
        stale_after=timedelta(minutes=90),
    )
    db.flush()
    db.refresh(stale)
    assert reconciled["geo_jobs"] == 1
    assert stale.estado == EstadoGeoJob.FAILED

    assert not repo.update_job_status_if_current(
        db,
        stale.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )
    assert not repo.update_job_status_if_current(
        db,
        stale.id,
        expected_estado=EstadoGeoJob.RUNNING,
        estado=EstadoGeoJob.COMPLETED,
    )
    db.refresh(stale)
    assert stale.estado == EstadoGeoJob.FAILED


def test_analisis_claim_cannot_resurrect_or_overwrite_terminal_rows(db) -> None:
    from app.domains.geo.reconciliation import reconcile_stale_geo_jobs
    from app.domains.geo.repository import GeoRepository
    from app.shared.celery_outbox import CeleryTaskKey, enqueue_celery_task

    repo = GeoRepository()
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    task_id = uuid.uuid4()

    fresh = repo.create_analisis(
        db,
        tipo=TipoAnalisisGee.FLOOD,
        fecha_analisis=date.today(),
    )
    stale = AnalisisGeo(
        id=uuid.uuid4(),
        tipo=TipoAnalisisGee.SAR_TEMPORAL,
        fecha_analisis=date.today(),
        estado=EstadoGeoJob.RUNNING,
        celery_task_id=str(task_id),
        updated_at=now - timedelta(hours=2),
    )
    completed = AnalisisGeo(
        tipo=TipoAnalisisGee.CLASSIFICATION,
        fecha_analisis=date.today(),
        estado=EstadoGeoJob.COMPLETED,
        resultado={"winner": True},
        updated_at=now - timedelta(hours=2),
    )
    db.add_all([stale, completed])
    intent = enqueue_celery_task(
        db,
        celery_task_id=task_id,
        task_key=CeleryTaskKey.SAR_TEMPORAL,
        task_kwargs={"analisis_id": str(stale.id)},
    )
    intent.published_at = now - timedelta(minutes=5)
    db.flush()

    assert repo.update_analisis_status_if_current(
        db,
        fresh.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )
    assert not repo.update_analisis_status_if_current(
        db,
        fresh.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )

    reconciled = reconcile_stale_geo_jobs(
        db,
        now=now,
        stale_after=timedelta(minutes=90),
    )
    db.flush()
    db.refresh(stale)

    assert reconciled["gee_analyses"] == 1
    assert stale.estado == EstadoGeoJob.FAILED
    reconciled_error = stale.error

    assert not repo.update_analisis_status_if_current(
        db,
        stale.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
    )
    assert not repo.update_analisis_status_if_current(
        db,
        stale.id,
        expected_estado=EstadoGeoJob.RUNNING,
        estado=EstadoGeoJob.COMPLETED,
        resultado={"late": True},
    )
    assert not repo.update_analisis_status_if_current(
        db,
        stale.id,
        expected_estado=EstadoGeoJob.RUNNING,
        estado=EstadoGeoJob.FAILED,
        error="late worker error",
    )
    assert not repo.update_analisis_status_if_current(
        db,
        completed.id,
        expected_estado=EstadoGeoJob.RUNNING,
        estado=EstadoGeoJob.FAILED,
        error="late worker error",
    )

    db.refresh(stale)
    db.refresh(completed)
    assert stale.estado == EstadoGeoJob.FAILED
    assert stale.error == reconciled_error
    assert stale.resultado is None
    assert completed.estado == EstadoGeoJob.COMPLETED
    assert completed.resultado == {"winner": True}
    assert completed.error is None
