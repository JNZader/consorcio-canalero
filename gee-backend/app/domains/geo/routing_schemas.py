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


class CorridorScenarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    profile: str
    request_payload: dict[str, Any]
    result_payload: dict[str, Any]
    notes: str | None = None
    is_approved: bool = False
    approved_at: datetime | None = None
    approved_by_id: uuid.UUID | None = None
    created_by_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class CorridorScenarioListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    profile: str
    notes: str | None = None
    is_approved: bool = False
    approved_at: datetime | None = None
    created_at: datetime
