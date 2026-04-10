"""Pydantic schemas for saved corridor routing scenarios."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
