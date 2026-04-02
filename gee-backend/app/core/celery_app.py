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
        "rainfall-daily-sync": {
            "task": "geo.rainfall_daily_sync",
            "schedule": crontab(minute="0", hour="8"),
            "options": {"queue": "geo"},
        },
    },
)

if __name__ == "__main__":
    celery_app.start()
