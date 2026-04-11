"""Hydrology summaries and canal routing endpoints."""

from pathlib import Path
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.exceptions import AppException, NotFoundError
from app.db.session import get_db
from app.domains.geo.models import GeoLayer
from app.domains.geo.router_common import _get_user_display_name, _require_operator
from app.domains.geo.routing_schemas import (
    CorridorScenarioApprovalEventResponse,
    CorridorScenarioApprovalRequest,
    CorridorScenarioFavoriteRequest,
    CorridorScenarioListItem,
    CorridorScenarioResponse,
    CorridorScenarioSaveRequest,
)
from app.domains.geo.repository import GeoRepository

router = APIRouter(tags=["Geo Processing"])


def _get_repo() -> GeoRepository:
    return GeoRepository()


def _attach_scenario_history(repo: GeoRepository, db: Session, scenario):
    if scenario is None or not getattr(scenario, "id", None):
        return scenario
    setattr(
        scenario,
        "approval_history",
        [
            CorridorScenarioApprovalEventResponse.model_validate(event)
            for event in repo.list_routing_scenario_approval_events(db, scenario.id)
        ],
    )
    return scenario


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


class CorridorRoutingRequest(BaseModel):
    """Request for network-based corridor routing between two points."""

    from_lon: float
    from_lat: float
    to_lon: float
    to_lat: float
    mode: Literal["network", "raster"] = "network"
    area_id: str | None = None
    profile: Literal["balanceado", "hidraulico", "evitar_propiedad"] = "balanceado"
    corridor_width_m: float | None = Field(default=None, gt=0)
    alternative_count: int | None = Field(default=None, ge=0, le=5)
    penalty_factor: float | None = Field(default=None, ge=1.0)
    weight_slope: float | None = Field(default=None, ge=0.0)
    weight_hydric: float | None = Field(default=None, ge=0.0)
    weight_property: float | None = Field(default=None, ge=0.0)
    weight_landcover: float | None = Field(default=None, ge=0.0)


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
    from app.domains.geo.routing import (
        assert_vertices_connected,
        find_nearest_vertex,
        shortest_path,
    )

    source = find_nearest_vertex(db, body.from_lon, body.from_lat)
    target = find_nearest_vertex(db, body.to_lon, body.to_lat)

    if not source or not target:
        raise NotFoundError("No vertices found near the given coordinates")

    assert_vertices_connected(db, source, target)

    path = shortest_path(db, source["id"], target["id"])

    if not path and source["id"] != target["id"]:
        raise NotFoundError(
            "Routing produced no path between source and target vertices. "
            "This usually indicates the canal_network has stale topology — "
            "rebuild it with pgr_createTopology and try again."
        )

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


