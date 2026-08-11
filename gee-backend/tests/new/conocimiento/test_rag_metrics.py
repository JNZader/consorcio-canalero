"""Retrieval metrics — pure set comparisons against gold citation keys (task 4.1).

Zero DB, zero LLM-as-judge, zero sampling: every number below is hand-computed
from a fixture small enough to check on paper, and the expected values are
written as decimal literals rather than re-derived from the function under test.
A metric test that recomputes the implementation's own formula proves only that
Python is deterministic.

The five metrics and their go/no-go bars come from the retrieval spec
(`Go/No-Go Thresholds and Gold-Set Precondition`): hit-rate@5 >= 0.85,
MRR >= 0.70, citation-precision = 1.00, norma-vs-secundaria separation = 1.00,
vigencia-correctness = 1.00. The spec fixes the BARS; the definitions live in
`metrics.py` and in design.md D6, because a bar without a definition is not a
gate.
"""

from __future__ import annotations

import pytest

from app.domains.conocimiento.eval.harness import BARRA_SEPARACION, Barra
from app.domains.conocimiento.eval.metrics import (
    HitEvaluado,
    PreguntaEvaluada,
    citation_precision,
    hit_rate_at_k,
    metricas_recuperacion,
    reciprocal_rank,
    separacion_norma_secundaria,
    vigencia_correctness,
)


def norma(citation_key: str, estado_vigencia: str | None = "vigente") -> HitEvaluado:
    return HitEvaluado(
        citation_key=citation_key,
        es_secundaria=False,
        estado_vigencia=estado_vigencia,
    )


def secundaria(citation_key: str) -> HitEvaluado:
    return HitEvaluado(citation_key=citation_key, es_secundaria=True, estado_vigencia=None)


def pregunta(
    id: str,
    esperadas: tuple[str, ...],
    claves_hits: tuple[str, ...],
    *,
    clase: str = "answerable",
    citas_vigencia: tuple[str, ...] = (),
    hits: tuple[HitEvaluado, ...] | None = None,
) -> PreguntaEvaluada:
    return PreguntaEvaluada(
        id=id,
        clase=clase,
        citas_esperadas=esperadas,
        citas_vigencia=citas_vigencia,
        hits=hits if hits is not None else tuple(norma(clave) for clave in claves_hits),
    )


# ---------------------------------------------------------------------------
# The hand-computed fixture. Four questions, every number checkable on paper.
# ---------------------------------------------------------------------------
#
#   Q1  gold {A}      hits [A, B, C]              hit@5 1   RR 1/1    R-prec 1/1 = 1.0
#   Q2  gold {A}      hits [B, C, A]              hit@5 1   RR 1/3    R-prec 0/1 = 0.0
#   Q3  gold {A,B}    hits [A, C, B, D]           hit@5 1   RR 1/1    R-prec 1/2 = 0.5
#   Q4  gold {Z}      hits [B, C, D, E, F, Z]     hit@5 0   RR 1/6    R-prec 0/1 = 0.0
#
#   hit-rate@5 = (1 + 1 + 1 + 0) / 4                     = 0.75
#   MRR        = (1 + 1/3 + 1 + 1/6) / 4 = 2.5 / 4       = 0.625
#   R-prec     = (1.0 + 0.0 + 0.5 + 0.0) / 4 = 1.5 / 4   = 0.375
#
# Q4's gold key sits at 0-based rank 5, i.e. OUTSIDE the top 5 and INSIDE the
# returned page: it is the case that separates hit-rate@5 from MRR.

Q1 = pregunta("Q1", ("A",), ("A", "B", "C"))
Q2 = pregunta("Q2", ("A",), ("B", "C", "A"))
Q3 = pregunta("Q3", ("A", "B"), ("A", "C", "B", "D"))
Q4 = pregunta("Q4", ("Z",), ("B", "C", "D", "E", "F", "Z"))

FIXTURE = (Q1, Q2, Q3, Q4)


