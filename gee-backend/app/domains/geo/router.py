from __future__ import annotations

import inspect
import uuid
from datetime import date  # noqa: F401 — needed for ForwardRef resolution in gee_router endpoints
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.exceptions import AppException
from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.intelligence.router import router as intel_router
from app.domains.geo.repository import GeoRepository
from app.domains.geo.router_analysis import router as analysis_router
from app.domains.geo.router_basins_bundle import (
    router as basins_bundle_router,
)
from app.domains.geo.router_bundle_io import router as bundle_io_router
from app.domains.geo.router_common import (
    ApprovedZonesMapPdfRequest,
    ApprovedZonesSaveRequest,
    _build_approved_zoning_export,
    _build_zonas_operativas_export,
    _get_repo,
    _get_tile_client,
    _get_user_display_name,
    _require_admin,
    _require_authenticated,
    _require_operator,
    _serialize_approved_zoning,
)
from app.domains.geo.router_core import (
    router as core_router,
)
from app.domains.geo.router_gee_support import (
    compare_flood_dates_impl,
    export_qgis_project_impl,
    get_available_image_dates_impl,
    get_available_visualizations_impl,
    get_caminos_coloreados_impl,
    get_caminos_consorcio_impl,
    get_caminos_por_nombre_consorcio_impl,
    get_estadisticas_caminos_impl,
    get_gee_layer_impl,
    get_historic_flood_tiles_impl,
    get_historic_floods_impl,
    get_sentinel1_image_impl,
    get_sentinel2_image_impl,
    get_sentinel2_tiles_impl,
    list_consorcios_camineros_impl,
    list_gee_layers_impl,
)
from app.domains.geo.router_misc_support import (
    export_current_approved_basin_zones_pdf_impl,
    export_current_map_approved_basin_zones_pdf_impl,
    export_geo_bundle_impl,
    get_gee_analysis_impl,
    list_gee_analyses_impl,
    submit_gee_analysis_impl,
)
from app.domains.geo.visualization.router import router as visualization_router
from app.domains.geo.schemas import (
    AnalisisGeoCreate,
    AnalisisGeoResponse,
    DemPipelineRequest,
    DemPipelineResponse,
    GeoJobCreate,
)
from app.domains.geo.service import dispatch_job

logger = get_logger(__name__)
router = APIRouter(tags=["Geo Processing"])


for subrouter in (
    core_router,
    basins_bundle_router,
    bundle_io_router,
    analysis_router,
):
    router.include_router(subrouter)


def submit_geo_job(
    payload: GeoJobCreate,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    return dispatch_job(db, tipo=payload.tipo, parametros=payload.parametros)


def trigger_dem_pipeline(
    payload: DemPipelineRequest = DemPipelineRequest(),
    db: Session = Depends(get_db),
    _user=Depends(_require_admin()),
):
    from app.domains.geo.models import TipoGeoJob

    job = dispatch_job(
        db,
        tipo=TipoGeoJob.DEM_FULL_PIPELINE,
        parametros={
            "area_id": payload.area_id,
            "min_basin_area_ha": payload.min_basin_area_ha,
        },
    )
    return DemPipelineResponse(job_id=job.id, tipo=job.tipo, estado=job.estado)


def save_current_approved_basin_zones(
    payload: ApprovedZonesSaveRequest,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    user=Depends(_require_operator()),
):
    zoning = repo.create_approved_zoning_version(
        db,
        nombre=payload.nombre,
        cuenca=payload.cuenca,
        feature_collection=payload.feature_collection,
        assignments=payload.assignments,
        zone_names=payload.zone_names,
        approved_by_id=getattr(user, "id", None),
        notes=payload.notes,
    )
    db.commit()
    db.refresh(zoning)
    return _serialize_approved_zoning(db, zoning)


def export_geo_bundle(
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_admin()),
):
    return export_geo_bundle_impl(
        db, repo, _build_zonas_operativas_export, _build_approved_zoning_export
    )


def export_current_approved_basin_zones_pdf(
    cuenca: Optional[str] = Query(
        default=None, description="Optional filter by cuenca name"
    ),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
):
    return export_current_approved_basin_zones_pdf_impl(
        cuenca, db, repo, _get_user_display_name
    )


def export_current_map_approved_basin_zones_pdf(
    payload: ApprovedZonesMapPdfRequest, db: Session = Depends(get_db)
):
    return export_current_map_approved_basin_zones_pdf_impl(payload, db)


