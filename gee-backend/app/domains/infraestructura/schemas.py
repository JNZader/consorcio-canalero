"""Pydantic v2 schemas for the infraestructura domain."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────
# ASSET SCHEMAS
# ──────────────────────────────────────────────


class AssetCreate(BaseModel):
    """Payload to create an infrastructure asset."""

    nombre: str = Field(..., min_length=2, max_length=200)
    tipo: str = Field(
        ...,
        description="Tipo de asset: canal, camino, puente, alcantarilla, compuerta, etc.",
    )
    descripcion: str = Field(..., min_length=10, max_length=5000)
    estado_actual: str = Field(
        default="bueno",
        description="Estado: bueno, regular, malo, critico",
    )
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)
    longitud_km: Optional[float] = Field(default=None, ge=0)
    material: Optional[str] = Field(default=None, max_length=100)
    anio_construccion: Optional[int] = Field(default=None, ge=1800, le=2100)
    responsable: Optional[str] = Field(default=None, max_length=200)


class AssetUpdate(BaseModel):
    """Partial update payload for an asset."""

    nombre: Optional[str] = Field(default=None, min_length=2, max_length=200)
    tipo: Optional[str] = None
    descripcion: Optional[str] = Field(default=None, min_length=10, max_length=5000)
    estado_actual: Optional[str] = None
    longitud_km: Optional[float] = Field(default=None, ge=0)
    material: Optional[str] = Field(default=None, max_length=100)
    anio_construccion: Optional[int] = Field(default=None, ge=1800, le=2100)
    responsable: Optional[str] = Field(default=None, max_length=200)


class AssetResponse(BaseModel):
    """Full asset detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    tipo: str
    descripcion: str
    estado_actual: str
    latitud: float
    longitud: float
    longitud_km: Optional[float] = None
    material: Optional[str] = None
    anio_construccion: Optional[int] = None
    responsable: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AssetListResponse(BaseModel):
    """Lightweight asset for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    tipo: str
    estado_actual: str
    latitud: float
    longitud: float
    longitud_km: Optional[float] = None
    created_at: datetime


# ──────────────────────────────────────────────
# MANTENIMIENTO SCHEMAS
# ──────────────────────────────────────────────


class MantenimientoLogCreate(BaseModel):
    """Payload to add a maintenance log entry."""

    tipo_trabajo: str = Field(..., min_length=3, max_length=200)
    descripcion: str = Field(..., min_length=10, max_length=5000)
    costo: Optional[float] = Field(default=None, ge=0)
    fecha_trabajo: date
    realizado_por: str = Field(..., min_length=2, max_length=200)


class MantenimientoLogResponse(BaseModel):
    """Single maintenance log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    tipo_trabajo: str
    descripcion: str
    costo: Optional[float] = None
    fecha_trabajo: date
    realizado_por: str
    usuario_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
