"""GEE materialisation seam shared by the Rainfall v2 provider adapters.

Every ``ee`` callout the rainfall adapters need lives here so a fake client
can replace it in tests — CI never touches the GEE network. The real path uses
the project's own initialiser (``gee_service._ensure_initialized``, service
account ``GEE_SERVICE_ACCOUNT_KEY`` + ``GEE_PROJECT_ID``) and was validated
read-only in the 2026-08-07 spike (engram obs #12820).

Asset mapping (validated at spike time): the deployment owns a single zone
asset, ``zona_cc_ampliada``; basin scopes map to the same-named operational
assets. No DB→asset table exists yet for arbitrary basin ids, so an unmapped
basin raises ``UnknownProviderScope`` instead of silently reducing over the
wrong geometry.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

DEFAULT_ZONE_ASSET = "zona_cc_ampliada"
BASIN_ASSET_NAMES = frozenset({"candil", "ml", "noroeste", "norte"})
ZONAL_SCALE_METERS = 1000  # reduction scale used by the validation spike


class UnknownProviderScope(ValueError):
    """No GEE asset is mapped to the requested provider scope."""


def asset_name_for(scope_kind: str, scope_id: str) -> str:
    """Resolve a rainfall scope to its GEE asset name."""
    if scope_kind == "zone":
        # The deployment is a single zone_cc asset today; zone ids in the DB
        # are zoning feature ids (geo_approved_zonings), not GEE asset names.
        return DEFAULT_ZONE_ASSET
    if scope_kind == "basin":
        if scope_id in BASIN_ASSET_NAMES:
            return scope_id
        raise UnknownProviderScope(
            f"no GEE asset mapped for basin scope {scope_id!r}; "
            f"known basin assets: {sorted(BASIN_ASSET_NAMES)}"
        )
    raise UnknownProviderScope(f"unsupported provider scope kind: {scope_kind!r}")


class GeeZonalClient:
    """Thin wrapper over the ee primitives the rainfall adapters need."""

    def __init__(
        self,
        *,
        asset_path: Callable[[str], str] | None = None,
        ensure_initialized: Callable[[], None] | None = None,
        scale_meters: int = ZONAL_SCALE_METERS,
    ) -> None:
        self.scale_meters = scale_meters
        self._asset_path = asset_path if asset_path is not None else self._default_asset_path
        self._ensure_initialized = (
            ensure_initialized if ensure_initialized is not None else self._default_ensure
        )

    @staticmethod
    def _default_asset_path(asset_name: str) -> str:
        from app.config import settings

        return f"projects/{settings.gee_project_id}/assets/{asset_name}"

    @staticmethod
    def _default_ensure() -> None:
        from app.domains.geo.gee_service import _ensure_initialized

        _ensure_initialized()

    def geometry(self, *, scope_kind: str, scope_id: str) -> Any:
        """Return the ee geometry for the scope's mapped asset."""
        self._ensure_initialized()
        import ee  # local import keeps adapter imports ee-free for tests

        asset = self._asset_path(asset_name_for(scope_kind, scope_id))
        return ee.FeatureCollection(asset).geometry()

    def zonal_series(
        self,
        *,
        collection_id: str,
        start: datetime,
        end: datetime,
        geometry: Any,
        band: str,
    ) -> list[tuple[datetime, float | None]]:
        """Return per-image mean zonal values as ``(interval_start, value)``.

        ``interval_start`` is the image's ``system:time_start`` (UTC). The
        reducer matches the validation spike: ``mean`` over the scope geometry
        at the client's scale with ``bestEffort=True``.
        """
        self._ensure_initialized()
        import ee

        series = (
            ee.ImageCollection(collection_id)
            .filterDate(start, end)
            .map(
                lambda image: ee.Feature(
                    None,
                    {
                        "t": image.date().millis(),
                        "v": image.reduceRegion(
                            reducer=ee.Reducer.mean(),
                            geometry=geometry,
                            scale=self.scale_meters,
                            bestEffort=True,
                        ).get(band),
                    },
                )
            )
        )
        features = series.getInfo().get("features", [])
        rows: list[tuple[datetime, float | None]] = []
        for feature in features:
            props = feature.get("properties") or {}
            raw_start = props.get("t")
            if not isinstance(raw_start, (int, float)):
                continue  # timestamp-less rows cannot anchor an interval
            value = props.get("v")
            rows.append(
                (
                    datetime.fromtimestamp(raw_start / 1000.0, tz=UTC),
                    None if value is None else float(value),
                )
            )
        rows.sort(key=lambda pair: pair[0])
        return rows
