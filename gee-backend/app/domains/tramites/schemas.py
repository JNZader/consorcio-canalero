"""Pydantic v2 schemas for the tramites domain."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.tramites.models import EstadoTramite, PrioridadTramite, TipoTramite
from app.shared.enum_params import choice_or_raise
from app.shared.patch_fields import forbid_explicit_nulls


def _required_choice(value: object, choices: type, field: str) -> str:
    parsed = choice_or_raise(value, choices, field)
    if parsed is None:
        raise ValueError(f"{field} invalido")
    return parsed


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

    @field_validator("tipo")
    @classmethod
    def validate_tipo(cls, v: str) -> str:
        return _required_choice(v, TipoTramite, "tipo")

    @field_validator("prioridad")
    @classmethod
    def validate_prioridad(cls, v: str) -> str:
        return _required_choice(v, PrioridadTramite, "prioridad")


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

    @field_validator("estado")
    @classmethod
    def validate_estado(cls, v: Optional[str]) -> Optional[str]:
        return choice_or_raise(v, EstadoTramite, "estado")

    @field_validator("prioridad")
    @classmethod
    def validate_prioridad(cls, v: Optional[str]) -> Optional[str]:
        return choice_or_raise(v, PrioridadTramite, "prioridad")

    _reject_nulls = forbid_explicit_nulls("estado", "prioridad")


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
    usuario_id: Optional[uuid.UUID] = None
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
    usuario_id: Optional[uuid.UUID] = None
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


class TramiteStatsResponse(BaseModel):
    """Aggregate counts surfaced by ``GET /tramites/stats``."""

    total: int
    por_estado: dict[str, int]
    por_tipo: dict[str, int]
    por_prioridad: dict[str, int]
