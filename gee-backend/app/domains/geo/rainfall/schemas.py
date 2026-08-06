"""Canonical provenance-first metric contract."""

from datetime import datetime
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Provenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    source_class: Literal["observed_station", "estimated_radar", "estimated_satellite"]
    method: str
    nominal_resolution: str
    aggregation: str
    spatial_scope: Literal["zone", "basin"]
    freshness: datetime
    available_through: datetime


class MetricResult(BaseModel):
    """A complete metric record; omitted evidence is a contract error, not unknown data."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    metric: str
    value: float | None = None
    unit: str
    state: Literal["available", "partial", "suppressed", "unavailable"]
    reason: str | None = None
    interval_start: datetime
    interval_end: datetime
    coverage: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    quality: dict[str, Any]
    discrepancies: tuple[str, ...]
    temporal_state: Literal["provisional", "final"]
    revision: str
    provenance: Provenance
    fallback_used: bool

    @model_validator(mode="after")
    def validate_contract(self) -> "MetricResult":
        if self.value is not None and not isfinite(self.value):
            raise ValueError("metric value must be finite")
        if not isfinite(self.coverage) or not isfinite(self.completeness):
            raise ValueError("metric coverage and completeness must be finite")
        if self.interval_end <= self.interval_start:
            raise ValueError("interval_end must be after interval_start")
        if self.state == "available" and self.value is None:
            raise ValueError("available metrics require a value")
        if self.state in {"suppressed", "unavailable"}:
            if self.value is not None:
                raise ValueError("suppressed or unavailable metrics must not disclose a value")
            if not self.reason:
                raise ValueError("suppressed or unavailable metrics require a reason")
        return self
