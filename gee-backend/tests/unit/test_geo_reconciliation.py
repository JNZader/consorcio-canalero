from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql


def test_geo_reconciliation_uses_one_outbox_aware_set_based_update() -> None:
    from app.domains.geo.models import EstadoGeoJob
    from app.domains.geo.reconciliation import reconcile_stale_geo_jobs

    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(rowcount=2),
        MagicMock(rowcount=0),
        MagicMock(rowcount=1),
        MagicMock(rowcount=0),
    ]

    counts = reconcile_stale_geo_jobs(
        db,
        stale_after=timedelta(minutes=90),
        now=datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc),
    )

    assert counts == {"geo_jobs": 2, "gee_analyses": 1}
    assert db.execute.call_count == 4

    geo_running = db.execute.call_args_list[0].args[0].compile(dialect=postgresql.dialect())
    geo_running_sql = str(geo_running)
    assert "UPDATE geo_jobs" in geo_running_sql
    assert EstadoGeoJob.RUNNING in geo_running.params.values()
    assert "worker_lost" in geo_running.params.values()
    assert "geo_jobs.estado IN" not in geo_running_sql

    geo_pending = db.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect())
    geo_pending_sql = str(geo_pending)
    assert "UPDATE geo_jobs" in geo_pending_sql
    assert "celery_task_outbox" in geo_pending_sql
    assert "NOT (EXISTS" in geo_pending_sql
    assert EstadoGeoJob.PENDING in geo_pending.params.values()
    assert "geo_jobs.estado IN" not in geo_pending_sql

    analysis_running = db.execute.call_args_list[2].args[0].compile(dialect=postgresql.dialect())
    assert "UPDATE geo_analisis_gee" in str(analysis_running)
    assert EstadoGeoJob.RUNNING in analysis_running.params.values()
    assert "worker_lost" in analysis_running.params.values()

    analysis_pending = db.execute.call_args_list[3].args[0].compile(dialect=postgresql.dialect())
    analysis_pending_sql = str(analysis_pending)
    assert "UPDATE geo_analisis_gee" in analysis_pending_sql
    assert "celery_task_outbox" in analysis_pending_sql
    assert EstadoGeoJob.PENDING in analysis_pending.params.values()
