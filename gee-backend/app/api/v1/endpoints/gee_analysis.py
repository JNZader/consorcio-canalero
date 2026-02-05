"""
GEE Analysis Endpoints.
Endpoints para análisis avanzados (NDVI, Humedad, Inundación).
"""

from datetime import date
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List

from app.services.gee_service import get_image_explorer
from app.core.logging import get_logger
from app.core.exceptions import get_safe_error_detail

router = APIRouter()
logger = get_logger(__name__)

@router.get("/indices")
async def get_advanced_index_tiles(
    target_date: date = Query(..., description="Fecha objetivo (YYYY-MM-DD)"),
    index_type: str = Query("ndvi", description="Tipo de índice (ndvi, ndwi, mndwi, falso_color)"),
    max_cloud: int = Query(40, ge=0, le=100, description="Porcentaje máximo de nubes"),
) -> Dict[str, Any]:
    """
    Obtener tiles XYZ para un índice específico (NDVI, Humedad, etc).
    """
    try:
        explorer = get_image_explorer()
        result = explorer.get_sentinel2_image(
            target_date=target_date,
            visualization=index_type,
            max_cloud=max_cloud
        )

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculando índice {index_type}", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_detail(e, f"índice {index_type}")
        )

@router.get("/visualizations")
async def list_visualizations():
    """Listar visualizaciones disponibles."""
    explorer = get_image_explorer()
    return explorer.get_available_visualizations()
