from __future__ import annotations

from datetime import date

from fastapi.responses import JSONResponse, StreamingResponse

from app.core.exceptions import AppException, NotFoundError, get_safe_error_detail
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _run_blocking(func, *args, **kwargs):
    return func(*args, **kwargs)

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


async def list_gee_layers_impl(lazy_gee_service) -> JSONResponse:
    svc = lazy_gee_service()
    return JSONResponse(
        content=svc["get_available_layers"](),
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def get_sentinel2_tiles_impl(
    *,
    start_date: date,
    end_date: date,
    max_cloud: int,
    ensure_gee,
):
    svc = ensure_gee()
    try:
        gee_service = svc["get_gee_service"]()
        result = await _run_blocking(
            gee_service.get_sentinel2_tiles, start_date, end_date, max_cloud
        )
        if "error" in result:
            raise NotFoundError(message=result["error"], code="SENTINEL2_NOT_FOUND")
        return result
    except AppException:
        raise
    except Exception as e:
        logger.error("Error obteniendo tiles Sentinel-2", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "tiles Sentinel-2"),
            code="GEE_TILES_ERROR",
            status_code=500,
        )


async def list_consorcios_camineros_impl(*, ensure_gee) -> JSONResponse:
    svc = ensure_gee()
    try:
        consorcios = await _run_blocking(svc["get_consorcios_camineros"])
        return JSONResponse(
            content={"consorcios": consorcios, "total": len(consorcios)},
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        logger.error("Error obteniendo consorcios camineros", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "consorcios camineros"),
            code="GEE_CONSORCIOS_ERROR",
            status_code=500,
        )


async def get_caminos_consorcio_impl(*, codigo: str, ensure_gee) -> JSONResponse:
    svc = ensure_gee()
    try:
        geojson = await _run_blocking(svc["get_caminos_by_consorcio"], codigo)
        if not geojson.get("features"):
            raise NotFoundError(
                message=f"No se encontraron caminos para el consorcio '{codigo}'",
                code="CONSORCIO_NOT_FOUND",
                resource_type="consorcio",
                resource_id=codigo,
            )
        return JSONResponse(
            content=geojson,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except AppException:
        raise
    except Exception as e:
        logger.error("Error obteniendo caminos por consorcio", codigo=codigo, error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "caminos del consorcio"),
            code="GEE_CAMINOS_ERROR",
            status_code=500,
        )


async def get_caminos_por_nombre_consorcio_impl(*, nombre: str, ensure_gee) -> JSONResponse:
    svc = ensure_gee()
    try:
        geojson = await _run_blocking(svc["get_caminos_by_consorcio_nombre"], nombre)
        if not geojson.get("features"):
            raise NotFoundError(
                message=f"No se encontraron caminos para el consorcio '{nombre}'",
                code="CONSORCIO_NOT_FOUND",
                resource_type="consorcio",
            )
        return JSONResponse(
            content=geojson,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except AppException:
        raise
    except Exception as e:
        logger.error("Error obteniendo caminos por nombre", nombre=nombre, error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "caminos del consorcio"),
            code="GEE_CAMINOS_ERROR",
            status_code=500,
        )


async def get_caminos_coloreados_impl(*, ensure_gee) -> JSONResponse:
    svc = ensure_gee()
    try:
        result = await _run_blocking(svc["get_caminos_con_colores"])
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        logger.error("Error obteniendo caminos coloreados", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "caminos coloreados"),
            code="GEE_CAMINOS_ERROR",
            status_code=500,
        )


async def get_estadisticas_caminos_impl(*, ensure_gee) -> JSONResponse:
    svc = ensure_gee()
    try:
        result = await _run_blocking(svc["get_estadisticas_consorcios"])
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        logger.error("Error obteniendo estadisticas de consorcios", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "estadisticas de consorcios"),
            code="GEE_STATS_ERROR",
            status_code=500,
        )


async def get_gee_layer_impl(*, layer_name: str, ensure_gee) -> JSONResponse:
    svc = ensure_gee()
    try:
        geojson = await _run_blocking(svc["get_layer_geojson"], layer_name)
        return JSONResponse(
            content=geojson,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except ValueError as e:
        raise NotFoundError(
            message=get_safe_error_detail(e, "capa"),
            code="LAYER_NOT_FOUND",
            resource_type="layer",
            resource_id=layer_name,
        )
    except Exception as e:
        logger.error("Error obteniendo capa GEE", layer=layer_name, error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "capa GEE"),
            code="GEE_LAYER_ERROR",
            status_code=500,
        )


async def get_available_image_dates_impl(
    *,
    year: int,
    month: int,
    sensor: str,
    max_cloud: int,
    ensure_gee,
):
    svc = ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        result = await _run_blocking(
            explorer.get_available_dates,
            year=year,
            month=month,
            sensor=sensor,
            max_cloud=max_cloud,
        )
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "fechas disponibles"),
            code="AVAILABLE_DATES_ERROR",
            status_code=500,
        )


async def get_sentinel2_image_impl(
    *,
    target_date: date,
    days_buffer: int,
    max_cloud: int,
    visualization: str,
    ensure_gee,
):
    svc = ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        result = await _run_blocking(
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


async def get_sentinel1_image_impl(
    *,
    target_date: date,
    days_buffer: int,
    visualization: str,
    ensure_gee,
):
    svc = ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        result = await _run_blocking(
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


async def compare_flood_dates_impl(
    *,
    flood_date: date,
    normal_date: date,
    days_buffer: int,
    max_cloud: int,
    ensure_gee,
):
    svc = ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        return await _run_blocking(
            explorer.get_flood_comparison,
            flood_date=flood_date,
            normal_date=normal_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
        )
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "comparacion de fechas"),
            code="IMAGE_COMPARE_ERROR",
            status_code=500,
        )


async def get_available_visualizations_impl():
    from app.domains.geo.gee_service import ImageExplorer

    visualizations = [
        {"id": key, "description": value["description"]}
        for key, value in ImageExplorer.VIS_PRESETS.items()
    ]
    return JSONResponse(
        content=visualizations,
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def get_historic_floods_impl():
    return JSONResponse(
        content={"floods": HISTORIC_FLOODS, "total": len(HISTORIC_FLOODS)},
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def get_historic_flood_tiles_impl(
    *,
    flood_id: str,
    visualization: str,
    ensure_gee,
):
    flood = next((f for f in HISTORIC_FLOODS if f["id"] == flood_id), None)
    if not flood:
        raise NotFoundError(
            message=f"Inundacion '{flood_id}' no encontrada",
            code="FLOOD_NOT_FOUND",
            resource_type="historic_flood",
            resource_id=flood_id,
        )

    svc = ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        flood_date = date.fromisoformat(flood["date"])
        days_buffer = 30 if flood_date.year < 2020 else 15

        result = await _run_blocking(
            explorer.get_sentinel2_image,
            target_date=flood_date,
            days_buffer=days_buffer,
            max_cloud=60,
            visualization=visualization,
            use_median=True,
        )

        if "error" in result:
            result = await _run_blocking(
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


async def export_qgis_project_impl():
    from app.config import settings
    from app.domains.geo.qgis_export import QGISProjectGenerator, fetch_vt_layers

    if not settings.martin_public_url:
        raise AppException(
            message="Martin tile server URL not configured (MARTIN_PUBLIC_URL)",
            code="MARTIN_URL_MISSING",
            status_code=503,
        )

    layers = await fetch_vt_layers(settings.martin_internal_url)
    zip_bytes = QGISProjectGenerator.build(layers, settings.martin_public_url)
    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="consorcio-canalero.qgz"'
        },
    )
