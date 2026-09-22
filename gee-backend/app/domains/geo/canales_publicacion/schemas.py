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


class CanalPublicacionPatch(BaseModel):
    publicado: Optional[bool] = None
    nombre_publico: Optional[str] = Field(default=None, min_length=1, max_length=200)


class CanalPublicacionList(BaseModel):
    items: list[CanalPublicacionRow]
    geojson: dict
