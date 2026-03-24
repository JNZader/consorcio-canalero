"""FastAPI router for the geo domain."""

import asyncio
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundError, get_safe_error_detail
from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.repository import GeoRepository
from app.domains.geo.schemas import (
    GeoJobCreate,
    GeoJobListResponse,
    GeoJobResponse,
    GeoLayerListResponse,
    GeoLayerResponse,
)

logger = get_logger(__name__)

router = APIRouter(tags=["Geo Processing"])


def _get_repo() -> GeoRepository:
    """Dependency that provides the repository instance."""
    return GeoRepository()


# Lazy import to avoid circular deps at module level.
def _require_operator():
    """Return the operator dependency at call time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _require_authenticated():
    """Return the authenticated dependency at call time."""
    from app.auth import require_authenticated

    return require_authenticated


# ──────────────────────────────────────────────
# JOBS
# ──────────────────────────────────────────────


@router.post("/jobs", response_model=GeoJobResponse, status_code=201)
def submit_geo_job(
    payload: GeoJobCreate,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """
    Submit a new geo processing job (requiere operador).

    The job is created in PENDING state. A Celery task will be
    dispatched to the geo-worker for actual processing.
    """
    job = repo.create_job(
        db,
        tipo=payload.tipo,
        parametros=payload.parametros,
    )
    db.commit()

    # TODO: dispatch Celery task based on job.tipo and update celery_task_id

    return job


@router.get("/jobs", response_model=dict)
def list_geo_jobs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """List geo processing jobs with pagination and filters."""
    items, total = repo.get_jobs(
        db,
        page=page,
        limit=limit,
        estado_filter=estado,
        tipo_filter=tipo,
    )
    return {
        "items": [GeoJobListResponse.model_validate(j) for j in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/jobs/{job_id}", response_model=GeoJobResponse)
def get_geo_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """Get geo job detail by ID."""
    job = repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Geo job no encontrado")
    return job


# ──────────────────────────────────────────────
# LAYERS
# ──────────────────────────────────────────────


@router.get("/layers", response_model=dict)
def list_geo_layers(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    fuente: Optional[str] = None,
    area_id: Optional[str] = None,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """List available geo layers with pagination and filters."""
    items, total = repo.get_layers(
        db,
        page=page,
        limit=limit,
        tipo_filter=tipo,
        fuente_filter=fuente,
        area_id_filter=area_id,
    )
    return {
        "items": [GeoLayerListResponse.model_validate(layer) for layer in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/layers/{layer_id}", response_model=GeoLayerResponse)
def get_geo_layer(
    layer_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """Get geo layer detail by ID."""
    layer = repo.get_layer_by_id(db, layer_id)
    if layer is None:
        raise HTTPException(status_code=404, detail="Geo layer no encontrado")
    return layer


# ──────────────────────────────────────────────
# GEE SUB-ROUTER  (Google Earth Engine endpoints)
# ──────────────────────────────────────────────

gee_router = APIRouter(prefix="/gee", tags=["GEE"])


def _lazy_gee_service():
    """Lazy-import the GEE service to avoid import-time initialization."""
    from app.domains.geo.gee_service import (
        _ensure_initialized,
        get_available_layers as gee_available_layers,
        get_caminos_by_consorcio,
        get_caminos_by_consorcio_nombre,
        get_caminos_con_colores,
        get_consorcios_camineros,
        get_estadisticas_consorcios,
        get_gee_service,
        get_image_explorer,
        get_layer_geojson,
        ImageExplorer,
    )
    return {
        "ensure_init": _ensure_initialized,
        "get_available_layers": gee_available_layers,
        "get_caminos_by_consorcio": get_caminos_by_consorcio,
        "get_caminos_by_consorcio_nombre": get_caminos_by_consorcio_nombre,
        "get_caminos_con_colores": get_caminos_con_colores,
        "get_consorcios_camineros": get_consorcios_camineros,
        "get_estadisticas_consorcios": get_estadisticas_consorcios,
        "get_gee_service": get_gee_service,
        "get_image_explorer": get_image_explorer,
        "get_layer_geojson": get_layer_geojson,
        "ImageExplorer": ImageExplorer,
    }


def _ensure_gee():
    """Try to init GEE; raise 503 if unavailable."""
    svc = _lazy_gee_service()
    try:
        svc["ensure_init"]()
    except Exception as e:
        logger.error("No se pudo inicializar GEE", error=str(e))
        raise AppException(
            message="Google Earth Engine no esta disponible temporalmente",
            code="GEE_UNAVAILABLE",
            status_code=503,
        )
    return svc


# ── GEE Layers ──


@gee_router.get("/layers")
async def list_gee_layers() -> JSONResponse:
    """Listar capas disponibles en GEE."""
    svc = _lazy_gee_service()
    return JSONResponse(
        content=svc["get_available_layers"](),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@gee_router.get("/layers/tiles/sentinel2")
async def get_sentinel2_tiles(
    start_date: date = Query(..., description="Fecha de inicio (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Fecha de fin (YYYY-MM-DD)"),
    max_cloud: int = Query(40, ge=0, le=100, description="Porcentaje maximo de nubes"),
):
    """Obtener URL de tiles Sentinel-2 RGB para visualizacion."""
    svc = _ensure_gee()
    try:
        gee_service = svc["get_gee_service"]()
        result = await asyncio.to_thread(
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


@gee_router.get("/layers/caminos/consorcios")
async def list_consorcios_camineros() -> JSONResponse:
    """Listar consorcios camineros disponibles en la red vial."""
    svc = _ensure_gee()
    try:
        consorcios = await asyncio.to_thread(svc["get_consorcios_camineros"])
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


@gee_router.get("/layers/caminos/consorcio/{codigo}")
async def get_caminos_consorcio(codigo: str) -> JSONResponse:
    """Obtener caminos de un consorcio caminero especifico."""
    svc = _ensure_gee()
    try:
        geojson = await asyncio.to_thread(svc["get_caminos_by_consorcio"], codigo)
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


@gee_router.get("/layers/caminos/por-nombre")
async def get_caminos_por_nombre_consorcio(
    nombre: str = Query(..., description="Nombre del consorcio (ccn)"),
) -> JSONResponse:
    """Obtener caminos de un consorcio caminero por nombre."""
    svc = _ensure_gee()
    try:
        geojson = await asyncio.to_thread(svc["get_caminos_by_consorcio_nombre"], nombre)
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


@gee_router.get("/layers/caminos/coloreados")
async def get_caminos_coloreados() -> JSONResponse:
    """Obtener red vial con colores distintos por consorcio caminero."""
    svc = _ensure_gee()
    try:
        result = await asyncio.to_thread(svc["get_caminos_con_colores"])
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


@gee_router.get("/layers/caminos/estadisticas")
async def get_estadisticas_caminos() -> JSONResponse:
    """Obtener estadisticas de kilometros por consorcio caminero."""
    svc = _ensure_gee()
    try:
        result = await asyncio.to_thread(svc["get_estadisticas_consorcios"])
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


@gee_router.get("/layers/{layer_name}")
async def get_gee_layer(layer_name: str) -> JSONResponse:
    """Obtener GeoJSON de una capa desde GEE."""
    svc = _ensure_gee()
    try:
        geojson = await asyncio.to_thread(svc["get_layer_geojson"], layer_name)
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


# ── GEE Analyze ──


@gee_router.post("/analyze")
async def submit_gee_analysis(
    start_date: date = Query(..., description="Fecha de inicio"),
    end_date: date = Query(..., description="Fecha de fin"),
    method: str = Query("fusion", description="Metodo de analisis"),
):
    """Submit a GEE analysis job (flood detection / classification)."""
    from app.domains.geo.gee_tasks import analyze_flood_task

    task = analyze_flood_task.delay(
        start_date.isoformat(), end_date.isoformat(), method
    )
    return {"task_id": task.id, "status": "submitted"}


# ── GEE Images (Image Explorer) ──


@gee_router.get("/images/sentinel2")
async def get_sentinel2_image(
    target_date: date = Query(..., description="Fecha objetivo (YYYY-MM-DD)"),
    days_buffer: int = Query(10, ge=1, le=30),
    max_cloud: int = Query(40, ge=0, le=100),
    visualization: str = Query("rgb"),
):
    """Obtener tiles de imagen Sentinel-2 para una fecha especifica."""
    svc = _ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
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


@gee_router.get("/images/sentinel1")
async def get_sentinel1_image(
    target_date: date = Query(..., description="Fecha objetivo (YYYY-MM-DD)"),
    days_buffer: int = Query(10, ge=1, le=30),
    visualization: str = Query("vv"),
):
    """Obtener tiles de imagen Sentinel-1 (SAR) para una fecha especifica."""
    svc = _ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
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


@gee_router.get("/images/compare")
async def compare_flood_dates(
    flood_date: date = Query(..., description="Fecha de inundacion"),
    normal_date: date = Query(..., description="Fecha de referencia (sin inundacion)"),
    days_buffer: int = Query(10, ge=1, le=30),
    max_cloud: int = Query(40, ge=0, le=100),
):
    """Comparar imagen de inundacion con imagen normal."""
    svc = _ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
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


@gee_router.get("/images/visualizations")
async def get_available_visualizations():
    """Obtener lista de visualizaciones disponibles para Sentinel-2."""
    from app.domains.geo.gee_service import ImageExplorer

    visualizations = [
        {"id": key, "description": value["description"]}
        for key, value in ImageExplorer.VIS_PRESETS.items()
    ]
    return JSONResponse(
        content=visualizations,
        headers={"Cache-Control": "public, max-age=86400"},
    )


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


@gee_router.get("/images/historic-floods")
async def get_historic_floods():
    """Obtener lista de inundaciones historicas pre-configuradas."""
    return JSONResponse(
        content={"floods": HISTORIC_FLOODS, "total": len(HISTORIC_FLOODS)},
        headers={"Cache-Control": "public, max-age=86400"},
    )


@gee_router.get("/images/historic-floods/{flood_id}")
async def get_historic_flood_tiles(
    flood_id: str,
    visualization: str = Query("rgb"),
):
    """Obtener tiles de una inundacion historica pre-configurada."""
    flood = next((f for f in HISTORIC_FLOODS if f["id"] == flood_id), None)
    if not flood:
        raise NotFoundError(
            message=f"Inundacion '{flood_id}' no encontrada",
            code="FLOOD_NOT_FOUND",
            resource_type="historic_flood",
            resource_id=flood_id,
        )

    svc = _ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        flood_date = date.fromisoformat(flood["date"])

        is_old_date = flood_date.year < 2020
        days_buffer = 30 if is_old_date else 15

        result = await asyncio.to_thread(
            explorer.get_sentinel2_image,
            target_date=flood_date,
            days_buffer=days_buffer,
            max_cloud=60,
            visualization=visualization,
            use_median=True,
        )

        if "error" in result:
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


# ── Include GEE sub-router into main geo router ──
router.include_router(gee_router)
