"""Parcel contract preflight — Python-side, pre-browser (RMEH-009-A/013-A)."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.rainfall_e2e_harness.safety import BootstrapPrerequisiteFailure


@dataclass(frozen=True)
class ParcelContract:
    alias: str
    stable_uuid: str
    nomenclature: str
    display_identity: str
    scope_kind: str
    scope_id: str
    scope_version: str
    effective_cache_key: str
    percentile: float
    accumulation_mm: float
    analysis_revision_id: str
    data_revision: str
    metric_revision: str
    ready: bool


@dataclass(frozen=True)
class Preflight:
    ok: bool
    aliases: tuple[str, ...]


_PARCEL_DISTINCT_FIELDS = (
    "stable_uuid",
    "nomenclature",
    "display_identity",
    "scope_id",
    "scope_version",
    "effective_cache_key",
    "percentile",
    "accumulation_mm",
    "analysis_revision_id",
    "data_revision",
    "metric_revision",
)


def preflight_parcel_contracts(contracts: list[ParcelContract]) -> Preflight:
    """Validate exactly three A/B/C parcels, ready and pairwise distinct. Aborts
    BEFORE the browser with diagnostics naming the failing contract and observed
    values. The TS browser helper has its own pure validator for the browser
    journey contract surface."""
    if len(contracts) != 3:
        raise BootstrapPrerequisiteFailure(
            f"cardinality: expected exactly 3 parcels, observed {len(contracts)}"
        )
    aliases = [c.alias for c in contracts]
    if sorted(aliases) != ["A", "B", "C"] or len(set(aliases)) != 3:
        raise BootstrapPrerequisiteFailure(
            f"alias: expected one each A/B/C, observed {sorted(aliases)}"
        )
    for contract in contracts:
        if not contract.ready:
            raise BootstrapPrerequisiteFailure(
                f"ready: parcel {contract.alias} is not rainfall-ready"
            )
        if contract.scope_kind not in ("zone", "basin"):
            raise BootstrapPrerequisiteFailure(
                f"scope_kind: parcel {contract.alias} has unsupported "
                f"scope_kind {contract.scope_kind!r}"
            )
    for field_name in _PARCEL_DISTINCT_FIELDS:
        values = [getattr(c, field_name) for c in contracts]
        if len(set(values)) != 3:
            raise BootstrapPrerequisiteFailure(
                f"{field_name}: not pairwise distinct across A/B/C, observed {values!r}"
            )
    return Preflight(ok=True, aliases=("A", "B", "C"))
