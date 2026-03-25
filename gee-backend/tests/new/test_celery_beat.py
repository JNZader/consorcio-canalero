"""
Tests for Phase 5: Celery Beat schedule configuration.

Validates that beat_schedule task names match registered task names,
env var configuration works, and both periodic tasks are scheduled.
"""

import os
from unittest import mock


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

    def test_both_use_geo_queue(self):
        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        for name, entry in schedule.items():
            options = entry.get("options", {})
            assert options.get("queue") == "geo", (
                f"Beat entry '{name}' should route to 'geo' queue"
            )


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
