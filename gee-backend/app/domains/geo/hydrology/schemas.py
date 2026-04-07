"""Pydantic v2 schemas for the hydrology subdomain."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class FloodFlowRequest(BaseModel):
    """Request to compute flood flow for one or more zones."""

    zona_ids: list[uuid.UUID] = Field(
        ..., min_length=1, description="Zone IDs to process"
    )
    fecha_lluvia: date = Field(
        ..., description="Rainfall event date for which to compute flood flow"
    )


class ZonaFloodFlowResult(BaseModel):
    """Per-zone computation result."""

    model_config = ConfigDict(from_attributes=True)

    zona_id: uuid.UUID
    zona_nombre: Optional[str] = None
    tc_minutos: float
    c_escorrentia: float
    c_source: str
    intensidad_mm_h: float
    area_km2: float
    caudal_m3s: float
    capacidad_m3s: Optional[float] = None
    porcentaje_capacidad: Optional[float] = None
    nivel_riesgo: str
    fecha_lluvia: date
    fecha_calculo: date


class FloodFlowResponse(BaseModel):
    """Response for flood flow computation."""

    total_zonas: int
    fecha_lluvia: date
    results: list[ZonaFloodFlowResult]
    errors: list[dict[str, Any]] = Field(default_factory=list)


class FloodFlowHistoryResponse(BaseModel):
    """Historical flood flow records for a zone."""

    model_config = ConfigDict(from_attributes=True)

    zona_id: uuid.UUID
    records: list[ZonaFloodFlowResult]
    total: int


class ZonaRiskSummary(BaseModel):
    """Minimal risk summary per zone — used for map coloring."""

    zona_id: str
    nivel_riesgo: Optional[str]


# ── Manning ───────────────────────────────────────────────────────────────────


class ManningRequest(BaseModel):
    """Parameters for Manning hydraulic capacity calculation."""

    ancho_m: float = Field(..., gt=0, description="Canal bottom width in meters")
    profundidad_m: float = Field(..., gt=0, description="Normal depth in meters")
    slope: float = Field(..., gt=0, description="Bed slope (dimensionless, rise/run)")
    talud: float = Field(
        default=0.0, ge=0, description="Side slope H:V (0=rectangular)"
    )
    material: Optional[str] = Field(
        default=None, description="Channel material for Manning n lookup"
    )
    coef_manning: Optional[float] = Field(
        default=None, gt=0, description="Override Manning n directly"
    )


class ManningResponse(BaseModel):
    """Manning hydraulic capacity result."""

    ancho_m: float
    profundidad_m: float
    talud: float
    slope: float
    n: float
    area_m2: float
    perimeter_m: float
    radio_hidraulico_m: float
    q_capacity_m3s: float
    velocidad_ms: float


# ── Return Periods ────────────────────────────────────────────────────────────


class ReturnPeriodResult(BaseModel):
    """Gumbel EV-I return period precipitation estimate."""

    return_period_years: int
    precipitation_mm: float


class ReturnPeriodsResponse(BaseModel):
    """Full return period analysis for a zona operativa."""

    zona_id: str
    years_of_data: int
    annual_maxima_count: int
    mean_annual_max_mm: float
    std_annual_max_mm: float
    return_periods: list[ReturnPeriodResult]
