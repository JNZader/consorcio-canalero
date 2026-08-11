"""Retrieval metrics — pure set comparisons against gold citation keys (D6).

No LLM-as-judge in V0. That is not a cost decision: a judge model would have to
be shown the retrieved legal text to score it, which re-opens the privacy
boundary the whole design closes by construction, and it would make the harness
non-deterministic (retrieval has no sampling; a judge does). Every function here
is pure, total, and takes only citation keys plus the two provenance flags that
the spec requires every hit to carry.

**Definitions, fixed here so the report cannot be argued with later.** The
retrieval spec fixes the BARS (hit-rate@5 >= 0.85, MRR >= 0.70,
citation-precision = 1.00, norma-vs-secundaria separation = 1.00,
vigencia-correctness = 1.00) and never defines the metrics. A bar without a
definition is not a gate, so:

| metric | definition | why not the obvious alternative |
|---|---|---|
| hit-rate@5 | 1 if any expected key is among the first 5 fused hits | — |
| MRR | `1/(rank+1)` of the FIRST expected key in the returned page, 0 if absent | averaging over all expected keys turns a complete composite answer into a worse score than a partial one |
| citation-precision | **R-precision**: precision at rank `|gold|` — `\\|top_m ∩ gold\\| / m` with `m = \\|gold\\|`; `None` for an item the running mode cannot reach by construction | any fixed window >= m makes "= 1.00" unreachable for a 1-key question on a 10-hit page, i.e. a decorative bar. At rank `m`, precision and recall coincide, so one number carries both "did it bring them all" and "did it bring junk". The `None` case is the over-ceiling exemption — see `citation_precision` |
| norma-vs-secundaria | 1 unless the top hit is `es_secundaria`, or any hit lacks an explicit flag; `None` when the page is empty | the gold set's own rule: citing the informe instead of the article is a failure even when the content is right. Scoring an empty page 1.0 would let a mode that retrieved nothing at all clear a hard `== 1.00` bar |
| vigencia-correctness | over trap questions only: every caveat-bearing key retrieved AND every norma hit carrying a vigencia state | scoring it over all questions would inflate the mean with free points from questions that never claimed the property |

**Scope.** The five are computed over `respondibles` (every item whose `clase` is
not `unanswerable`). The spec scopes MRR that way explicitly and the reason
generalises: an unanswerable question has `|gold| = 0`, so each of these is a
division by zero wearing a score's clothes. Unanswerable items are measured by
the abstention pair instead (`abstention.py`), which is the metric that was
designed for them.

An aggregate over an empty denominator is `None`, never `0.0`. Zero is a
measurement — "we tried and got nothing right" — and `None` is the absence of
one; a report that prints `0.00` for a metric nobody could compute is lying in
the direction that looks rigorous.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

#: The spec's `hit-rate@5`. Named rather than inlined because the report prints
#: the k it used, and a report whose label and computation can drift apart is
#: the failure this module exists to prevent.
HIT_RATE_K = 5

#: Items with this `clase` have no expected citation and are scored by the
#: abstention pair, never by the retrieval metrics.
CLASE_SIN_RESPUESTA = "unanswerable"


@dataclass(frozen=True)
class HitEvaluado:
    """One returned hit, reduced to exactly what the metrics may look at.

    Deliberately NOT the full `CitaRecuperada`: the verbatim `texto` has no
    business in a scoring function, and a metric that could read it would be one
    refactor away from string-matching a legal answer.

    `es_secundaria` is typed optional so that "the flag never arrived" stays
    distinguishable from "the flag says False". They are different failures and
    only one of them is a retrieval result.
    """

    citation_key: str
    es_secundaria: bool | None
    estado_vigencia: str | None


@dataclass(frozen=True)
class PreguntaEvaluada:
    """One gold question plus what the run returned for it, in fused order."""

    id: str
    clase: str
    citas_esperadas: tuple[str, ...]
    #: The subset of `citas_esperadas` that carries the vigencia caveat — the
    #: unit whose absence turns a byte-exact citation into a wrong answer (the
    #: `10679#vigencia-de-los-fondos` case). Empty for every question that is not
    #: a vigencia trap.
    citas_vigencia: tuple[str, ...]
    hits: tuple[HitEvaluado, ...]
    #: True when EVERY expected citation of this item is a unit the running mode
    #: cannot reach BY CONSTRUCTION rather than by ranking badly — today, the
    #: over-the-8192-token units of a single-leg `vector` run, which have no
    #: vector at all and are FTS-only by design. Set by the harness, which is the
    #: only layer that knows both the mode and the snapshot; this module stays
    #: mode-agnostic and simply honours the flag.
    precision_no_evaluable: bool = False

    @property
    def es_respondible(self) -> bool:
        return self.clase != CLASE_SIN_RESPUESTA

    @property
    def claves(self) -> tuple[str, ...]:
        return tuple(hit.citation_key for hit in self.hits)


@dataclass(frozen=True)
class MetricasRecuperacion:
    """Aggregate over the answerable subset. `None` means "no denominator"."""

    n_respondibles: int
    hit_rate_at_5: float | None
    mrr: float | None
    citation_precision: float | None
    separacion_norma_secundaria: float | None
    vigencia_correctness: float | None
    n_vigencia: int
    #: How many answerable questions actually returned a page, i.e. the
    #: denominator `separacion_norma_secundaria` was averaged over. Printed for
    #: the same reason `n_vigencia` is: a mean over 3 of 29 questions and a mean
    #: over 29 are different claims and must not look alike.
    n_separacion: int = 0
    #: The denominator `citation_precision` was averaged over — smaller than
    #: `n_respondibles` exactly when the mode cannot reach some item's citations
    #: by construction (the over-ceiling exemption of a single-leg `vector` run).
    n_citation_precision: int = 0
    k_hit_rate: int = HIT_RATE_K


def hit_rate_at_k(pregunta: PreguntaEvaluada, k: int = HIT_RATE_K) -> float:
    """1.0 when any expected key is inside the first `k` fused hits."""
    esperadas = set(pregunta.citas_esperadas)
    return 1.0 if esperadas.intersection(pregunta.claves[:k]) else 0.0


def reciprocal_rank(pregunta: PreguntaEvaluada) -> float:
    """`1/(rank+1)` of the first expected key in the returned page, else 0.0.

    Ranks are 0-based, matching `fusion.reciprocal_rank_fusion`, so a gold key at
    the top scores 1.0.
    """
    esperadas = set(pregunta.citas_esperadas)
    for rango, citation_key in enumerate(pregunta.claves):
        if citation_key in esperadas:
            return 1.0 / (rango + 1)
    return 0.0


def citation_precision(pregunta: PreguntaEvaluada) -> float | None:
    """R-precision: precision at rank `|gold|`. `None` when the mode cannot reach it.

    For a one-citation question this is "is the top hit the right one". For C-2
    (`9750#11` AND `9750#22`, where the corpus offers two removal procedures with
    different majorities and answering with one of them is wrong even though the
    citation is real) it is "are both of them the answer, and nothing else".

    **`precision_no_evaluable` leaves the denominator**, the same rule
    `separacion_norma_secundaria` and `vigencia_correctness` already follow. The
    case is gold D-8, whose single expected citation `8560#5` is one of the three
    units over the 8192-token embedding ceiling: by ratified design it is
    ingested whole, stays FTS-retrievable and is never embedded. A single-leg
    `vector` run therefore CANNOT return it — not because the ranking is bad but
    because the vector leg has nothing to rank — and this metric feeds a hard
    `== 1.00` bar. Scoring the item 0.0 would put a permanent, unreachable floor
    under the vector arm of the ablation and make its citation-precision bar
    unfalsifiable in the failing direction, which is the mirror image of the
    RAG4-004 defect (a bar passed BY failing). `hybrid` and `fts` are unaffected:
    the lexical leg reaches the unit, so there the score is a real measurement.
    """
    if pregunta.precision_no_evaluable:
        return None
    esperadas = set(pregunta.citas_esperadas)
    if not esperadas:
        return 0.0
    m = len(esperadas)
    return len(esperadas.intersection(pregunta.claves[:m])) / m


def separacion_norma_secundaria(pregunta: PreguntaEvaluada) -> float | None:
    """1.0 unless a secundaria hit leads the page. `None` when nothing came back.

    Two halves, both load-bearing:

    * every returned hit must carry an explicit `es_secundaria` boolean — the
      structural half, which is 1.00 by construction today and is here as a
      regression guard on the hydration join;
    * the top hit must not be `es_secundaria`. The gold set's own note 2 states
      the rule: *"Si una respuesta cita el informe en lugar del artículo, cuenta
      como fallo aunque el contenido sea correcto"*. Every answerable gold item
      cites norms only, so a secundaria at rank 0 is a commentary presented as
      grounds.

    **A question that returned NO hits scores `None`, not 1.0** — the same
    denominator rule `vigencia_correctness` already follows, and it was the one
    metric in this module that broke it. "The top hit was not a secondary source"
    is vacuously true of a page with no top hit, so a total retrieval failure
    used to score PERFECTLY here, and this metric feeds a hard `== 1.00` bar. A
    mode whose legs came back empty for every question would have cleared it
    unanimously — a bar passed BY failing, which is the exact shape of an
    unfalsifiable gate. Absence is not a measurement; it stays out of the
    denominator and shows up in `n_separacion`.
    """
    if not pregunta.hits:
        return None
    if any(hit.es_secundaria is None for hit in pregunta.hits):
        return 0.0
    if pregunta.hits[0].es_secundaria:
        return 0.0
    return 1.0


def vigencia_correctness(pregunta: PreguntaEvaluada) -> float | None:
    """Over vigencia traps only: `None` when the question declares no caveat key.

    A trap is answered correctly when BOTH hold: every caveat-bearing expected
    key is in the returned page (the article alone is the historic text — Ley
    10679's art. 17 says "hasta el 31 de diciembre de 2023" and the truth is
    2032), and every norma hit carries a vigencia state, so a derogated article
    cannot come back looking live.
    """
    if not pregunta.citas_vigencia:
        return None
    devueltas = set(pregunta.claves)
    if not set(pregunta.citas_vigencia).issubset(devueltas):
        return 0.0
    for hit in pregunta.hits:
        if hit.es_secundaria is False and hit.estado_vigencia is None:
            return 0.0
    return 1.0


def _media(valores: Sequence[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


def metricas_recuperacion(
    preguntas: Sequence[PreguntaEvaluada],
    k: int = HIT_RATE_K,
) -> MetricasRecuperacion:
    """Aggregate the five metrics over the answerable subset."""
    respondibles = [pregunta for pregunta in preguntas if pregunta.es_respondible]
    vigencias = [
        valor
        for valor in (vigencia_correctness(pregunta) for pregunta in respondibles)
        if valor is not None
    ]
    separaciones = [
        valor
        for valor in (separacion_norma_secundaria(pregunta) for pregunta in respondibles)
        if valor is not None
    ]
    precisiones = [
        valor
        for valor in (citation_precision(pregunta) for pregunta in respondibles)
        if valor is not None
    ]
    return MetricasRecuperacion(
        n_respondibles=len(respondibles),
        hit_rate_at_5=_media([hit_rate_at_k(pregunta, k) for pregunta in respondibles]),
        mrr=_media([reciprocal_rank(pregunta) for pregunta in respondibles]),
        citation_precision=_media(precisiones),
        separacion_norma_secundaria=_media(separaciones),
        vigencia_correctness=_media(vigencias),
        n_vigencia=len(vigencias),
        n_separacion=len(separaciones),
        n_citation_precision=len(precisiones),
        k_hit_rate=k,
    )
