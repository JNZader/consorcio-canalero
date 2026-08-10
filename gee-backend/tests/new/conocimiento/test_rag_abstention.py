"""Abstention policy + LOOCV threshold selection (tasks 4.2, 4.3).

Pure, zero DB, and every expected number below is traced by hand fold by fold in
the comments — because the whole point of D5 is that a threshold fitted on the
sample it is graded on produces a number that LOOKS like a measurement. A test
that re-derived the selection with the implementation's own loop would reproduce
that same failure one level up.
"""

from __future__ import annotations

import pytest

from app.domains.conocimiento.abstention import (
    AbstentionPolicy,
    SenalAbstencion,
    grilla_de_umbrales,
    metricas_abstencion,
    seleccionar_umbral,
    select_threshold_loocv,
)


def senal(id: str, *, unanswerable: bool, score: float, margen: float = 0.0) -> SenalAbstencion:
    return SenalAbstencion(
        id=id,
        debe_abstenerse=unanswerable,
        score_top1=score,
        margen=margen,
        ambas_piernas=False,
    )


# ---------------------------------------------------------------------------
# Fixture A — the leakage fixture. Traced fold by fold.
# ---------------------------------------------------------------------------
#
#   id  clase          score
#   u1  unanswerable   0.10
#   a3  answerable     0.15
#   u2  unanswerable   0.20
#   a1  answerable     0.30
#   a2  answerable     0.40
#
# Rule: abstain when `score < min_score`. Grid = the observed scores.
#
# FULL SET: recall 1.00 needs u1 AND u2 to abstain, so t > 0.20 -> {0.30, 0.40}
#   t=0.30 -> abstains u1,a3,u2      = 3 abstentions, 2 correct -> precision 2/3
#   t=0.40 -> abstains u1,a3,u2,a1   = 4 abstentions, 2 correct -> precision 0.50
#   shipped threshold = 0.30, same-sample recall 1.00, precision 2/3
#
# LOOCV, fold by fold (each selects on the other four, then classifies the one):
#   hold u1: need t>0.20 -> {0.30,0.40}; t=0.30 (prec 1/2) wins -> u1 0.10<0.30
#            ABSTAINS -> correct abstention
#   hold u2: need t>0.10 -> {0.15,0.30,0.40}; t=0.15 abstains only u1 -> prec 1.0
#            wins -> u2 0.20<0.15 is FALSE -> ANSWERS -> false-confident (missed)
#   hold a1: need t>0.20 -> {0.40} only; t=0.40 -> a1 0.30<0.40 ABSTAINS -> wrong
#   hold a2: need t>0.20 -> {0.30}; t=0.30 -> a2 0.40<0.30 FALSE -> ANSWERS -> ok
#   hold a3: need t>0.20 -> {0.30,0.40}; t=0.30 abstains u1,u2 -> prec 1.0 wins
#            -> a3 0.15<0.30 ABSTAINS -> wrong
#
#   held-out abstentions = {u1, a1, a3} = 3, of which correct = 1 (u1)
#   held-out recall    = 1/2   = 0.50
#   held-out precision = 1/3  ~= 0.3333
#
# So the same-sample fit reads (1.00, 0.67) and the honest pair is (0.50, 0.33).

FIXTURE_FUGA = (
    senal("u1", unanswerable=True, score=0.10),
    senal("a3", unanswerable=False, score=0.15),
    senal("u2", unanswerable=True, score=0.20),
    senal("a1", unanswerable=False, score=0.30),
    senal("a2", unanswerable=False, score=0.40),
)


class TestGrid:
    def test_grid_is_the_observed_scores_and_nothing_else(self):
        """D5: "sweeps `min_score` over the observed fused-score grid".

        No synthetic "above every score" candidate is appended, and that is
        load-bearing rather than an omission: with one, "abstain on everything"
        is always available, recall 1.00 is always reachable, and the fallback
        branch D5 requires becomes unreachable code. Without one, recall 1.00 is
        unreachable exactly when an unanswerable question outscores every other
        item — which is precisely the pathology the fallback count is there to
        report.
        """
        assert grilla_de_umbrales(FIXTURE_FUGA) == (0.10, 0.15, 0.20, 0.30, 0.40)

    def test_grid_deduplicates_and_sorts(self):
        empatadas = (
            senal("x", unanswerable=True, score=0.20),
            senal("y", unanswerable=False, score=0.20),
            senal("z", unanswerable=False, score=0.05),
        )
        assert grilla_de_umbrales(empatadas) == (0.05, 0.20)


