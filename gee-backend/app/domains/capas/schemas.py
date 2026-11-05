"""Pydantic v2 schemas for the capas (map layers) domain."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.capas.models import FuenteCapa, TipoCapa
from app.shared.enum_params import choice_or_raise
from app.shared.patch_fields import forbid_explicit_nulls


def _required_choice(value: object, choices: type, field: str) -> str:
    parsed = choice_or_raise(value, choices, field)
    if parsed is None:
        raise ValueError(f"{field} invalido")
    return parsed


# ──────────────────────────────────────────────
# STYLE SUB-SCHEMA
# ──────────────────────────────────────────────


class EstiloCapa(BaseModel):
    """Visual style properties for a map layer."""

    color: str = Field(default="#3388ff", description="Stroke / border color")
    weight: int = Field(default=2, ge=0, le=20, description="Stroke width in px")
    fillColor: str = Field(default="#3388ff", description="Fill color")
    fillOpacity: float = Field(default=0.2, ge=0.0, le=1.0, description="Fill opacity 0..1")


# ──────────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────────


class CapaCreate(BaseModel):
    """Payload to create a new map layer."""

    nombre: str = Field(..., min_length=1, max_length=200)
    descripcion: Optional[str] = None
    tipo: str = Field(..., description="polygon | line | point | raster | tile")
    fuente: str = Field(..., description="local | gee | upload")
    url: Optional[str] = Field(
        default=None, max_length=1000, description="URL for external tile/raster layers"
    )
    geojson_data: Optional[dict[str, Any]] = Field(
        default=None, description="Inline GeoJSON data for stored layers"
    )
    estilo: EstiloCapa = Field(default_factory=EstiloCapa)
    visible: bool = True
    orden: int = Field(default=0, ge=0)
    es_publica: bool = False

    @field_validator("tipo")
    @classmethod
    def validate_tipo(cls, v: str) -> str:
        return _required_choice(v, TipoCapa, "tipo")

    @field_validator("fuente")
    @classmethod
    def validate_fuente(cls, v: str) -> str:
        return _required_choice(v, FuenteCapa, "fuente")


# ──────────────────────────────────────────────
# UPDATE
# ──────────────────────────────────────────────


class CapaUpdate(BaseModel):
    """Partial update for a map layer."""

    nombre: Optional[str] = Field(default=None, min_length=1, max_length=200)
    descripcion: Optional[str] = None
    tipo: Optional[str] = None
    fuente: Optional[str] = None
    url: Optional[str] = None
    geojson_data: Optional[dict[str, Any]] = None
    estilo: Optional[EstiloCapa] = None
    visible: Optional[bool] = None
    orden: Optional[int] = Field(default=None, ge=0)
    es_publica: Optional[bool] = None

    @field_validator("tipo")
    @classmethod
    def validate_tipo(cls, v: Optional[str]) -> Optional[str]:
        return choice_or_raise(v, TipoCapa, "tipo")

    @field_validator("fuente")
    @classmethod
    def validate_fuente(cls, v: Optional[str]) -> Optional[str]:
        return choice_or_raise(v, FuenteCapa, "fuente")

    _reject_nulls = forbid_explicit_nulls(
        "nombre",
        "tipo",
        "fuente",
        "estilo",
        "visible",
        "orden",
        "es_publica",
    )


# ──────────────────────────────────────────────
# REORDER
# ──────────────────────────────────────────────


class CapaReorder(BaseModel):
    """Batch reorder request — list of layer IDs in desired order."""

    ordered_ids: list[uuid.UUID] = Field(..., description="Layer IDs in the desired display order")


# ──────────────────────────────────────────────
# RESPONSES
# ──────────────────────────────────────────────


class CapaResponse(BaseModel):
    """Full layer detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    fuente: str
    url: Optional[str] = None
    geojson_data: Optional[dict[str, Any]] = None
    estilo: dict[str, Any]
    visible: bool
    orden: int
    es_publica: bool
    created_at: datetime
    updated_at: datetime


class CapaListResponse(BaseModel):
    """Lightweight layer for list endpoints (no geojson_data)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    fuente: str
    url: Optional[str] = None
    estilo: dict[str, Any]
    visible: bool
    orden: int
    es_publica: bool
    created_at: datetime


class CapaReorderResponse(BaseModel):
    """Result of ``PUT /capas/reorder`` — how many rows had their
    ``orden`` updated."""

    message: str
    count: int
