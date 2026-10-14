"""Anonymous elevation profile for the public map.

Samples only the local filled DEM (Copernicus GLO-30, plus MDE-Ar when the
sibling tif exists). AW3D30/NASADEM bring Earth Engine cost, so they stay
operator-only on the authenticated ``POST /api/v2/geo/elevation-profile``.

Same body as the operator route; ``compare_dems`` is forced ``False`` so no
anonymous caller can reach GEE through this router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/map", tags=["public-elevation"])


class PublicElevationProfileRequest(BaseModel):
    """WGS84 LineString a visitor picked (published canal/road, or drawn)."""

    geometry: dict = Field(..., description="GeoJSON LineString in EPSG:4326")
    area_id: str | None = Field(
        default=None,
        description="DEM area; newest filled DEM across areas when omitted",
    )


@router.post("/elevation-profile")
def public_elevation_profile(
    body: PublicElevationProfileRequest,
    db: Session = Depends(get_db),
):
    """Distance vs elevation on Copernicus GLO-30. Not a project grade."""
    from app.domains.geo.elevation_profile_service import perfil_de_geojson

    return perfil_de_geojson(
        db,
        geometry=body.geometry,
        area_id=body.area_id,
        compare_dems=False,
    )
