"""
Jobs Endpoints.
Manage and monitor background tasks (Celery).
"""

from fastapi import APIRouter, Depends
from celery.result import AsyncResult
from typing import Any, Dict
from pydantic import BaseModel

from app.auth import User, require_authenticated
from app.core.celery_app import celery_app
from app.services.gee_analysis_tasks import (
    analyze_flood_task,
    supervised_classification_task,
)

router = APIRouter()


class JobResponse(BaseModel):
    job_id: str
    status: str


class FloodAnalysisRequest(BaseModel):
    start_date: str
    end_date: str
    method: str = "fusion"


@router.post("/flood-analysis", response_model=JobResponse)
async def start_flood_analysis(
    request: FloodAnalysisRequest,
    user: User = Depends(require_authenticated),
):
    """
    Start an asynchronous flood analysis task.
    Returns a job_id to track progress.
    """
    task = analyze_flood_task.delay(
        request.start_date, request.end_date, request.method
    )
    return {"job_id": task.id, "status": "PENDING"}


@router.post("/classification", response_model=JobResponse)
async def start_classification(
    start_date: str,
    end_date: str,
    user: User = Depends(require_authenticated),
):
    """
    Start an asynchronous land use classification task.
    """
    task = supervised_classification_task.delay(start_date, end_date)
    return {"job_id": task.id, "status": "PENDING"}


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    user: User = Depends(require_authenticated),
):
    """
    Get the status and result of a background job.
    """
    result = AsyncResult(job_id, app=celery_app)

    response: Dict[str, Any] = {
        "job_id": job_id,
        "status": result.status,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response
