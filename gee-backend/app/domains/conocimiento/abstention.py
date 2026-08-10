"""Abstention policy and leave-one-out threshold selection (design.md D5).

Pure, zero DB, deterministic, and a mutation-testing target: everything here is
arithmetic over precomputed signals, so a surviving mutant would mean the tests
are decorative.

**Why the selection is cross-validated at all.** Sweeping `min_score` on the
gold set and then reporting precision/recall on that same set fits the threshold
to the very items it is about to be graded on. The result is a training fit read
as a measurement — post-hoc overfit wearing the costume of rigour, and the
smaller the set the louder the lie. So the shipped threshold is still the
full-set one (that is the threshold a V1 would actually run), while the numbers
that decide go/no-go come from `select_threshold_loocv`, where each item is
classified by a threshold selected without it.

**The signals are precomputed on purpose.** A fold re-running retrieval would be
n queries per fold, and worse, it would let the fitting loop touch the database
— which is how "the threshold" and "the run it was fitted on" quietly stop being
separable. `harness.senales_desde` turns one retrieval run into one
`SenalAbstencion` per question, and every function here is then a pure function
of that tuple.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

#: The owner's ratified pair (retrieval spec, `Go/No-Go Thresholds`). Recall is
#: STRICT: a single false-confident answer — one unanswerable question that got
#: an answer — fails go/no-go regardless of every other metric.
RECALL_OBJETIVO = 1.0
PRECISION_MINIMA = 0.80


@dataclass(frozen=True)
class SenalAbstencion:
    """Everything the abstention decision for one question depends on.

    Deliberately no citation keys and no text: an abstention decision that could
    see the gold citations would be able to cheat, and this dataclass is the
    boundary that makes that impossible rather than merely discouraged.

    `debe_abstenerse` is the gold label (`clase == 'unanswerable'`), carried here
    only so the scoring functions can compare a decision against it — the policy
    itself never reads it.
    """

    id: str
    debe_abstenerse: bool
    #: Fused RRF score of the top hit. 0.0 when the run returned nothing at all,
    #: which is itself a below-any-threshold signal and therefore an abstention.
    score_top1: float
    #: `score_top1 - score_top2`, 0.0 when there is at most one hit.
    margen: float
    #: Did the top hit come from BOTH legs? False for every item of a
    #: single-leg mode, by construction.
    ambas_piernas: bool


@dataclass(frozen=True)
class AbstentionPolicy:
    """`min_score` + `min_margin` + `require_both_legs`, tunable by construction.

    V0 sweeps `min_score` only, and the other two stay at their neutral defaults
    for a stated reason rather than an oversight: `require_both_legs` is False
    for every item of an `fts` or `vector` run (one leg ran), so enabling it
    there does not tune anything — it abstains on the entire mode and replaces
    its numbers with the word "abstained". `min_margin` needs a second hit to
    mean anything and would interact with `k`; V1 can sweep both once there is a
    serving decision to make.
    """

    min_score: float
    min_margin: float = 0.0
    require_both_legs: bool = False

    def abstiene(self, senal: SenalAbstencion) -> bool:
        """Abstain when the top hit is not confident enough to be cited.

        Strictly below: a score exactly AT the threshold answers. The boundary
        has to be nailed down somewhere, and `>=` is what makes each value of the
        observed grid reachable as an "answer this one" threshold — with `>` the
        grid's own points would be unusable and the sweep would silently explore
        n-1 distinct behaviours instead of n.
        """
        if senal.score_top1 < self.min_score:
            return True
        if senal.margen < self.min_margin:
            return True
        if self.require_both_legs and not senal.ambas_piernas:
            return True
        return False


@dataclass(frozen=True)
class ParAbstencion:
    """The go/no-go pair for one policy over one sample.

    `recall` is `None` — not 0.0, and certainly not 1.0 — when the sample holds
    no unanswerable item. There is no denominator, so there is no measurement,
    and "recall 1.00, nothing to miss" is the single most flattering way to
    report having measured nothing.
    """

    n: int
    n_unanswerable: int
    abstenciones: int
    abstenciones_correctas: int

    @property
    def recall(self) -> float | None:
        if self.n_unanswerable == 0:
            return None
        return self.abstenciones_correctas / self.n_unanswerable

    @property
    def precision(self) -> float:
        """Correct abstentions over all abstentions; 0.0 when it never abstained.

        0/0 is a convention and this one is chosen out loud. The vacuous reading
        ("nothing it abstained on was wrong") would print 1.00 for a policy that
        abstains on nothing, right next to a recall of 0.00. It cannot change an
        outcome — recall 0 already fails the pair — so the only thing at stake is
        whether the number reads as an achievement, and it must not.
        """
        if self.abstenciones == 0:
            return 0.0
        return self.abstenciones_correctas / self.abstenciones

    def pasa_el_par(
        self,
        recall_minimo: float = RECALL_OBJETIVO,
        precision_minima: float = PRECISION_MINIMA,
    ) -> bool:
        """BOTH terms, or neither. Recall alone is gamed by always abstaining."""
        recall = self.recall
        if recall is None:
            return False
        return recall >= recall_minimo and self.precision >= precision_minima


@dataclass(frozen=True)
class SeleccionUmbral:
    """One threshold selection over one sample, with how it was reached."""

    umbral: float
    recall: float | None
    precision: float
    #: True when NO threshold on the grid reached recall 1.00 and the selection
    #: fell back to the highest-recall candidate. Counted, never swallowed: a
    #: fallback that fires often is itself a no-go signal (D5).
    fallback: bool
    n: int


@dataclass(frozen=True)
class Fold:
    """One leave-one-out fold: fitted on n-1, used to classify the held-out one."""

    id: str
    debe_abstenerse: bool
    abstuvo: bool
    umbral: float
    fallback: bool
    ids_de_ajuste: tuple[str, ...]


@dataclass(frozen=True)
class ResultadoLOOCV:
    """Held-out pair, the shipped threshold, and the same-sample upper bound.

    The two pairs are reported side by side on purpose. `recall`/`precision` are
    the held-out figures and are the ONLY ones that may decide go/no-go;
    `same_sample_*` are useful as a ceiling and are labelled
    `upper bound (fit on the scoring sample)` wherever they appear.
    """

    n: int
    umbral_shipped: float
    folds: tuple[Fold, ...]
    par: ParAbstencion
    same_sample: ParAbstencion
    seleccion_shipped: SeleccionUmbral

    @property
    def recall(self) -> float | None:
        return self.par.recall

    @property
    def precision(self) -> float:
        return self.par.precision

    @property
    def same_sample_recall(self) -> float | None:
        return self.same_sample.recall

    @property
    def same_sample_precision(self) -> float:
        return self.same_sample.precision

    @property
    def folds_con_fallback(self) -> int:
        return sum(1 for fold in self.folds if fold.fallback)

    @property
    def fraccion_fallback(self) -> float:
        return self.folds_con_fallback / self.n if self.n else 0.0

    def pasa_el_par(
        self,
        recall_minimo: float = RECALL_OBJETIVO,
        precision_minima: float = PRECISION_MINIMA,
    ) -> bool:
        return self.par.pasa_el_par(recall_minimo, precision_minima)


def grilla_de_umbrales(senales: Sequence[SenalAbstencion]) -> tuple[float, ...]:
    """The observed fused-score grid: sorted, deduplicated, and nothing added.

    No synthetic candidate above the maximum is appended, and that omission is
    the design. With one, "abstain on everything" is always available, recall
    1.00 is therefore always reachable, and D5's fallback branch becomes
    unreachable code that the report would nonetheless claim to count. Without
    one, recall 1.00 is unreachable in exactly one situation — an unanswerable
    question outscoring every other item in the sample — which is the pathology
    the fallback count exists to surface.
    """
    return tuple(sorted({senal.score_top1 for senal in senales}))


def metricas_abstencion(
    senales: Sequence[SenalAbstencion],
    politica: AbstentionPolicy,
) -> ParAbstencion:
    """Score one policy over one sample. Pure counting, no selection."""
    abstenciones = 0
    correctas = 0
    for senal in senales:
        if politica.abstiene(senal):
            abstenciones += 1
            if senal.debe_abstenerse:
                correctas += 1
    return ParAbstencion(
        n=len(senales),
        n_unanswerable=sum(1 for senal in senales if senal.debe_abstenerse),
        abstenciones=abstenciones,
        abstenciones_correctas=correctas,
    )


def seleccionar_umbral(
    senales: Sequence[SenalAbstencion],
    recall_objetivo: float = RECALL_OBJETIVO,
) -> SeleccionUmbral:
    """Highest precision among thresholds reaching recall 1.00; ties by lower.

    Fallback when none reaches it: highest recall, then highest precision, then
    the lower threshold — and the selection says so, so the caller can count it.
    """
    grilla = grilla_de_umbrales(senales)
    if not grilla:
        return SeleccionUmbral(umbral=0.0, recall=None, precision=0.0, fallback=True, n=0)

    evaluadas = [
        (umbral, metricas_abstencion(senales, AbstentionPolicy(umbral))) for umbral in grilla
    ]
    alcanzan = [
        (umbral, par)
        for umbral, par in evaluadas
        if par.recall is not None and par.recall >= recall_objetivo
    ]

    if alcanzan:
        # Sort key: precision descending, then threshold ascending. Written as a
        # total order rather than a max() so ties can never depend on iteration
        # order — the grid is sorted, but relying on that is a silent coupling.
        umbral, par = min(alcanzan, key=lambda item: (-item[1].precision, item[0]))
        return SeleccionUmbral(
            umbral=umbral,
            recall=par.recall,
            precision=par.precision,
            fallback=False,
            n=len(senales),
        )

    umbral, par = min(
        evaluadas,
        key=lambda item: (-(item[1].recall or 0.0), -item[1].precision, item[0]),
    )
    return SeleccionUmbral(
        umbral=umbral,
        recall=par.recall,
        precision=par.precision,
        fallback=True,
        n=len(senales),
    )


def select_threshold_loocv(
    senales: Sequence[SenalAbstencion],
    recall_objetivo: float = RECALL_OBJETIVO,
) -> ResultadoLOOCV:
    """Leave-one-out: select on the other n-1, then classify the held-out item.

    At the ratified n = 52 this is 52 sweeps over a grid of at most 52 candidate
    scores — milliseconds, fully deterministic, no sampling. The reported pair is
    computed over the n held-out decisions, so no item was ever graded by a
    threshold that had seen it.
    """
    senales = tuple(senales)
    seleccion_shipped = seleccionar_umbral(senales, recall_objetivo)

    folds: list[Fold] = []
    abstenciones = 0
    correctas = 0
    for indice, senal in enumerate(senales):
        resto = senales[:indice] + senales[indice + 1 :]
        seleccion = seleccionar_umbral(resto, recall_objetivo)
        abstuvo = AbstentionPolicy(seleccion.umbral).abstiene(senal)
        if abstuvo:
            abstenciones += 1
            if senal.debe_abstenerse:
                correctas += 1
        folds.append(
            Fold(
                id=senal.id,
                debe_abstenerse=senal.debe_abstenerse,
                abstuvo=abstuvo,
                umbral=seleccion.umbral,
                fallback=seleccion.fallback,
                ids_de_ajuste=tuple(otra.id for otra in resto),
            )
        )

    par = ParAbstencion(
        n=len(senales),
        n_unanswerable=sum(1 for senal in senales if senal.debe_abstenerse),
        abstenciones=abstenciones,
        abstenciones_correctas=correctas,
    )
    return ResultadoLOOCV(
        n=len(senales),
        umbral_shipped=seleccion_shipped.umbral,
        folds=tuple(folds),
        par=par,
        same_sample=metricas_abstencion(senales, AbstentionPolicy(seleccion_shipped.umbral)),
        seleccion_shipped=seleccion_shipped,
    )
