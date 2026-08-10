"""Ingestion gates (tasks 2.10, 2.11, 2.12).

The gate logic is exercised against hand-built unit sets so each failure mode is
isolated, plus a full run over the real SHA-pinned corpus where one is available.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from app.domains.conocimiento.expectations import (
    CorpusExpectations,
    DocumentPolicy,
    ExcludedHeading,
    NonArticleUnit,
    load_expectations,
)
from app.domains.conocimiento.gates import (
    TOKEN_CEILING,
    GateReport,
    article_count_gate,
    citation_key_uniqueness_gate,
    corpus_file_inventory_gate,
    estimate_tokens,
    heading_coverage_gate,
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


def make_expectations(policy: DocumentPolicy, **overrides) -> CorpusExpectations:
    """A one-document corpus contract, for gates that need a policy but no corpus."""
    defaults = dict(
        corpus_sha="0" * 40,
        manifest_version=2,
        articulos_declarados=policy.articulos,
        subtotales_articulo={},
        no_articulos_declarados=len(policy.no_articulos),
        documentos={policy.documento_id: policy},
        clases_excluidas={"editorial": "corpus commentary, not the norm"},
        archivos_no_documento=frozenset({"MANIFEST.md"}),
    )
    defaults.update(overrides)
    return CorpusExpectations(**defaults)  # type: ignore[arg-type]


def make_policy(**overrides) -> DocumentPolicy:
    defaults = dict(
        documento_id="d",
        archivo="d.md",
        tipo="ley-provincial",
        es_secundaria=False,
        key_prefix="d",
        key_style="numero",
        articulos=0,
        no_articulos=(),
        excluidos=(),
    )
    defaults.update(overrides)
    return DocumentPolicy(**defaults)  # type: ignore[arg-type]


class TestHeadingCoverageGate:
    """RAG2-001: the count gates only check what the YAML claims.

    A section declared in no inventory is invisible to every one of them, which
    is how Res. APRHI 3/2026's two anexos stayed out of the index with a green
    run.
    """

    SOURCE = "---\ntitulo: D\n---\n\n# Título\n\n## Art. 1\n\ncuerpo\n\n## Huérfana\n\ntexto\n"

    def test_heading_in_no_inventory_fails(self):
        report = GateReport()
        policy = make_policy()
        heading_coverage_gate({"d": []}, {"d": self.SOURCE}, make_expectations(policy), report)
        assert not report.ok
        assert any("Huérfana" in failure for failure in report.failures)

    def test_heading_inside_a_captured_unit_passes(self):
        """A `##` sub-heading of a captured unit is part of it, not a new one."""
        start = self.SOURCE.index("## Art. 1")
        unidad = replace(make_unidad("d#1", texto=self.SOURCE[start:]), source_offset=start)
        report = GateReport()
        policy = make_policy(excluidos=(ExcludedHeading(heading="Título", clase="editorial"),))
        heading_coverage_gate(
            {"d": [unidad]}, {"d": self.SOURCE}, make_expectations(policy), report
        )
        assert report.ok, report.failures

    def test_declared_exclusion_passes(self):
        report = GateReport()
        policy = make_policy(
            excluidos=(
                ExcludedHeading(heading="Título", clase="editorial"),
                ExcludedHeading(heading="Art. 1", clase="editorial"),
                ExcludedHeading(heading="Huérfana", clase="editorial"),
            )
        )
        heading_coverage_gate({"d": []}, {"d": self.SOURCE}, make_expectations(policy), report)
        assert report.ok, report.failures

    def test_declared_non_article_heading_passes(self):
        report = GateReport()
        policy = make_policy(
            no_articulos=(
                NonArticleUnit(heading="Huérfana", tipo_chunk="nota-vigencia", citation_key="d#h"),
            ),
            excluidos=(
                ExcludedHeading(heading="Título", clase="editorial"),
                ExcludedHeading(heading="Art. 1", clase="editorial"),
            ),
        )
        heading_coverage_gate({"d": []}, {"d": self.SOURCE}, make_expectations(policy), report)
        assert report.ok, report.failures

    def test_hash_line_inside_frontmatter_is_not_a_heading(self):
        """`#` is legal YAML comment syntax; only the body carries headings."""
        source = "---\n# no soy un heading\ntitulo: D\n---\n\ncuerpo\n"
        report = GateReport()
        heading_coverage_gate({"d": []}, {"d": source}, make_expectations(make_policy()), report)
        assert report.ok, report.failures


class TestCorpusFileInventoryGate:
    """A corpus `.md` nobody declared is never opened, parsed, counted or reported."""

    def _corpus_dir(self, tmp_path, *names: str):
        for name in names:
            (tmp_path / name).write_text("---\ntitulo: x\n---\n", encoding="utf-8")
        return tmp_path

    def test_unlisted_md_file_fails(self, tmp_path):
        path = self._corpus_dir(tmp_path, "d.md", "MANIFEST.md", "ley-fantasma.md")
        report = GateReport()
        corpus_file_inventory_gate(path, make_expectations(make_policy()), report)
        assert not report.ok
        assert any("ley-fantasma.md" in failure for failure in report.failures)

    def test_declared_document_and_declared_non_document_pass(self, tmp_path):
        path = self._corpus_dir(tmp_path, "d.md", "MANIFEST.md")
        report = GateReport()
        corpus_file_inventory_gate(path, make_expectations(make_policy()), report)
        assert report.ok, report.failures

    def test_missing_corpus_directory_fails(self, tmp_path):
        report = GateReport()
        corpus_file_inventory_gate(tmp_path / "nope", make_expectations(make_policy()), report)
        assert not report.ok


class TestExclusionVocabulary:
    def test_every_declared_exclusion_class_exists(self):
        used = {
            item.clase for policy in EXPECTATIONS.documentos.values() for item in policy.excluidos
        }
        assert used, "the exclusion inventory must not be empty"
        assert used <= set(EXPECTATIONS.clases_excluidas)

    def test_undeclared_exclusion_class_is_rejected(self, tmp_path):
        """An exclusion with no declared class is an exclusion with no reason."""
        raw = {
            "corpus_sha": "0" * 40,
            "manifest_version": 2,
            "articulos_declarados": 0,
            "subtotales_articulo": {},
            "no_articulos_declarados": 0,
            "clases_excluidas": {"editorial": "…"},
            "documentos": {
                "d": {
                    "archivo": "d.md",
                    "articulos": 0,
                    "es_secundaria": False,
                    "key_prefix": "d",
                    "key_style": "numero",
                    "no_articulos": [],
                    "excluidos": [{"heading": "H", "clase": "inventada"}],
                    "tipo": "ley-provincial",
                }
            },
        }
        path = tmp_path / "expectations.yaml"
        path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
        with pytest.raises(ValueError, match="undeclared class"):
            load_expectations(path)


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

    def test_every_heading_is_captured_declared_or_excluded(self, corpus):
        """No heading may be silently absent from all three inventories.

        The count gates compare produced units against *declared* ones, so a
        section declared nowhere is invisible to both. This is the gate that
        would have caught RAG2-001 on the day the resolution was added.
        """
        report = GateReport()
        heading_coverage_gate(corpus.parsed, corpus.sources, corpus.expectations, report)
        assert report.ok, report.failures[:10]

    def test_aprhi_3_2026_anexos_are_indexed(self, corpus):
        """RAG2-001: art. 1° declares both anexos to integrate the instrument.

        ANEXO I carries the 25 afectaciones (nomenclatura, titular, valuación) —
        content that exists in no other document of the corpus — and ANEXO II
        the cajetín of the plano. Neither was in any inventory, so neither was
        retrievable, while every count gate reported success.
        """
        unidades = {u.citation_key: u for doc in corpus.documentos for u in doc.unidades}

        anexo_i = unidades["res-aprhi-3-2026#anexo-i-planilla-de-individualizacion-de-terrenos"]
        assert anexo_i.tipo_chunk == "anexo-normativo"
        assert "25" in anexo_i.texto and "SISTEMATIZACION DE CUENCA TRES COLONIAS" in anexo_i.texto

        anexo_ii = unidades["res-aprhi-3-2026#anexo-ii-planos-de-afectacion-parcelaria-cajetin"]
        assert anexo_ii.tipo_chunk == "anexo-normativo"

    def test_every_corpus_md_file_is_declared(self, corpus):
        """A corpus file nobody listed is never opened and never reported."""
        report = GateReport()
        corpus_file_inventory_gate(real_corpus_path(), corpus.expectations, report)
        assert report.ok, report.failures

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
