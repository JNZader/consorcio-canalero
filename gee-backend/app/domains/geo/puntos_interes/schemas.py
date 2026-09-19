"""Request and GeoJSON response contracts for staff map pins."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PuntoInteresTipo = Literal["alcantarilla", "alteo", "taponamiento", "otro"]


class PuntoInteresCreate(BaseModel):
    """Click-to-save body. Coordinates are WGS84 degrees, not a GeoJSON geometry."""

    model_config = ConfigDict(extra="forbid")

    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    titulo: str = Field(min_length=1, max_length=120)
    nota: Optional[str] = Field(default=None, max_length=2000)
    tipo: PuntoInteresTipo


class PuntoInteresProperties(BaseModel):
    id: str
    titulo: str
    nota: Optional[str] = None
    tipo: PuntoInteresTipo


class PuntoInteresFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: dict[str, Any]
    properties: PuntoInteresProperties


class PuntoInteresFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[PuntoInteresFeature]
