"""Pydantic v2 schemas for the reuniones domain."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────
# REUNION CREATE / UPDATE
# ──────────────────────────────────────────────


class ReunionCreate(BaseModel):
    """Payload to create a reunion (requires operator)."""

    titulo: str = Field(..., min_length=3, max_length=200)
    fecha_reunion: datetime
    lugar: str = Field(default="Sede Consorcio", max_length=200)
    descripcion: Optional[str] = None
    tipo: str = Field(
        default="ordinaria",
        description="Tipo de reunion: ordinaria, extraordinaria, urgente",
    )
    orden_del_dia_items: list[str] = Field(default_factory=list)


class ReunionUpdate(BaseModel):
    """Operator payload to update a reunion."""

    titulo: Optional[str] = Field(default=None, min_length=3, max_length=200)
    fecha_reunion: Optional[datetime] = None
    lugar: Optional[str] = Field(default=None, max_length=200)
    descripcion: Optional[str] = None
    tipo: Optional[str] = None
    estado: Optional[str] = None
    orden_del_dia_items: Optional[list[str]] = None


# ──────────────────────────────────────────────
# AGENDA ITEM CREATE / UPDATE
# ──────────────────────────────────────────────


class AgendaReferenciaCreate(BaseModel):
    """Single cross-entity reference for an agenda item."""

    entidad_tipo: str = Field(..., max_length=50)
    entidad_id: uuid.UUID
    metadata: Optional[dict] = None


class AgendaItemCreate(BaseModel):
    """Payload to add an agenda item to a reunion."""

    titulo: str = Field(..., min_length=2, max_length=200)
    descripcion: Optional[str] = None
    orden: int = Field(default=0, ge=0)
    referencias: list[AgendaReferenciaCreate] = Field(default_factory=list)


class AgendaItemUpdate(BaseModel):
    """Payload to update an agenda item."""

    titulo: Optional[str] = Field(default=None, min_length=2, max_length=200)
    descripcion: Optional[str] = None
    orden: Optional[int] = Field(default=None, ge=0)
    completado: Optional[bool] = None


# ──────────────────────────────────────────────
# RESPONSES
# ──────────────────────────────────────────────


class AgendaReferenciaResponse(BaseModel):
    """Single cross-entity reference response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agenda_item_id: uuid.UUID
    entidad_tipo: str
    entidad_id: uuid.UUID
    metadata_json: Optional[dict] = None
    created_at: datetime


class AgendaItemResponse(BaseModel):
    """Agenda item with nested referencias."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reunion_id: uuid.UUID
    titulo: str
    descripcion: Optional[str] = None
    orden: int
    completado: bool
    created_at: datetime
    referencias: list[AgendaReferenciaResponse] = []


class ReunionResponse(BaseModel):
    """Full reunion detail (includes agenda items)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    fecha_reunion: datetime
    lugar: str
    descripcion: Optional[str] = None
    tipo: str
    estado: str
    orden_del_dia_items: list = []
    usuario_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    agenda_items: list[AgendaItemResponse] = []


class ReunionListResponse(BaseModel):
    """Lightweight reunion for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    fecha_reunion: datetime
    lugar: str
    tipo: str
    estado: str
    orden_del_dia_items: list = []
    created_at: datetime


class ReunionCreateResponse(BaseModel):
    """Response after creating a new reunion."""

    id: uuid.UUID
    message: str
    estado: str
