"""IMERG V07 provider adapter (GEE zonal statistics, 30-minute steps).

IMERG Early/Late/Final ``NASA/GPM_L3/IMERG_V07`` is the validated fallback
for the high-resolution ``intensity`` role when the preferred radar candidate
(RQPE/SINARAME) is ineligible or unavailable (spec R3). V06 is deprecated and
must not be used. Each 30-minute image carries the accumulated precipitation
``mm`` of its half-open slot, so every grid step becomes one interval.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.domains.geo.rainfall.adapters.gee_client import GeeZonalClient
from app.domains.geo.rainfall.adapters.zonal import build_zonal_batch
from app.domains.geo.rainfall.ports import SourceBatch

IMERG_V07_COLLECTION = "NASA/GPM_L3/IMERG_V07"
IMERG_BAND = "precipitation"


class ImergV07Adapter:
    """IMERG V07 30-minute zonal accumulation over the scope geometry."""

    cadence = timedelta(minutes=30)
    band = IMERG_BAND
    unit = "mm"
    provider_revision = "v07"

    def __init__(self, gee: Any | None = None) -> None:
        self._gee = gee if gee is not None else GeeZonalClient()

    def fetch(
        self,
        *,
        source_id: str,
        scope_kind: str,
        scope_id: str,
        scope_version: str,
        start: Any,
        end: Any,
    ) -> SourceBatch:
        if source_id != "imerg-v07":
            raise ValueError(f"unsupported IMERG source_id: {source_id!r}")
        geometry = self._gee.geometry(scope_kind=scope_kind, scope_id=scope_id)
        series = self._gee.zonal_series(
            collection_id=IMERG_V07_COLLECTION,
            start=start,
            end=end,
            geometry=geometry,
            band=self.band,
        )
        return build_zonal_batch(
            source_id=source_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            scope_version=scope_version,
            cadence=self.cadence,
            provider_revision=self.provider_revision,
            unit=self.unit,
            catalog_id=IMERG_V07_COLLECTION,
            band=self.band,
            scale_m=self._gee.scale_meters,
            start=start,
            end=end,
            series=series,
        )
