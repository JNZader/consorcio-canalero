"""
Image Explorer API endpoints.
Permite explorar imágenes satelitales de fechas específicas.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.services.gee_service import get_image_explorer
from app.core.exceptions import get_safe_error_detail

router = APIRouter(prefix="/images", tags=["Image Explorer"])


@router.get("/sentinel2")
async def get_sentinel2_image(
    target_date: date = Query(..., description="Fecha objetivo (YYYY-MM-DD)"),
    days_buffer: int = Query(10, ge=1, le=30, description="Días de búsqueda antes/después"),
    max_cloud: int = Query(40, ge=0, le=100, description="Porcentaje máximo de nubes"),
    visualization: str = Query("rgb", description="Tipo de visualización"),
):
    """
    Obtener tiles de imagen Sentinel-2 para una fecha específica.

    Visualizaciones disponibles:
    - **rgb**: Color natural
    - **falso_color**: Falso color (vegetación en rojo)
    - **agricultura**: Agricultura (suelo en magenta)
    - **ndwi**: Índice de agua NDWI
    - **mndwi**: Índice de agua modificado MNDWI
    - **ndvi**: Índice de vegetación NDVI
    - **inundacion**: Detección de agua

    Returns:
        tile_url para usar en mapa Leaflet/Mapbox
    """
    try:
        explorer = get_image_explorer()
        result = explorer.get_sentinel2_image(
            target_date=target_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
            visualization=visualization,
        )

        if "error" in result:
            raise HTTPException(status_code=404, detail=result)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_detail(e, "imagen Sentinel-2"))


@router.get("/sentinel1")
async def get_sentinel1_image(
    target_date: date = Query(..., description="Fecha objetivo (YYYY-MM-DD)"),
    days_buffer: int = Query(10, ge=1, le=30, description="Días de búsqueda antes/después"),
    visualization: str = Query("vv", description="vv o vv_flood"),
):
    """
    Obtener tiles de imagen Sentinel-1 (SAR) para una fecha específica.

    Visualizaciones:
    - **vv**: Radar SAR banda VV (escala de grises)
    - **vv_flood**: Detección de agua (cyan)

    El SAR funciona con nubes y detecta agua por su respuesta oscura.
    """
    try:
        explorer = get_image_explorer()
        result = explorer.get_sentinel1_image(
            target_date=target_date,
            days_buffer=days_buffer,
            visualization=visualization,
        )

        if "error" in result:
            raise HTTPException(status_code=404, detail=result)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_detail(e, "imagen Sentinel-1"))


@router.get("/compare")
async def compare_flood_dates(
    flood_date: date = Query(..., description="Fecha de inundación"),
    normal_date: date = Query(..., description="Fecha de referencia (sin inundación)"),
    days_buffer: int = Query(10, ge=1, le=30),
    max_cloud: int = Query(40, ge=0, le=100),
):
    """
    Comparar imagen de inundación con imagen normal.

    Útil para mostrar a la comisión el antes/después de una inundación.

    Returns:
        Tiles de ambas fechas (RGB y detección de agua)
    """
    try:
        explorer = get_image_explorer()
        result = explorer.get_flood_comparison(
            flood_date=flood_date,
            normal_date=normal_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
        )
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_detail(e, "comparacion de fechas"))


@router.get("/visualizations")
async def get_available_visualizations():
    """
    Obtener lista de visualizaciones disponibles para Sentinel-2.
    """
    explorer = get_image_explorer()
    return JSONResponse(
        content=explorer.get_available_visualizations(),
        headers={
            "Cache-Control": "public, max-age=86400",  # Cache 24 horas - lista estatica
        }
    )


# ============================================
# ESCENAS HISTÓRICAS PRE-CONFIGURADAS
# ============================================

HISTORIC_FLOODS = [
    {
        "id": "feb_2017",
        "name": "Inundación Febrero 2017",
        "date": "2017-02-20",
        "description": "Gran inundación que afectó Bell Ville y zona rural",
        "severity": "alta",
    },
    {
        "id": "sep_2025",
        "name": "Inundación Septiembre 2025",
        "date": "2025-09-05",
        "description": "Evento de anegamiento por lluvias intensas",
        "severity": "media",
    },
]


@router.get("/historic-floods")
async def get_historic_floods():
    """
    Obtener lista de inundaciones históricas pre-configuradas.

    Estas son fechas importantes que se pueden mostrar rápidamente a la comisión.
    """
    return JSONResponse(
        content={
            "floods": HISTORIC_FLOODS,
            "total": len(HISTORIC_FLOODS),
        },
        headers={
            "Cache-Control": "public, max-age=86400",  # Cache 24 horas - lista estatica
        }
    )


@router.get("/historic-floods/{flood_id}")
async def get_historic_flood_tiles(
    flood_id: str,
    visualization: str = Query("rgb", description="Tipo de visualización"),
):
    """
    Obtener tiles de una inundación histórica pre-configurada.
    """
    flood = next((f for f in HISTORIC_FLOODS if f["id"] == flood_id), None)
    if not flood:
        raise HTTPException(status_code=404, detail=f"Inundación '{flood_id}' no encontrada")

    try:
        explorer = get_image_explorer()
        flood_date = date.fromisoformat(flood["date"])

        # Use larger buffer for historic floods to ensure full coverage
        # Older dates (pre-2020) need more buffer due to fewer satellite passes
        is_old_date = flood_date.year < 2020
        days_buffer = 30 if is_old_date else 15

        result = explorer.get_sentinel2_image(
            target_date=flood_date,
            days_buffer=days_buffer,
            max_cloud=60,  # Allow more clouds for historic floods
            visualization=visualization,
            use_median=True,  # Use median composite for better coverage
        )

        if "error" in result:
            # Intentar con SAR si no hay imágenes ópticas
            result = explorer.get_sentinel1_image(
                target_date=flood_date,
                days_buffer=days_buffer,
                visualization="vv_flood",
            )

        result["flood_info"] = flood
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_detail(e, "inundacion historica"))