class TestHitRateAndMRR:
    """4.1: `test_hit_rate_at_5_and_mrr`."""

    def test_hit_rate_at_5_is_binary_per_question(self):
        assert hit_rate_at_k(Q1, k=5) == 1.0
        assert hit_rate_at_k(Q2, k=5) == 1.0
        assert hit_rate_at_k(Q3, k=5) == 1.0
        # The gold key IS returned, at 0-based rank 5 — one position past the
        # window. hit-rate@5 must not credit it.
        assert hit_rate_at_k(Q4, k=5) == 0.0

    def test_hit_rate_window_is_the_k_it_is_given(self):
        assert hit_rate_at_k(Q4, k=6) == 1.0
        assert hit_rate_at_k(Q1, k=1) == 1.0
        assert hit_rate_at_k(Q2, k=1) == 0.0

    def test_reciprocal_rank_uses_the_first_gold_key(self):
        assert reciprocal_rank(Q1) == 1.0
        assert reciprocal_rank(Q2) == pytest.approx(1 / 3)
        # Q3's gold set is {A, B}; A is first, so the FIRST hit decides. A metric
        # that averaged over both gold keys would report 1/2 * (1 + 1/3) here.
        assert reciprocal_rank(Q3) == 1.0
        assert reciprocal_rank(Q4) == pytest.approx(1 / 6)

    def test_reciprocal_rank_is_zero_when_no_gold_key_was_returned(self):
        assert reciprocal_rank(pregunta("Q0", ("A",), ("B", "C"))) == 0.0

    def test_hand_computed_aggregates(self):
        agregado = metricas_recuperacion(FIXTURE)
        assert agregado.n_respondibles == 4
        # Exact: both are dyadic rationals and survive IEEE754 untouched.
        assert agregado.hit_rate_at_5 == 0.75
        assert agregado.citation_precision == 0.375
        # EXACT, and it did not use to be: `1 + 1/3 + 1 + 1/6` accumulated
        # left-to-right gives 2.4999999999999996, so the mean printed
        # 0.6249999999999999 — below the hand-computed 0.625, not noise around
        # it. `_media` sums with `math.fsum` (exact partial sums, rounded once),
        # so the aggregate now equals the value a person computes on paper.
        # `metricas_recuperacion` still does NOT round: rounding belongs to the
        # report, and a metric that rounds before comparison hides exactly the
        # drift the next test pins.
        assert agregado.mrr == 0.625

    def test_the_aggregate_is_bit_identical_across_runs_and_interpreters(self):
        """Determinism is a claim about the float, not about the rounded print.

        Builtin `sum` rounds at every step, so its result is a property of the
        summation ORDER — the gold set's file order — and of the interpreter's
        FP evaluation. `math.fsum` is exact-then-rounded-once, so this repr is
        the same on every build, which is what lets the number be pinned at all.
        Verified under CPython 3.11 (this venv) and 3.14 (the repo venv).

        A reordering of the gold set, or a refactor back to a step-rounding sum,
        shows up here as a failing test rather than as a report whose last digits
        moved for no stated reason.
        """
        primera = metricas_recuperacion(FIXTURE)
        segunda = metricas_recuperacion(FIXTURE)
        assert repr(primera.mrr) == repr(segunda.mrr) == "0.625"

    def test_fsum_is_what_makes_the_mean_order_independent(self):
        """The property, asserted directly rather than only through the fixture.

        Same four values, every permutation: one number, on every interpreter.

        The contrast against builtin `sum` is deliberately NOT asserted here,
        and the reason is the finding itself. Measured on this fixture:

            CPython 3.11.15   sum -> 0.6249999999999999   order-dependent
            CPython 3.14.6    sum -> 0.625                order-independent

        CPython 3.12 switched `sum()` to Neumaier compensated summation for
        floats, so an assertion that builtin `sum` disagrees with itself passes
        on 3.11 and fails on 3.14 — an interpreter-dependent test, which is the
        very class of defect being removed. `math.fsum` has been exact-then-
        rounded-once since long before either, so only its property is pinned.
        """
        import itertools

        from app.domains.conocimiento.eval.metrics import _media

        valores = [1.0, 1 / 3, 1.0, 1 / 6]
        medias = {_media(list(orden)) for orden in itertools.permutations(valores)}
        assert medias == {0.625}


