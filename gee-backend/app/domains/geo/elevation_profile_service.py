"""Resolve the filled DEM and sample a WGS84 LineString."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.domains.geo.elevation_profile import (
    MAX_LENGTH_M,
    aplicar_mde_ar,
    perfil_desde_linea_metrica,
)
from app.domains.geo.elevation_profile_cache import (
    build_cache_key,
    build_source_identity,
    read_cached_profile,
    write_cached_profile,
)
from app.domains.geo.elevation_profile_gee import aplicar_gee_dems
from app.domains.geo.intelligence.cruces_camino_support import (
    DEM_JOB_TIPOS,
    dem_resultados_por_area,
)
from app.domains.geo.relevamiento.clasificador import DemFilledNoDisponible, resolver_dem_filled

SQL_DEM_RESULTADOS_RECIENTE = text(
    """
    SELECT resultado FROM geo_jobs
     WHERE tipo::text = ANY(:tipos)
       AND resultado IS NOT NULL
     ORDER BY created_at DESC
     LIMIT 20
    """
)

logger = get_logger(__name__)


def _read_cache(cache_key: str) -> Optional[dict[str, Any]]:
    """A cache failure must never cost the caller the profile.

    No rollback: the cache owns its own session, so the caller's transaction is
    untouched either way (review R3).
    """
    try:
        return read_cached_profile(cache_key)
    except Exception as exc:  # noqa: BLE001 — degraded cache, not a failed request
        logger.warning("profile cache read failed", error_type=type(exc).__name__)
        return None


def _write_cache(
    *,
    cache_key: str,
    source_identity: str,
    payload: dict[str, Any],
) -> None:
    """Best effort: the response is already computed and must still be served.

    No rollback here for the same reason: the caller's session is never touched.
    """
    try:
        write_cached_profile(
            cache_key=cache_key,
            source_identity=source_identity,
            payload=payload,
        )
    except Exception as exc:  # noqa: BLE001 — degraded cache, not a failed request
        logger.warning("profile cache write failed", error_type=type(exc).__name__)


def _raster_crs(path: str):
    import rasterio

    with rasterio.open(path) as src:
        return src.crs


def _resultados(db: Session, area_id: Optional[str]) -> list[dict[str, Any]]:
    if area_id:
        return dem_resultados_por_area(db, area_id)
    rows = db.execute(SQL_DEM_RESULTADOS_RECIENTE, {"tipos": list(DEM_JOB_TIPOS)}).scalars().all()
    return [row for row in rows if isinstance(row, dict)]


def adjuntar_series_opcionales(
    payload: dict[str, Any],
    dem_path: str,
    *,
    compare_dems: bool = False,
) -> dict[str, Any]:
    """MDE-Ar is local. GEE DEMs stay off the critical path unless requested."""
    sampled = aplicar_mde_ar(payload, dem_path)
    if not compare_dems:
        return sampled
    return aplicar_gee_dems(sampled)


def perfil_de_geojson(
    db: Session,
    *,
    geometry: dict[str, Any],
    area_id: Optional[str] = None,
    compare_dems: bool = False,
) -> dict[str, Any]:
    from shapely.geometry import shape
    import geopandas as gpd

    try:
        geom = shape(geometry)
    except (TypeError, ValueError) as exc:
        raise ValidationError(message="geometry GeoJSON inválida") from exc
    if geom.geom_type != "LineString":
        raise ValidationError(message="solo LineString (canal, camino o traza)")
    if geom.is_empty or len(geom.coords) < 2:
        raise ValidationError(message="hace falta un LineString con al menos dos vértices")

    try:
        dem_path = resolver_dem_filled(_resultados(db, area_id))
    except DemFilledNoDisponible as exc:
        raise NotFoundError(message=str(exc), resource_type="dem_filled") from exc

    linea_metric = (
        gpd.GeoDataFrame({"geometry": [geom]}, geometry="geometry", crs=4326)
        .to_crs(_raster_crs(dem_path))
        .geometry.iloc[0]
    )
    if float(linea_metric.length) > MAX_LENGTH_M:
        raise ValidationError(message=f"la traza supera {int(MAX_LENGTH_M)} m")

    # Plain series only. The GEE comparison must never be served out of a stored
    # GLO-30 payload, so it bypasses the cache entirely.
    cache_key: Optional[str] = None
    source_identity: Optional[str] = None
    if not compare_dems:
        source_identity = build_source_identity(dem_path)
        cache_key = build_cache_key(geometry, source_identity)
        cached = _read_cache(cache_key)
        if cached is not None:
            return {**cached, "cache": "hit"}
    try:
        payload = perfil_desde_linea_metrica(linea_metric, dem_path)
    except ValueError as exc:
        raise ValidationError(message=str(exc)) from exc
    vertices = payload.pop("_vertices_xy", None)
    if not isinstance(vertices, list) or not vertices:
        # Degenerate trace: no lon/lat to hang on the map, not worth a row.
        return payload
    from shapely.geometry import Point

    serie = gpd.GeoSeries(
        [Point(xy) for xy in vertices],
        crs=_raster_crs(dem_path),
    ).to_crs(4326)
    for index, punto in enumerate(payload["puntos"]):
        punto["lon"] = float(serie.iloc[index].x)
        punto["lat"] = float(serie.iloc[index].y)
    resultado = adjuntar_series_opcionales(payload, dem_path, compare_dems=compare_dems)
    if cache_key is not None and source_identity is not None:
        _write_cache(
            cache_key=cache_key,
            source_identity=source_identity,
            payload=resultado,
        )
        return {**resultado, "cache": "miss"}
    return resultado
