"""Pydantic v2 schemas for the denuncias domain."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────────


class DenunciaCreate(BaseModel):
    """Public payload to create a denuncia (no auth required)."""

    tipo: str = Field(
        ...,
        description="Tipo de denuncia: alcantarilla_tapada, desborde, camino_danado, otro",
    )
    descripcion: str = Field(..., min_length=10, max_length=2000)
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)
    cuenca: Optional[str] = None
    contacto_telefono: Optional[str] = Field(
        default=None, max_length=50
    )
    contacto_email: Optional[str] = Field(
        default=None, max_length=255
    )
    foto_url: Optional[str] = None


# ──────────────────────────────────────────────
# UPDATE (admin / operator)
# ──────────────────────────────────────────────


class DenunciaUpdate(BaseModel):
    """Admin/operator payload to change estado or add a respuesta."""

    estado: Optional[str] = None
    respuesta: Optional[str] = None
    comentario: Optional[str] = Field(
        default=None,
        description="Comentario para el historial de cambios",
    )


# ──────────────────────────────────────────────
# RESPONSES
# ──────────────────────────────────────────────


class HistorialResponse(BaseModel):
    """Single entry in the denuncia audit log."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    denuncia_id: uuid.UUID
    estado_anterior: str
    estado_nuevo: str
    comentario: Optional[str] = None
    usuario_id: uuid.UUID
    created_at: datetime


class DenunciaResponse(BaseModel):
    """Full denuncia detail (includes historial)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    descripcion: str
    latitud: float
    longitud: float
    cuenca: Optional[str] = None
    estado: str
    contacto_telefono: Optional[str] = None
    contacto_email: Optional[str] = None
    foto_url: Optional[str] = None
    user_id: Optional[uuid.UUID] = None
    respuesta: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    historial: list[HistorialResponse] = []


class DenunciaListResponse(BaseModel):
    """Lightweight denuncia for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    descripcion: str
    latitud: float
    longitud: float
    cuenca: Optional[str] = None
    estado: str
    foto_url: Optional[str] = None
    created_at: datetime


class DenunciaCreateResponse(BaseModel):
    """Response after creating a new denuncia."""

    id: uuid.UUID
    message: str
    estado: str
