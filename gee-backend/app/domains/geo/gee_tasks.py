"""
Celery tasks for Google Earth Engine analysis.

Handles long-running GEE operations in the background.
These tasks run on the DEFAULT queue (not geo queue) because GEE
is cloud-based, not GDAL-based — no heavy local computation needed.

NOTE: classify_parcels and classify_parcels_by_cuenca were part of the
legacy MonitoringService (app.services.monitoring_service) which has been
removed. These tasks are stubs until the classification logic is migrated
into app.domains.geo.
"""

from celery.utils.log import get_task_logger

from app.core.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="gee.analyze_flood", bind=True)
def analyze_flood_task(
    self, start_date_str: str, end_date_str: str, method: str = "fusion"
):
    """
    Async task to analyze floods using SAR and Optical data.
    Currently a stub — classify_parcels needs migration to domain architecture.
    """
    logger.warning(
        f"analyze_flood_task called ({start_date_str} to {end_date_str}, {method}) "
        "but classify_parcels is not yet migrated to domain architecture."
    )
    raise NotImplementedError(
        "classify_parcels not yet migrated to domain architecture. "
        "Legacy app.services.monitoring_service has been removed."
    )


@celery_app.task(name="gee.supervised_classification", bind=True)
def supervised_classification_task(self, start_date_str: str, end_date_str: str):
    """
    Async task for land use classification.
    Currently a stub — classify_parcels_by_cuenca needs migration to domain architecture.
    """
    logger.warning(
        f"supervised_classification_task called ({start_date_str} to {end_date_str}) "
        "but classify_parcels_by_cuenca is not yet migrated to domain architecture."
    )
    raise NotImplementedError(
        "classify_parcels_by_cuenca not yet migrated to domain architecture. "
        "Legacy app.services.monitoring_service has been removed."
    )