class TestCitationPrecisionAndSeparation:
    """4.1: `test_citation_precision_norma_secundaria_vigencia_correctness`."""

    def test_citation_precision_is_r_precision(self):
        """Precision at the question's OWN gold size, not at `k`.

        Any fixed window >= |gold| makes "precision = 1.00" unreachable for a
        single-gold question the moment the page is longer than one hit, which
        would turn the spec's hard bar into a decorative one.
        """
        assert citation_precision(Q1) == 1.0
        assert citation_precision(Q2) == 0.0
        assert citation_precision(Q3) == 0.5
        assert citation_precision(Q4) == 0.0

    def test_citation_precision_rewards_the_complete_composite_answer(self):
        """C-2's failure mode: one of two required citations is not an answer."""
        ambas = pregunta("C2ok", ("9750#11", "9750#22"), ("9750#11", "9750#22", "9750#3"))
        una = pregunta("C2parcial", ("9750#11", "9750#22"), ("9750#11", "9750#3", "9750#22"))
        assert citation_precision(ambas) == 1.0
        assert citation_precision(una) == 0.5

    def test_separation_fails_when_a_secundaria_hit_is_the_answer(self):
        """The gold set's own rule: citing the informe instead of the article is
        a failure even when the content is right."""
        buena = pregunta(
            "S1",
            ("9750#3",),
            (),
            hits=(norma("9750#3"), secundaria("informe-f3#sec-3")),
        )
        mala = pregunta(
            "S2",
            ("9750#3",),
            (),
            hits=(secundaria("informe-f3#sec-3"), norma("9750#3")),
        )
        assert separacion_norma_secundaria(buena) == 1.0
        assert separacion_norma_secundaria(mala) == 0.0

    def test_separation_needs_every_hit_to_carry_an_explicit_flag(self):
        sin_flag = PreguntaEvaluada(
            id="S3",
            clase="answerable",
            citas_esperadas=("9750#3",),
            citas_vigencia=(),
            hits=(
                HitEvaluado(citation_key="9750#3", es_secundaria=None, estado_vigencia="vigente"),
            ),
        )
        assert separacion_norma_secundaria(sin_flag) == 0.0

    def test_citation_precision_is_none_when_the_mode_cannot_reach_the_citation(self):
        """The D-8 case: `8560#5` is over the 8192-token embedding ceiling.

        It is ingested whole and stays FTS-retrievable, and by ratified design it
        is never embedded — so a single-leg `vector` run has nothing to rank for
        it. Scoring 0.0 would put a permanent floor under the vector arm's hard
        `= 1.00` bar: the bar could then never be cleared no matter how good
        retrieval got, which is the RAG4-004 defect with the sign flipped.
        """
        exenta = PreguntaEvaluada(
            id="D-8",
            clase="answerable",
            citas_esperadas=("8560#5",),
            citas_vigencia=(),
            hits=(norma("8560#28"), norma("5589#207")),
            precision_no_evaluable=True,
        )
        alcanzable = PreguntaEvaluada(
            id="D-8-fts",
            clase="answerable",
            citas_esperadas=("8560#5",),
            citas_vigencia=(),
            hits=(norma("8560#28"), norma("5589#207")),
        )
        assert citation_precision(exenta) is None
        # The SAME question, same hits, in a mode that can reach the unit: a real
        # 0.0. The flag must not be a way to make a genuine miss disappear.
        assert citation_precision(alcanzable) == 0.0

    def test_an_exempt_item_leaves_the_precision_denominator_and_says_so(self):
        exenta = PreguntaEvaluada(
            id="D-8",
            clase="answerable",
            citas_esperadas=("8560#5",),
            citas_vigencia=(),
            hits=(norma("8560#28"),),
            precision_no_evaluable=True,
        )
        agregado = metricas_recuperacion((Q1, exenta))
        # Q1 alone: 1.0 / 1, not 1.0 / 2. And the shrunk denominator is visible.
        assert agregado.citation_precision == 1.0
        assert agregado.n_citation_precision == 1
        assert agregado.n_respondibles == 2

    def test_every_answerable_item_exempt_leaves_no_measurement_at_all(self):
        """`None`, never 1.00 — the bar must fail, not pass vacuously."""
        exenta = PreguntaEvaluada(
            id="D-8",
            clase="answerable",
            citas_esperadas=("8560#5",),
            citas_vigencia=(),
            hits=(),
            precision_no_evaluable=True,
        )
        agregado = metricas_recuperacion((exenta,))
        assert agregado.citation_precision is None
        assert agregado.n_citation_precision == 0
        barra = Barra("citation-precision", agregado.citation_precision, 1.0, "==", "answerable")
        assert barra.pasa is False

    def test_separation_is_none_when_nothing_was_retrieved(self):
        """The one metric that used to award PERFECTION to total failure.

        "The top hit was not a secondary source" is vacuously true of a page with
        no top hit, so an empty result scored 1.0 — into a hard `== 1.00` bar. A
        mode whose legs came back empty on every question cleared that bar
        unanimously: a gate passed BY failing, which is a gate that cannot be
        falsified. Absence leaves the denominator, exactly as
        `vigencia_correctness` already did for a question that declares no caveat.
        """
        vacia = pregunta("S4", ("9750#3",), ())
        assert vacia.hits == ()
        assert separacion_norma_secundaria(vacia) is None

    def test_an_all_empty_run_cannot_clear_the_separation_bar(self):
        """The aggregate half of the same defect, and the reason it was CRITICAL.

        Three answerable questions, every one of them retrieving nothing. Before
        the fix the mean was 1.00 and `norma-vs-secundaria` passed; now there is
        no denominator, the aggregate is `None`, and `Barra.pasa` is False for a
        `None` — a metric nobody could compute never counts as a metric that was
        met.
        """
        vacias = [pregunta(f"E{i}", ("9750#3",), ()) for i in range(3)]
        metricas = metricas_recuperacion(vacias)
        assert metricas.n_respondibles == 3
        assert metricas.n_separacion == 0
        assert metricas.separacion_norma_secundaria is None

        barra = Barra(
            "norma-vs-secundaria",
            metricas.separacion_norma_secundaria,
            BARRA_SEPARACION,
            "==",
            "answerable subset",
        )
        assert barra.pasa is False

    def test_the_separation_denominator_counts_only_answered_questions(self):
        con_hits = pregunta("S5", ("9750#3",), (), hits=(norma("9750#3"),))
        vacia = pregunta("S6", ("9750#3",), ())
        metricas = metricas_recuperacion([con_hits, vacia])
        assert metricas.n_respondibles == 2
        assert metricas.n_separacion == 1
        assert metricas.separacion_norma_secundaria == 1.0

    def test_vigencia_correctness_needs_the_caveat_unit_retrieved(self):
        """T-1/T-2: the article alone is the historic text; the caveat unit is
        what makes the answer true today."""
        completa = pregunta(
            "T1",
            ("10679#17", "10679#vigencia-de-los-fondos"),
            ("10679#17", "10679#vigencia-de-los-fondos"),
            clase="trampa-vigencia",
            citas_vigencia=("10679#vigencia-de-los-fondos",),
        )
        solo_articulo = pregunta(
            "T1malo",
            ("10679#17", "10679#vigencia-de-los-fondos"),
            ("10679#17", "10679#20"),
            clase="trampa-vigencia",
            citas_vigencia=("10679#vigencia-de-los-fondos",),
        )
        assert vigencia_correctness(completa) == 1.0
        assert vigencia_correctness(solo_articulo) == 0.0

    def test_vigencia_correctness_fails_a_norma_hit_with_no_vigencia_state(self):
        sin_estado = pregunta(
            "T5",
            ("5589#276",),
            (),
            clase="trampa-vigencia",
            citas_vigencia=("5589#276",),
            hits=(norma("5589#276", estado_vigencia=None),),
        )
        assert vigencia_correctness(sin_estado) == 0.0

    def test_vigencia_correctness_is_not_applicable_without_a_caveat_key(self):
        """Returning 0.0 here would punish 24 ordinary questions for a property
        they never claimed; returning 1.0 would inflate the mean with free
        points. Neither is a measurement, so the question leaves the denominator."""
        assert vigencia_correctness(Q1) is None

    def test_aggregate_vigencia_denominator_counts_only_trap_questions(self):
        trampa = pregunta(
            "T2",
            ("10679#20", "10679#vigencia-de-los-fondos"),
            ("10679#20", "10679#vigencia-de-los-fondos"),
            clase="trampa-vigencia",
            citas_vigencia=("10679#vigencia-de-los-fondos",),
        )
        agregado = metricas_recuperacion((*FIXTURE, trampa))
        assert agregado.n_vigencia == 1
        assert agregado.vigencia_correctness == 1.0

    def test_aggregate_reports_none_when_no_trap_question_exists(self):
        agregado = metricas_recuperacion(FIXTURE)
        assert agregado.n_vigencia == 0
        assert agregado.vigencia_correctness is None


class TestScopeOfTheRetrievalMetrics:
    def test_unanswerable_questions_are_excluded_from_every_retrieval_metric(self):
        """The spec scopes MRR to the answerable set, and the reason generalises:
        an unanswerable question has no gold citation, so `|gold| = 0` and every
        one of these metrics is a division by zero dressed up as a score."""
        sin_respuesta = pregunta("X1", (), ("8555#20",), clase="unanswerable")
        agregado = metricas_recuperacion((*FIXTURE, sin_respuesta))
        assert agregado.n_respondibles == 4
        assert agregado.hit_rate_at_5 == 0.75
        assert agregado.mrr == pytest.approx(0.625)

    def test_empty_question_set_reports_zero_n_and_no_scores(self):
        agregado = metricas_recuperacion(())
        assert agregado.n_respondibles == 0
        assert agregado.hit_rate_at_5 is None
        assert agregado.mrr is None
        assert agregado.citation_precision is None
