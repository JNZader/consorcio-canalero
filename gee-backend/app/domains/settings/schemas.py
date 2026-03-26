"""Pydantic v2 schemas for the settings domain."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SettingResponse(BaseModel):
    """Full setting detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clave: str
    valor: Any
    categoria: str
    descripcion: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SettingUpdate(BaseModel):
    """Payload to update a setting value."""

    valor: Any = Field(..., description="New value (JSON-compatible)")
    descripcion: Optional[str] = Field(
        default=None, description="Optional description override"
    )


class SettingsByCategoryResponse(BaseModel):
    """Settings grouped by category."""

    categoria: str
    settings: list[SettingResponse]


class BrandingResponse(BaseModel):
    """Public-facing branding settings (no auth required)."""

    nombre_organizacion: Optional[str] = None
    logo_url: Optional[str] = None
    color_primario: Optional[str] = None
    color_secundario: Optional[str] = None


# ── Map image selection schemas ──


class ImagenMapaParams(BaseModel):
    """Parameters to regenerate a satellite image tile from GEE."""

    sensor: str = Field(..., description="Sentinel-1 or Sentinel-2")
    target_date: str = Field(..., description="YYYY-MM-DD")
    visualization: str = Field(..., description="rgb, ndvi, ndwi, vv, etc.")
    max_cloud: Optional[int] = Field(
        default=None, ge=0, le=100, description="Max cloud % (Sentinel-2 only)"
    )
    days_buffer: int = Field(default=10, ge=1, le=30)


class ImagenComparacionParams(BaseModel):
    """Parameters for image comparison mode."""

    enabled: bool = False
    left: Optional[ImagenMapaParams] = None
    right: Optional[ImagenMapaParams] = None


class ImagenMapaResponse(BaseModel):
    """Response with saved map image parameters."""

    imagen_principal: Optional[ImagenMapaParams] = None
    imagen_comparacion: Optional[ImagenComparacionParams] = None
