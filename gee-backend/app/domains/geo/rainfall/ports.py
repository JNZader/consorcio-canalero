"""Typed canonical adapter boundary; provider SDK objects never leave adapters."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class SourceInterval:
    interval_start: datetime
    interval_end: datetime
    value: float
    unit: str
    provider_revision: str

    def __post_init__(self) -> None:
        if not isfinite(self.value):
            raise ValueError("source interval value must be finite")
        if self.interval_start.tzinfo is None or self.interval_end.tzinfo is None:
            raise ValueError("source intervals must be timezone-aware UTC")
        if (
            self.interval_start.utcoffset() != timedelta()
            or self.interval_end.utcoffset() != timedelta()
        ):
            raise ValueError("source intervals must use UTC boundaries")
        if self.interval_end <= self.interval_start:
            raise ValueError("source interval must be half-open with end after start")
        if self.unit not in {"mm", "mm/h"}:
            raise ValueError("source interval unit is not canonical")
        if not self.provider_revision:
            raise ValueError("source interval requires a provider revision")


@dataclass(frozen=True, slots=True)
class SourceBatch:
    source_id: str
    scope_kind: Literal["zone", "basin"]
    scope_id: str
    scope_version: str
    cadence: timedelta
    intervals: tuple[SourceInterval, ...]
    coverage: float
    completeness: float
    quality: dict[str, object]
    discrepancies: tuple[str, ...]
    checksum: str

    def __post_init__(self) -> None:
        if (
            not self.source_id
            or not self.scope_kind
            or not self.scope_id
            or not self.scope_version
            or not self.checksum
        ):
            raise ValueError("source batch requires stable source and scope identity plus checksum")
        if self.scope_kind not in {"zone", "basin"}:
            raise ValueError("source batch scope kind is not supported")
        if self.cadence <= timedelta():
            raise ValueError("source batch cadence must be positive")
        if (
            not isfinite(self.coverage)
            or not isfinite(self.completeness)
            or not 0 <= self.coverage <= 1
            or not 0 <= self.completeness <= 1
        ):
            raise ValueError("source batch coverage and completeness must be between zero and one")
        for interval in self.intervals:
            if interval.interval_end - interval.interval_start != self.cadence:
                raise ValueError("source interval does not match declared cadence")


class RainfallSourceAdapter(Protocol):
    def fetch(
        self,
        *,
        source_id: str,
        scope_kind: Literal["zone", "basin"],
        scope_id: str,
        scope_version: str,
        start: datetime,
        end: datetime,
    ) -> SourceBatch: ...
