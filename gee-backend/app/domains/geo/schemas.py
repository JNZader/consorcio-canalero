"""Pydantic v2 schemas for the geo domain."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────
# JOB SCHEMAS
# ──────────────────────────────────────────────


class GeoJobCreate(BaseModel):
    """Payload to submit a geo processing job."""

    tipo: str = Field(
        ...,
        description="Job type: dem_pipeline, slope, aspect, flow_dir, etc.",
    )
    parametros: dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters (e.g. dem_path, area_id, threshold)",
    )


class GeoJobResponse(BaseModel):
    """Full geo job detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    estado: str
    celery_task_id: Optional[str] = None
    parametros: Optional[dict[str, Any]] = None
    resultado: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    progreso: int = 0
    usuario_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class GeoJobListResponse(BaseModel):
    """Lightweight geo job for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    estado: str
    progreso: int
    created_at: datetime


# ──────────────────────────────────────────────
# LAYER SCHEMAS
# ──────────────────────────────────────────────


class GeoLayerResponse(BaseModel):
    """Full geo layer detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    tipo: str
    fuente: str
    archivo_path: str
    formato: str
    srid: int
    bbox: Optional[list[float]] = None
    metadata_extra: Optional[dict[str, Any]] = None
    area_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class GeoLayerListResponse(BaseModel):
    """Lightweight geo layer for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    tipo: str
    fuente: str
    formato: str
    area_id: Optional[str] = None
    created_at: datetime
