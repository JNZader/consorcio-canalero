"""
GEE Analysis Endpoints.
Endpoints para analisis avanzados (NDVI, Humedad, Inundacion).
"""

import asyncio
from datetime import date
from fastapi import APIRouter, Query, Depends
from typing import Dict, Any, List

from app.services.gee_service import get_image_explorer
from app.auth import User, require_authenticated
from app.core.logging import get_logger
from app.core.exceptions import AppException, NotFoundError, get_safe_error_detail

router = APIRouter()
logger = get_logger(__name__)

@router.get("/indices")
async def get_advanced_index_tiles(
    target_date: date = Query(..., description="Fecha objetivo (YYYY-MM-DD)"),
    index_type: str = Query("ndvi", description="Tipo de indice (ndvi, ndwi, mndwi, falso_color)"),
    max_cloud: int = Query(40, ge=0, le=100, description="Porcentaje maximo de nubes"),
    user: User = Depends(require_authenticated),
) -> Dict[str, Any]:
    """
    Obtener tiles XYZ para un indice especifico (NDVI, Humedad, etc).
    """
    try:
        explorer = get_image_explorer()
        result = await asyncio.to_thread(
            explorer.get_sentinel2_image,
            target_date=target_date,
            visualization=index_type,
            max_cloud=max_cloud,
        )

        if "error" in result:
            raise NotFoundError(
                message=result["error"],
                code="INDEX_NOT_FOUND",
            )

        return result
    except AppException:
        raise
    except Exception as e:
        logger.error(f"Error calculando indice {index_type}", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, f"indice {index_type}"),
            code="GEE_INDEX_ERROR",
            status_code=500,
        )

@router.get("/visualizations")
async def list_visualizations(
    user: User = Depends(require_authenticated),
):
    """Listar visualizaciones disponibles."""
    explorer = get_image_explorer()
    return explorer.get_available_visualizations()
