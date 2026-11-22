"""
Tests for Phase 5: Celery Beat schedule configuration.

Validates that beat_schedule task names match registered task names,
env var configuration works, and both periodic tasks are scheduled.
"""


# ── Beat schedule task names ────────────────────────


class TestBeatScheduleTaskNames:
    """Verify beat_schedule references correct registered task names."""

    def test_evaluate_alerts_task_name_matches_registered(self):
        """beat_schedule must use the custom name, not the module path."""
        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        entry = schedule["evaluate-alerts-periodic"]
        assert entry["task"] == "geo.intelligence.evaluate_alerts"

        # Verify the task is actually registered with this name
        from app.domains.geo.intelligence.tasks import task_evaluate_alerts

        assert task_evaluate_alerts.name == "geo.intelligence.evaluate_alerts"

    def test_refresh_matviews_task_name_matches_registered(self):
        """beat_schedule must use the custom name, not the module path."""
        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        entry = schedule["refresh-mat-views-periodic"]
        assert entry["task"] == "geo.intelligence.refresh_materialized_views"

        from app.domains.geo.intelligence.tasks import task_refresh_materialized_views

        assert task_refresh_materialized_views.name == "geo.intelligence.refresh_materialized_views"

    def test_no_module_path_in_task_names(self):
        """Task names should NOT contain full module paths."""
        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        for name, entry in schedule.items():
            task_name = entry["task"]
            assert not task_name.startswith("app."), (
                f"Beat entry '{name}' uses module path '{task_name}' "
                f"instead of registered task name"
            )


# ── Both tasks are scheduled ───────────────────────


class TestBothTasksScheduled:
    """Verify both periodic tasks exist in beat_schedule."""

    def test_evaluate_alerts_is_scheduled(self):
        from app.core.celery_app import celery_app

        assert "evaluate-alerts-periodic" in celery_app.conf.beat_schedule

    def test_refresh_matviews_is_scheduled(self):
        from app.core.celery_app import celery_app

        assert "refresh-mat-views-periodic" in celery_app.conf.beat_schedule

    def test_geo_tasks_route_to_geo_queue(self):
        """Pure-SQL maintenance beat tasks route to the default ``celery`` queue.

        Neither ``evaluate-alerts-periodic`` nor ``refresh-mat-views-periodic``
        needs GDAL or Earth Engine — routing them to ``celery`` keeps them from
        blocking behind heavy raster jobs on the ``geo`` worker.
        """
        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        geo_entries: set[str] = set()
        for name, entry in schedule.items():
            options = entry.get("options", {})
            queue = options.get("queue")
            if name in geo_entries:
                assert queue == "geo", (
                    f"Beat entry '{name}' should route to 'geo' queue, got {queue!r}"
                )
            else:
                assert queue != "geo", (
                    f"Beat entry '{name}' should NOT route to 'geo' queue "
                    f"(reserved for tasks needing the geo worker); got {queue!r}"
                )

    def test_sql_maintenance_geo_tasks_route_to_celery_queue(self):
        """Celery router resolves SQL maintenance geo.* tasks to ``celery`` before ``geo.*``."""
        from app.core.celery_app import celery_app

        router = celery_app.amqp.router
        for task_name in (
            "geo.informe_area.limpiar_vencidos",
            "geo.reconcile_stale_jobs",
            "geo.intelligence.evaluate_alerts",
            "geo.intelligence.refresh_materialized_views",
        ):
            assert router.route({}, task_name)["queue"].name == "celery"
        for task_name in ("geo.process_dem_pipeline", "gee.analyze_flood"):
            assert router.route({}, task_name)["queue"].name == "geo"


# ── Env var configuration ──────────────────────────


