"""
Celery tasks for Google Earth Engine analysis.
Handles long-running GEE operations in the background.
"""

from datetime import date
from celery.utils.log import get_task_logger

from app.core.celery_app import celery_app
from app.services.monitoring_service import get_monitoring_service

logger = get_task_logger(__name__)


@celery_app.task(name="analyze_flood_task", bind=True)
def analyze_flood_task(
    self, start_date_str: str, end_date_str: str, method: str = "fusion"
):
    """
    Async task to analyze floods using SAR and Optical data.
    Uses classify_parcels which performs multi-index classification
    including flood/waterlogging detection.
    """
    logger.info(
        f"Starting flood analysis: {start_date_str} to {end_date_str} using {method}"
    )

    try:
        # Convert strings back to date objects
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        monitoring = get_monitoring_service()

        # Use classify_parcels which includes flood detection via
        # water surface and waterlogged parcel classification
        result = monitoring.classify_parcels(
            start_date=start_date,
            end_date=end_date,
            layer_name="zona",
        )

        logger.info("Flood analysis completed successfully")
        return result

    except Exception as e:
        logger.error(f"Error in flood analysis task: {str(e)}")
        # Re-raise to let Celery handle it as a failure
        raise e


@celery_app.task(name="supervised_classification_task", bind=True)
def supervised_classification_task(self, start_date_str: str, end_date_str: str):
    """
    Async task for land use classification.
    Uses classify_parcels_by_cuenca for per-watershed classification.
    """
    logger.info(f"Starting classification task: {start_date_str} to {end_date_str}")

    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        monitoring = get_monitoring_service()

        # Use classify_parcels_by_cuenca which classifies all watersheds
        result = monitoring.classify_parcels_by_cuenca(
            start_date=start_date,
            end_date=end_date,
        )

        return result
    except Exception as e:
        logger.error(f"Error in classification task: {str(e)}")
        raise e
