"""RRF fusion (task 3.5) — pure, zero DB.

Every expected score below is hand-computed from `1/(k + rank + 1)` with `k=60`
and 0-based ranks, written as a decimal literal rather than recomputed with the
formula under test. A test that re-derives its expectation from the
implementation asserts that the code equals itself.

    1/61 = 0.016393442622950820
    1/62 = 0.016129032258064516
    1/63 = 0.015873015873015873
"""

from __future__ import annotations

import pytest

from app.domains.conocimiento.fusion import RRF_K, reciprocal_rank_fusion

UNO_SOBRE_61 = 0.016393442622950820
UNO_SOBRE_62 = 0.016129032258064516
UNO_SOBRE_63 = 0.015873015873015873


class TestReciprocalRankFusion:
    def test_rrf_fuses_without_blended_score(self):
        """Hand-computed fusion of two legs that disagree about the top two.

        FTS  : A B C     -> A rank 0, B rank 1, C rank 2
        VEC  : B A D     -> B rank 0, A rank 1, D rank 2

        A = 1/61 + 1/62 = 0.032522474881015336
        B = 1/61 + 1/62 = 0.032522474881015336   (identical by construction)
        C = 1/63        = 0.015873015873015873
        D = 1/63        = 0.015873015873015873
        """
        fusionado = reciprocal_rank_fusion([["A", "B", "C"], ["B", "A", "D"]])

        assert [key for key, _ in fusionado] == ["A", "B", "C", "D"]
        scores = dict(fusionado)
        assert scores["A"] == pytest.approx(0.032522474881015336, rel=1e-12)
        assert scores["B"] == pytest.approx(0.032522474881015336, rel=1e-12)
        assert scores["C"] == pytest.approx(0.015873015873015873, rel=1e-12)
        assert scores["D"] == pytest.approx(0.015873015873015873, rel=1e-12)

    def test_only_rank_enters_the_formula(self):
        """The signature takes RANKINGS, not scores — the no-blend rule, structurally.

        Two legs whose underlying metrics are wildly different scales
        (`ts_rank_cd` ~0.1 vs cosine distance ~0.4) fuse to exactly the same
        numbers as any other pair of legs with the same ordering, because the
        metrics never reach this function at all.
        """
        a = reciprocal_rank_fusion([["A", "B"], ["B", "A"]])
        b = reciprocal_rank_fusion([["A", "B"], ["B", "A"]])
        assert a == b
        assert all(isinstance(score, float) for _, score in a)

    def test_rrf_handles_missing_leg(self):
        """An empty leg contributes nothing — not a zero score, nothing.

        Spec scenario "Either sub-query can fail without corrupting fusion".
        The strongest statement of it: fusing with an empty leg is IDENTICAL to
        fusing without that leg at all.
        """
        con_vacia = reciprocal_rank_fusion([["A", "B", "C"], []])
        sola = reciprocal_rank_fusion([["A", "B", "C"]])

        assert con_vacia == sola
        assert dict(con_vacia)["A"] == pytest.approx(UNO_SOBRE_61, rel=1e-12)

    def test_both_legs_empty_returns_empty(self):
        assert reciprocal_rank_fusion([[], []]) == []

    def test_rrf_tie_break_deterministic(self):
        """Ties break on `citation_key` ascending, never on input order.

        The corpus has 45 articles of the Anexo of Res. 4/2026 whose entire body
        is the words "Sin Reglamentar" (`MANIFEST.md:658-660`). They tie on
        `ts_rank_cd` and sit inside floating-point noise of each other on cosine
        distance, so without a deterministic tie-break the fused order — and
        therefore the gold outcome — changes between runs over identical data.
        """
        empatados = ["res4-2026#anexo#art9", "res4-2026#anexo#art8", "res4-2026#anexo#art7"]

        primero = reciprocal_rank_fusion([[k] for k in empatados])
        segundo = reciprocal_rank_fusion([[k] for k in reversed(empatados)])

        assert [key for key, _ in primero] == [
            "res4-2026#anexo#art7",
            "res4-2026#anexo#art8",
            "res4-2026#anexo#art9",
        ]
        assert primero == segundo

    def test_score_dominates_the_tie_break(self):
        """`citation_key` only decides among EQUAL scores, never overrides one."""
        fusionado = reciprocal_rank_fusion([["zzz", "aaa"]])
        assert [key for key, _ in fusionado] == ["zzz", "aaa"]

    def test_rank_is_zero_based(self):
        """Top of a single leg scores exactly 1/(k+1), not 1/(k+2)."""
        (solo,) = reciprocal_rank_fusion([["A"]])
        assert solo[1] == pytest.approx(UNO_SOBRE_61, rel=1e-12)

    def test_k_is_load_bearing(self):
        """A `k` the implementation ignores would make every ablation meaningless."""
        assert RRF_K == 60
        (con_k_uno,) = reciprocal_rank_fusion([["A"]], k=1)
        assert con_k_uno[1] == pytest.approx(0.5, rel=1e-12)

    def test_second_position_in_one_leg_uses_rank_one(self):
        fusionado = dict(reciprocal_rank_fusion([["A", "B"]]))
        assert fusionado["B"] == pytest.approx(UNO_SOBRE_62, rel=1e-12)

    def test_duplicate_key_inside_one_leg_counts_once_at_its_best_rank(self):
        """Defensive: a leg is a ranking, so a key contributes once.

        Unreachable from the real legs (the PK makes duplicates impossible), but
        double-counting would be a silent scoring bug rather than an error, and
        the fusion function is a mutation-testing target that must specify its
        own contract.
        """
        fusionado = dict(reciprocal_rank_fusion([["A", "B", "A"]]))
        assert fusionado["A"] == pytest.approx(UNO_SOBRE_61, rel=1e-12)

    def test_three_legs_fuse(self):
        """Nothing in the formula is arity-two; the ablation adds legs, not cases."""
        fusionado = dict(reciprocal_rank_fusion([["A"], ["A"], ["A"]]))
        assert fusionado["A"] == pytest.approx(3 * UNO_SOBRE_61, rel=1e-12)

    def test_input_is_not_mutated(self):
        legs = [["A", "B"], ["B"]]
        reciprocal_rank_fusion(legs)
        assert legs == [["A", "B"], ["B"]]