@router.post("/routing/corridor")
def calculate_corridor_route(
    body: CorridorRoutingRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Compute a corridor routing payload with centerline, corridor and alternatives."""
    from app.domains.geo.routing import corridor_routing

    return corridor_routing(
        db,
        from_lon=body.from_lon,
        from_lat=body.from_lat,
        to_lon=body.to_lon,
        to_lat=body.to_lat,
        mode=body.mode,
        area_id=body.area_id,
        profile=body.profile,
        corridor_width_m=body.corridor_width_m,
        alternative_count=body.alternative_count,
        penalty_factor=body.penalty_factor,
        weight_overrides={
            "slope": body.weight_slope,
            "hydric": body.weight_hydric,
            "property": body.weight_property,
            "landcover": body.weight_landcover,
        },
    )


@router.get("/routing/stats")
def get_routing_network_stats(
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Get canal network statistics."""
    from app.domains.geo.routing import get_network_stats

    return get_network_stats(db)


@router.post(
    "/routing/corridor/scenarios",
    response_model=CorridorScenarioResponse,
    status_code=201,
)
def save_corridor_scenario(
    body: CorridorScenarioSaveRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
    repo: GeoRepository = Depends(_get_repo),
):
    scenario = repo.create_routing_scenario(
        db,
        name=body.name,
        profile=body.profile,
        request_payload=body.request_payload,
        result_payload=body.result_payload,
        notes=body.notes,
        previous_version_id=body.previous_version_id,
        is_favorite=body.is_favorite,
        created_by_id=_user.id,
    )
    db.commit()
    db.refresh(scenario)
    return _attach_scenario_history(repo, db, scenario)


@router.get("/routing/corridor/scenarios")
def list_corridor_scenarios(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
    repo: GeoRepository = Depends(_get_repo),
):
    items, total = repo.list_routing_scenarios(db, page=page, limit=limit)
    return {
        "items": [CorridorScenarioListItem.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get(
    "/routing/corridor/scenarios/{scenario_id}",
    response_model=CorridorScenarioResponse,
)
def get_corridor_scenario(
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
    repo: GeoRepository = Depends(_get_repo),
):
    scenario = repo.get_routing_scenario(db, scenario_id)
    if scenario is None:
        raise NotFoundError("Routing scenario not found")
    return _attach_scenario_history(repo, db, scenario)


@router.post(
    "/routing/corridor/scenarios/{scenario_id}/approve",
    response_model=CorridorScenarioResponse,
)
def approve_corridor_scenario(
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
    repo: GeoRepository = Depends(_get_repo),
    body: CorridorScenarioApprovalRequest | None = None,
):
    scenario = repo.approve_routing_scenario(
        db,
        scenario_id,
        approved_by_id=getattr(_user, "id", None),
        note=body.note if body else None,
    )
    if scenario is None:
        raise NotFoundError("Routing scenario not found")
    db.commit()
    db.refresh(scenario)
    return _attach_scenario_history(repo, db, scenario)


@router.post(
    "/routing/corridor/scenarios/{scenario_id}/unapprove",
    response_model=CorridorScenarioResponse,
)
def unapprove_corridor_scenario(
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
    repo: GeoRepository = Depends(_get_repo),
    body: CorridorScenarioApprovalRequest | None = None,
):
    scenario = repo.unapprove_routing_scenario(
        db,
        scenario_id,
        approved_by_id=getattr(_user, "id", None),
        note=body.note if body else None,
    )
    if scenario is None:
        raise NotFoundError("Routing scenario not found")
    db.commit()
    db.refresh(scenario)
    return _attach_scenario_history(repo, db, scenario)


@router.post(
    "/routing/corridor/scenarios/{scenario_id}/favorite",
    response_model=CorridorScenarioResponse,
)
def favorite_corridor_scenario(
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
    repo: GeoRepository = Depends(_get_repo),
    body: CorridorScenarioFavoriteRequest | None = None,
):
    scenario = repo.set_routing_scenario_favorite(
        db,
        scenario_id,
        is_favorite=body.is_favorite if body else True,
    )
    if scenario is None:
        raise NotFoundError("Routing scenario not found")
    db.commit()
    db.refresh(scenario)
    return _attach_scenario_history(repo, db, scenario)


@router.get("/routing/corridor/scenarios/{scenario_id}/geojson")
def export_corridor_scenario_geojson(
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
    repo: GeoRepository = Depends(_get_repo),
):
    from app.domains.geo.routing import build_corridor_export_feature_collection

    scenario = repo.get_routing_scenario(db, scenario_id)
    if scenario is None:
        raise NotFoundError("Routing scenario not found")
    return build_corridor_export_feature_collection(scenario.result_payload)


@router.get("/routing/corridor/scenarios/{scenario_id}/pdf")
def export_corridor_scenario_pdf(
    scenario_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
    repo: GeoRepository = Depends(_get_repo),
):
    from app.shared.pdf import build_corridor_routing_pdf, get_branding

    scenario = repo.get_routing_scenario(db, scenario_id)
    if scenario is None:
        raise NotFoundError("Routing scenario not found")
    approval_history = repo.list_routing_scenario_approval_events(db, scenario_id)

    pdf_buffer = build_corridor_routing_pdf(
        scenario,
        get_branding(db),
        approved_by_name=_get_user_display_name(
            db, getattr(scenario, "approved_by_id", None)
        ),
        approval_history=approval_history,
    )
    filename = f"corridor-scenario-{scenario.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
