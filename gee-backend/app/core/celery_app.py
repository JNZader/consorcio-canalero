import os
from celery import Celery
from celery.schedules import crontab
from kombu import Queue
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Redis URL configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Configurable periodic task intervals (hours)
GEO_ALERT_EVAL_HOURS = int(os.environ.get("GEO_ALERT_EVAL_HOURS", "6"))
GEO_MATVIEW_REFRESH_HOURS = int(os.environ.get("GEO_MATVIEW_REFRESH_HOURS", "6"))

# Create Celery instance
celery_app = Celery(
    "consorcio_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.domains.geo.tasks",
        "app.domains.geo.gee_tasks",
        "app.domains.geo.gee_tasks_warming",
        "app.domains.geo.intelligence.tasks",
    ],
)

# Optional configuration
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Argentina/Cordoba",
    enable_utc=True,
    # Max time a task can run (10 minutes default, geo tasks override below)
    task_time_limit=600,
    # Queue definitions
    task_queues=(
        Queue("celery", routing_key="celery"),
        Queue("geo", routing_key="geo"),
    ),
    task_default_queue="celery",
    task_default_routing_key="celery",
    # Route geo.* tasks to the geo queue
    task_routes={
        "geo.*": {"queue": "geo", "routing_key": "geo"},
    },
    # Periodic task schedule (Celery Beat)
    beat_schedule={
        "evaluate-alerts-periodic": {
            "task": "geo.intelligence.evaluate_alerts",
            "schedule": crontab(minute="0", hour=f"*/{GEO_ALERT_EVAL_HOURS}"),
            "options": {"queue": "geo"},
        },
        "refresh-mat-views-periodic": {
            "task": "geo.intelligence.refresh_materialized_views",
            "schedule": crontab(minute="30", hour=f"*/{GEO_MATVIEW_REFRESH_HOURS}"),
            "options": {"queue": "geo"},
        },
        # Phase 2.1: purge expired / long-revoked refresh tokens so the
        # ``refresh_tokens`` table stays bounded. Daily at 04:15 UTC.
        "purge-stale-refresh-tokens": {
            "task": "auth.purge_stale_refresh_tokens",
            "schedule": crontab(minute="15", hour="4"),
            "options": {"queue": "celery"},
        },
    },
)


@celery_app.task(name="auth.purge_stale_refresh_tokens")
def purge_stale_refresh_tokens_task() -> int:
    """Sync wrapper for the async cleanup so Celery can schedule it."""
    import asyncio

    from app.auth.cleanup_tasks import purge_stale_refresh_tokens
    from app.db.session import AsyncSessionLocal

    async def _run() -> int:
        async with AsyncSessionLocal() as session:
            return await purge_stale_refresh_tokens(session)

    return asyncio.run(_run())


if __name__ == "__main__":
    celery_app.start()
