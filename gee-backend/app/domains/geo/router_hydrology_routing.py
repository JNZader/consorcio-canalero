"""Hydrology summaries and canal routing endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.exceptions import AppException, NotFoundError
from app.db.session import get_db
from app.domains.geo.models import GeoLayer
from app.domains.geo.router_common import _require_operator

router = APIRouter(tags=["Geo Processing"])

# ── Hydrology Analysis ────────────────────────────────────────────


@router.get("/hydrology/twi-summary")
def get_twi_summary(
    area_id: str = Query(default="zona_principal"),
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Get TWI classification summary with area statistics per zone."""
    layer = (
        db.query(GeoLayer)
        .filter(GeoLayer.tipo == "twi", GeoLayer.area_id == area_id)
        .order_by(GeoLayer.created_at.desc())
        .first()
    )
    if not layer:
        raise NotFoundError(f"No TWI layer found for area_id={area_id}")

    raster_path = layer.archivo_path
    if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
        cog = layer.metadata_extra["cog_path"]
        if Path(cog).exists():
            raster_path = cog

    if not Path(raster_path).exists():
        raise AppException(
            message="TWI raster not found", code="RASTER_NOT_FOUND", status_code=404
        )

    from app.domains.geo.hydrology_terrain import compute_twi_zone_summary

    return compute_twi_zone_summary(raster_path)


@router.get("/hydrology/canal-capacity")
def get_canal_capacity(
    area_id: str = Query(default="zona_principal"),
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Analyze flow accumulation along canal segments to identify capacity risks.

    Returns canals sorted by maximum upstream flow, indicating which
    segments receive the most water and are at risk of overflowing.
    """
    layer = (
        db.query(GeoLayer)
        .filter(GeoLayer.tipo == "flow_acc", GeoLayer.area_id == area_id)
        .order_by(GeoLayer.created_at.desc())
        .first()
    )
    if not layer:
        raise NotFoundError(f"No flow_acc layer found for area_id={area_id}")

    raster_path = layer.archivo_path
    if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
        cog = layer.metadata_extra["cog_path"]
        if Path(cog).exists():
            raster_path = cog

    if not Path(raster_path).exists():
        raise AppException(
            message="Flow accumulation raster not found",
            code="RASTER_NOT_FOUND",
            status_code=404,
        )

    # Use canales_existentes as the primary canal source
    canal_path = "/app/data/waterways/canales_existentes.geojson"
    if not Path(canal_path).exists():
        raise AppException(
            message="Canal GeoJSON not found", code="GEOJSON_NOT_FOUND", status_code=404
        )

    from app.domains.geo.hydrology_terrain import compute_flow_acc_at_canals

    results = compute_flow_acc_at_canals(raster_path, canal_path)

    return {
        "area_id": area_id,
        "canals_analyzed": len(results),
        "results": results,
    }


# ── Canal Network Routing (pgRouting) ─────────────────────────────


class ImportCanalsRequest(BaseModel):
    """Request to import canals from GeoJSON into the routing network."""

    geojson_paths: list[str] = Field(
        ...,
        description="List of GeoJSON file paths to import",
    )
    rebuild_topology: bool = Field(
        default=True,
        description="Rebuild pgRouting topology after import",
    )
    tolerance: float = Field(
        default=0.0001,
        description="Snapping tolerance for topology",
    )


class ShortestPathRequest(BaseModel):
    """Request for shortest path between two points."""

    from_lon: float
    from_lat: float
    to_lon: float
    to_lat: float


@router.post("/routing/import")
def import_canal_network(
    body: ImportCanalsRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Import canal GeoJSON files into the routing network and build topology."""
    from app.domains.geo.routing import (
        import_canals_from_geojson,
        build_topology,
        get_network_stats,
    )

    total_imported = 0
    for path in body.geojson_paths:
        tipo = Path(path).stem
        count = import_canals_from_geojson(db, path, tipo=tipo)
        total_imported += count

    topology = None
    if body.rebuild_topology and total_imported > 0:
        topology = build_topology(db, tolerance=body.tolerance)

    stats = get_network_stats(db)

    return {
        "imported": total_imported,
        "topology": topology,
        "network": stats,
    }


@router.post("/routing/shortest-path")
def find_shortest_path(
    body: ShortestPathRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Find shortest path between two points on the canal network.

    Snaps input coordinates to the nearest network vertices, then
    runs Dijkstra's algorithm via pgRouting.
    """
    from app.domains.geo.routing import find_nearest_vertex, shortest_path

    source = find_nearest_vertex(db, body.from_lon, body.from_lat)
    target = find_nearest_vertex(db, body.to_lon, body.to_lat)

    if not source or not target:
        raise NotFoundError("No vertices found near the given coordinates")

    path = shortest_path(db, source["id"], target["id"])

    # Build GeoJSON FeatureCollection for the path
    features = []
    for edge in path:
        if edge["geometry"]:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "nombre": edge["nombre"],
                        "cost": edge["cost"],
                        "agg_cost": edge["agg_cost"],
                        "path_seq": edge["path_seq"],
                    },
                    "geometry": edge["geometry"],
                }
            )

    total_cost = path[-1]["agg_cost"] if path else 0

    return {
        "source": source,
        "target": target,
        "total_distance_m": round(total_cost, 2),
        "edges": len(path),
        "geojson": {
            "type": "FeatureCollection",
            "features": features,
        },
    }


@router.get("/routing/stats")
def get_routing_network_stats(
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Get canal network statistics."""
    from app.domains.geo.routing import get_network_stats

    return get_network_stats(db)
