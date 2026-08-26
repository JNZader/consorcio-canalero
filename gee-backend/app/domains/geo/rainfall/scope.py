"""Scope contract: only stable regional zone and basin computations execute."""

import unicodedata
from dataclasses import dataclass
from typing import Literal


def normalized_basin_name(cuenca: str) -> str:
    """``zonas_operativas.cuenca`` free text reduced to its basin-identity form.

    NFKD-decompose, drop combining marks, trim, case-fold. Deliberately NOT a
    slugifier: it must not invent a mapping by rewriting separators, because
    every rewrite it performs is a chance to land on a DIFFERENT watershed's
    asset name and reduce over the wrong geometry.

    This lives HERE, next to the scope contract, rather than inside the GEE
    adapter that used to own it, because both ends of the system must agree on
    what makes two rows the same watershed: ``repository.resolve_parcel_scopes``
    when it groups rows into a scope, and ``gee_client.asset_name_for`` when it
    maps that scope to an asset. Two copies of this rule -- or one copy and one
    raw comparison -- means the identity of a scope depends on which half is
    looking at it, which is exactly the defect this function's single home
    exists to prevent.
    """
    decomposed = unicodedata.normalize("NFKD", cuenca)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip().casefold()


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
