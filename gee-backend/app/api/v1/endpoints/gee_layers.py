"""
GEE Layers Endpoints.
Endpoints para obtener capas desde Google Earth Engine.
"""

from datetime import date
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import List, Dict, Any

from app.services.gee_service import (
    get_layer_geojson,
    get_available_layers,
    get_gee_service,
    get_consorcios_camineros,
    get_caminos_by_consorcio,
    get_caminos_by_consorcio_nombre,
    get_caminos_con_colores,
    get_estadisticas_consorcios,
    _gee_initialized,
    initialize_gee,
)
from app.core.logging import get_logger
from app.core.exceptions import get_safe_error_detail

router = APIRouter()
logger = get_logger(__name__)


@router.get("")
async def list_gee_layers() -> JSONResponse:
    """
    Listar capas disponibles en GEE.

    Retorna lista de capas con id, nombre y descripcion.
    """
    return JSONResponse(
        content=get_available_layers(),
        headers={
            "Cache-Control": "public, max-age=86400",  # Cache 24 horas - lista es estatica
        }
    )


@router.get("/tiles/sentinel2")
async def get_sentinel2_tiles(
    start_date: date = Query(..., description="Fecha de inicio (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Fecha de fin (YYYY-MM-DD)"),
    max_cloud: int = Query(40, ge=0, le=100, description="Porcentaje maximo de nubes"),
) -> Dict[str, Any]:
    """
    Obtener URL de tiles Sentinel-2 RGB para visualizacion.

    Retorna URL XYZ para usar en mapas (Leaflet, etc).
    La imagen es un mosaico de las imagenes disponibles en el rango de fechas,
    filtradas por cobertura de nubes.

    Args:
        start_date: Fecha de inicio del rango
        end_date: Fecha de fin del rango
        max_cloud: Porcentaje maximo de cobertura de nubes (default 40%)

    Returns:
        Dict con:
        - tile_url: URL XYZ template para cargar tiles
        - imagenes_disponibles: Numero de imagenes encontradas
        - start_date, end_date: Fechas del rango
    """
    if not _gee_initialized:
        try:
            initialize_gee()
        except Exception as e:
            logger.error("No se pudo inicializar GEE", error=str(e))
            raise HTTPException(
                status_code=503,
                detail="Google Earth Engine no esta disponible temporalmente"
            )

    try:
        gee_service = get_gee_service()
        result = gee_service.get_sentinel2_tiles(start_date, end_date, max_cloud)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error obteniendo tiles Sentinel-2", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_detail(e, "tiles Sentinel-2")
        )


# =========================================================================
# ENDPOINTS DE RED VIAL POR CONSORCIO CAMINERO
# =========================================================================

@router.get("/caminos/consorcios")
async def list_consorcios_camineros() -> JSONResponse:
    """
    Listar consorcios camineros disponibles en la red vial.

    Retorna lista de consorcios con:
    - nombre: Nombre completo (ccn) ej: "C.C. 269 - SAN MARCOS SUD"
    - codigo: Codigo corto (ccc) ej: "CC269"
    - tramos: Cantidad de tramos de caminos
    - longitud_total_km: Longitud total en kilometros
    """
    if not _gee_initialized:
        try:
            initialize_gee()
        except Exception as e:
            logger.error("No se pudo inicializar GEE", error=str(e))
            raise HTTPException(
                status_code=503,
                detail="Google Earth Engine no esta disponible temporalmente"
            )

    try:
        consorcios = get_consorcios_camineros()
        return JSONResponse(
            content={
                "consorcios": consorcios,
                "total": len(consorcios),
            },
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache 1 hora
            }
        )
    except Exception as e:
        logger.error("Error obteniendo consorcios camineros", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_detail(e, "consorcios camineros")
        )


@router.get("/caminos/consorcio/{codigo}")
async def get_caminos_consorcio(codigo: str) -> JSONResponse:
    """
    Obtener caminos de un consorcio caminero especifico.

    Args:
        codigo: Codigo del consorcio (ccc) ej: "CC269"

    Returns:
        GeoJSON FeatureCollection con los caminos del consorcio
    """
    if not _gee_initialized:
        try:
            initialize_gee()
        except Exception as e:
            logger.error("No se pudo inicializar GEE", error=str(e))
            raise HTTPException(
                status_code=503,
                detail="Google Earth Engine no esta disponible temporalmente"
            )

    try:
        geojson = get_caminos_by_consorcio(codigo)
        num_features = len(geojson.get("features", []))

        if num_features == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontraron caminos para el consorcio '{codigo}'"
            )

        return JSONResponse(
            content=geojson,
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache 1 hora
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error obteniendo caminos por consorcio", codigo=codigo, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_detail(e, "caminos del consorcio")
        )


