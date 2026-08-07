"""Scope contract: only stable regional zone and basin computations execute."""

from dataclasses import dataclass
from typing import Literal


class UnsupportedDirectScope(ValueError):
    """Raised when a parcel or arbitrary geometry is requested as a compute target."""


class AmbiguousScope(ValueError):
    """Raised until a parcel caller chooses one regional scope."""


class NoScopeMatch(ValueError):
    """Raised when a parcel does not intersect an approved regional scope."""


@dataclass(frozen=True, slots=True)
class ScopeRef:
    kind: Literal["zone", "basin", "parcel", "geometry"]
    id: str | None = None
    version: str | None = None
    nomenclature: str | None = None
    geometry: dict | None = None


@dataclass(frozen=True, slots=True)
class AnalysisScope:
    kind: Literal["zone", "basin"]
    id: str
    version: str
    regional_estimate: bool


def executable_scope(scope: ScopeRef) -> AnalysisScope:
    """Validate a direct regional scope without ever treating a parcel as measured."""
    if scope.kind not in {"zone", "basin"}:
        raise UnsupportedDirectScope(f"direct {scope.kind} computation is unavailable")
    if not scope.id or not scope.version:
        raise NoScopeMatch("stable scope id and version are required")
    return AnalysisScope(scope.kind, scope.id, scope.version, regional_estimate=False)


def resolve_parcel(
    parcel: ScopeRef,
    choices: tuple[AnalysisScope, ...],
    *,
    selected: AnalysisScope | None = None,
) -> AnalysisScope:
    """Return an explicit parcel-selected regional estimate, never a parcel metric."""
    if parcel.kind != "parcel" or not parcel.nomenclature:
        raise UnsupportedDirectScope("parcel resolution requires a parcel nomenclature")
    if not choices:
        raise NoScopeMatch("no approved zone or basin intersects this parcel")
    if selected is None:
        if len(choices) != 1:
            raise AmbiguousScope("select one resolved regional scope")
        selected = choices[0]
    elif selected not in choices:
        raise NoScopeMatch("selected regional scope is unavailable for this parcel")
    return AnalysisScope(selected.kind, selected.id, selected.version, regional_estimate=True)
