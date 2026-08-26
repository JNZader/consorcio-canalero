"""Core geo router endpoints for jobs, layers, bundles and approved basins."""

import os
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.models import GeoLayer
from app.domains.geo.repository import GeoRepository
from app.domains.geo.rescale_policy import validate_rescale
from app.domains.geo.router_common import (
    _get_repo,
    _get_tile_client,
    _require_admin,
    _require_operator,
)
from app.domains.geo.schemas import (
    DemPipelineRequest,
    DemPipelineResponse,
    GeoJobCreate,
    GeoJobListResponse,
    GeoJobResponse,
    GeoLayerListResponse,
    GeoLayerResponse,
)
from app.domains.geo.service import dispatch_job
from app.shared.pagination import PaginatedResponse

logger = get_logger(__name__)

router = APIRouter(tags=["Geo Processing"])

# Deepest XYZ zoom the public tile proxy will forward. Web-Mercator tiles stop
# being meaningful long before this (z22 ≈ 4 cm/px at the equator) and every
# raster we publish is 30 m/px; the bound exists to keep ``2 ** z`` — computed
# downstream to derive the tile bounds — out of caller control.
#
# DUPLICATED ON PURPOSE in ``tile_service.py`` (the geo-worker tile service is a
# SEPARATE process listening on its own port, so it cannot import this and must
# not trust an upstream). If you change this number, change that one too.
MAX_TILE_ZOOM = 22

PUBLIC_TILE_CAPABLE_TYPES = {
    "dem_raw",
    "slope",
    "aspect",
    "twi",
    "hand",
    "flow_acc",
    "flow_dir",
    "terrain_class",
    "flood_risk",
    "drainage_need",
    "precip_normal",
}


# Layer types published to anonymous visitors in production.
# `terrain_class` was published at the consortium's request (2026-07-30).
# `flood_risk` and `drainage_need` are raster overlays for the parcel map
# (2026-08-01), and `precip_normal` exposes CHIRPS 1991-2020 normals for the
# multi-hazard viewer (2026-08-17). Other DEM pipeline types remain private.
# Basins are served by the separate public `/geo/basins` endpoint.
PUBLIC_PRODUCTION_LAYER_TYPES = {
    "dem_raw",
    "terrain_class",
    "flood_risk",
    "drainage_need",
    "precip_normal",
}


# Throttle for the "rescale layer lookup unavailable" warning.
#
# The tile route is deliberately EXEMPT from the global rate limiter (see the
# ``proxy_tile`` docstring), and logs ship off-box to BetterStack whenever a
# Logtail token is set (``app/core/logging.py``). A database outage therefore
# hits this warning once per tile — ~256 tiles per viewport, per visitor — so an
# unthrottled emit turns a DB incident into a billable log flood. The message is
# identical every time, so one line per minute carries the same information.
#
# Process-local on purpose: no shared state, no lock. ``proxy_tile`` is async, so
# every execution in a worker runs on that worker's single event-loop thread;
# with several workers each keeps its own latch, which is the intended blast
# radius (one line per minute per worker). A benign race would at worst emit a
# second line.
_RESCALE_LOOKUP_WARN_INTERVAL_S = 60.0
_rescale_lookup_warn_last: Optional[float] = None
_rescale_lookup_warn_suppressed = 0


def _rescale_lookup_warn_budget(now: float) -> Optional[int]:
    """Claim permission to emit the lookup-failure warning.

    Returns the number of occurrences suppressed since the previous emission
    (``0`` on the first failure, so the first one is always logged), or ``None``
    when the caller must stay silent because an identical warning was emitted
    less than ``_RESCALE_LOOKUP_WARN_INTERVAL_S`` ago.
    """
    global _rescale_lookup_warn_last, _rescale_lookup_warn_suppressed

    last = _rescale_lookup_warn_last
    if last is not None and (now - last) < _RESCALE_LOOKUP_WARN_INTERVAL_S:
        _rescale_lookup_warn_suppressed += 1
        return None

    suppressed = _rescale_lookup_warn_suppressed
    _rescale_lookup_warn_last = now
    _rescale_lookup_warn_suppressed = 0
    return suppressed