@router.get("/caminos/por-nombre")
async def get_caminos_por_nombre_consorcio(
    nombre: str = Query(..., description="Nombre del consorcio (ccn)")
) -> JSONResponse:
    """
    Obtener caminos de un consorcio caminero por nombre.

    Args:
        nombre: Nombre completo del consorcio (ccn) ej: "C.C. 269 - SAN MARCOS SUD"

    Returns:
        GeoJSON FeatureCollection con los caminos del consorcio
    """
    if not _gee_initialized:
        try:
            initialize_gee()
        except Exception as e:
            logger.error("No se pudo inicializar GEE", error=str(e))
            raise HTTPException(
                status_code=503,
                detail="Google Earth Engine no esta disponible temporalmente"
            )

    try:
        geojson = get_caminos_by_consorcio_nombre(nombre)
        num_features = len(geojson.get("features", []))

        if num_features == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontraron caminos para el consorcio '{nombre}'"
            )

        return JSONResponse(
            content=geojson,
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache 1 hora
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error obteniendo caminos por nombre consorcio", nombre=nombre, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_detail(e, "caminos del consorcio")
        )


@router.get("/caminos/coloreados")
async def get_caminos_coloreados() -> JSONResponse:
    """
    Obtener red vial con colores distintos por consorcio caminero.

    Retorna un GeoJSON donde cada feature tiene una propiedad 'color'
    asignada segun su consorcio caminero. Incluye leyenda y estadisticas.

    Ideal para pintar el mapa con colores diferenciados por consorcio.

    Returns:
        - features: GeoJSON FeatureCollection con propiedad 'color'
        - consorcios: Lista de consorcios con color, codigo y estadisticas
        - metadata: Totales (tramos, km, cantidad de consorcios)
    """
    if not _gee_initialized:
        try:
            initialize_gee()
        except Exception as e:
            logger.error("No se pudo inicializar GEE", error=str(e))
            raise HTTPException(
                status_code=503,
                detail="Google Earth Engine no esta disponible temporalmente"
            )

    try:
        result = get_caminos_con_colores()
        return JSONResponse(
            content=result,
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache 1 hora
            }
        )
    except Exception as e:
        logger.error("Error obteniendo caminos coloreados", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_detail(e, "caminos coloreados")
        )


@router.get("/caminos/estadisticas")
async def get_estadisticas_caminos() -> JSONResponse:
    """
    Obtener estadisticas de kilometros por consorcio caminero.

    Retorna:
    - Por consorcio: km totales, cantidad de tramos, desglose por jerarquia y superficie
    - Totales: km totales de red vial, cantidad de consorcios, cantidad de tramos

    Ordenado por km de mayor a menor.
    """
    if not _gee_initialized:
        try:
            initialize_gee()
        except Exception as e:
            logger.error("No se pudo inicializar GEE", error=str(e))
            raise HTTPException(
                status_code=503,
                detail="Google Earth Engine no esta disponible temporalmente"
            )

    try:
        result = get_estadisticas_consorcios()
        return JSONResponse(
            content=result,
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache 1 hora
            }
        )
    except Exception as e:
        logger.error("Error obteniendo estadisticas de consorcios", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_detail(e, "estadisticas de consorcios")
        )


# =========================================================================
# ENDPOINT GENERICO DE CAPAS
# =========================================================================

@router.get("/{layer_name}")
async def get_gee_layer(layer_name: str) -> JSONResponse:
    """
    Obtener GeoJSON de una capa desde GEE.

    Args:
        layer_name: zona, candil, ml, noroeste, norte, caminos

    Returns:
        GeoJSON FeatureCollection
    """
    # Intentar inicializar GEE si no está listo
    if not _gee_initialized:
        try:
            initialize_gee()
        except Exception as e:
            logger.error("No se pudo inicializar GEE", error=str(e))
            raise HTTPException(
                status_code=503,
                detail="Google Earth Engine no esta disponible temporalmente"
            )

    try:
        geojson = get_layer_geojson(layer_name)
        return JSONResponse(
            content=geojson,
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache 1 hora
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=get_safe_error_detail(e, "capa"))
    except Exception as e:
        logger.error("Error obteniendo capa GEE", layer=layer_name, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_detail(e, "capa GEE")
        )
