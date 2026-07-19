"""Narrow unauthenticated GEE projections used by the public map.

The protected ``/geo/gee/*`` API intentionally remains the complete operator
surface.  This router exposes only fixed, server-chosen projections: callers
cannot supply an Earth Engine asset, expression, collection, date, sensor, or
analysis parameter.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.router_gee_support import (
    get_caminos_coloreados_impl,
    get_gee_layer_impl,
    get_satellite_image_impl,
)
from app.domains.settings.schemas import ImagenMapaParams
from app.domains.settings.service import SettingsService

logger = get_logger(__name__)

_PUBLIC_PROJECTION_CACHE = "public, max-age=3600, stale-while-revalidate=86400"
_PUBLIC_IMAGE_CACHE = "public, max-age=300, stale-while-revalidate=600"
_PUBLIC_DEGRADED_CACHE = "public, max-age=60"
_ALLOWED_SETTING_FIELDS = {
    "sensor",
    "target_date",
    "visualization",
    "max_cloud",
    "days_buffer",
    "mode",
}
_OPTICAL_VISUALIZATIONS = frozenset(
    {"rgb", "falso_color", "agricultura", "ndwi", "mndwi", "ndvi", "inundacion"}
)
_SENSOR_RULES: dict[str, tuple[str, date, frozenset[str]]] = {
    "Sentinel-1": ("sentinel1", date(2014, 10, 3), frozenset({"vv", "vv_flood"})),
    "Sentinel-2": ("sentinel2", date(2015, 6, 23), _OPTICAL_VISUALIZATIONS),
    "Landsat 8": ("landsat8", date(2013, 4, 11), _OPTICAL_VISUALIZATIONS),
    "Landsat 7": ("landsat7", date(1999, 4, 15), _OPTICAL_VISUALIZATIONS),
    "Landsat 5": ("landsat5", date(1984, 3, 1), _OPTICAL_VISUALIZATIONS),
}

PublicMapStatus = Literal["available", "unavailable"]
PublicMapReason = Literal[
    "not_configured",
    "configuration_not_approved",
    "temporarily_unavailable",
]
PublicProjectionName = Literal["zona", "caminos"]


class PublicMapProjectionResponse(BaseModel):
    """Allowlisted GeoJSON projection envelope."""

    status: PublicMapStatus
    projection: PublicProjectionName
    data: dict[str, Any] | None = None
    reason: PublicMapReason | None = None


class PublicCurrentMapImage(BaseModel):
    """Minimal safe image projection; collection and asset identifiers stay private."""

    tile_url: str
    target_date: str
    sensor: Literal["Sentinel-1", "Sentinel-2", "Landsat 8", "Landsat 7", "Landsat 5"]
    visualization: str
    visualization_description: str
    images_count: int
    days_buffer: int
    max_cloud: int | None = None
    mode: Literal["scene", "composite"]


class PublicCurrentMapImageResponse(BaseModel):
    """Server-approved current image or an explicit degraded state."""

    status: PublicMapStatus
    image: PublicCurrentMapImage | None = None
    reason: PublicMapReason | None = None


def _reject_query_params(request: Request) -> None:
    """Fail closed instead of silently ignoring arbitrary public GEE inputs."""
    if request.query_params:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Public map projections do not accept query parameters",
        )


router = APIRouter(
    prefix="/map/gee",
    tags=["public-map"],
    dependencies=[Depends(_reject_query_params)],
)


def _ensure_public_gee():
    """Reuse the protected router's centralized GEE initialization lazily."""
    from app.domains.geo.router import _ensure_gee

    return _ensure_gee()


def _get_settings_service() -> SettingsService:
    return SettingsService()


def _set_cache(response: Response, value: str) -> None:
    response.headers["Cache-Control"] = value


