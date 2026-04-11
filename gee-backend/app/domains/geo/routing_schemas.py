"""Pydantic schemas for corridor routing scenarios and auto-analysis."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CorridorScenarioSaveRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=255)
    profile: str
    request_payload: dict[str, Any]
    result_payload: dict[str, Any]
    notes: str | None = None
    previous_version_id: uuid.UUID | None = None
    is_favorite: bool = False


class CorridorScenarioApprovalRequest(BaseModel):
    note: str | None = None


class CorridorScenarioFavoriteRequest(BaseModel):
    is_favorite: bool = True


class CorridorScenarioApprovalEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scenario_id: uuid.UUID
    action: str
    note: str | None = None
    acted_by_id: uuid.UUID | None = None
    acted_at: datetime


class CorridorScenarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    profile: str
    version: int = 1
    previous_version_id: uuid.UUID | None = None
    request_payload: dict[str, Any]
    result_payload: dict[str, Any]
    notes: str | None = None
    approval_note: str | None = None
    is_approved: bool = False
    is_favorite: bool = False
    approved_at: datetime | None = None
    approved_by_id: uuid.UUID | None = None
    created_by_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    approval_history: list[CorridorScenarioApprovalEventResponse] = []


class CorridorScenarioListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    profile: str
    version: int = 1
    notes: str | None = None
    approval_note: str | None = None
    is_approved: bool = False
    is_favorite: bool = False
    approved_at: datetime | None = None
    created_at: datetime


class AutoCorridorAnalysisRequest(BaseModel):
    scope_type: Literal["cuenca", "subcuenca", "consorcio", "punto", "zona"] = "consorcio"
    scope_id: str | None = None
    point_lon: float | None = None
    point_lat: float | None = None
    mode: Literal["network", "raster"] = "raster"
    profile: Literal["balanceado", "hidraulico", "evitar_propiedad"] = "balanceado"
    max_candidates: int = Field(default=10, ge=1, le=20)
    corridor_width_m: float | None = Field(default=None, gt=0)
    alternative_count: int | None = Field(default=None, ge=0, le=5)
    penalty_factor: float | None = Field(default=None, ge=1.0)
    weight_slope: float | None = Field(default=None, ge=0.0)
    weight_hydric: float | None = Field(default=None, ge=0.0)
    weight_property: float | None = Field(default=None, ge=0.0)
    weight_landcover: float | None = Field(default=None, ge=0.0)
    include_unroutable: bool = True
