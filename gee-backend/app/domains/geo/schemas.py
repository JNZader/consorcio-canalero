"""Pydantic v2 schemas for the geo domain."""

import uuid
from datetime import date, datetime
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


# ──────────────────────────────────────────────
# GEE ANALYSIS SCHEMAS
# ──────────────────────────────────────────────


class AnalisisGeoCreate(BaseModel):
    """Payload to submit a GEE analysis."""

    tipo: str = Field(
        ...,
        description="Analysis type: flood, vegetation, classification, ndvi, custom",
    )
    parametros: dict[str, Any] = Field(
        default_factory=dict,
        description="Analysis params: start_date, end_date, method, thresholds, etc.",
    )
    fecha_inicio: Optional[datetime] = Field(
        None,
        description="Analysis period start date",
    )
    fecha_fin: Optional[datetime] = Field(
        None,
        description="Analysis period end date",
    )


class AnalisisGeoResponse(BaseModel):
    """Full GEE analysis detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    fecha_analisis: date
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    parametros: Optional[dict[str, Any]] = None
    resultado: Optional[dict[str, Any]] = None
    estado: str
    error: Optional[str] = None
    celery_task_id: Optional[str] = None
    usuario_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class AnalisisGeoListResponse(BaseModel):
    """Lightweight GEE analysis for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    fecha_analisis: date
    estado: str
    created_at: datetime
