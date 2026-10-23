"""Core geo router endpoints for jobs, layers, bundles and approved basins."""

import os
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool
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
# multi-hazard viewer (2026-08-17). `hand` (height above nearest drainage)
# is tile-capable already; publishing it is UX-12 (2026-10-12).
# Other DEM pipeline types remain private.
# Basins are served by the separate public `/geo/basins` endpoint.
PUBLIC_PRODUCTION_LAYER_TYPES = {
    "dem_raw",
    "terrain_class",
    "flood_risk",
    "drainage_need",
    "precip_normal",
    "hand",
}


# Throttle for the "publicity layer lookup unavailable" warning.
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
#
# Renamed with the C1 fix: the lookup being warned about stopped being
# rescale-only when the publicity gate became unconditional — the latch and the
# budget logic are unchanged.
_PUBLICITY_LOOKUP_WARN_INTERVAL_S = 60.0
_publicity_lookup_warn_last: Optional[float] = None
_publicity_lookup_warn_suppressed = 0


def _publicity_lookup_warn_budget(now: float) -> Optional[int]:
    """Claim permission to emit the lookup-failure warning.

    Returns the number of occurrences suppressed since the previous emission
    (``0`` on the first failure, so the first one is always logged), or ``None``
    when the caller must stay silent because an identical warning was emitted
    less than ``_PUBLICITY_LOOKUP_WARN_INTERVAL_S`` ago.
    """
    global _publicity_lookup_warn_last, _publicity_lookup_warn_suppressed

    last = _publicity_lookup_warn_last
    if last is not None and (now - last) < _PUBLICITY_LOOKUP_WARN_INTERVAL_S:
        _publicity_lookup_warn_suppressed += 1
        return None

    suppressed = _publicity_lookup_warn_suppressed
    _publicity_lookup_warn_last = now
    _publicity_lookup_warn_suppressed = 0
    return suppressed


def _reset_publicity_lookup_warn_throttle() -> None:
    """Clear the warning latch. Test hook — the state is module-global."""
    global _publicity_lookup_warn_last, _publicity_lookup_warn_suppressed
    _publicity_lookup_warn_last = None
    _publicity_lookup_warn_suppressed = 0


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


def _public_layer_for_tile(db: Session, layer_id: uuid.UUID):
    """Sync publicity lookup so the async tile proxy does not block the event loop.

    Returns the layer ONLY when it is in the public publication set
    (``_public_layer_types`` + source filter); ``None`` means "not forwardable
    to an anonymous tile client", whether the id is missing, the tipo is
    private, or the fuente is unpublished. Formerly
    ``_public_layer_for_rescale``: the same query used to run only on the
    rescale path to resolve the canonical override (audit C1/GEO-1 moved it to
    the gate, so the name follows its new role).
    """
    return (
        db.query(GeoLayer)
        .filter(
            GeoLayer.id == layer_id,
            GeoLayer.tipo.in_(_public_layer_types()),
            _public_layer_source_filter(),
        )
        .one_or_none()
    )


# Per-process TTL cache of the publicity verdict (review RES-001, audit
# 2026-10-23 follow-up). The unconditional gate costs one DB round-trip per
# tile; a viewport bursts ~256 tiles in parallel, and under a Postgres
# brownout each of those holds a threadpool token up to statement_timeout —
# starving unrelated sync API traffic that shares the same 40-token pool.
# Caching the verdict per layer collapses that to one query per layer per
# TTL window.
#
# Security stance: the TTL (60 s) is two orders of magnitude tighter than
# the ``Cache-Control: public, max-age=3600`` the tile responses themselves
# already carry — an unpublished layer stops being forwarded by this proxy
# within 60 s while CDN/browser copies of its bytes persist up to an hour
# regardless. Negative verdicts (404) are cached too: a layer published
# becomes visible within 60 s, publication being a rare staff action.
# Failures are NEVER cached — ``_public_layer_for_tile`` raising
# ``SQLAlchemyError`` bypasses the cache entirely and fails closed (503).
#
# Process-local on purpose (same blast-radius reasoning as the warn latch
# above). The route is public and rate-limit exempt, and a negative verdict
# is cached per caller-chosen UUID, so the key space is NOT the ~10 public
# rows. A full cache drops expired rows first, then the single oldest
# negative verdict. A flood of unknown ids churns that negative set and does
# not wipe a cached public layer. Concurrent misses may race and
# double-query — harmless, both store the same idempotent verdict.
_PUBLICITY_CACHE_TTL_S = 60.0
_PUBLICITY_CACHE_MAX_ENTRIES = 512
_publicity_cache: dict[uuid.UUID, tuple[float, Optional[str]]] = {}


def _evict_one_publicity_entry(now: float) -> None:
    """Make room for one new key without flushing cached public layers.

    Expired rows go first. A still-full cache then drops the oldest negative
    (``tipo is None`` — a missing or private id, which is what an anonymous
    caller can mint). A positive verdict is evicted only when the cache holds
    nothing else.
    """
    expired = [key for key, (deadline, _tipo) in _publicity_cache.items() if deadline <= now]
    for key in expired:
        del _publicity_cache[key]
    if len(_publicity_cache) < _PUBLICITY_CACHE_MAX_ENTRIES:
        return

    negatives = [
        (key, deadline) for key, (deadline, tipo) in _publicity_cache.items() if tipo is None
    ]
    if negatives:
        oldest = min(negatives, key=lambda item: item[1])[0]
        del _publicity_cache[oldest]
        return

    if _publicity_cache:
        oldest = min(_publicity_cache, key=lambda key: _publicity_cache[key][0])
        del _publicity_cache[oldest]


