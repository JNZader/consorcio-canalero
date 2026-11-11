from __future__ import annotations

import inspect
import uuid
from datetime import date  # noqa: F401 — needed for ForwardRef resolution in gee_router endpoints
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.models import User
from app.config import settings
from app.core.exceptions import AppException, NotFoundError, RateLimitExceededError
from app.core.logging import get_logger
from app.core.rate_limit import DistributedRateLimiter
from app.db.session import get_db
from app.domains.geo.intelligence.router import router as intel_router
from app.domains.geo.canales_publicacion.router import router as canales_publicacion_router
from app.domains.geo.puntos_interes.router import router as puntos_interes_router
from app.domains.geo.rainfall.router import router as rainfall_router
from app.domains.geo.relevamiento.router import router as relevamiento_router
from app.domains.geo.repository import GeoRepository
from app.domains.geo.router_analysis import router as analysis_router
from app.domains.geo.router_basins_bundle import (
    router as basins_bundle_router,
)
from app.domains.geo.router_bundle_io import router as bundle_io_router
from app.domains.geo.router_common import (
    _get_repo,
    _require_operator,
)
from app.domains.geo.router_core import (
    router as core_router,
)
from app.domains.geo.router_ficha import router as ficha_router
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
    get_all_imagery_shortlists_impl,
    get_historic_flood_candidates_impl,
    get_historic_flood_water_delta_impl,
    get_historic_flood_tiles_impl,
    get_historic_floods_impl,
    get_image_scenes_impl,
    get_sentinel1_image_impl,
    get_sentinel2_image_impl,
    get_sentinel2_annual_impl,
    get_sentinel2_monthly_impl,
    get_jrc_occurrence_impl,
    get_jrc_year_impl,
    get_satellite_image_impl,
    get_sentinel2_tiles_impl,
    list_consorcios_camineros_impl,
    list_gee_layers_impl,
)
from app.domains.geo.router_misc_support import (
    get_gee_analysis_impl,
    list_gee_analyses_impl,
    submit_gee_analysis_impl,
)
from app.domains.geo.visualization.router import router as visualization_router
from app.domains.geo.schemas import (
    AnalisisGeoCreate,
    AnalisisGeoListResponse,
    AnalisisGeoResponse,
)
from app.shared.pagination import PaginatedResponse

logger = get_logger(__name__)
router = APIRouter(tags=["Geo Processing"])


for subrouter in (
    core_router,
    basins_bundle_router,
    bundle_io_router,
    analysis_router,
    # Public + rate limited, and a router of its own so neither property leaks
    # onto the operator routes above (design §2, JDB-003).
    ficha_router,
):
    router.include_router(subrouter)


# ─────────────────────────────────────────────────────────────────────────────
# NOTE: this module is an AGGREGATOR. Every geo handler lives in one of the
# sub-routers included above. Seven un-decorated copies of those handlers used
# to sit here — never registered, never reached, and two of them were the
# PRE-HARDENING versions (a map-PDF export with no body/image/list caps and a
# tile proxy with no zoom bound). Re-decorating one would have restored the
# hole. Do not reintroduce handler bodies in this file.
# ─────────────────────────────────────────────────────────────────────────────


gee_router = APIRouter(
    prefix="/gee",
    tags=["GEE"],
    dependencies=[Depends(_require_operator())],
)


# ── Per-operator throttle on POST /api/v2/geo/gee/analysis (#713) ────────────
# Each accepted run publishes a Celery task whose GEE work mints map tiles
# against the project's METERED quota, so this bounds spend per account, not
# per IP: the route is operator-only and several operators share an office
# NAT. It lives on the POST route only — GET /analysis (list) and
# GET /analysis/{id} (poll) are cheap reads and must stay unthrottled, which
# is also why the dependency is NOT on ``gee_router`` itself (same isolation
# argument as the ficha router, JDB-003).
_gee_analysis_limiter: DistributedRateLimiter | None = None


