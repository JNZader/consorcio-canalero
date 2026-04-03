"""
STAC-like catalog service for GeoLayer assets.

Exposes GeoLayer records following the STAC (SpatioTemporal Asset Catalog)
specification format. This enables standardized search and discovery of
geospatial assets without deploying a full stac-fastapi service.

Reference: https://stacspec.org/
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.geo.models import GeoLayer

logger = logging.getLogger(__name__)

STAC_VERSION = "1.0.0"


def layer_to_stac_item(layer: GeoLayer, base_url: str = "") -> dict[str, Any]:
    """Convert a GeoLayer record to a STAC Item."""
    bbox = layer.bbox or []
    geometry = None
    if bbox and len(bbox) == 4:
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [bbox[0], bbox[1]],
                [bbox[2], bbox[1]],
                [bbox[2], bbox[3]],
                [bbox[0], bbox[3]],
                [bbox[0], bbox[1]],
            ]],
        }

    properties = {
        "datetime": layer.created_at.isoformat() if layer.created_at else None,
        "title": layer.nombre,
        "description": f"{layer.tipo} layer from {layer.fuente}",
        "consorcio:tipo": str(layer.tipo),
        "consorcio:fuente": str(layer.fuente),
        "consorcio:formato": str(layer.formato),
        "consorcio:area_id": layer.area_id,
        "proj:epsg": layer.srid,
    }

    if layer.metadata_extra:
        for key in ("resolution", "nodata", "cog_path", "statistics"):
            if key in layer.metadata_extra:
                properties[f"consorcio:{key}"] = layer.metadata_extra[key]

    assets = {}
    if layer.archivo_path:
        media_type = (
            "image/tiff; application=geotiff"
            if "geotiff" in str(layer.formato).lower()
            else "application/geo+json"
        )
        assets["data"] = {
            "href": layer.archivo_path,
            "type": media_type,
            "title": "Data file",
            "roles": ["data"],
        }

        # Add COG asset if available
        if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
            assets["cog"] = {
                "href": layer.metadata_extra["cog_path"],
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": "Cloud-Optimized GeoTIFF",
                "roles": ["data", "cloud-optimized"],
            }

    # Tile endpoint if applicable
    if base_url and "geotiff" in str(layer.formato).lower():
        assets["tiles"] = {
            "href": f"{base_url}/tiles/{layer.id}/{{z}}/{{x}}/{{y}}.png",
            "type": "application/x-protobuf",
            "title": "XYZ tiles",
            "roles": ["visual"],
        }

    return {
        "type": "Feature",
        "stac_version": STAC_VERSION,
        "id": str(layer.id),
        "geometry": geometry,
        "bbox": bbox,
        "properties": properties,
        "links": [
            {"rel": "self", "href": f"{base_url}/stac/items/{layer.id}"},
            {"rel": "collection", "href": f"{base_url}/stac/collections/{layer.tipo}"},
        ],
        "assets": assets,
    }


def search_catalog(
    db: Session,
    *,
    tipo: str | None = None,
    area_id: str | None = None,
    fuente: str | None = None,
    datetime_range: tuple[datetime | None, datetime | None] = (None, None),
    bbox: list[float] | None = None,
    limit: int = 50,
    offset: int = 0,
    base_url: str = "",
) -> dict[str, Any]:
    """Search GeoLayer catalog with STAC-compatible parameters.

    Args:
        db: Database session.
        tipo: Filter by layer type.
        area_id: Filter by processing area.
        fuente: Filter by data source.
        datetime_range: (start, end) datetime filter.
        bbox: Spatial filter [minx, miny, maxx, maxy].
        limit: Max items to return.
        offset: Pagination offset.
        base_url: Base URL for building STAC links.

    Returns:
        STAC-compatible ItemCollection.
    """
    query = db.query(GeoLayer)

    if tipo:
        query = query.filter(GeoLayer.tipo == tipo)
    if area_id:
        query = query.filter(GeoLayer.area_id == area_id)
    if fuente:
        query = query.filter(GeoLayer.fuente == fuente)

    start_dt, end_dt = datetime_range
    if start_dt:
        query = query.filter(GeoLayer.created_at >= start_dt)
    if end_dt:
        query = query.filter(GeoLayer.created_at <= end_dt)

    total = query.count()
    layers = query.order_by(GeoLayer.created_at.desc()).offset(offset).limit(limit).all()

    features = [layer_to_stac_item(layer, base_url) for layer in layers]

    return {
        "type": "FeatureCollection",
        "stac_version": STAC_VERSION,
        "features": features,
        "numberMatched": total,
        "numberReturned": len(features),
        "links": [
            {"rel": "self", "href": f"{base_url}/stac/search"},
            {"rel": "root", "href": f"{base_url}/stac"},
        ],
        "context": {
            "returned": len(features),
            "matched": total,
            "limit": limit,
        },
    }


def get_collections(db: Session, base_url: str = "") -> dict[str, Any]:
    """Get STAC collections (grouped by GeoLayer type)."""
    type_counts = (
        db.query(GeoLayer.tipo, func.count(GeoLayer.id))
        .group_by(GeoLayer.tipo)
        .all()
    )

    collections = []
    for tipo, count in type_counts:
        collections.append({
            "type": "Collection",
            "stac_version": STAC_VERSION,
            "id": str(tipo),
            "title": str(tipo).split(".")[-1].replace("_", " ").title(),
            "description": f"{count} {tipo} layers",
            "extent": {
                "spatial": {"bbox": [[-63.0, -33.0, -62.0, -32.0]]},
                "temporal": {"interval": [[None, None]]},
            },
            "links": [
                {"rel": "items", "href": f"{base_url}/stac/search?tipo={tipo}"},
            ],
            "item_count": count,
        })

    return {
        "collections": collections,
        "links": [
            {"rel": "self", "href": f"{base_url}/stac/collections"},
            {"rel": "root", "href": f"{base_url}/stac"},
        ],
    }
