from __future__ import annotations

import asyncio
from datetime import date
from typing import Literal

from fastapi import Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.exceptions import AppException, NotFoundError, get_safe_error_detail
from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.rainfall import catalog_view
from app.domains.geo.rainfall.repository import read_events

logger = get_logger(__name__)


# Cache TTLs (seconds) — see README for justification.
GEE_LAYER_TTL = 24 * 60 * 60  # 24 h — vector layers rarely change
GEE_CAMINOS_TTL = 6 * 60 * 60  # 6 h — road status updated occasionally
GEE_SENTINEL2_TTL = 60 * 60  # 1 h — image-by-date tiles


async def _run_blocking(func, *args, **kwargs):
    """Run a synchronous, potentially-slow function in a worker thread so it
    does NOT block the uvicorn event loop.

    Why this matters
    ----------------
    The GEE service calls in this module make blocking network requests to
    Google Earth Engine that can take 30 s to 2 min. Without offloading to a
    thread, awaiting them stalls the entire event loop — every other endpoint
    queues behind them, which is what produced the 21–161 s tail latency on
    `/basins/approved-zones/current` (a totally unrelated PostGIS endpoint).

    `asyncio.to_thread` propagates the current contextvars (request id,
    structlog binding, etc.) so logging stays consistent.
    """
    return await asyncio.to_thread(func, *args, **kwargs)


# DEAD AS OF B2a, DELETED IN B2b. The list handler below reads the catalog
# (`rainfall_extreme_event`, seeded with these three anchors verbatim by
# migration `lluvia_ext_002`); the ONLY remaining reader is
# `get_historic_flood_tiles_impl`, which still resolves an id by scanning this
# literal and is rewired in the next slice.
#
# Kept deliberately for one merge window rather than deleted here: removing it
# now would drag the bridge rewiring, the five dispatcher tests bound to these
# ids (one of which monkeypatches this very symbol) and the router shape
# assertions into this slice — one ~1,100-line PR whose production component
# crosses the 400 ceiling. Everything bound to the symbol dies WITH the symbol,
# in B2b.
HISTORIC_FLOODS = [
    {
        "id": "mar_2015",
        "name": "Inundacion Marzo 2015",
        "date": "2015-03-15",
        "description": "Evento historico para revisar con Landsat 8/Landsat 7 y Sentinel-1",
        "severity": "alta",
        "sensor": "landsat8",
        "max_cloud": 80,
        "days_buffer": 30,
    },
    {
        "id": "feb_2017",
        "name": "Inundacion Febrero 2017",
        "date": "2017-02-20",
        "description": "Gran inundacion que afecto Bell Ville y zona rural",
        "severity": "alta",
        "sensor": "sentinel2",
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
    max_cloud: int = 80,
    ensure_gee=None,
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
    cache = get_cache()
    cache_key = "gee:caminos:coloreados"
    cached = await cache.get(cache_key)
    if cached is not None:
        return JSONResponse(
            content=cached,
            headers={"Cache-Control": "public, max-age=3600", "X-Cache": "HIT"},
        )
    svc = ensure_gee()
    try:
        result = await _run_blocking(svc["get_caminos_con_colores"])
        await cache.set(cache_key, result, ttl_seconds=GEE_CAMINOS_TTL)
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "public, max-age=3600", "X-Cache": "MISS"},
        )
    except Exception as e:
        logger.error("Error obteniendo caminos coloreados", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "caminos coloreados"),
            code="GEE_CAMINOS_ERROR",
            status_code=500,
        )


async def get_estadisticas_caminos_impl(*, ensure_gee) -> JSONResponse:
    cache = get_cache()
    cache_key = "gee:caminos:estadisticas"
    cached = await cache.get(cache_key)
    if cached is not None:
        return JSONResponse(
            content=cached,
            headers={"Cache-Control": "public, max-age=3600", "X-Cache": "HIT"},
        )
    svc = ensure_gee()
    try:
        result = await _run_blocking(svc["get_estadisticas_consorcios"])
        await cache.set(cache_key, result, ttl_seconds=GEE_CAMINOS_TTL)
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "public, max-age=3600", "X-Cache": "MISS"},
        )
    except Exception as e:
        logger.error("Error obteniendo estadisticas de consorcios", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "estadisticas de consorcios"),
            code="GEE_STATS_ERROR",
            status_code=500,
        )


async def get_gee_layer_impl(*, layer_name: str, ensure_gee) -> JSONResponse:
    cache = get_cache()
    cache_key = f"gee:layer:{layer_name}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return JSONResponse(
            content=cached,
            headers={"Cache-Control": "public, max-age=3600", "X-Cache": "HIT"},
        )
    svc = ensure_gee()
    try:
        geojson = await _run_blocking(svc["get_layer_geojson"], layer_name)
        await cache.set(cache_key, geojson, ttl_seconds=GEE_LAYER_TTL)
        return JSONResponse(
            content=geojson,
            headers={"Cache-Control": "public, max-age=3600", "X-Cache": "MISS"},
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
    max_cloud: int = 80,
    ensure_gee=None,
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
    max_cloud: int = 80,
    visualization: str = "rgb",
    ensure_gee=None,
):
    cache = get_cache()
    cache_key = f"gee:s2:{target_date.isoformat()}:{days_buffer}:{max_cloud}:{visualization}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached
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
        await cache.set(cache_key, result, ttl_seconds=GEE_SENTINEL2_TTL)
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
    return await get_satellite_image_impl(
        sensor="sentinel1",
        target_date=target_date,
        days_buffer=days_buffer,
        max_cloud=100,
        visualization=visualization,
        ensure_gee=ensure_gee,
    )


