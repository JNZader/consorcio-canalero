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
