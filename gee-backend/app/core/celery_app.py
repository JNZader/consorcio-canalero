import os
from celery import Celery
from kombu import Queue
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Redis URL configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery instance
celery_app = Celery(
    "consorcio_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.services.gee_analysis_tasks",
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
)

if __name__ == "__main__":
    celery_app.start()