def _reset_rescale_lookup_warn_throttle() -> None:
    """Clear the warning latch. Test hook — the state is module-global."""
    global _rescale_lookup_warn_last, _rescale_lookup_warn_suppressed
    _rescale_lookup_warn_last = None
    _rescale_lookup_warn_suppressed = 0


def _parse_rescale_query_value(name: str, value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{name} debe ser un valor numerico") from exc


def _truthy_env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _public_map_layer_eval_enabled() -> bool:
    from app.config import _is_production_env, settings

    # Review/evaluation flag only; it is not a production publication policy.
    # OJO: no hay opt-in del frontend (el flag VITE_PUBLIC_MAP_LAYER_EVAL se
    # elimino cuando el backend paso a ser la unica autoridad de publicacion):
    # con este flag prendido en un entorno no-productivo, el mapa ANONIMO
    # muestra directamente los 10 tipos tile-capable. Prod/staging quedan
    # bloqueados server-side por _is_production_env.
    return _truthy_env_flag("PUBLIC_MAP_LAYER_EVAL") and not _is_production_env(
        settings.environment
    )


def _public_layer_types() -> set[str]:
    return (
        PUBLIC_TILE_CAPABLE_TYPES
        if _public_map_layer_eval_enabled()
        else PUBLIC_PRODUCTION_LAYER_TYPES
    )


def _public_layer_source_filter():
    return or_(
        and_(GeoLayer.fuente == "dem_pipeline", GeoLayer.tipo != "precip_normal"),
        and_(GeoLayer.fuente == "gee", GeoLayer.tipo == "precip_normal"),
    )


@router.post("/jobs", response_model=GeoJobResponse, status_code=201)
def submit_geo_job(
    payload: GeoJobCreate,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """
    Submit a new geo processing job (requiere operador).

    The job and durable Celery publication intent are committed together.
    Publication is attempted immediately and retried asynchronously if needed.
    """
    return dispatch_job(
        db,
        tipo=payload.tipo,
        parametros=payload.parametros,
    )


@router.get("/jobs", response_model=PaginatedResponse[GeoJobListResponse])
def list_geo_jobs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
) -> PaginatedResponse[GeoJobListResponse]:
    """List geo processing jobs with pagination and filters."""
    items, total = repo.get_jobs(
        db,
        page=page,
        limit=limit,
        estado_filter=estado,
        tipo_filter=tipo,
    )
    return PaginatedResponse[GeoJobListResponse].create(
        items=[GeoJobListResponse.model_validate(j) for j in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/jobs/{job_id}", response_model=GeoJobResponse)
def get_geo_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Get geo job detail by ID."""
    job = repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Geo job no encontrado")
    return job


# ──────────────────────────────────────────────
# LAYERS
# ──────────────────────────────────────────────


@router.get("/layers", response_model=PaginatedResponse[GeoLayerListResponse])
def list_geo_layers(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    fuente: Optional[str] = None,
    area_id: Optional[str] = None,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
) -> PaginatedResponse[GeoLayerListResponse]:
    """List available geo layers with pagination and filters."""
    items, total = repo.get_layers(
        db,
        page=page,
        limit=limit,
        tipo_filter=tipo,
        fuente_filter=fuente,
        area_id_filter=area_id,
    )
    return PaginatedResponse[GeoLayerListResponse].create(
        items=[GeoLayerListResponse.model_validate(layer) for layer in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/layers/public",
    response_model=PaginatedResponse[GeoLayerListResponse],
)
def list_public_geo_layers(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    fuente: Optional[str] = None,
    area_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[GeoLayerListResponse]:
    """List a safe public subset of geo layers.

    Non-authenticated base visualization only. Publication is source/type
    scoped, so this endpoint never becomes a general public metadata catalog.

    In production only `PUBLIC_PRODUCTION_LAYER_TYPES` is exposed; the local
    review flag widens the set to every tile-capable type.
    """
    allowed_types = _public_layer_types()
    if tipo and tipo not in allowed_types:
        return PaginatedResponse[GeoLayerListResponse].create(
            items=[], total=0, page=page, limit=limit
        )
    # Terrain products come from the DEM pipeline; CHIRPS normals are
    # registered by their production generator as GEE layers.
    if fuente and fuente not in {"dem_pipeline", "gee"}:
        return PaginatedResponse[GeoLayerListResponse].create(
            items=[], total=0, page=page, limit=limit
        )

    query = db.query(GeoLayer).filter(
        GeoLayer.tipo.in_(allowed_types), _public_layer_source_filter()
    )
    if tipo:
        query = query.filter(GeoLayer.tipo == tipo)
    if area_id:
        query = query.filter(GeoLayer.area_id == area_id)
    if fuente:
        query = query.filter(GeoLayer.fuente == fuente)
    total = query.count()
    items = (
        query.order_by(GeoLayer.created_at.desc(), GeoLayer.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return PaginatedResponse[GeoLayerListResponse].create(
        items=[GeoLayerListResponse.model_validate(layer) for layer in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/layers/{layer_id}", response_model=GeoLayerResponse)
def get_geo_layer(
    layer_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Get geo layer detail by ID."""
    layer = repo.get_layer_by_id(db, layer_id)
    if layer is None:
        raise HTTPException(status_code=404, detail="Geo layer no encontrado")
    return layer


@router.get("/layers/{layer_id}/file")
def get_geo_layer_file(
    layer_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Serve a GeoLayer file (GeoTIFF or GeoJSON) for download or frontend rendering.

    Returns a streaming response with the appropriate content-type.
    """
    layer = repo.get_layer_by_id(db, layer_id)
    if layer is None:
        raise HTTPException(status_code=404, detail="Geo layer no encontrado")

    file_path = Path(layer.archivo_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Archivo no encontrado en disco: {layer.archivo_path}",
        )

    # Determine content type based on format
    content_type_map = {
        "geotiff": "image/tiff",
        "geojson": "application/geo+json",
    }
    content_type = content_type_map.get(layer.formato, "application/octet-stream")

    def _file_iterator():
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    return StreamingResponse(
        _file_iterator(),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_path.name}"',
            "Cache-Control": "public, max-age=3600",
        },
    )


# ──────────────────────────────────────────────
# DEM PIPELINE
# ──────────────────────────────────────────────


@router.post("/dem-pipeline", response_model=DemPipelineResponse, status_code=201)
def trigger_dem_pipeline(
    payload: DemPipelineRequest = DemPipelineRequest(),
    db: Session = Depends(get_db),
    _user=Depends(_require_admin()),
):
    """Trigger the full DEM pipeline: download from GEE + terrain analysis + basin delineation.

    Admin only. Returns a job ID for status polling via GET /jobs/{job_id}.
    """
    from app.domains.geo.models import TipoGeoJob

    job = dispatch_job(
        db,
        tipo=TipoGeoJob.DEM_FULL_PIPELINE,
        parametros={
            "area_id": payload.area_id,
            "min_basin_area_ha": payload.min_basin_area_ha,
        },
    )
    return DemPipelineResponse(
        job_id=job.id,
        tipo=job.tipo,
        estado=job.estado,
    )


# ──────────────────────────────────────────────
# TILE PROXY (forwards to geo-worker tile service)
# ──────────────────────────────────────────────


@router.get("/layers/{layer_id}/tiles/{z}/{x}/{y}.png")
async def proxy_tile(
    layer_id: uuid.UUID,
    z: int = PathParam(..., ge=0, le=MAX_TILE_ZOOM),
    x: int = PathParam(..., ge=0),
    y: int = PathParam(..., ge=0),
    colormap: Optional[str] = Query(default=None),
    encoding: Optional[str] = Query(default=None),
    hide_classes: Optional[str] = Query(default=None),
    hide_ranges: Optional[str] = Query(default=None),
    terrain_smoothing: Optional[str] = Query(default=None),
    rescale_min: Optional[str] = Query(default=None),
    rescale_max: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Proxy tile requests to the geo-worker tile service (public).

    Forwards the request to the internal tile service running on the
    geo-worker container and streams the response back to the client.

    Public endpoint — Leaflet TileLayer cannot set custom auth headers
    on tile requests, and DEM tiles are not sensitive data.

    z/x/y are BOUNDED here. This route is public AND exempt from the global
    rate limiter (``DistributedRateLimitMiddleware`` skips any path containing
    ``/tiles/``, because tiles are high-volume), so an unbounded ``z`` was an
    unauthenticated, unthrottled amplification knob: the tile service computes
    ``2 ** z`` to derive the mercator bounds, and a caller-chosen exponent in
    the billions turns that into a multi-hundred-MB bigint on the geo-worker.
    Zoom 22 is already ~4 cm/px — far past any DEM product we serve.
    """
    from app.config import settings

    _cors = {"Access-Control-Allow-Origin": "*"}

    parsed_rescale_min = _parse_rescale_query_value("rescale_min", rescale_min)
    parsed_rescale_max = _parse_rescale_query_value("rescale_max", rescale_max)
    # Reject globally unsupported public ranges before any layer existence check.
    validate_rescale("precip_normal", parsed_rescale_min, parsed_rescale_max)
    canonical_rescale = None
    if parsed_rescale_min is not None:
        try:
            layer = (
                db.query(GeoLayer)
                .filter(
                    GeoLayer.id == layer_id,
                    GeoLayer.tipo.in_(_public_layer_types()),
                    _public_layer_source_filter(),
                )
                .one_or_none()
            )
        except SQLAlchemyError as exc:
            # The layer-tipo lookup hit a database failure. It exists only to
            # resolve the CANONICAL rescale override for the layer's type, so
            # forward the tile without an override rather than fail it.
            #
            # Be honest about how much this buys during a real outage. The
            # geo-worker is NOT independent of this database: ``_get_layer``
            # (tile_service.py) opens its own ``SessionLocal`` against the SAME
            # Postgres and raises 404 when it cannot read the row, which the
            # blanket ``>= 400 -> 204`` mapping at the end of this function
            # turns into a blank tile. So this does NOT mean "the worker
            # re-renders with its defaults".
            #
            # What it actually preserves is the worker's BYTE CACHE: the cache
            # lookup in ``get_tile`` returns before ``_get_layer`` is ever
            # called, so an already-cached tile is still served during the
            # outage. Note the cache key embeds the rescale token, so the hit
            # has to be on the no-override (``r=-``) variant of that tile —
            # dropping the override changes which cached entry we ask for.
            # Everything else (cold miss, uncached variant) degrades from a
            # 500 to a 204, which is strictly no worse for the caller and keeps
            # the failure inside the tile instead of the whole response.
            #
            # The 404 "is this layer public?" check degrades with the lookup;
            # the worker cannot serve an unknown layer from cache anyway.
            #
            # Only SQLAlchemyError degrades — a programmer error must still
            # surface as a 500 rather than be masked as a blank tile.
            suppressed = _rescale_lookup_warn_budget(time.monotonic())
            if suppressed is not None:
                logger.warning(
                    "Tile rescale layer lookup unavailable; forwarding without override",
                    # A sample, not the only affected layer: the warning is
                    # throttled and covers every failure in the window.
                    layer_id=str(layer_id),
                    error_type=type(exc).__name__,
                    suppressed_since_last=suppressed,
                )
        else:
            if layer is None:
                raise HTTPException(status_code=404, detail="Geo layer no encontrado")
            layer_tipo = getattr(layer.tipo, "value", layer.tipo)
            canonical_rescale = validate_rescale(layer_tipo, parsed_rescale_min, parsed_rescale_max)

    # x/y must be inside the pyramid for this zoom; outside is "no tile here",
    # which is exactly what the upstream answers for an out-of-bounds tile.
    if x >= 2**z or y >= 2**z:
        return Response(status_code=204, headers=_cors)

    # Build the upstream URL
    params = {}
    if colormap:
        params["colormap"] = colormap
    if encoding:
        params["encoding"] = encoding
    if hide_classes:
        params["hide_classes"] = hide_classes
    if hide_ranges:
        params["hide_ranges"] = hide_ranges
    if terrain_smoothing:
        params["terrain_smoothing"] = terrain_smoothing
    if canonical_rescale is not None:
        params["rescale_min"], params["rescale_max"] = canonical_rescale

    upstream_url = f"{settings.geo_worker_tile_url}/tiles/{layer_id}/{z}/{x}/{y}.png"

    try:
        client = _get_tile_client()
        resp = await client.get(upstream_url, params=params)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return Response(status_code=204, headers=_cors)

    if resp.status_code == 204:
        return Response(status_code=204, headers=_cors)

    if resp.status_code >= 400:
        return Response(status_code=204, headers=_cors)

    return Response(
        content=resp.content,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            **_cors,
        },
    )
