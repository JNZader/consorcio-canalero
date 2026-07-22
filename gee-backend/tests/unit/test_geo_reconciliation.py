from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql


def test_geo_reconciliation_uses_one_outbox_aware_set_based_update() -> None:
    from app.domains.geo.models import EstadoGeoJob
    from app.domains.geo.reconciliation import reconcile_stale_geo_jobs

    db = MagicMock()
    geo_result = MagicMock(rowcount=2)
    analysis_result = MagicMock(rowcount=1)
    db.execute.side_effect = [geo_result, analysis_result]

    counts = reconcile_stale_geo_jobs(
        db,
        stale_after=timedelta(minutes=90),
        now=datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc),
    )

    assert counts == {"geo_jobs": 2, "gee_analyses": 1}
    assert db.execute.call_count == 2

    geo_statement = db.execute.call_args_list[0].args[0]
    geo_compiled = geo_statement.compile(dialect=postgresql.dialect())
    geo_sql = str(geo_compiled)
    assert "UPDATE geo_jobs" in geo_sql
    assert "celery_task_outbox" in geo_sql
    assert "NOT (EXISTS" in geo_sql
    assert "celery_task_outbox.published_at IS NULL" in geo_sql
    assert "celery_task_outbox.published_at >=" in geo_sql
    assert "geo_jobs.celery_task_id" in geo_sql
    assert EstadoGeoJob.RUNNING in geo_compiled.params.values()
    assert EstadoGeoJob.PENDING in geo_compiled.params.values()
    assert geo_sql.count("geo_jobs.estado =") == 2
    assert " OR geo_jobs.estado =" in geo_sql
    assert " AND NOT (EXISTS" in geo_sql
    assert "geo_jobs.estado IN" not in geo_sql

    analysis_statement = db.execute.call_args_list[1].args[0]
    analysis_compiled = analysis_statement.compile(dialect=postgresql.dialect())
    analysis_sql = str(analysis_compiled)
    assert "UPDATE geo_analisis_gee" in analysis_sql
    assert "celery_task_outbox" in analysis_sql
    assert "NOT (EXISTS" in analysis_sql
    assert "celery_task_outbox.published_at IS NULL" in analysis_sql
    assert "celery_task_outbox.published_at >=" in analysis_sql
    assert "geo_analisis_gee.celery_task_id" in analysis_sql
    assert EstadoGeoJob.RUNNING in analysis_compiled.params.values()
    assert EstadoGeoJob.PENDING in analysis_compiled.params.values()
    assert analysis_sql.count("geo_analisis_gee.estado =") == 2
    assert " OR geo_analisis_gee.estado =" in analysis_sql
    assert " AND NOT (EXISTS" in analysis_sql
    assert "geo_analisis_gee.estado IN" not in analysis_sql
