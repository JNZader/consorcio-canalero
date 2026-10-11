"""Resolve the filled DEM and sample a WGS84 LineString."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.domains.geo.elevation_profile import (
    MAX_LENGTH_M,
    aplicar_mde_ar,
    perfil_desde_linea_metrica,
)
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


def _raster_crs(path: str):
    import rasterio

    with rasterio.open(path) as src:
        return src.crs


def _resultados(db: Session, area_id: Optional[str]) -> list[dict[str, Any]]:
    if area_id:
        return dem_resultados_por_area(db, area_id)
    rows = db.execute(SQL_DEM_RESULTADOS_RECIENTE, {"tipos": list(DEM_JOB_TIPOS)}).scalars().all()
    return [row for row in rows if isinstance(row, dict)]


def perfil_de_geojson(
    db: Session,
    *,
    geometry: dict[str, Any],
    area_id: Optional[str] = None,
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
    try:
        payload = perfil_desde_linea_metrica(linea_metric, dem_path)
    except ValueError as exc:
        raise ValidationError(message=str(exc)) from exc
    vertices = payload.pop("_vertices_xy", None)
    if not isinstance(vertices, list) or not vertices:
        return payload
    from shapely.geometry import Point

    serie = gpd.GeoSeries(
        [Point(xy) for xy in vertices],
        crs=_raster_crs(dem_path),
    ).to_crs(4326)
    for index, punto in enumerate(payload["puntos"]):
        punto["lon"] = float(serie.iloc[index].x)
        punto["lat"] = float(serie.iloc[index].y)
    return aplicar_mde_ar(payload, dem_path)