def get_gee_analysis_rate_limiter() -> DistributedRateLimiter:
    """Own limiter instance, own Redis key namespace for GEE analysis runs.

    Redis-down policy (same as ``router_ficha.get_ficha_rate_limiter``):
    ``DistributedRateLimiter`` degrades to a per-process in-memory window and
    logs a warning. It does NOT fail open and does NOT fail the request.

    Degraded ceiling, concretely: the fallback window is per PROCESS, and
    ``app/server.py`` runs uvicorn with ``workers=2``, so with Redis down the
    real limit is 2 x ``gee_analysis_rate_limit_requests`` = 20 runs/h per
    operator, not 10 — and it grows linearly with workers and replicas.
    Accepted because the limiter is a cost bound, not a security bound: the
    route is already operator-authenticated, and the GEE work itself is
    serialized behind the Celery worker pool.

    Why 10/h: one analysis run mints one GEE map per layer involved, so the
    metered-call count scales with RUNS, not with request volume. A
    legitimate operator preparing a report re-runs a comparison a handful of
    times in an hour; 10 covers that with margin while capping the
    multiplication the >=1d fusion gate (#713) made cheap.
    """
    global _gee_analysis_limiter
    if _gee_analysis_limiter is None:
        _gee_analysis_limiter = DistributedRateLimiter(
            redis_url=settings.redis_url,
            max_requests=settings.gee_analysis_rate_limit_requests,
            window_seconds=settings.gee_analysis_rate_limit_window,
            key_prefix="ratelimit:gee_analysis:",
        )
    return _gee_analysis_limiter


async def enforce_gee_analysis_rate_limit(
    user: User = Depends(_require_operator()),
) -> None:
    """429 ``RATE_LIMIT_EXCEEDED`` per operator BEFORE the run is accepted.

    Reuses the router's operator dependency (``_require_operator()`` returns
    the same callable, so FastAPI solves it once per request and hands the
    authenticated ``User`` here) — the limit key is ``operator:{user.id}``,
    one bucket per ACCOUNT.

    Route-level ``dependencies=[...]``, not a handler parameter: FastAPI
    solves the route's dependency list before the endpoint's own parameters,
    so the 429 fires before the body is parsed and before any DB session,
    repo or Celery outbox row exists. Honors ``settings.rate_limit_disabled``
    exactly like the ficha limiter.
    """
    if settings.rate_limit_disabled:
        return

    limiter = get_gee_analysis_rate_limiter()
    permitido, _restantes, reset = await limiter.check(f"operator:{user.id}")
    if not permitido:
        raise RateLimitExceededError(
            message="Límite de corridas de análisis GEE alcanzado. Reintentá más tarde.",
            retry_after=max(1, int(reset)),
            # El límite REAL es el del limiter que acaba de denegar — leer el
            # setting acá divorciaba el 429 de la ventana que realmente corre
            # (un limiter con budget parcheado en la instancia reportaba el default).
            limit=limiter.max_requests,
        )


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


def _retired_time_layer(handler):
    """JRC and annual/monthly Sentinel-2 have no frontend consumer.

    #637 removed the UI. Leaving the handlers live kept spending Earth
    Engine quota on a surface nobody paints. The routes stay so an old
    client gets 404 instead of a tile URL, and they return before
    ``ensure_gee``.
    """

    async def endpoint(*args, **kwargs):
        raise NotFoundError(
            message="Esta capa temporal ya no está publicada.",
            code="TIME_LAYER_RETIRED",
        )

    endpoint.__name__ = getattr(handler, "__name__", "retired_time_layer")
    endpoint.__signature__ = inspect.signature(handler)
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
get_sentinel2_annual = _retired_time_layer(_gee_async(get_sentinel2_annual_impl))
get_sentinel2_monthly = _retired_time_layer(_gee_async(get_sentinel2_monthly_impl))
get_jrc_occurrence = _retired_time_layer(_gee_async(get_jrc_occurrence_impl))
get_jrc_year = _retired_time_layer(_gee_async(get_jrc_year_impl))
get_sentinel1_image = _gee_async(get_sentinel1_image_impl)
get_satellite_image = _gee_async(get_satellite_image_impl)
get_image_scenes = _gee_async(get_image_scenes_impl)
compare_flood_dates = _gee_async(compare_flood_dates_impl)

