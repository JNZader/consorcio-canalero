"""Pydantic schemas for canal publication."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CanalPublicacionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    estado: Literal["relevado", "propuesto"]
    nombre_interno: str
    nombre_publico: str
    publicado: bool
    longitud_m: Optional[float] = None
    codigo: Optional[str] = None
    origen: Literal["kmz", "aprhi", "sr_pa"] = "kmz"


class CanalPublicacionPatch(BaseModel):
    publicado: Optional[bool] = None
    nombre_publico: Optional[str] = Field(default=None, min_length=1, max_length=200)


def _empty_feature_collection() -> dict:
    return {"type": "FeatureCollection", "features": []}


class CanalPublicacionList(BaseModel):
    items: list[CanalPublicacionRow]
    geojson: dict
    aprhi_items: list[CanalPublicacionRow] = Field(default_factory=list)
    geojson_aprhi: dict = Field(default_factory=_empty_feature_collection)
    sr_pa_items: list[CanalPublicacionRow] = Field(default_factory=list)
    geojson_sr_pa: dict = Field(default_factory=_empty_feature_collection)