def _remember_publicity(
    layer_id: uuid.UUID, deadline: float, tipo: Optional[str], now: float
) -> None:
    """Store one verdict. Refreshing a key never evicts its neighbors."""
    if layer_id in _publicity_cache:
        _publicity_cache[layer_id] = (deadline, tipo)
        return
    if len(_publicity_cache) >= _PUBLICITY_CACHE_MAX_ENTRIES:
        _evict_one_publicity_entry(now)
    _publicity_cache[layer_id] = (deadline, tipo)


async def _cached_public_layer_tipo(db: Session, layer_id: uuid.UUID) -> Optional[str]:
    """Publicity verdict for ``layer_id``, cached: the layer's ``tipo`` value
    when forwardable, ``None`` when not. See the cache block above."""
    now = time.monotonic()
    hit = _publicity_cache.get(layer_id)
    if hit is not None and hit[0] > now:
        return hit[1]

    layer = await run_in_threadpool(_public_layer_for_tile, db, layer_id)
    tipo: Optional[str] = None if layer is None else getattr(layer.tipo, "value", layer.tipo)
    _remember_publicity(layer_id, now + _PUBLICITY_CACHE_TTL_S, tipo, now)
    return tipo


@router.get("/layers/{layer_id}/tiles/{z}/{x}/{y}.png")
async def proxy_tile(
    layer_id: uuid.UUID,
    z: int = PathParam(..., ge=0, le=MAX_TILE_ZOOM),
    x: int = PathParam(..., ge=0),
    y: int = PathParam(..., ge=0),
    colormap: Optional[str] = Query(default=None),
    encoding: Optional[str] = Query(default=None),
    z_factor: Optional[float] = Query(default=None, ge=1, le=30),
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
    on tile requests, and the published tile products (the public set
    gated below) carry no privileged information.

    Only layers in the public publication set are forwarded: the publicity
    gate below runs on EVERY request, with or without rescale params (audit
    C1/GEO-1 — previously the check only ran on the rescale path).

    z/x/y are BOUNDED here. This route is public AND exempt from the global
    rate limiter (only the exact ``/tiles/{id}/{z}/{x}/{y}.png`` and
    ``/api/v2/geo/layers/{id}/tiles/{z}/{x}/{y}.png`` prefixes), so an unbounded
    ``z`` was an unauthenticated, unthrottled amplification knob: the tile
    service computes
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

    # PUBLICITY GATE — runs for EVERY tile request (audit C1/GEO-1,
    # docs/auditorias/AUDITORIA_CONSORCIO_CANALERO_2026-10-23). Before the fix
    # the only publicity check lived inside the ``if parsed_rescale_min ...``
    # branch below, so the DEFAULT request shape — no rescale params, which is
    # what every base-map tile fetch uses — forwarded ANY GeoLayer UUID to the
    # geo-worker, whose ``get_tile`` (tile_service.py) selects by id with no
    # tipo/publicity filter. Anonymous + rate-limit-exempt access to the
    # deliberately private DEM layer types (slope, aspect, twi, flow_dir,
    # flow_acc, drainage, profile_curvature, tpi) and manual sources.
    #
    # Ordering contract: rescale globals → publicity gate → pyramid 204 →
    # forward. The gate deliberately runs BEFORE the pyramid fast path: with
    # the old order, an out-of-pyramid request would answer 204 without ever
    # loading the layer, and the gate would only fire for in-pyramid tiles —
    # here no layer bytes or existence signals leak for unforwardable layers.
    try:
        layer_tipo = await _cached_public_layer_tipo(db, layer_id)
    except SQLAlchemyError as exc:
        # FAIL CLOSED. If the lookup raises we cannot verify publicity, so we
        # do NOT forward — 503, not a tile.
        #
        # The pre-existing degrade-on-SQLAlchemyError block (forward without
        # the rescale override, preserving the worker's byte cache during an
        # outage) applied to the rescale OVERRIDE decision, never to
        # authorization. This one lookup now serves BOTH roles for every
        # request, so the degrade rationale is retired wholesale: an outage
        # costs the proxy the worker-cached no-override tiles it used to serve
        # (the worker's own cache lookup in ``get_tile`` returns before
        # ``_get_layer`` touches the same Postgres), and that is the accepted
        # price of never forwarding a layer we cannot prove is public. The
        # geo-worker itself is unchanged and still answers direct internal
        # callers.
        #
        # 503 (not 404): an unreachable DB is a transient server problem, and
        # 404 would invite Leaflet and CDNs to cache "layer missing" for a
        # layer that may be perfectly public once the database recovers.
        #
        # Only SQLAlchemyError fails closed — a programmer error must still
        # surface as a 500 rather than be masked as an outage.
        suppressed = _publicity_lookup_warn_budget(time.monotonic())
        if suppressed is not None:
            logger.warning(
                "Tile publicity lookup unavailable; failing closed",
                # A sample, not the only affected layer: the warning is
                # throttled and covers every failure in the window.
                layer_id=str(layer_id),
                error_type=type(exc).__name__,
                suppressed_since_last=suppressed,
            )
        raise HTTPException(status_code=503, detail="Capa no disponible temporalmente") from exc

    if layer_tipo is None:
        # Non-public layer (or plain missing) → 404 ALWAYS, not only when
        # rescale params are present. 404 over 403 so an anonymous caller
        # cannot use the proxy to confirm that a private layer id exists.
        raise HTTPException(status_code=404, detail="Geo layer no encontrado")

    canonical_rescale = None
    if parsed_rescale_min is not None:
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
    if z_factor is not None:
        params["z_factor"] = z_factor
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
