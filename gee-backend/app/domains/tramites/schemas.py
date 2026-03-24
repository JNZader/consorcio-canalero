"""Pydantic v2 schemas for the tramites domain."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────────


class TramiteCreate(BaseModel):
    """Payload to create a tramite (requires operator)."""

    tipo: str = Field(
        ...,
        description="Tipo de tramite: obra, permiso, habilitacion, reclamo, otro",
    )
    titulo: str = Field(..., min_length=5, max_length=200)
    descripcion: str = Field(..., min_length=10, max_length=5000)
    solicitante: str = Field(..., min_length=2, max_length=200)
    prioridad: str = Field(
        default="media",
        description="Prioridad: baja, media, alta, urgente",
    )
    fecha_ingreso: Optional[date] = None


# ──────────────────────────────────────────────
# UPDATE (operator)
# ──────────────────────────────────────────────


class TramiteUpdate(BaseModel):
    """Operator payload to change estado or add resolution."""

    estado: Optional[str] = None
    resolucion: Optional[str] = None
    prioridad: Optional[str] = None
    comentario: Optional[str] = Field(
        default=None,
        description="Comentario para el seguimiento de cambios",
    )


# ──────────────────────────────────────────────
# SEGUIMIENTO CREATE
# ──────────────────────────────────────────────


class SeguimientoCreate(BaseModel):
    """Add a follow-up entry to a tramite."""

    comentario: str = Field(..., min_length=5, max_length=5000)


# ──────────────────────────────────────────────
# RESPONSES
# ──────────────────────────────────────────────


class SeguimientoResponse(BaseModel):
    """Single entry in the tramite audit log."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tramite_id: uuid.UUID
    estado_anterior: str
    estado_nuevo: str
    comentario: str
    usuario_id: uuid.UUID
    created_at: datetime


class TramiteResponse(BaseModel):
    """Full tramite detail (includes seguimiento history)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    titulo: str
    descripcion: str
    solicitante: str
    estado: str
    prioridad: str
    fecha_ingreso: date
    fecha_resolucion: Optional[date] = None
    resolucion: Optional[str] = None
    usuario_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    seguimiento: list[SeguimientoResponse] = []


class TramiteListResponse(BaseModel):
    """Lightweight tramite for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    titulo: str
    solicitante: str
    estado: str
    prioridad: str
    fecha_ingreso: date
    fecha_resolucion: Optional[date] = None
    created_at: datetime


class TramiteCreateResponse(BaseModel):
    """Response after creating a new tramite."""

    id: uuid.UUID
    message: str
    estado: str
