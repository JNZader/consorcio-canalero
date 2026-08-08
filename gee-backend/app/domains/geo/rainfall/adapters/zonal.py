"""Canonical SourceBatch builder for gridded precipitation zonal series.

Pure logic shared by the CHIRPS and IMERG adapters: aligns the client's
``(interval_start, value)`` rows to the cadence grid, computes coverage /
completeness / discrepancies and a deterministic content checksum, and
returns one :class:`SourceBatch` per the canonical ports contract.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from math import isfinite

from app.domains.geo.rainfall.ports import SourceBatch, SourceInterval


def _snap_to_cadence(cadence: timedelta, moment: datetime) -> datetime:
    if cadence >= timedelta(days=1):
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return moment.replace(second=0, microsecond=0)


def _expected_slots(
    start: datetime, end: datetime, cadence: timedelta
) -> list[tuple[datetime, datetime]]:
    slots: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        slot_end = cursor + cadence
        if slot_end > end:
            break  # the provider window is not a whole number of cadences
        slots.append((cursor, slot_end))
        cursor = slot_end
    return slots


def _content_checksum(intervals: Sequence[SourceInterval]) -> str:
    payload = [
        (interval.interval_start.isoformat(), round(interval.value, 6)) for interval in intervals
    ]
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"sha256:{digest}"


def build_zonal_batch(
    *,
    source_id: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    cadence: timedelta,
    provider_revision: str,
    unit: str,
    catalog_id: str,
    band: str,
    scale_m: int,
    start: datetime,
    end: datetime,
    series: Sequence[tuple[datetime, float | None]],
) -> SourceBatch:
    """Assemble one canonical batch over the cadence grid in ``[start, end)``.

    Series rows are snapped to the cadence grid: daily cadences anchor at UTC
    midnight (CHIRPS), sub-daily cadences at the minute (IMERG algorithm slots
    are at ``:00``/``:30``). Two values landing on the same slot after snapping
    are treated as a provider anomaly and rejected loudly instead of averaged.
    """
    values_by_slot: dict[datetime, list[float]] = {}
    for raw_start, raw_value in series:
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not isfinite(value):
            continue
        slot = _snap_to_cadence(cadence, raw_start)
        values_by_slot.setdefault(slot, []).append(value)

    duplicated = [slot for slot, values in values_by_slot.items() if len(values) > 1]
    if duplicated:
        raise ValueError(
            f"duplicate provider values for slot(s) {duplicated[:3]} — refusing to blend"
        )
    values = {slot: values[0] for slot, values in values_by_slot.items()}

    intervals: list[SourceInterval] = []
    discrepancies: list[str] = []
    expected_slots = _expected_slots(start, end, cadence)
    for slot_start, slot_end in expected_slots:
        value = values.get(slot_start)
        if value is None:
            discrepancies.append(f"expected_interval={slot_start.isoformat()}")
            continue
        intervals.append(SourceInterval(slot_start, slot_end, value, unit, provider_revision))

    expected_count = len(expected_slots)
    completeness = len(intervals) / expected_count if expected_count else 0.0
    coverage = completeness  # every materialised interval carries a zonal mean
    quality = {
        "catalog_id": catalog_id,
        "band": band,
        "reduction": "mean",
        "scale_m": scale_m,
        "provider_revision": provider_revision,
    }
    return SourceBatch(
        source_id,
        scope_kind,
        scope_id,
        scope_version,
        cadence,
        tuple(intervals),
        coverage,
        completeness,
        quality,
        tuple(discrepancies),
        _content_checksum(intervals),
    )
