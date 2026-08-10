"""Ingestion gates (tasks 2.10, 2.11, 2.12).

The gate logic is exercised against hand-built unit sets so each failure mode is
isolated, plus a full run over the real SHA-pinned corpus where one is available.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.domains.conocimiento.expectations import CorpusExpectations, load_expectations
from app.domains.conocimiento.gates import (
    TOKEN_CEILING,
    GateReport,
    article_count_gate,
    citation_key_uniqueness_gate,
    estimate_tokens,
    non_article_inventory_gate,
    run_all_gates,
    token_ceiling_gate,
    verbatim_substring_gate,
)
from app.domains.conocimiento.parser import Unidad
from app.domains.conocimiento.service import gate_corpus, load_corpus

from .conftest import real_corpus_path, requires_real_corpus

EXPECTATIONS = load_expectations()


def make_unidad(citation_key: str, tipo_chunk: str = "articulo", texto: str = "x") -> Unidad:
    return Unidad(
        citation_key=citation_key,
        tipo_chunk=tipo_chunk,
        epigrafe=None,
        texto=texto,
        texto_indexado=texto,
        source_offset=0,
    )


def parsed_from_expectations(expectations: CorpusExpectations) -> dict[str, list[Unidad]]:
    """A synthetic parse that satisfies every declared count exactly."""
    parsed: dict[str, list[Unidad]] = {}
    for documento_id, policy in expectations.documentos.items():
        unidades = [
            make_unidad(f"{policy.key_prefix}#synthetic-{i}") for i in range(policy.articulos)
        ]
        unidades += [
            make_unidad(item.citation_key, item.tipo_chunk) for item in policy.no_articulos
        ]
        parsed[documento_id] = unidades
    return parsed


class TestArticleCountGate:
    def test_all_counts_match_ingestion_succeeds(self):
        report = GateReport()
        article_count_gate(parsed_from_expectations(EXPECTATIONS), EXPECTATIONS, report)
        assert report.ok, report.failures
        assert report.articulos_total == EXPECTATIONS.articulos_declarados == 1383

    def test_per_document_and_total_articulo_count_gate(self):
        """A total-only check is how a compensating over/under pair passes.

        One document loses a unit, another gains one: the corpus total is still
        1383 and a naive gate reports success.
        """
        parsed = parsed_from_expectations(EXPECTATIONS)
        parsed["ley-9750-consorcios-canaleros"].pop()
        parsed["ley-5589-codigo-aguas-cordoba"].append(make_unidad("5589#compensating-extra"))

        report = GateReport()
        article_count_gate(parsed, EXPECTATIONS, report)

        # The total still matches — that is the trap.
        assert report.articulos_total == EXPECTATIONS.articulos_declarados
        assert not report.ok
        assert any("ley-9750" in failure for failure in report.failures)
        assert any("ley-5589" in failure for failure in report.failures)

    def test_single_document_shortfall_fails_even_though_total_is_close(self):
        parsed = parsed_from_expectations(EXPECTATIONS)
        doc = "ley-8803-acceso-informacion-cordoba"
        # Drop an ARTICLE, not one of the document's guia-de-uso units.
        first_article = next(i for i, u in enumerate(parsed[doc]) if u.tipo_chunk == "articulo")
        parsed[doc].pop(first_article)
        report = GateReport()
        article_count_gate(parsed, EXPECTATIONS, report)
        assert not report.ok
        assert report.articulos_total == 1382


class TestNonArticleInventoryGate:
    def test_non_article_inventory_gated_separately(self):
        """Every article count matches, but an expected non-article unit is gone.

        This is the Ley 10679 vigencia case: without its own inventory the
        section quietly never gets ingested and the system answers "el FDA
        venció en 2023" with a byte-exact citation.
        """
        parsed = parsed_from_expectations(EXPECTATIONS)
        parsed["ley-10679-modificatoria-ctp-fda"] = [
            u
            for u in parsed["ley-10679-modificatoria-ctp-fda"]
            if u.citation_key != "10679#vigencia-de-los-fondos"
        ]

        article_report = GateReport()
        article_count_gate(parsed, EXPECTATIONS, article_report)
        assert article_report.ok, "article counts are untouched — that is the point"

        report = GateReport()
        non_article_inventory_gate(parsed, EXPECTATIONS, report)
        assert not report.ok
        assert any("10679#vigencia-de-los-fondos" in f for f in report.failures)

    def test_non_article_units_never_counted_toward_1383(self):
        report = GateReport()
        parsed = parsed_from_expectations(EXPECTATIONS)
        article_count_gate(parsed, EXPECTATIONS, report)
        non_article_inventory_gate(parsed, EXPECTATIONS, report)
        assert report.articulos_total == 1383
        assert report.no_articulos_total == EXPECTATIONS.no_articulos_declarados
        assert report.no_articulos_total > 0

    def test_undeclared_non_article_unit_is_rejected(self):
        parsed = parsed_from_expectations(EXPECTATIONS)
        parsed["ley-9750-consorcios-canaleros"].append(
            make_unidad("9750#invented-section", "seccion-secundaria")
        )
        report = GateReport()
        non_article_inventory_gate(parsed, EXPECTATIONS, report)
        assert not report.ok
        assert any("undeclared" in f for f in report.failures)

    def test_secondary_types_es_secundaria_true_zero_contribution(self):
        """The 6 fuente-secundaria documents contribute 0 articles, on purpose."""
        secundarios = [
            policy for policy in EXPECTATIONS.documentos.values() if policy.es_secundaria
        ]
        assert len(secundarios) == 6
        assert all(policy.articulos == 0 for policy in secundarios)
        # They are still indexed — as `seccion-secundaria`, so they can answer
        # real questions while never being mistaken for a norm.
        assert all(policy.no_articulos for policy in secundarios)
        assert EXPECTATIONS.subtotales_articulo["secundarios"] == 0

    def test_class_subtotals_sum_to_the_declared_total(self):
        subtotals = EXPECTATIONS.subtotales_articulo
        assert subtotals["normas-generales"] == 1358
        assert subtotals["guia-tecnica"] == 6
        assert subtotals["actos-particulares"] == 19
        assert subtotals["secundarios"] == 0
        assert sum(subtotals.values()) == EXPECTATIONS.articulos_declarados == 1383


class TestIntegrityGates:
    def test_verbatim_substring_gate(self):
        source = "prefix ARTICULO UNO suffix"
        good = replace(make_unidad("d#1", texto="ARTICULO UNO"), source_offset=7)
        report = GateReport()
        verbatim_substring_gate({"d": [good]}, {"d": source}, report)
        assert report.ok, report.failures

        # Same text, wrong offset: the citation would still "look" verbatim, but
        # `source_offset` — which provenance rests on — is a lie.
        bad_offset = replace(good, source_offset=0)
        report = GateReport()
        verbatim_substring_gate({"d": [bad_offset]}, {"d": source}, report)
        assert not report.ok

        # Text that is not in the source at all (an enrichment leak).
        leaked = replace(make_unidad("d#2", texto="ARTICULO UNO (comentado)"), source_offset=7)
        report = GateReport()
        verbatim_substring_gate({"d": [leaked]}, {"d": source}, report)
        assert not report.ok

    def test_citation_key_uniqueness_including_d9(self):
        report = GateReport()
        citation_key_uniqueness_gate(
            {
                "10demayo": [
                    make_unidad("10demayo#res189-2014#art1"),
                    make_unidad("10demayo#res005-2026#art1"),
                ]
            },
            report,
        )
        assert report.ok, "D-9's composite keys are distinct, not duplicates"

        # A flat key would have collapsed the pair; the gate must catch that.
        report = GateReport()
        citation_key_uniqueness_gate(
            {"10demayo": [make_unidad("10demayo#art1"), make_unidad("10demayo#art1")]},
            report,
        )
        assert not report.ok
        assert any("duplicate" in f for f in report.failures)

    def test_duplicate_across_two_documents_is_caught(self):
        report = GateReport()
        citation_key_uniqueness_gate(
            {"a": [make_unidad("shared#1")], "b": [make_unidad("shared#1")]}, report
        )
        assert not report.ok


class TestTokenCeiling:
    def test_token_ceiling_aborts_not_truncates(self):
        oversized = "palabra " * 40_000
        unidad = make_unidad("doc#huge", texto=oversized)
        assert estimate_tokens(unidad.texto_indexado) > TOKEN_CEILING

        report = GateReport()
        token_ceiling_gate({"doc": [unidad]}, report, strict=True)
        assert not report.ok
        assert any("truncate" in f for f in report.failures)

        # The unit is reported intact — nothing was cut to fit.
        assert report.over_ceiling == [("doc#huge", estimate_tokens(unidad.texto_indexado))]
        assert unidad.texto == oversized
        assert unidad.texto_indexado.endswith("palabra ")

    def test_over_ceiling_unit_is_recorded_even_when_not_strict(self):
        """Never silent. Non-strict reports it; it is still not truncated."""
        unidad = make_unidad("doc#huge", texto="palabra " * 40_000)
        report = GateReport()
        token_ceiling_gate({"doc": [unidad]}, report, strict=False)
        assert report.ok, "an embedding-only limit does not block FTS ingestion"
        assert report.over_ceiling and report.over_ceiling[0][0] == "doc#huge"

    def test_unit_under_ceiling_passes(self):
        report = GateReport()
        token_ceiling_gate({"doc": [make_unidad("doc#small", texto="corto")]}, report, strict=True)
        assert report.ok
        assert report.over_ceiling == []

    def test_injected_real_tokenizer_overrides_the_estimate(self):
        """Slice 3 passes the real BGE-M3 tokenizer; the gate must honour it."""
        unidad = make_unidad("doc#x", texto="corto")
        report = GateReport()
        token_ceiling_gate({"doc": [unidad]}, report, token_counter=lambda _: 99_999, strict=True)
        assert not report.ok


@requires_real_corpus
class TestAgainstRealCorpus:
    """The gates as they actually run at ingestion time (task 2.9/2.10)."""

    @pytest.fixture(scope="class")
    def corpus(self):
        return load_corpus(real_corpus_path())

    def test_real_corpus_passes_every_gate(self, corpus):
        report = gate_corpus(corpus)
        assert report.ok, report.failures

    def test_real_corpus_matches_manifest_declared_counts(self, corpus):
        report = gate_corpus(corpus)
        assert report.documentos == 35
        assert report.articulos_total == 1383
        assert report.no_articulos_total == EXPECTATIONS.no_articulos_declarados

    def test_vigencia_canary_ingested_and_under_ceiling(self, corpus):
        """T-1/T-2 canary: the section exists, is `nota-vigencia`, and is one
        chunk that fits — exactly what design.md D2 predicted."""
        unidades = {u.citation_key: u for doc in corpus.documentos for u in doc.unidades}
        canary = unidades["10679#vigencia-de-los-fondos"]
        assert canary.tipo_chunk == "nota-vigencia"
        assert estimate_tokens(canary.texto_indexado) <= TOKEN_CEILING
        assert "31 de diciembre de 2032" in canary.texto

    def test_real_corpus_citation_keys_are_unique(self, corpus):
        keys = [u.citation_key for doc in corpus.documentos for u in doc.unidades]
        assert len(keys) == len(set(keys))

    def test_real_corpus_texto_is_verbatim_everywhere(self, corpus):
        report = GateReport()
        verbatim_substring_gate(corpus.parsed, corpus.sources, report)
        assert report.ok, report.failures[:5]

    def test_parse_is_deterministic_across_runs(self, corpus):
        """Same SHA in, byte-identical units out."""
        again = load_corpus(real_corpus_path())
        first = [
            (u.citation_key, u.texto, u.source_offset)
            for d in corpus.documentos
            for u in d.unidades
        ]
        second = [
            (u.citation_key, u.texto, u.source_offset) for d in again.documentos for u in d.unidades
        ]
        assert first == second

    def test_run_all_gates_reports_the_known_over_ceiling_units(self, corpus):
        """Three real units genuinely exceed the embedding ceiling.

        Recorded rather than truncated, and not folded into `failures` — see
        `GateReport.over_ceiling`.
        """
        report = run_all_gates(corpus.parsed, corpus.sources, corpus.expectations)
        assert report.ok
        keys = {key for key, _ in report.over_ceiling}
        assert "10593#1" in keys
        assert "8560#5" in keys
        assert "10679#vigencia-de-los-fondos" not in keys