get_available_visualizations = _gee_simple(get_available_visualizations_impl)
gee_router.get("/images/visualizations")(get_available_visualizations)
get_historic_floods = _gee_simple(get_historic_floods_impl)
gee_router.get("/images/historic-floods")(get_historic_floods)
get_all_imagery_shortlists = _gee_simple(get_all_imagery_shortlists_impl)
gee_router.get("/images/imagery-shortlists")(get_all_imagery_shortlists)
get_historic_flood_candidates = _gee_simple(get_historic_flood_candidates_impl)
gee_router.get("/images/historic-floods/{flood_id}/candidates")(get_historic_flood_candidates)
get_historic_flood_water_delta = _gee_simple(get_historic_flood_water_delta_impl)
gee_router.get("/images/historic-floods/{flood_id}/water-delta")(get_historic_flood_water_delta)
get_historic_flood_tiles = _gee_async(get_historic_flood_tiles_impl)

gee_router.get("/layers/tiles/sentinel2")(get_sentinel2_tiles)
gee_router.get("/layers/caminos/consorcios")(list_consorcios_camineros)
gee_router.get("/layers/caminos/consorcio/{codigo}")(get_caminos_consorcio)
gee_router.get("/layers/caminos/por-nombre")(get_caminos_por_nombre_consorcio)
gee_router.get("/layers/caminos/coloreados")(get_caminos_coloreados)
gee_router.get("/layers/caminos/estadisticas")(get_estadisticas_caminos)
gee_router.get("/layers/jrc-surface-water")(get_jrc_occurrence)
gee_router.get("/layers/jrc-surface-water/year")(get_jrc_year)
gee_router.get("/layers/{layer_name}")(get_gee_layer)
gee_router.get("/images/available-dates")(get_available_image_dates)
gee_router.get("/images/sentinel2/annual")(get_sentinel2_annual)
gee_router.get("/images/sentinel2/monthly")(get_sentinel2_monthly)
gee_router.get("/images/sentinel2")(get_sentinel2_image)
gee_router.get("/images/sentinel1")(get_sentinel1_image)
gee_router.get("/images/compare")(compare_flood_dates)
gee_router.get("/images/scenes/{sensor}")(get_image_scenes)
gee_router.get("/images/{sensor}")(get_satellite_image)
gee_router.get("/images/historic-floods/{flood_id}")(get_historic_flood_tiles)


@gee_router.post(
    "/analysis",
    response_model=AnalisisGeoResponse,
    status_code=201,
    # Order of defense: operator auth (router-level dep above) → per-operator
    # rate limit (here, before the body is parsed) → payload validation → the
    # handler's DB write + Celery outbox row. Rejecting after the write would
    # leave a throttled caller still holding a metered run (#713).
    dependencies=[Depends(enforce_gee_analysis_rate_limit)],
)
def submit_gee_analysis(
    payload: AnalisisGeoCreate,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    return submit_gee_analysis_impl(payload, db, repo)


@gee_router.get(
    "/analysis",
    response_model=PaginatedResponse[AnalisisGeoListResponse],
)
def list_gee_analyses(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
) -> PaginatedResponse[AnalisisGeoListResponse]:
    return list_gee_analyses_impl(page, limit, tipo, estado, db, repo)


@gee_router.get("/analysis/{analisis_id}", response_model=AnalisisGeoResponse)
def get_gee_analysis(
    analisis_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    return get_gee_analysis_impl(analisis_id, db, repo)


router.include_router(gee_router)


router.include_router(intel_router, prefix="/intelligence")
router.include_router(puntos_interes_router, prefix="/puntos-interes")
router.include_router(canales_publicacion_router, prefix="/canales")
router.include_router(rainfall_router)
# Fase B: the segment survey and its DEM candidate. Operator-and-admin only,
# append-only, and published nowhere.
router.include_router(relevamiento_router)
router.include_router(visualization_router, prefix="/render", tags=["Visualization"])


@router.get("/export/qgis", tags=["Export"])
async def export_qgis_project(_user: User = Depends(_require_operator())):
    try:
        return await export_qgis_project_impl()
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
