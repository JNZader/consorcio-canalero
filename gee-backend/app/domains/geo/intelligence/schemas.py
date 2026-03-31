"""Pydantic v2 schemas for the operational intelligence sub-module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────
# ZONA OPERATIVA
# ──────────────────────────────────────────────


class ZonaOperativaResponse(BaseModel):
    """Full operational zone detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    cuenca: str
    superficie_ha: float
    geometria: Optional[dict[str, Any]] = Field(
        default=None,
        description="Zone boundary as GeoJSON geometry object (Polygon)",
    )
    created_at: datetime
    updated_at: datetime


class ZonaOperativaListResponse(BaseModel):
    """Lightweight zone for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    cuenca: str
    superficie_ha: float


# ──────────────────────────────────────────────
# INDICE HIDRICO
# ──────────────────────────────────────────────


class IndiceHidricoResponse(BaseModel):
    """Full HCI calculation result."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    zona_id: uuid.UUID
    fecha_calculo: date
    pendiente_media: float
    acumulacion_media: float
    twi_medio: float
    proximidad_canal_m: float
    historial_inundacion: float
    indice_final: float
    nivel_riesgo: str
    created_at: datetime
    updated_at: datetime


class CriticidadRequest(BaseModel):
    """Request to calculate HCI for a zone."""

    zona_id: uuid.UUID = Field(..., description="Zone to calculate HCI for")
    pendiente_media: float = Field(..., ge=0, le=1, description="Normalized mean slope")
    acumulacion_media: float = Field(
        ..., ge=0, le=1, description="Normalized mean flow accumulation"
    )
    twi_medio: float = Field(..., ge=0, le=1, description="Normalized mean TWI")
    proximidad_canal_m: float = Field(
        ..., ge=0, description="Average distance to nearest canal (m)"
    )
    historial_inundacion: float = Field(
        ..., ge=0, le=1, description="Flood history factor"
    )
    pesos: Optional[dict[str, float]] = Field(
        default=None, description="Custom weight dict"
    )


class CriticidadResponse(BaseModel):
    """HCI calculation result."""

    zona_id: uuid.UUID
    indice_final: float
    nivel_riesgo: str
    componentes: dict[str, float]


# ──────────────────────────────────────────────
# PUNTO DE CONFLICTO
# ──────────────────────────────────────────────


class PuntoConflictoResponse(BaseModel):
    """Full conflict point detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    descripcion: str
    severidad: str
    infraestructura_ids: Optional[list[str]] = None
    acumulacion_valor: float
    pendiente_valor: float
    created_at: datetime
    updated_at: datetime


class ConflictoDetectarRequest(BaseModel):
    """Request to run conflict detection."""

    buffer_m: float = Field(default=50.0, ge=10, le=500, description="Buffer in meters")
    flow_acc_threshold: float = Field(
        default=500.0, ge=0, description="Min flow accumulation"
    )
    slope_threshold: float = Field(
        default=5.0, ge=0, description="Max slope in degrees"
    )


# ──────────────────────────────────────────────
# ESCORRENTIA
# ──────────────────────────────────────────────


class EscorrentiaRequest(BaseModel):
    """Request to run runoff simulation."""

    punto_inicio: list[float] = Field(
        ..., min_length=2, max_length=2, description="[lon, lat]"
    )
    lluvia_mm: float = Field(..., gt=0, le=500, description="Rainfall in mm")


class EscorrentiaResponse(BaseModel):
    """Runoff simulation result (GeoJSON FeatureCollection)."""

    type: str = "FeatureCollection"
    features: list[dict[str, Any]]
    properties: Optional[dict[str, Any]] = None


# ──────────────────────────────────────────────
# ZONIFICACION
# ──────────────────────────────────────────────


class ZonificacionRequest(BaseModel):
    """Request to generate operational zones."""

    dem_layer_id: uuid.UUID = Field(..., description="GeoLayer ID of the DEM")
    threshold: int = Field(default=2000, ge=100, description="Pour point threshold")


class ZonificacionResponse(BaseModel):
    """Zonification generation result."""

    zonas_creadas: int
    zonas: list[ZonaOperativaListResponse]


# ──────────────────────────────────────────────
# ALERTAS
# ──────────────────────────────────────────────


class AlertaResponse(BaseModel):
    """Full alert detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    mensaje: str
    nivel: str
    datos: Optional[dict[str, Any]] = None
    activa: bool
    zona_id: Optional[uuid.UUID] = None
    created_at: datetime


