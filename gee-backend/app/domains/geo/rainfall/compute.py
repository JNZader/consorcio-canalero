"""Pure Rainfall v2 materialization logic: no Session, no network.

Boundary rule (design.md "Technical Approach"): adapters own providers,
``compute.py`` is pure, ``repository.py`` owns SQL, ``tasks.py`` only
orchestrates and owns the Session. Every function in this module is a plain
transformation over its inputs and is safe to unit-test without a database.
"""

from __future__ import annotations

_CORRECTION_SEPARATOR = "+r"


def revision_family(provider_revision: str) -> str:
    """Strip a correction suffix, returning the provider-revision family.

    ``"v3-nrt+r2"`` -> ``"v3-nrt"``; a bare family revision (no adapter has
    ever emitted a correction for it) maps to itself. ``"+r"`` is reserved as
    the correction separator (design.md "NRT Correction Supersession");
    adapters MUST NOT emit ``+`` in a ``provider_revision``.
    """
    return provider_revision.split(_CORRECTION_SEPARATOR, 1)[0]


def correction_revision(family: str, ordinal: int) -> str:
    """Build the n-th correction's ``provider_revision`` string for *family*.

    ``("v3-nrt", 2)`` -> ``"v3-nrt+r2"``. The ordinal is 1 for a slot's first
    correction, chained off the current row's own ordinal for later ones
    (design.md "NRT Correction Supersession" step 2, "changed" branch).
    """
    if ordinal < 1:
        raise ValueError(f"correction ordinal must be >= 1, got {ordinal}")
    return f"{family}{_CORRECTION_SEPARATOR}{ordinal}"