async def get_satellite_image_impl(
    *,
    sensor: str,
    target_date: date,
    days_buffer: int,
    max_cloud: int = 80,
    visualization: str = "rgb",
    # Literal, not str: `get_image` compares `mode == "composite"` exactly, so
    # any other value (a typo, "Composite") degraded SILENTLY to a cloudy
    # mosaic — the same class of regression that put clouds back on the
    # historic floods. FastAPI now rejects it with 422, like the public map
    # route already did (public_map.py:84).
    mode: Literal["scene", "composite"] = "scene",
    ensure_gee=None,
):
    cache = get_cache()
    cache_key = f"gee:image:{sensor}:{target_date.isoformat()}:{days_buffer}:{max_cloud}:{visualization}:{mode}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached
    svc = ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        result = await _run_blocking(
            explorer.get_image,
            sensor=sensor,
            target_date=target_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
            visualization=visualization,
            mode=mode,
        )
        if "error" in result:
            raise NotFoundError(
                message=result.get("error", "Imagen no encontrada"),
                code="SATELLITE_IMAGE_NOT_FOUND",
            )
        await cache.set(cache_key, result, ttl_seconds=GEE_SENTINEL2_TTL)
        return result
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, f"imagen {sensor}"),
            code="IMAGE_EXPLORER_ERROR",
            status_code=500,
        )


async def get_image_scenes_impl(
    *,
    sensor: str,
    target_date: date,
    days_buffer: int = 1,
    max_cloud: int = 80,
    visualization: str = "rgb",
    ensure_gee=None,
):
    cache = get_cache()
    cache_key = f"gee:image-scenes:{sensor}:{target_date.isoformat()}:{days_buffer}:{max_cloud}:{visualization}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached
    svc = ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        result = await _run_blocking(
            explorer.get_image_scenes,
            sensor=sensor,
            target_date=target_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
            visualization=visualization,
        )
        if "error" in result:
            raise NotFoundError(
                message=result.get("error", "Escenas no encontradas"),
                code="SATELLITE_SCENES_NOT_FOUND",
            )
        await cache.set(cache_key, result, ttl_seconds=GEE_SENTINEL2_TTL)
        return result
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, f"escenas {sensor}"),
            code="IMAGE_SCENES_ERROR",
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


#: The catalog key every served read resolves against: the same
#: `(source_id, scope_kind, scope_id, scope_version)` the persisted baseline
#: and the curated seed (`lluvia_ext_002`) use. Spelled out here rather than
#: imported from the runbook CLI, which owns the WRITE side and takes both as
#: command-line arguments -- a served read that followed an operator's flag
#: would answer a different question on every box.
CATALOG_SCOPE = {
    "source_id": "chirps-v3-final",
    "scope_kind": "provider_asset",
    "scope_id": "zona_cc_ampliada",
    "scope_version": "v1",
}


async def get_historic_floods_impl(
    *,
    tier: Literal["extrema", "alta"] = catalog_view.DEFAULT_TIER,
    year: int | None = None,
    limit: int = Query(catalog_view.DEFAULT_LIMIT, ge=1, le=catalog_view.MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """The catalog-backed historic-flood list (D8-D12).

    The read is offloaded through :func:`_run_blocking` for the reason this
    module's own docstring records: both historic-flood handlers are
    ``async def``, and blocking work on the event loop inside exactly these
    handlers is what produced the 21-161 s tail latency on an unrelated PostGIS
    endpoint. Detection NEVER happens here -- the catalog is written by the
    hand-run runbook (D6) and this handler only reads it.
    """
    generation = await _run_blocking(read_events, db, **CATALOG_SCOPE)
    payload = catalog_view.build_catalog_response(
        generation, tier=tier, year=year, limit=limit, offset=offset
    )
    return JSONResponse(
        content=payload,
        # `private`, and five minutes rather than a day (D12). Over three
        # module constants `public, max-age=86400` was harmless; over a
        # DB-backed, filtered response on a router gated by
        # `Depends(_require_operator())` it is both a shared-cache leak and a
        # day-long staleness window after a detector run.
        headers={"Cache-Control": "private, max-age=300"},
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
        days_buffer = int(flood.get("days_buffer") or (30 if flood_date.year < 2020 else 15))
        sensor = str(flood.get("sensor") or "sentinel2")
        max_cloud = int(flood.get("max_cloud") or 60)

        # Historic floods always composite (temporal median) for optical sensors
        # so transient clouds are rejected — this is the original use_median=True
        # behavior. SAR (Sentinel-1) has no optical clouds, so it stays scene.
        result = await _run_blocking(
            explorer.get_image,
            sensor=sensor,
            target_date=flood_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
            visualization=visualization,
            mode="scene" if sensor == "sentinel1" else "composite",
        )

        if "error" in result:
            result = await _run_blocking(
                explorer.get_sentinel1_image,
                target_date=flood_date,
                days_buffer=days_buffer,
                visualization="vv_flood",
            )

        # Tag composite so a persisted flood selection regenerates with the
        # median (cloud-free) path on reload instead of drifting back to mosaic.
        # Check the RESULT sensor, not the requested one, so the SAR fallback
        # (which is scene/mosaic, no optical clouds) is never mislabeled.
        if "error" not in result and result.get("sensor") != "Sentinel-1":
            result.setdefault("composition_mode", "composite")
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
        headers={"Content-Disposition": 'attachment; filename="consorcio-canalero.qgz"'},
    )