# ──────────────────────────────────────────────
# PRIORIDAD / RIESGO
# ──────────────────────────────────────────────


class CanalPrioridadResponse(BaseModel):
    """Canal with its priority score."""

    canal_id: str
    nombre: str
    prioridad: float
    detalles: Optional[dict[str, Any]] = None


class CaminoRiesgoResponse(BaseModel):
    """Road segment with its risk score."""

    camino_id: str
    nombre: str
    riesgo: float
    detalles: Optional[dict[str, Any]] = None


# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────


class DashboardInteligente(BaseModel):
    """Aggregated intelligence dashboard."""

    porcentaje_area_riesgo: float = Field(
        ..., description="Percentage of total area at risk (medio+)"
    )
    canales_criticos: int = Field(
        ..., description="Number of canals with priority > 70"
    )
    caminos_vulnerables: int = Field(
        ..., description="Number of roads with risk > 70"
    )
    conflictos_activos: int = Field(
        ..., description="Number of detected conflict points"
    )
    alertas_activas: int = Field(
        ..., description="Number of active alerts"
    )
    zonas_por_nivel: dict[str, int] = Field(
        default_factory=dict,
        description="Count of zones per risk level",
    )
    evolucion_temporal: list[dict[str, Any]] = Field(
        default_factory=list,
        description="HCI evolution over time",
    )


# ──────────────────────────────────────────────
# COMPOSITE ANALYSIS
# ──────────────────────────────────────────────


class CompositeAnalysisRequest(BaseModel):
    """Request to trigger composite analysis (flood risk + drainage need)."""

    area_id: str = Field(..., description="Processing area identifier")
    weights_flood: Optional[dict[str, float]] = Field(
        default=None,
        description="Custom flood risk weights (keys: twi, hand, flow_acc, slope). Must sum to 1.0",
    )
    weights_drainage: Optional[dict[str, float]] = Field(
        default=None,
        description="Custom drainage need weights (keys: flow_acc, twi, hand, dist_drainage). Must sum to 1.0",
    )


class CompositeZonalStatsResponse(BaseModel):
    """Zonal statistics for a composite raster (flood risk or drainage need)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    zona_id: uuid.UUID
    zona_nombre: Optional[str] = Field(
        default=None, description="Zone name (joined from ZonaOperativa)"
    )
    cuenca: Optional[str] = Field(default=None, description="Parent watershed / basin family")
    superficie_ha: Optional[float] = Field(default=None, description="Zone area in hectares")
    tipo: str = Field(..., description="flood_risk | drainage_need")
    mean_score: float
    max_score: float
    p90_score: float
    area_high_risk_ha: float
    weights_used: Optional[dict[str, float]] = None
    fecha_calculo: date


class BasinRiskRankingResponse(BaseModel):
    """List of basins ranked by composite risk score."""

    items: list[CompositeZonalStatsResponse]
    total: int


class CompositeComparisonItemResponse(BaseModel):
    """Before/after comparison for a zone under a given composite analysis."""

    zona_id: uuid.UUID
    zona_nombre: Optional[str] = None
    cuenca: Optional[str] = None
    superficie_ha: Optional[float] = None
    tipo: str
    current_mean_score: float
    baseline_mean_score: float
    delta_mean_score: float
    current_area_high_risk_ha: float
    baseline_area_high_risk_ha: float
    delta_area_high_risk_ha: float


class CompositeComparisonResponse(BaseModel):
    """Comparison response between current and baseline composite stats."""

    area_id: str
    tipo: str
    items: list[CompositeComparisonItemResponse]
    total: int
