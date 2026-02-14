"""
Image Explorer API endpoints.
Permite explorar imagenes satelitales de fechas especificas.
"""

import asyncio
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.services.gee_service import get_image_explorer
from app.core.exceptions import AppException, NotFoundError, get_safe_error_detail

router = APIRouter(prefix="/images", tags=["Image Explorer"])


@router.get("/sentinel2")
async def get_sentinel2_image(
    target_date: date = Query(..., description="Fecha objetivo (YYYY-MM-DD)"),
    days_buffer: int = Query(10, ge=1, le=30, description="Dias de busqueda antes/despues"),
    max_cloud: int = Query(40, ge=0, le=100, description="Porcentaje maximo de nubes"),
    visualization: str = Query("rgb", description="Tipo de visualizacion"),
):
    """
    Obtener tiles de imagen Sentinel-2 para una fecha especifica.

    Visualizaciones disponibles:
    - **rgb**: Color natural
    - **falso_color**: Falso color (vegetacion en rojo)
    - **agricultura**: Agricultura (suelo en magenta)
    - **ndwi**: Indice de agua NDWI
    - **mndwi**: Indice de agua modificado MNDWI
    - **ndvi**: Indice de vegetacion NDVI
    - **inundacion**: Deteccion de agua

    Returns:
        tile_url para usar en mapa Leaflet/Mapbox
    """
    try:
        explorer = get_image_explorer()
        result = await asyncio.to_thread(
            explorer.get_sentinel2_image,
            target_date=target_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
            visualization=visualization,
        )

        if "error" in result:
            raise NotFoundError(
                message=result.get("error", "Imagen no encontrada"),
                code="SENTINEL2_NOT_FOUND",
            )

        return result

    except AppException:
        raise
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "imagen Sentinel-2"),
            code="IMAGE_EXPLORER_ERROR",
            status_code=500,
        )


@router.get("/sentinel1")
async def get_sentinel1_image(
    target_date: date = Query(..., description="Fecha objetivo (YYYY-MM-DD)"),
    days_buffer: int = Query(10, ge=1, le=30, description="Dias de busqueda antes/despues"),
    visualization: str = Query("vv", description="vv o vv_flood"),
):
    """
    Obtener tiles de imagen Sentinel-1 (SAR) para una fecha especifica.

    Visualizaciones:
    - **vv**: Radar SAR banda VV (escala de grises)
    - **vv_flood**: Deteccion de agua (cyan)

    El SAR funciona con nubes y detecta agua por su respuesta oscura.
    """
    try:
        explorer = get_image_explorer()
        result = await asyncio.to_thread(
            explorer.get_sentinel1_image,
            target_date=target_date,
            days_buffer=days_buffer,
            visualization=visualization,
        )

        if "error" in result:
            raise NotFoundError(
                message=result.get("error", "Imagen no encontrada"),
                code="SENTINEL1_NOT_FOUND",
            )

        return result

    except AppException:
        raise
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "imagen Sentinel-1"),
            code="IMAGE_EXPLORER_ERROR",
            status_code=500,
        )


@router.get("/compare")
async def compare_flood_dates(
    flood_date: date = Query(..., description="Fecha de inundacion"),
    normal_date: date = Query(..., description="Fecha de referencia (sin inundacion)"),
    days_buffer: int = Query(10, ge=1, le=30),
    max_cloud: int = Query(40, ge=0, le=100),
):
    """
    Comparar imagen de inundacion con imagen normal.

    Util para mostrar a la comision el antes/despues de una inundacion.

    Returns:
        Tiles de ambas fechas (RGB y deteccion de agua)
    """
    try:
        explorer = get_image_explorer()
        result = await asyncio.to_thread(
            explorer.get_flood_comparison,
            flood_date=flood_date,
            normal_date=normal_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
        )
        return result

    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "comparacion de fechas"),
            code="IMAGE_COMPARE_ERROR",
            status_code=500,
        )


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
# ESCENAS HISTORICAS PRE-CONFIGURADAS
# ============================================

HISTORIC_FLOODS = [
    {
        "id": "feb_2017",
        "name": "Inundacion Febrero 2017",
        "date": "2017-02-20",
        "description": "Gran inundacion que afecto Bell Ville y zona rural",
        "severity": "alta",
    },
    {
        "id": "sep_2025",
        "name": "Inundacion Septiembre 2025",
        "date": "2025-09-05",
        "description": "Evento de anegamiento por lluvias intensas",
        "severity": "media",
    },
]


@router.get("/historic-floods")
async def get_historic_floods():
    """
    Obtener lista de inundaciones historicas pre-configuradas.

    Estas son fechas importantes que se pueden mostrar rapidamente a la comision.
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
    visualization: str = Query("rgb", description="Tipo de visualizacion"),
):
    """
    Obtener tiles de una inundacion historica pre-configurada.
    """
    flood = next((f for f in HISTORIC_FLOODS if f["id"] == flood_id), None)
    if not flood:
        raise NotFoundError(
            message=f"Inundacion '{flood_id}' no encontrada",
            code="FLOOD_NOT_FOUND",
            resource_type="historic_flood",
            resource_id=flood_id,
        )

    try:
        explorer = get_image_explorer()
        flood_date = date.fromisoformat(flood["date"])

        # Use larger buffer for historic floods to ensure full coverage
        # Older dates (pre-2020) need more buffer due to fewer satellite passes
        is_old_date = flood_date.year < 2020
        days_buffer = 30 if is_old_date else 15

        result = await asyncio.to_thread(
            explorer.get_sentinel2_image,
            target_date=flood_date,
            days_buffer=days_buffer,
            max_cloud=60,  # Allow more clouds for historic floods
            visualization=visualization,
            use_median=True,  # Use median composite for better coverage
        )

        if "error" in result:
            # Intentar con SAR si no hay imagenes opticas
            result = await asyncio.to_thread(
                explorer.get_sentinel1_image,
                target_date=flood_date,
                days_buffer=days_buffer,
                visualization="vv_flood",
            )

        result["flood_info"] = flood
        return result

    except AppException:
        raise
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "inundacion historica"),
            code="HISTORIC_FLOOD_ERROR",
            status_code=500,
        )