async def proxy_tile(
    layer_id: uuid.UUID,
    z: int,
    x: int,
    y: int,
    colormap: Optional[str] = None,
    encoding: Optional[str] = None,
    hide_classes: Optional[str] = None,
    hide_ranges: Optional[str] = None,
):
    from app.config import settings

    params = {
        k: v
        for k, v in {
            "colormap": colormap,
            "encoding": encoding,
            "hide_classes": hide_classes,
            "hide_ranges": hide_ranges,
        }.items()
        if v
    }
    try:
        resp = await _get_tile_client().get(
            f"{settings.geo_worker_tile_url}/tiles/{layer_id}/{z}/{x}/{y}.png",
            params=params,
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        return Response(status_code=204, headers={"Access-Control-Allow-Origin": "*"})
    if resp.status_code == 204 or resp.status_code >= 400:
        return Response(status_code=204, headers={"Access-Control-Allow-Origin": "*"})
    return Response(
        content=resp.content,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


gee_router = APIRouter(prefix="/gee", tags=["GEE"])


def _lazy_gee_service():
    from app.domains.geo.gee_service import (
        ImageExplorer,
        _ensure_initialized,
        get_available_layers,
        get_caminos_by_consorcio,
        get_caminos_by_consorcio_nombre,
        get_caminos_con_colores,
        get_consorcios_camineros,
        get_estadisticas_consorcios,
        get_gee_service,
        get_image_explorer,
        get_layer_geojson,
    )

    return {
        "ensure_init": _ensure_initialized,
        "get_available_layers": get_available_layers,
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


def _gee_async(handler):
    async def endpoint(*args, **kwargs):
        return await handler(*args, **kwargs, ensure_gee=_ensure_gee)

    endpoint.__name__ = getattr(handler, "__name__", "gee_endpoint")
    endpoint.__signature__ = inspect.Signature(
        parameters=[
            parameter
            for name, parameter in inspect.signature(handler).parameters.items()
            if name != "ensure_gee"
        ]
    )
    return endpoint


def _gee_simple(handler):
    async def endpoint(*args, **kwargs):
        return await handler(*args, **kwargs)

    endpoint.__name__ = getattr(handler, "__name__", "gee_simple_endpoint")
    endpoint.__signature__ = inspect.signature(handler)
    return endpoint


list_gee_layers = _gee_simple(lambda: list_gee_layers_impl(_lazy_gee_service))
gee_router.get("/layers")(list_gee_layers)
get_sentinel2_tiles = _gee_async(get_sentinel2_tiles_impl)
list_consorcios_camineros = _gee_async(list_consorcios_camineros_impl)
get_caminos_consorcio = _gee_async(get_caminos_consorcio_impl)
get_caminos_por_nombre_consorcio = _gee_async(get_caminos_por_nombre_consorcio_impl)
get_caminos_coloreados = _gee_async(get_caminos_coloreados_impl)
get_estadisticas_caminos = _gee_async(get_estadisticas_caminos_impl)
get_gee_layer = _gee_async(get_gee_layer_impl)
get_available_image_dates = _gee_async(get_available_image_dates_impl)
get_sentinel2_image = _gee_async(get_sentinel2_image_impl)
get_sentinel1_image = _gee_async(get_sentinel1_image_impl)
compare_flood_dates = _gee_async(compare_flood_dates_impl)

get_available_visualizations = _gee_simple(get_available_visualizations_impl)
gee_router.get("/images/visualizations")(get_available_visualizations)
get_historic_floods = _gee_simple(get_historic_floods_impl)
gee_router.get("/images/historic-floods")(get_historic_floods)
get_historic_flood_tiles = _gee_async(get_historic_flood_tiles_impl)

gee_router.get("/layers/tiles/sentinel2")(get_sentinel2_tiles)
gee_router.get("/layers/caminos/consorcios")(list_consorcios_camineros)
gee_router.get("/layers/caminos/consorcio/{codigo}")(get_caminos_consorcio)
gee_router.get("/layers/caminos/por-nombre")(get_caminos_por_nombre_consorcio)
gee_router.get("/layers/caminos/coloreados")(get_caminos_coloreados)
gee_router.get("/layers/caminos/estadisticas")(get_estadisticas_caminos)
gee_router.get("/layers/{layer_name}")(get_gee_layer)
gee_router.get("/images/available-dates")(get_available_image_dates)
gee_router.get("/images/sentinel2")(get_sentinel2_image)
gee_router.get("/images/sentinel1")(get_sentinel1_image)
gee_router.get("/images/compare")(compare_flood_dates)
gee_router.get("/images/historic-floods/{flood_id}")(get_historic_flood_tiles)


@gee_router.post("/analysis", response_model=AnalisisGeoResponse, status_code=201)
def submit_gee_analysis(
    payload: AnalisisGeoCreate,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    return submit_gee_analysis_impl(payload, db, repo)


@gee_router.get("/analysis", response_model=dict)
def list_gee_analyses(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    return list_gee_analyses_impl(page, limit, tipo, estado, db, repo)


@gee_router.get("/analysis/{analisis_id}", response_model=AnalisisGeoResponse)
def get_gee_analysis(
    analisis_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    return get_gee_analysis_impl(analisis_id, db, repo)


router.include_router(gee_router)


router.include_router(intel_router, prefix="/intelligence")
router.include_router(visualization_router, prefix="/render", tags=["Visualization"])


@router.get("/export/qgis", tags=["Export"])
async def export_qgis_project(_user: User = Depends(_require_operator())):
    try:
        return await export_qgis_project_impl()
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
