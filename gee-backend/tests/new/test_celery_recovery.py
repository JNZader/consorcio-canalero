"""Regression tests for worker-loss delivery and stale geo-job recovery."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

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


def test_reconcile_stale_geo_jobs_marks_only_old_active_rows(db) -> None:
    from app.domains.geo.reconciliation import reconcile_stale_geo_jobs

    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    stale_at = now - timedelta(hours=2)
    recent_at = now - timedelta(minutes=5)

    stale_job = GeoJob(
        tipo=TipoGeoJob.DEM_PIPELINE,
        estado=EstadoGeoJob.RUNNING,
        updated_at=stale_at,
    )
    recent_job = GeoJob(
        tipo=TipoGeoJob.SLOPE,
        estado=EstadoGeoJob.PENDING,
        updated_at=recent_at,
    )
    completed_job = GeoJob(
        tipo=TipoGeoJob.ASPECT,
        estado=EstadoGeoJob.COMPLETED,
        updated_at=stale_at,
    )
    stale_analysis = AnalisisGeo(
        tipo=TipoAnalisisGee.FLOOD,
        fecha_analisis=date.today(),
        estado=EstadoGeoJob.PENDING,
        updated_at=stale_at,
    )
    db.add_all([stale_job, recent_job, completed_job, stale_analysis])
    db.flush()

    reconciled = reconcile_stale_geo_jobs(
        db,
        now=now,
        stale_after=timedelta(minutes=90),
    )
    db.flush()
    db.refresh(stale_job)
    db.refresh(recent_job)
    db.refresh(completed_job)
    db.refresh(stale_analysis)

    assert reconciled == {"geo_jobs": 1, "gee_analyses": 1}
    assert stale_job.estado == EstadoGeoJob.FAILED
    assert "stale" in (stale_job.error or "").lower()
    assert stale_analysis.estado == EstadoGeoJob.FAILED
    assert recent_job.estado == EstadoGeoJob.PENDING
    assert completed_job.estado == EstadoGeoJob.COMPLETED


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

    repo = GeoRepository()
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)

    fresh = repo.create_analisis(
        db,
        tipo=TipoAnalisisGee.FLOOD,
        fecha_analisis=date.today(),
    )
    stale = AnalisisGeo(
        tipo=TipoAnalisisGee.SAR_TEMPORAL,
        fecha_analisis=date.today(),
        estado=EstadoGeoJob.PENDING,
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
