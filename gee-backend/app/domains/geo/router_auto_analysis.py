"""Automatic corridor-analysis endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.models import User
from app.db.session import get_db
from app.domains.geo.router_common import _require_operator
from app.domains.geo.routing_auto_analysis import auto_analyze_corridors
from app.domains.geo.routing_schemas import AutoCorridorAnalysisRequest

router = APIRouter(tags=["Geo Processing"])


@router.post("/routing/auto-analysis")
def calculate_auto_corridor_analysis(
    body: AutoCorridorAnalysisRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    return auto_analyze_corridors(
        db,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        point_lon=body.point_lon,
        point_lat=body.point_lat,
        mode=body.mode,
        profile=body.profile,
        max_candidates=body.max_candidates,
        corridor_width_m=body.corridor_width_m,
        alternative_count=body.alternative_count,
        penalty_factor=body.penalty_factor,
        include_unroutable=body.include_unroutable,
        weight_overrides={
            "slope": body.weight_slope,
            "hydric": body.weight_hydric,
            "property": body.weight_property,
            "landcover": body.weight_landcover,
        },
    )
