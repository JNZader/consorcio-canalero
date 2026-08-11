"""Reciprocal Rank Fusion — the ONLY place the two legs meet (design.md D4).

Pure, zero DB, and deliberately typed to take **rankings** rather than scores:
`ts_rank_cd` and cosine distance are not commensurable, and any function that
accepted both numbers would be one refactor away from averaging them. No blended
or weighted single score exists anywhere in this codebase, and this signature is
what makes that a structural fact instead of a convention.

Two sort rules together carry the determinism claim (design.md D6), and either
one alone leaves a reproducibility hole:

* each leg query sorts by `citation_key` as its secondary key (repository.py);
* fusion sorts by `(-score, citation_key)` here.

The corpus is why: 45 articles of the Anexo of Res. 4/2026 have the words "Sin
Reglamentar" as their entire body (`MANIFEST.md:658-660`), plus their
counterparts in Decreto 318/2007. They collide on `ts_rank_cd` and sit within
floating-point noise of each other on cosine distance, so an arbitrary tie order
at the `LIMIT 50` boundary decides which of them enters fusion at all — flipping
fused ranks, and therefore gold outcomes, between runs over identical data.
"""

from __future__ import annotations

from typing import Sequence

#: The rag-advanced default, and the constant the eval report pins. It is not a
#: tuning knob in V0: changing it changes every mode's fused-score grid, which
#: is what the abstention thresholds are calibrated over (design.md D5).
RRF_K = 60


def reciprocal_rank_fusion(
    listas: Sequence[Sequence[str]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Fuse per-leg rankings into one, `1/(k + rank + 1)` summed across legs.

    `listas` is one ranked list of citation keys per leg, best first. Ranks are
    0-based, so the top of a leg contributes `1/(k+1)`.

    A key absent from a leg contributes **nothing** from that leg. That is not
    the same as imputing a zero score and then averaging: an empty leg produces
    exactly the fusion of the remaining legs, which is what the spec's "either
    sub-query can fail without corrupting fusion" requires. There is no
    imputation, no normalisation and no blending anywhere in this function.

    A key repeated inside one leg counts once, at its best (first) rank. That is
    unreachable from the real legs — `citation_key` is half the primary key — but
    double-counting would be a silent scoring error rather than a loud one, and
    this module is a mutation-testing target that has to specify its own edges.

    Returns `[(citation_key, score)]` sorted by descending score, ties broken by
    `citation_key` ascending.
    """
    scores: dict[str, float] = {}
    for lista in listas:
        vistos: set[str] = set()
        for rank, citation_key in enumerate(lista):
            if citation_key in vistos:
                continue
            vistos.add(citation_key)
            scores[citation_key] = scores.get(citation_key, 0.0) + 1.0 / (k + rank + 1)

    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