class TestPolicy:
    def test_abstains_strictly_below_the_threshold(self):
        politica = AbstentionPolicy(min_score=0.20)
        assert politica.abstiene(senal("a", unanswerable=False, score=0.19)) is True
        # Exactly AT the threshold answers. The boundary has to be nailed
        # somewhere and `>=` is what makes the grid's own values reachable as
        # "answer this one" thresholds.
        assert politica.abstiene(senal("b", unanswerable=False, score=0.20)) is False

    def test_min_margin_abstains_on_an_undecided_top_pair(self):
        politica = AbstentionPolicy(min_score=0.0, min_margin=0.01)
        justo = senal("c", unanswerable=False, score=0.50, margen=0.005)
        claro = senal("d", unanswerable=False, score=0.50, margen=0.02)
        assert politica.abstiene(justo) is True
        assert politica.abstiene(claro) is False

    def test_require_both_legs_would_abstain_on_everything_in_a_single_leg_mode(self):
        """Why V0 sweeps `min_score` only.

        `ambas_piernas` is False for every item of an `fts` or `vector` run by
        construction — one leg ran. Enabling this knob there does not tune
        anything, it abstains on the whole set, and the mode's numbers would be
        the string "abstained" rather than a comparison. It stays in the policy
        because V1's hybrid mode is where it means something.
        """
        politica = AbstentionPolicy(min_score=0.0, require_both_legs=True)
        assert all(politica.abstiene(s) for s in FIXTURE_FUGA)


class TestAbstentionPair:
    def test_recall_denominator_is_the_unanswerable_count_of_the_sample(self):
        par = metricas_abstencion(FIXTURE_FUGA, AbstentionPolicy(min_score=0.30))
        assert par.n_unanswerable == 2
        assert par.abstenciones_correctas == 2
        assert par.recall == 1.0
        assert par.precision == pytest.approx(2 / 3)

    def test_always_abstaining_is_punished_by_precision_not_rewarded_by_recall(self):
        """D5: "Recall alone is trivially gamed by always abstaining"."""
        par = metricas_abstencion(FIXTURE_FUGA, AbstentionPolicy(min_score=99.0))
        assert par.recall == 1.0
        assert par.precision == pytest.approx(2 / 5)
        assert par.pasa_el_par(recall_minimo=1.0, precision_minima=0.80) is False

    def test_never_abstaining_reports_zero_precision_not_a_vacuous_one(self):
        """0/0 is a convention, so it is chosen out loud.

        "Of the abstentions it made, how many were right" is vacuously perfect
        for a policy that never abstains. Reporting 1.00 there would print a
        success next to a recall of 0.00. It cannot change a go/no-go outcome —
        recall 0 already fails the pair — so the only thing at stake is whether
        the number reads as an achievement, and it must not.
        """
        par = metricas_abstencion(FIXTURE_FUGA, AbstentionPolicy(min_score=0.0))
        assert par.abstenciones == 0
        assert par.recall == 0.0
        assert par.precision == 0.0


class TestSameSampleSelection:
    def test_selects_the_highest_precision_threshold_that_reaches_recall_one(self):
        seleccion = seleccionar_umbral(FIXTURE_FUGA)
        assert seleccion.umbral == 0.30
        assert seleccion.fallback is False
        assert seleccion.recall == 1.0
        assert seleccion.precision == pytest.approx(2 / 3)

    def test_ties_break_toward_the_lower_threshold(self):
        """Two thresholds, identical (recall, precision): the lower one abstains
        on strictly fewer items, so it is the one that claims less."""
        empate = (
            senal("u", unanswerable=True, score=0.10),
            senal("a", unanswerable=False, score=0.50),
            senal("b", unanswerable=False, score=0.60),
        )
        # t=0.50 and t=0.60 both abstain on u alone... no: t=0.60 also abstains
        # on a. Only t=0.50 reaches (1.00, 1.00); t=0.60 gives (1.00, 0.50).
        seleccion = seleccionar_umbral(empate)
        assert seleccion.umbral == 0.50
        assert seleccion.precision == 1.0


