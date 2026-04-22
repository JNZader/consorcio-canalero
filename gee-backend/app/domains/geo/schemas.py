"""Pydantic v2 schemas for the geo domain."""

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.domains.geo.models import TipoGeoJob


# ──────────────────────────────────────────────
# JOB SCHEMAS
# ──────────────────────────────────────────────


class GeoJobCreate(BaseModel):
    """Payload to submit a geo processing job."""

    tipo: TipoGeoJob = Field(
        ...,
        description="Job type: dem_pipeline, slope, aspect, flow_dir, gee_flood, gee_classification, etc.",
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
        description="Analysis type: flood, vegetation, classification, ndvi, custom, sar_temporal",
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


# ──────────────────────────────────────────────
# DEM PIPELINE SCHEMAS
# ──────────────────────────────────────────────


# ──────────────────────────────────────────────
# FLOOD EVENT SCHEMAS
# ──────────────────────────────────────────────


class FloodLabelCreate(BaseModel):
    """A single zone label within a flood event."""

    zona_id: uuid.UUID = Field(..., description="FK to zonas_operativas.id")
    is_flooded: bool = Field(..., description="Whether this zone was flooded")


class FloodEventCreate(BaseModel):
    """Payload to create a flood event with labeled zones."""

    event_date: date = Field(..., description="Date of satellite observation")
    description: Optional[str] = Field(None, description="Optional notes")
    labels: list[FloodLabelCreate] = Field(
        ...,
        min_length=1,
        description="At least one zone label required",
    )


class FloodLabelResponse(BaseModel):
    """A zone label within a flood event response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    zona_id: uuid.UUID
    is_flooded: bool
    ndwi_value: Optional[float] = None
    extracted_features: Optional[dict[str, Any]] = None


class FloodEventResponse(BaseModel):
    """Full flood event detail with labels."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_date: date
    description: Optional[str] = None
    satellite_source: str
    labels: list[FloodLabelResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class FloodEventListResponse(BaseModel):
    """Lightweight flood event for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_date: date
    description: Optional[str] = None
    label_count: int = 0
    created_at: datetime


# ──────────────────────────────────────────────
# TRAINING SCHEMAS
# ──────────────────────────────────────────────


class TrainingResultResponse(BaseModel):
    """Response from the flood model training endpoint."""

    events_used: int = Field(
        ..., description="Number of labeled events used for training"
    )
    epochs: int = Field(..., description="Number of training epochs run")
    initial_loss: float = Field(..., description="Loss at epoch 0")
    final_loss: float = Field(..., description="Loss at final epoch")
    weights_before: dict[str, float] = Field(
        ..., description="Model weights before training"
    )
    weights_after: dict[str, float] = Field(
        ..., description="Model weights after training"
    )
    bias: float = Field(..., description="Model bias after training")
    backup_path: str = Field(
        ..., description="Path where pre-training model was backed up"
    )


# ──────────────────────────────────────────────
# DEM PIPELINE SCHEMAS
# ──────────────────────────────────────────────


class DemPipelineRequest(BaseModel):
    """Payload to trigger the full DEM pipeline (download + process + basins)."""

    area_id: str = Field(
        default="zona_principal",
        description="Identifier for the processing area",
    )
    min_basin_area_ha: float = Field(
        default=5000.0,
        ge=0.0,
        description="Minimum basin area in hectares (basins below this are filtered out)",
    )


class DemPipelineResponse(BaseModel):
    """Response after triggering a DEM pipeline job."""

    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    tipo: str
    estado: str
    message: str = "Pipeline DEM iniciado correctamente"


# ──────────────────────────────────────────────
# NDWI BASELINE SCHEMAS
# ──────────────────────────────────────────────


class NdwiBaselineComputeRequest(BaseModel):
    """Payload to trigger NDWI baseline computation."""

    zona_ids: Optional[list[uuid.UUID]] = Field(
        None,
        description="Specific zona IDs. If null, all active zonas.",
    )
    dry_season_months: Optional[list[int]] = Field(
        None,
        description="Month numbers for dry season (1-12). Default: [6,7,8]",
        example=[6, 7, 8],
    )
    years_back: int = Field(
        3,
        ge=1,
        le=10,
        description="Years of Sentinel-2 history to use",
    )


class NdwiBaselineResponse(BaseModel):
    """NDWI dry-season baseline for a zona operativa."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    zona_operativa_id: uuid.UUID
    ndwi_mean: float
    ndwi_std: float
    sample_count: int
    dry_season_months: list[int]
    years_back: int
    computed_at: datetime
    created_at: datetime
    updated_at: datetime


# ── Afectados por Zona de Riesgo ─────────────────────────────────────────────


class ParcelaImportResult(BaseModel):
    imported: int
    skipped: int
    total: int


class AfectadoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    consorcista_id: uuid.UUID
    nombre: str
    parcela: Optional[str]
    hectareas: Optional[float]
    nomenclatura: str
    zona_nombre: str


class AfectadosResponse(BaseModel):
    zona_id: str
    zona_nombre: str
    total_consorcistas: int
    total_ha: float
    afectados: list[AfectadoItem]


class EventoAfectadosResponse(BaseModel):
    event_id: str
    event_date: str
    total_consorcistas: int
    total_ha: float
    zonas_afectadas: list[AfectadosResponse]