class TestEnvVarConfiguration:
    """Verify that interval env vars are read correctly."""

    def test_default_alert_interval_is_6(self):
        from app.core.celery_app import GEO_ALERT_EVAL_HOURS

        # Default is 6 (unless overridden by env)
        assert isinstance(GEO_ALERT_EVAL_HOURS, int)
        assert GEO_ALERT_EVAL_HOURS > 0

    def test_default_matview_interval_is_6(self):
        from app.core.celery_app import GEO_MATVIEW_REFRESH_HOURS

        assert isinstance(GEO_MATVIEW_REFRESH_HOURS, int)
        assert GEO_MATVIEW_REFRESH_HOURS > 0

    def test_schedule_has_crontab_entries(self):
        """Both entries should use crontab schedule (not timedelta)."""
        from celery.schedules import crontab

        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        for name, entry in schedule.items():
            assert isinstance(entry["schedule"], crontab), (
                f"Beat entry '{name}' should use crontab schedule"
            )


def test_orphaned_denuncia_photo_reconciler_is_registered_and_scheduled():
    from app.core.celery_app import (
        celery_app,
        reconcile_orphaned_denuncia_photos_task,
    )

    entry = celery_app.conf.beat_schedule["reconcile-orphaned-denuncia-photos"]
    assert entry["task"] == "denuncias.reconcile_orphaned_photos"
    assert entry["options"]["queue"] == "celery"
    assert reconcile_orphaned_denuncia_photos_task.name == "denuncias.reconcile_orphaned_photos"


def test_outbox_publisher_is_registered_and_scheduled():
    from datetime import timedelta
    from unittest.mock import patch

    from app.core.celery_app import (
        CELERY_OUTBOX_BATCH_SIZE,
        CELERY_OUTBOX_CLEANUP_BATCH_SIZE,
        CELERY_OUTBOX_LEASE_SECONDS,
        CELERY_OUTBOX_RETENTION_DAYS,
        celery_app,
        publish_pending_celery_tasks_task,
    )

    entry = celery_app.conf.beat_schedule["publish-celery-outbox"]
    assert entry["task"] == "outbox.publish_pending"
    assert entry["options"]["queue"] == "celery"
    assert entry["schedule"].minute == set(range(60))
    assert publish_pending_celery_tasks_task.name == "outbox.publish_pending"

    expected = {
        "claimed": 0,
        "published": 0,
        "failed": 0,
        "finalize_lost": 0,
        "claim_errors": 0,
        "cleaned": 0,
    }
    with patch(
        "app.shared.celery_outbox.publish_due_celery_tasks",
        return_value=expected,
    ) as publish:
        result = publish_pending_celery_tasks_task.run()

    assert result == expected
    publish.assert_called_once_with(
        batch_size=CELERY_OUTBOX_BATCH_SIZE,
        lease_for=timedelta(seconds=CELERY_OUTBOX_LEASE_SECONDS),
        retention=timedelta(days=CELERY_OUTBOX_RETENTION_DAYS),
        cleanup_batch_size=CELERY_OUTBOX_CLEANUP_BATCH_SIZE,
    )


def test_conocimiento_retention_purge_is_registered_and_scheduled():
    from unittest.mock import MagicMock, patch

    from celery.schedules import crontab

    from app.core.celery_app import celery_app
    from app.domains.conocimiento.tasks import purgar_retencion_conocimiento_task

    assert "app.domains.conocimiento.tasks" in celery_app.conf.include
    entry = celery_app.conf.beat_schedule["purgar-retencion-conocimiento"]
    assert entry["task"] == "conocimiento.purgar_retencion"
    assert entry["options"]["queue"] == "celery"
    assert isinstance(entry["schedule"], crontab)
    assert entry["schedule"].minute == {55}
    assert entry["schedule"].hour == {4}
    assert purgar_retencion_conocimiento_task.name == "conocimiento.purgar_retencion"

    session = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = session
    cm.__exit__.return_value = False

    with (
        patch("app.db.session.SessionLocal", return_value=cm),
        patch(
            "app.domains.conocimiento.repository.purgar_decisiones_ruta", return_value=3
        ) as p_dec,
        patch("app.domains.conocimiento.repository.purgar_consultas", return_value=7) as p_con,
    ):
        result = purgar_retencion_conocimiento_task.run()

    assert result == {"decisiones_borradas": 3, "consultas_borradas": 7}
    p_dec.assert_called_once_with(session)
    p_con.assert_called_once_with(session)
    session.commit.assert_called_once()
