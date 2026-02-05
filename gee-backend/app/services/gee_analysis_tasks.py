"""
Celery tasks for Google Earth Engine analysis.
Handles long-running GEE operations in the background.
"""

from typing import Dict, Any, Optional
from datetime import date
from celery.utils.log import get_task_logger

from app.core.celery_app import celery_app
from app.services.gee_service import get_gee_service, get_image_explorer
from app.services.monitoring_service import get_monitoring_service

logger = get_task_logger(__name__)

@celery_app.task(name="analyze_flood_task", bind=True)
def analyze_flood_task(self, start_date_str: str, end_date_str: str, method: str = "fusion"):
    """
    Async task to analyze floods using SAR and Optical data.
    """
    logger.info(f"Starting flood analysis: {start_date_str} to {end_date_str} using {method}")
    
    try:
        # Convert strings back to date objects
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        
        monitoring = get_monitoring_service()
        
        # This is the heavy GEE call
        result = monitoring.analyze_floods(
            start_date=start_date,
            end_date=end_date,
            method=method
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
    Async task for land use classification using Random Forest.
    """
    logger.info(f"Starting classification task: {start_date_str} to {end_date_str}")
    
    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        
        monitoring = get_monitoring_service()
        
        # Heavy ML operation in GEE
        result = monitoring.get_supervised_classification(
            start_date=start_date,
            end_date=end_date
        )
        
        return result
    except Exception as e:
        logger.error(f"Error in classification task: {str(e)}")
        raise e
