"""STAC catalog and temporal analysis endpoints."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.exceptions import AppException, NotFoundError
from app.db.session import get_db
from app.domains.geo.intelligence.models import ZonaOperativa
from app.domains.geo.models import GeoLayer
from app.domains.geo.router_common import _require_operator

router = APIRouter(tags=["Geo Processing"])

# ── STAC Catalog ──────────────────────────────────────────────────


@router.get("/stac")
def stac_root(request: Request):
    """STAC API root — catalog landing page."""
    base_url = f"{request.base_url}api/v2/geo"
    return {
        "type": "Catalog",
        "stac_version": "1.0.0",
        "id": "consorcio-canalero",
        "title": "Consorcio Canalero — Geospatial Catalog",
        "description": "Catalog of DEM pipeline outputs, satellite imagery, and analysis results",
        "links": [
            {"rel": "self", "href": f"{base_url}/stac"},
            {"rel": "collections", "href": f"{base_url}/stac/collections"},
            {"rel": "search", "href": f"{base_url}/stac/search"},
        ],
    }


@router.get("/stac/collections")
def stac_collections(
    request: Request,
    db: Session = Depends(get_db),
):
    """List STAC collections (grouped by GeoLayer type)."""
    from app.domains.geo.stac import get_collections

    base_url = f"{request.base_url}api/v2/geo"
    return get_collections(db, base_url)


@router.get("/stac/search")
def stac_search(
    request: Request,
    db: Session = Depends(get_db),
    tipo: str | None = Query(default=None),
    area_id: str | None = Query(default=None),
    fuente: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Search the STAC catalog with filters."""
    from app.domains.geo.stac import search_catalog

    base_url = f"{request.base_url}api/v2/geo"
    return search_catalog(
        db,
        tipo=tipo,
        area_id=area_id,
        fuente=fuente,
        limit=limit,
        offset=offset,
        base_url=base_url,
    )


@router.get("/stac/items/{item_id}")
def stac_item(
    item_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get a single STAC item by ID."""
    from app.domains.geo.stac import layer_to_stac_item

    layer = db.query(GeoLayer).filter(GeoLayer.id == item_id).first()
    if not layer:
        raise NotFoundError(f"Item not found: {item_id}")
    base_url = f"{request.base_url}api/v2/geo"
    return layer_to_stac_item(layer, base_url)


# ── Temporal Analysis ─────────────────────────────────────────────


class NdwiTrendRequest(BaseModel):
    """Request for NDWI time-series analysis via GEE + Xee."""

    zona_id: uuid.UUID = Field(..., description="Zona operativa ID")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    cloud_cover_max: int = Field(default=30, ge=0, le=100)


@router.post("/temporal/ndwi-trend")
def analyze_ndwi_trend(
    body: NdwiTrendRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Analyze NDWI (water index) trend over time for a zona operativa.

    Uses Sentinel-2 imagery from GEE via Xee + xarray. Returns mean NDWI
    per image date, linear trend, and anomalies.

    NOTE: This can take 30-60s depending on the date range and GEE load.
    """
    from geoalchemy2.functions import ST_AsGeoJSON

    zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == body.zona_id).first()
    if not zona:
        raise NotFoundError(f"Zona not found: {body.zona_id}")

    # Get geometry as GeoJSON
    from sqlalchemy import select

    geojson_str = db.execute(
        select(ST_AsGeoJSON(ZonaOperativa.geometria)).where(
            ZonaOperativa.id == body.zona_id
        )
    ).scalar()

    import json

    geometry = json.loads(geojson_str)

    from app.domains.geo.temporal import analyze_ndwi_trend_gee

    result = analyze_ndwi_trend_gee(
        geometry_geojson=geometry,
        start_date=body.start_date,
        end_date=body.end_date,
        cloud_cover_max=body.cloud_cover_max,
    )

    return {
        "zona": {"id": str(zona.id), "nombre": zona.nombre},
        **result,
    }


class RasterCompareRequest(BaseModel):
    """Request to compare multiple rasters temporally."""

    layer_tipo: str = Field(..., description="GeoLayer type (e.g. slope, twi)")
    zona_id: uuid.UUID | None = Field(
        default=None, description="Optional zona to clip to"
    )


@router.post("/temporal/compare-rasters")
def compare_rasters(
    body: RasterCompareRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Compare multiple rasters of the same type across time.

    Finds all GeoLayers of the given type and computes per-raster stats
    plus change analysis between first and last.
    """
    layers = (
        db.query(GeoLayer)
        .filter(GeoLayer.tipo == body.layer_tipo)
        .order_by(GeoLayer.created_at.asc())
        .all()
    )

    if not layers:
        raise NotFoundError(f"No layers found for tipo={body.layer_tipo}")

    raster_paths = []
    labels = []
    for layer in layers:
        path = layer.archivo_path
        if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
            cog = layer.metadata_extra["cog_path"]
            if Path(cog).exists():
                path = cog
        if Path(path).exists():
            raster_paths.append(path)
            labels.append(f"{layer.tipo}_{layer.created_at.date()}")

    if not raster_paths:
        raise AppException(
            message="No raster files found on disk",
            code="RASTERS_NOT_FOUND",
            status_code=404,
        )

    # Get zona geometry if provided
    zona_wkt = None
    if body.zona_id:
        from geoalchemy2.functions import ST_AsText
        from sqlalchemy import select

        zona_wkt = db.execute(
            select(ST_AsText(ZonaOperativa.geometria)).where(
                ZonaOperativa.id == body.zona_id
            )
        ).scalar()

    from app.domains.geo.temporal import compare_rasters_temporal

    return compare_rasters_temporal(raster_paths, labels, zona_wkt)