def _response_body(response: JSONResponse) -> dict[str, Any]:
    payload = json.loads(response.body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GEE projection is not a JSON object")
    return payload


def _unavailable_projection(projection: PublicProjectionName) -> PublicMapProjectionResponse:
    return PublicMapProjectionResponse(
        status="unavailable",
        projection=projection,
        reason="temporarily_unavailable",
    )


async def _load_projection(projection: PublicProjectionName) -> PublicMapProjectionResponse:
    try:
        if projection == "zona":
            raw = await get_gee_layer_impl(
                layer_name="zona",
                ensure_gee=_ensure_public_gee,
            )
        else:
            raw = await get_caminos_coloreados_impl(ensure_gee=_ensure_public_gee)
        return PublicMapProjectionResponse(
            status="available",
            projection=projection,
            data=_response_body(raw),
        )
    except Exception as exc:  # Public viewers receive a stable degraded contract.
        logger.warning(
            "Public GEE projection unavailable",
            projection=projection,
            error_type=type(exc).__name__,
        )
        return _unavailable_projection(projection)


@router.get("/zona", response_model=PublicMapProjectionResponse)
async def get_public_zona(response: Response) -> PublicMapProjectionResponse:
    """Return the single vetted jurisdiction boundary projection."""
    result = await _load_projection("zona")
    _set_cache(
        response,
        _PUBLIC_PROJECTION_CACHE if result.status == "available" else _PUBLIC_DEGRADED_CACHE,
    )
    return result


@router.get("/caminos", response_model=PublicMapProjectionResponse)
async def get_public_caminos(response: Response) -> PublicMapProjectionResponse:
    """Return the single vetted colored-road projection."""
    result = await _load_projection("caminos")
    _set_cache(
        response,
        _PUBLIC_PROJECTION_CACHE if result.status == "available" else _PUBLIC_DEGRADED_CACHE,
    )
    return result


def _validated_current_image(raw: object) -> tuple[ImagenMapaParams, str, date, str] | None:
    if not isinstance(raw, dict) or set(raw) - _ALLOWED_SETTING_FIELDS:
        return None
    try:
        params = ImagenMapaParams.model_validate(raw)
        target_date = date.fromisoformat(params.target_date)
    except (ValidationError, ValueError):
        return None

    rule = _SENSOR_RULES.get(params.sensor)
    if rule is None:
        return None
    sensor_endpoint, earliest_date, visualizations = rule
    if target_date < earliest_date or target_date > date.today():
        return None
    if params.visualization not in visualizations:
        return None

    mode = params.mode or "scene"
    if params.sensor == "Sentinel-1" and mode != "scene":
        return None
    return params, sensor_endpoint, target_date, mode


def _is_safe_tile_url(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = urlparse(value.replace("{x}", "0").replace("{y}", "0").replace("{z}", "0"))
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname == "earthengine.googleapis.com"


def _project_current_image(
    result: object,
    params: ImagenMapaParams,
    mode: str,
) -> PublicCurrentMapImage | None:
    if not isinstance(result, dict) or not _is_safe_tile_url(result.get("tile_url")):
        return None
    images_count = result.get("images_count")
    description = result.get("visualization_description")
    if isinstance(images_count, bool) or not isinstance(images_count, int) or images_count < 0:
        return None
    if not isinstance(description, str):
        return None

    return PublicCurrentMapImage(
        tile_url=result["tile_url"],
        target_date=params.target_date,
        sensor=params.sensor,
        visualization=params.visualization,
        visualization_description=description,
        images_count=images_count,
        days_buffer=params.days_buffer,
        max_cloud=(
            None
            if params.sensor == "Sentinel-1"
            else (params.max_cloud if params.max_cloud is not None else 80)
        ),
        mode=mode,
    )


@router.get("/current-image", response_model=PublicCurrentMapImageResponse)
async def get_public_current_image(
    response: Response,
    db: Session = Depends(get_db),
    service: SettingsService = Depends(_get_settings_service),
) -> PublicCurrentMapImageResponse:
    """Regenerate only the operator-approved current image; accepts no caller inputs."""
    _set_cache(response, _PUBLIC_DEGRADED_CACHE)
    try:
        raw = service.get_setting(db, "mapa/imagen_principal")
    except Exception as exc:
        logger.warning(
            "Public current map setting unavailable",
            error_type=type(exc).__name__,
        )
        return PublicCurrentMapImageResponse(
            status="unavailable",
            reason="temporarily_unavailable",
        )
    if raw is None:
        return PublicCurrentMapImageResponse(status="unavailable", reason="not_configured")

    validated = _validated_current_image(raw)
    if validated is None:
        return PublicCurrentMapImageResponse(
            status="unavailable",
            reason="configuration_not_approved",
        )
    params, sensor_endpoint, target_date, mode = validated

    try:
        result = await get_satellite_image_impl(
            sensor=sensor_endpoint,
            target_date=target_date,
            days_buffer=params.days_buffer,
            max_cloud=params.max_cloud if params.max_cloud is not None else 80,
            visualization=params.visualization,
            mode=mode,
            ensure_gee=_ensure_public_gee,
        )
        image = _project_current_image(result, params, mode)
    except Exception as exc:  # Never turn public-map degradation into an auth bypass.
        logger.warning(
            "Public current map image unavailable",
            error_type=type(exc).__name__,
        )
        image = None

    if image is None:
        return PublicCurrentMapImageResponse(
            status="unavailable",
            reason="temporarily_unavailable",
        )
    _set_cache(response, _PUBLIC_IMAGE_CACHE)
    return PublicCurrentMapImageResponse(status="available", image=image)