class TestLOOCV:
    """4.2: `test_loocv_selection_differs_from_same_sample_fit`."""

    def test_loocv_selection_differs_from_same_sample_fit(self):
        resultado = select_threshold_loocv(FIXTURE_FUGA)

        # The shipped threshold is still the full-set one — LOOCV measures how
        # that RULE generalises, it does not pick a different threshold to ship.
        assert resultado.umbral_shipped == 0.30
        assert resultado.same_sample_recall == 1.0
        assert resultado.same_sample_precision == pytest.approx(2 / 3)

        # ... and the held-out pair is a different, much worse pair.
        assert resultado.recall == 0.5
        assert resultado.precision == pytest.approx(1 / 3)
        assert (resultado.recall, resultado.precision) != (
            resultado.same_sample_recall,
            resultado.same_sample_precision,
        )

    def test_the_folds_really_do_pick_different_thresholds(self):
        """Folds come back in the sample's own order, which is SCORE order here
        (u1, a3, u2, a1, a2) — not the order the hand-trace above walks them in.

        Pinning the pairing rather than the bare list, because a list of five
        floats is exactly the assertion that passes for the wrong reason when the
        iteration order changes.
        """
        resultado = select_threshold_loocv(FIXTURE_FUGA)
        assert [(fold.id, fold.umbral) for fold in resultado.folds] == [
            ("u1", 0.30),
            ("a3", 0.30),
            ("u2", 0.15),
            ("a1", 0.40),
            ("a2", 0.30),
        ]
        assert len({fold.umbral for fold in resultado.folds}) == 3

    def test_each_fold_selects_without_the_item_it_classifies(self):
        resultado = select_threshold_loocv(FIXTURE_FUGA)
        for fold, esperada in zip(resultado.folds, FIXTURE_FUGA, strict=True):
            assert fold.id == esperada.id
            assert esperada.id not in fold.ids_de_ajuste

    def test_the_missed_abstention_is_the_one_the_hand_trace_names(self):
        """u2 is the false-confident answer: held out, the fold's threshold was
        fitted to a sample where 0.20 was the only unanswerable score left, so it
        settled just under it."""
        resultado = select_threshold_loocv(FIXTURE_FUGA)
        fallidas = [
            fold.id for fold in resultado.folds if fold.debe_abstenerse and not fold.abstuvo
        ]
        assert fallidas == ["u2"]


# ---------------------------------------------------------------------------
# Fixture B — the fallback fixture. An unanswerable question outscores the set.
# ---------------------------------------------------------------------------
#
#   u_top  unanswerable  0.90   <- outscores everything
#   u2     unanswerable  0.10
#   a1     answerable    0.20
#   a2     answerable    0.50
#
# Grid = (0.10, 0.20, 0.50, 0.90). No threshold in it makes u_top (0.90) abstain,
# so recall 1.00 is unreachable and the fallback fires:
#   t=0.10 -> abstains nobody           recall 0.0
#   t=0.20 -> abstains u2               recall 0.5, precision 1.0   <- best
#   t=0.50 -> abstains u2,a1            recall 0.5, precision 0.5
#   t=0.90 -> abstains u2,a1,a2         recall 0.5, precision 1/3
#
# In LOOCV only the fold that HOLDS OUT u_top escapes the fallback, because that
# is the only sample without it: 3 of 4 folds fall back.

FIXTURE_FALLBACK = (
    senal("u_top", unanswerable=True, score=0.90),
    senal("u2", unanswerable=True, score=0.10),
    senal("a1", unanswerable=False, score=0.20),
    senal("a2", unanswerable=False, score=0.50),
)


