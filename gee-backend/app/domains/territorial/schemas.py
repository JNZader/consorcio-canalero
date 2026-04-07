"""Pydantic v2 schemas for the territorial domain."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class GeoJSONImportRequest(BaseModel):
    """Body for GeoJSON import endpoints."""

    geojson: dict[str, Any]


class ImportResponse(BaseModel):
    imported: int
    message: str


class SueloBreakdown(BaseModel):
    """Soil type entry within a territorial report."""

    model_config = ConfigDict(from_attributes=True)

    simbolo: str
    cap: str | None
    ha: float
    pct: float  # percentage of total analysed area


class TerritorialReportResponse(BaseModel):
    """Aggregated territorial report for a given scope."""

    scope: str  # "consorcio" | "cuenca" | "zona"
    scope_name: str
    km_canales: float
    suelos: list[SueloBreakdown]
    total_ha_analizada: float


class CuencaListResponse(BaseModel):
    cuencas: list[str]
