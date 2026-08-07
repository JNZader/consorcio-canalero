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
# Recoverable geo/GEE tasks may legitimately run for hours. Keep the soft/hard
# limits below Redis visibility, and reconciliation beyond visibility, so a
# healthy long task is neither duplicated nor declared stale.
LONG_TASK_SOFT_TIME_LIMIT_SECONDS = int(
    os.environ.get("LONG_TASK_SOFT_TIME_LIMIT_SECONDS", "10800")
)
LONG_TASK_TIME_LIMIT_SECONDS = int(os.environ.get("LONG_TASK_TIME_LIMIT_SECONDS", "11100"))
CELERY_VISIBILITY_TIMEOUT_SECONDS = int(
    os.environ.get("CELERY_VISIBILITY_TIMEOUT_SECONDS", "14400")
)
GEO_STALE_JOB_MINUTES = int(os.environ.get("GEO_STALE_JOB_MINUTES", "300"))
CELERY_OUTBOX_BATCH_SIZE = max(
    1,
    min(int(os.environ.get("CELERY_OUTBOX_BATCH_SIZE", "25")), 100),
)
CELERY_OUTBOX_LEASE_SECONDS = max(
    30,
    min(int(os.environ.get("CELERY_OUTBOX_LEASE_SECONDS", "300")), 3600),
)
CELERY_OUTBOX_RETENTION_DAYS = max(
    1,
    min(int(os.environ.get("CELERY_OUTBOX_RETENTION_DAYS", "30")), 365),
)
CELERY_OUTBOX_CLEANUP_BATCH_SIZE = max(
    1,
    min(int(os.environ.get("CELERY_OUTBOX_CLEANUP_BATCH_SIZE", "500")), 1000),
)

RECOVERABLE_LONG_TASKS = frozenset(
    {
        "geo.process_dem_pipeline",
        "geo.run_full_dem_pipeline",
        "gee.analyze_flood",
        "gee.supervised_classification",
        "gee.sar_temporal",
    }
)
RECOVERABLE_TASK_ANNOTATIONS = {
    task_name: {
        "acks_late": True,
        "acks_on_failure_or_timeout": True,
        "reject_on_worker_lost": True,
        "soft_time_limit": LONG_TASK_SOFT_TIME_LIMIT_SECONDS,
        "time_limit": LONG_TASK_TIME_LIMIT_SECONDS,
    }
    for task_name in RECOVERABLE_LONG_TASKS
}

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
        "app.domains.geo.rainfall.tasks",
    ],
)

# Optional configuration
celery_app.conf.update(
    task_track_started=True,
    # Early acknowledgement is the safe default: several intelligence tasks
    # create rows and are not idempotent. Only the explicit allowlist below is
    # eligible for worker-loss redelivery.
    task_acks_late=False,
    task_reject_on_worker_lost=False,
    task_annotations=RECOVERABLE_TASK_ANNOTATIONS,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": CELERY_VISIBILITY_TIMEOUT_SECONDS},
    result_backend_transport_options={"visibility_timeout": CELERY_VISIBILITY_TIMEOUT_SECONDS},
    visibility_timeout=CELERY_VISIBILITY_TIMEOUT_SECONDS,
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
        # Phase 4 / F4-K: hard-delete denuncias the owner asked to
        # cancel more than 1 year ago. Runs daily at 04:30 UTC so it
        # doesn't overlap with the refresh-token purge.
        "purge-soft-deleted-denuncias": {
            "task": "denuncias.purge_soft_deleted_denuncias",
            "schedule": crontab(minute="30", hour="4"),
            "options": {"queue": "celery"},
        },
        # Reclaim immutable replacement versions left behind by ambiguous
        # commits or failed post-commit cleanup. The reconciler has its own
        # 24-hour safety grace and bounded batch; run it daily at 04:45 UTC.
        "reconcile-orphaned-denuncia-photos": {
            "task": "denuncias.reconcile_orphaned_photos",
            "schedule": crontab(minute="45", hour="4"),
            "options": {"queue": "celery"},
        },
        "publish-celery-outbox": {
            "task": "outbox.publish_pending",
            "schedule": crontab(minute="*"),
            "options": {"queue": "celery"},
        },
        "reconcile-stale-geo-jobs": {
            "task": "geo.reconcile_stale_jobs",
            "schedule": crontab(minute="*/15"),
            "options": {"queue": "celery"},
        },
        "rainfall-process-outbox": {
            "task": "rainfall.process_outbox",
            "schedule": 60.0,
            "options": {"queue": "celery"},
        },
    },
)


