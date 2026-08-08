"""CHIRPS v3 provider adapter (GEE zonal statistics).

Validated by the 2026-08-07 spike (engram obs #12820): catalog ids are
CASE-SENSITIVE; ``UCSB-CHC/CHIRPS/V3/DAILY_RNL`` is the v3 Final (ERA5-aligned)
collection and ``UCSB-CHC/CHIRPS/V3/DAILY_SAT`` the v3 NRT (IMERG-aligned) one.
``source_id`` selects the profile:

- ``chirps-v3-final`` → RNN collection, historical/climatology contract.
- ``chirps-v3-sat`` → SAT collection, daily-operational fallback contract
  (spec: daily MAY use validated CHIRPS v3 when SQPE-OBS is unavailable).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.domains.geo.rainfall.adapters.gee_client import GeeZonalClient
from app.domains.geo.rainfall.adapters.zonal import build_zonal_batch
from app.domains.geo.rainfall.ports import SourceBatch

CHIRPS_V3_RNN_COLLECTION = "UCSB-CHC/CHIRPS/V3/DAILY_RNL"
CHIRPS_V3_SAT_COLLECTION = "UCSB-CHC/CHIRPS/V3/DAILY_SAT"
CHIRPS_BAND = "precipitation"

CHIRPS_SOURCE_CATALOGS: dict[str, tuple[str, str]] = {
    "chirps-v3-final": (CHIRPS_V3_RNN_COLLECTION, "v3-final"),
    "chirps-v3-sat": (CHIRPS_V3_SAT_COLLECTION, "v3-nrt"),
}


class ChirpsV3Adapter:
    """CHIRPS v3 daily zonal totals for a zone/basin scope geometry."""

    cadence = timedelta(days=1)
    band = CHIRPS_BAND
    unit = "mm"

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
        if source_id not in CHIRPS_SOURCE_CATALOGS:
            raise ValueError(f"unsupported CHIRPS source_id: {source_id!r}")
        catalog_id, provider_revision = CHIRPS_SOURCE_CATALOGS[source_id]
        geometry = self._gee.geometry(scope_kind=scope_kind, scope_id=scope_id)
        series = self._gee.zonal_series(
            collection_id=catalog_id,
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
            provider_revision=provider_revision,
            unit=self.unit,
            catalog_id=catalog_id,
            band=self.band,
            scale_m=self._gee.scale_meters,
            start=start,
            end=end,
            series=series,
        )