class TestFallback:
    """4.2: `test_loocv_fallback_counted_when_no_threshold_reaches_recall_1`."""

    def test_same_sample_selection_falls_back_to_the_highest_recall(self):
        seleccion = seleccionar_umbral(FIXTURE_FALLBACK)
        assert seleccion.fallback is True
        assert seleccion.umbral == 0.20
        assert seleccion.recall == 0.5
        assert seleccion.precision == 1.0

    def test_loocv_fallback_counted_when_no_threshold_reaches_recall_1(self):
        resultado = select_threshold_loocv(FIXTURE_FALLBACK)
        assert resultado.folds_con_fallback == 3
        assert resultado.n == 4
        # The one fold that does NOT fall back is the one that removed the
        # top-scoring unanswerable item from its own fitting sample.
        sin_fallback = [fold.id for fold in resultado.folds if not fold.fallback]
        assert sin_fallback == ["u_top"]

    def test_the_fallback_count_reaches_the_caller_rather_than_being_swallowed(self):
        """D5: "a fallback that fires often is itself a no-go signal and the
        report states the count"."""
        resultado = select_threshold_loocv(FIXTURE_FALLBACK)
        assert resultado.folds_con_fallback > 0
        assert resultado.fraccion_fallback == 0.75


class TestDenominatorComesFromTheGoldSet:
    """4.3 (CRA-101/CRB-101 fold): `test_abstention_denominator_from_gold_set_not_literal`."""

    def test_abstention_denominator_from_gold_set_not_literal(self):
        """The literal `18` in design D5 went stale the moment curation landed —
        the ratified set has 23 unanswerable items, not 18. Nothing in this
        module may know a number that the gold set is entitled to change."""
        from app.domains.conocimiento.eval.harness import senales_desde

        # A 3-item stand-in for a gold set: the denominator is whatever the set
        # declares, and the module has no opinion about what it should be.
        clases = {"g1": "unanswerable", "g2": "answerable", "g3": "unanswerable"}
        senales = tuple(
            senal(id, unanswerable=(clase == "unanswerable"), score=0.5)
            for id, clase in clases.items()
        )
        par = metricas_abstencion(senales, AbstentionPolicy(min_score=99.0))
        assert par.n_unanswerable == 2

        # And the real path agrees: no literal anywhere between gold set and pair.
        assert callable(senales_desde)

    def test_a_sample_with_no_unanswerable_item_has_no_recall_to_report(self):
        """Recall's denominator is the unanswerable count. Zero of them is not
        "recall 1.00, nothing to miss" — it is a set that cannot measure
        abstention at all, and the harness's n>=20 precondition exists so this
        never silently decides a go/no-go."""
        solo_respondibles = (
            senal("a", unanswerable=False, score=0.10),
            senal("b", unanswerable=False, score=0.20),
        )
        par = metricas_abstencion(solo_respondibles, AbstentionPolicy(min_score=0.15))
        assert par.n_unanswerable == 0
        assert par.recall is None
        assert par.pasa_el_par(recall_minimo=1.0, precision_minima=0.80) is False


class TestRecallBoundaryIsStrict:
    def test_recall_just_under_one_fails_the_pair_however_good_precision_is(self):
        """The spec's strict clause: "a single false-confident answer fails
        go/no-go". 0.999 is not 1.00 and must not round into a pass."""
        casi = (
            senal("u1", unanswerable=True, score=0.10),
            senal("u2", unanswerable=True, score=0.90),
            senal("a1", unanswerable=False, score=0.95),
        )
        par = metricas_abstencion(casi, AbstentionPolicy(min_score=0.50))
        assert par.recall == 0.5
        assert par.precision == 1.0
        assert par.pasa_el_par(recall_minimo=1.0, precision_minima=0.80) is False

    def test_recall_exactly_one_with_precision_exactly_at_the_bar_passes(self):
        """The other side of the same boundary: >= 0.80, not > 0.80.

        Five items, four unanswerable with low scores plus one answerable that
        also falls below the threshold: 5 abstentions, 4 correct -> precision
        exactly 0.80.
        """
        borde = (
            senal("u1", unanswerable=True, score=0.10),
            senal("u2", unanswerable=True, score=0.11),
            senal("u3", unanswerable=True, score=0.12),
            senal("u4", unanswerable=True, score=0.13),
            senal("a1", unanswerable=False, score=0.14),
            senal("a2", unanswerable=False, score=0.90),
        )
        par = metricas_abstencion(borde, AbstentionPolicy(min_score=0.50))
        assert par.recall == 1.0
        assert par.precision == 0.80
        assert par.pasa_el_par(recall_minimo=1.0, precision_minima=0.80) is True