@celery_app.task(name="auth.purge_stale_refresh_tokens")
def purge_stale_refresh_tokens_task() -> int:
    """Sync wrapper for the async cleanup so Celery can schedule it.

    NOTE on worker pool compatibility: ``asyncio.run`` creates a NEW
    event loop, which fails with ``RuntimeError: This event loop is
    already running`` when the Celery worker is started with
    ``--pool=gevent|eventlet`` (those pools install a running loop at
    process start). Our compose files start celery-worker with the
    default ``prefork`` pool — DO NOT switch to gevent / eventlet
    without first rewriting this task (and any other ``asyncio.run``
    callsite under Celery) to schedule onto the existing loop instead.
    """
    import asyncio

    from app.auth.cleanup_tasks import purge_stale_refresh_tokens
    from app.db.session import AsyncSessionLocal

    async def _run() -> int:
        async with AsyncSessionLocal() as session:
            return await purge_stale_refresh_tokens(session)

    return asyncio.run(_run())


@celery_app.task(name="denuncias.purge_soft_deleted_denuncias")
def purge_soft_deleted_denuncias_task() -> int:
    """Hard-delete denuncia rows that have been soft-deleted for >1y.

    See the prefork-pool note on the refresh-token task above —
    same constraint applies here for the same reason.
    """
    import asyncio

    from app.auth.cleanup_tasks import purge_soft_deleted_denuncias
    from app.db.session import AsyncSessionLocal

    async def _run() -> int:
        async with AsyncSessionLocal() as session:
            return await purge_soft_deleted_denuncias(session)

    return asyncio.run(_run())


@celery_app.task(name="denuncias.reconcile_orphaned_photos")
def reconcile_orphaned_denuncia_photos_task() -> int:
    """Reclaim old immutable photo versions that no DB row references.

    See the prefork-pool note on the refresh-token task above.
    """
    import asyncio

    from app.auth.cleanup_tasks import reconcile_orphaned_denuncia_photos
    from app.db.session import AsyncSessionLocal

    async def _run() -> int:
        async with AsyncSessionLocal() as session:
            return await reconcile_orphaned_denuncia_photos(session)

    return asyncio.run(_run())


@celery_app.task(name="outbox.publish_pending")
def publish_pending_celery_tasks_task() -> dict[str, int]:
    """Publish and retain a bounded batch of durable Celery intents."""
    from datetime import timedelta

    from app.shared.celery_outbox import publish_due_celery_tasks

    return publish_due_celery_tasks(
        batch_size=CELERY_OUTBOX_BATCH_SIZE,
        lease_for=timedelta(seconds=CELERY_OUTBOX_LEASE_SECONDS),
        retention=timedelta(days=CELERY_OUTBOX_RETENTION_DAYS),
        cleanup_batch_size=CELERY_OUTBOX_CLEANUP_BATCH_SIZE,
    )


@celery_app.task(name="geo.reconcile_stale_jobs")
def reconcile_stale_geo_jobs_task() -> dict[str, int]:
    """Fail DB jobs that remained active well beyond the delivery window."""
    from datetime import timedelta

    from app.db.session import SessionLocal
    from app.domains.geo.reconciliation import reconcile_stale_geo_jobs

    with SessionLocal() as db:
        counts = reconcile_stale_geo_jobs(
            db,
            stale_after=timedelta(minutes=GEO_STALE_JOB_MINUTES),
        )
        db.commit()
        return counts


if __name__ == "__main__":
    celery_app.start()
