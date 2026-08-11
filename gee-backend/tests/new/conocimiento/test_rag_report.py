"""The eval report writer (task 4.11).

The report is the V0 deliverable, which makes it the last place a fabricated
number can enter the record — and the easiest, because a markdown file looks
authoritative regardless of what produced it. So the tests here are mostly about
what the writer REFUSES to do.

The central one is the synthetic gate: `DeterministicEmbedder` exists so the
whole pipeline can be exercised without a 2.2 GB model, and a report rendered
over hash noise would be shaped exactly like a real one. RAG3-001 closed that at
the load and query layers; this closes it at the layer that publishes.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from app.domains.conocimiento.eval.report import (
    EvalSinteticoNoEsEval,
    escribir_reporte,
    nombre_de_archivo,
    renderizar_markdown,
)
from app.domains.conocimiento.repository import FTS_OPERADOR, registrar_procedencia

from .test_rag_eval_harness import PREGUNTAS, SHA, gold_item, gold_set, seed

MOMENTO = dt.datetime(2026, 8, 10, 16, 30, tzinfo=dt.timezone.utc)


@pytest.fixture
def corrida(db):
    seed(db)
    from app.domains.conocimiento.eval.harness import evaluar

    return db, evaluar(db, SHA, PREGUNTAS, modos=("fts",))


def procedencia(db, *, sintetico: bool, modelo: str = "BAAI/bge-m3"):
    registrar_procedencia(
        db,
        SHA,
        modelo=modelo,
        revision_hf=None if sintetico else "a" * 40,
        sintetico=sintetico,
        artifact_sha256="b" * 64,
    )
    db.flush()
    from app.domains.conocimiento.service import procedencia_embeddings

    return procedencia_embeddings(db, SHA)


class TestSyntheticRefusal:
    """The RAG3-001 gate, extended to the layer that publishes."""

    def test_a_synthetic_snapshot_refuses_to_render_as_a_real_eval(self, corrida):
        db, resultado = corrida
        proc = procedencia(db, sintetico=True, modelo="deterministic")
        with pytest.raises(EvalSinteticoNoEsEval) as excinfo:
            renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        mensaje = str(excinfo.value)
        assert "deterministic" in mensaje
        assert "--allow-synthetic" in mensaje or "permitir_sintetico" in mensaje

    def test_a_permitted_smoke_run_renders_but_never_as_an_eval(self, corrida):
        db, resultado = corrida
        proc = procedencia(db, sintetico=True, modelo="deterministic")
        markdown = renderizar_markdown(
            resultado,
            proc,
            generado_en=MOMENTO,
            device_consulta="cpu",
            permitir_sintetico=True,
        )
        assert "SMOKE RUN" in markdown
        assert "NOT AN EVAL" in markdown
        # And the verdict cannot be GO, whatever the numbers say.
        assert "GO**" not in markdown.replace("NO-GO**", "")
        assert "NO EVALUABLE" in markdown

    def test_the_smoke_filename_cannot_be_mistaken_for_an_eval_in_docs_rag(self):
        real = nombre_de_archivo(SHA, MOMENTO, sintetico=False)
        humo = nombre_de_archivo(SHA, MOMENTO, sintetico=True)
        assert real == "retrieval-eval-dddddddd-2026-08-10.md"
        assert humo == "retrieval-eval-SINTETICO-dddddddd-2026-08-10.md"

    def test_a_real_model_renders_normally(self, corrida):
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert "SMOKE RUN" not in markdown
        assert "BAAI/bge-m3" in markdown


class TestProvenanceComesFromTheDatabase:
    def test_the_block_reports_the_recorded_model_revision_and_artifact(self, corrida):
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert "BAAI/bge-m3" in markdown
        assert "a" * 40 in markdown
        assert "b" * 64 in markdown
        assert SHA[:8] in markdown

    def test_a_never_embedded_snapshot_says_so_instead_of_leaving_a_blank(self, corrida):
        db, resultado = corrida
        from app.domains.conocimiento.service import procedencia_embeddings

        proc = procedencia_embeddings(db, SHA)
        assert proc is not None and proc.cargado is False
        markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert "nunca embebido" in markdown

    def test_the_corpus_side_device_is_reported_as_unrecorded_not_as_the_query_side(self, corrida):
        """RAG4-002. `conocimiento_004` records model / revision / sintetico /
        artifact sha / timestamp — and NOT the batch's torch version or device.

        D6 asks the report to pin torch version and device "for both legs". Half
        of that is not in the database, and printing the QUERY process's torch
        and device next to the corpus leg would be the actual lie: those vectors
        came off a CUDA box that this process has never seen.
        """
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert "no registrado en la base" in markdown


class TestDeterminism:
    def test_same_inputs_and_same_timestamp_render_byte_identically(self, corrida):
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        primera = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        segunda = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert primera == segunda

    def test_the_timestamp_is_an_argument_and_never_a_clock_reading(self, corrida):
        """Determinism is the claim; an internal `now()` would silently break it
        while every test that renders twice in the same second still passed."""
        import ast
        import inspect

        from app.domains.conocimiento.eval import report

        arbol = ast.parse(inspect.getsource(report))
        llamadas = [
            nodo
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr in {"now", "utcnow", "today", "time"}
        ]
        assert llamadas == []

    def test_a_different_timestamp_changes_only_the_header(self, corrida):
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        temprano = renderizar_markdown(
            resultado, proc, generado_en=MOMENTO, device_consulta="cpu"
        ).splitlines()
        tarde = renderizar_markdown(
            resultado,
            proc,
            generado_en=MOMENTO + dt.timedelta(hours=3),
            device_consulta="cpu",
        ).splitlines()
        distintas = [a for a, b in zip(temprano, tarde, strict=True) if a != b]
        assert len(distintas) == 1
        assert "2026-08-10" in distintas[0]


class TestMethodologyDisclosure:
    def test_every_mode_block_states_what_was_fitted(self, corrida):
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert "leave-one-out" in markdown
        assert "upper bound (fit on the scoring sample)" in markdown
        assert "LOOCV held-out" in markdown
        assert "folds con fallback" in markdown

    def test_the_report_states_why_it_is_not_evaluable(self, corrida):
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert "NO EVALUABLE" in markdown
        assert "< 20" in markdown

    def test_a_degraded_leg_is_named_next_to_the_metrics_it_explains(self, corrida):
        db, _ = corrida
        from app.domains.conocimiento.eval.harness import evaluar

        vacia = gold_set(
            gold_item("g-hueco", "cuántos metros de ancho tiene la zona de camino", "answerable")
        )
        resultado = evaluar(db, SHA, vacia, modos=("fts",))
        proc = procedencia(db, sintetico=False)
        markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert "LEG DEGRADADA" in markdown
        assert "RAG4-001" in markdown

    def test_the_report_names_the_lexical_operator_it_used(self, corrida):
        """An ablation whose lexical operator is not printed is a comparison the
        reader cannot name. RAG4-001 was a change to that operator and nothing
        else, so the operator belongs in the artifact beside the numbers."""
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert FTS_OPERADOR in markdown
        assert "websearch_to_tsquery" in FTS_OPERADOR

    def test_the_metric_table_states_each_bar_denominator(self, corrida):
        """A mean over 3 questions and a mean over 29 must not look alike."""
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert "| métrica | valor | barra | fuente | n | ¿pasa? |" in markdown


class TestExencionOverCeilingEnElReporte:
    """RJDA-003 / RJDB-006: the exemption must never be silent.

    A denominator that shrinks without an explanation is worse than one that
    does not shrink at all: the number still looks like a measurement and the
    reason it stopped being one is nowhere in the artifact.
    """

    def test_a_mode_with_a_lexical_leg_states_that_nothing_is_exempt(self, corrida):
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert "Exención por ceiling de embedding" in markdown
        assert "no aplica en este modo" in markdown

    def test_the_json_carries_the_exemption_for_a_machine_reader(self, corrida, tmp_path):
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        escrito = escribir_reporte(
            resultado, proc, destino=tmp_path, generado_en=MOMENTO, device_consulta="cpu"
        )
        datos = json.loads(escrito.json.read_text(encoding="utf-8"))
        exencion = datos["modos"]["fts"]["exencion_over_ceiling"]
        assert exencion["aplica"] is False
        assert exencion["claves_sin_vector"] == []
        assert exencion["preguntas_exentas"] == []
        assert exencion["metrica_afectada"] == "citation-precision"
        assert "FTS" in exencion["motivo"] or "recuperables por FTS" in exencion["motivo"]
        # And the shrinkable denominator is published next to its value.
        assert "n_citation_precision" in datos["modos"]["fts"]["metricas"]

    def test_an_exempting_run_names_the_keys_the_items_and_the_reason(self, corrida):
        """Rendered from a hand-built `ResultadoModo`: the exemption only ever
        arises in a `vector` run, which needs pgvector, and this assertion is
        about the REPORT rather than about the query."""
        import dataclasses

        from app.domains.conocimiento.eval.harness import ExencionOverCeiling

        db, resultado = corrida
        corrida_fts = resultado.por_modo["fts"]
        exenta = dataclasses.replace(
            corrida_fts,
            modo="vector",
            exencion=ExencionOverCeiling(
                aplica=True,
                claves=("8560#5",),
                preguntas=("D-8",),
            ),
        )
        alterado = dataclasses.replace(resultado, modos=("vector",), por_modo={"vector": exenta})
        proc = procedencia(db, sintetico=False)
        markdown = renderizar_markdown(alterado, proc, generado_en=MOMENTO, device_consulta="cpu")
        assert "`8560#5`" in markdown
        assert "D-8" in markdown
        assert "FTS-only by design" in markdown
        assert "nunca se truncan" in markdown


class TestArtifacts:
    def test_writes_markdown_and_json_side_by_side(self, corrida, tmp_path):
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        escrito = escribir_reporte(
            resultado,
            proc,
            destino=tmp_path,
            generado_en=MOMENTO,
            device_consulta="cpu",
        )
        assert escrito.markdown.name == "retrieval-eval-dddddddd-2026-08-10.md"
        assert escrito.json.name == "retrieval-eval-dddddddd-2026-08-10.results.json"
        datos = json.loads(escrito.json.read_text(encoding="utf-8"))
        assert datos["corpus_sha"] == SHA
        assert datos["procedencia"]["modelo"] == "BAAI/bge-m3"
        assert datos["modos"]["fts"]["go_no_go"]["veredicto"] == "NO EVALUABLE"
        assert datos["modos"]["fts"]["metodologia"]["etiqueta_same_sample"] == (
            "upper bound (fit on the scoring sample)"
        )

    def test_the_json_is_stable_across_runs(self, corrida, tmp_path):
        db, resultado = corrida
        proc = procedencia(db, sintetico=False)
        uno = escribir_reporte(
            resultado, proc, destino=tmp_path / "a", generado_en=MOMENTO, device_consulta="cpu"
        )
        dos = escribir_reporte(
            resultado, proc, destino=tmp_path / "b", generado_en=MOMENTO, device_consulta="cpu"
        )
        assert uno.json.read_text(encoding="utf-8") == dos.json.read_text(encoding="utf-8")

    def test_a_synthetic_run_refuses_to_write_at_all_without_the_flag(self, corrida, tmp_path):
        db, resultado = corrida
        proc = procedencia(db, sintetico=True, modelo="deterministic")
        with pytest.raises(EvalSinteticoNoEsEval):
            escribir_reporte(
                resultado, proc, destino=tmp_path, generado_en=MOMENTO, device_consulta="cpu"
            )
        assert list(tmp_path.glob("*")) == []


def test_the_per_question_table_carries_expected_and_returned_keys(corrida):
    db, resultado = corrida
    proc = procedencia(db, sintetico=False)
    markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
    assert "g-quorum" in markdown
    assert "9750#14" in markdown
    # The unanswerable question is in the table too, with no expected citation —
    # a reader has to be able to see WHY it was scored as an abstention.
    assert "g-hueco" in markdown


def test_the_report_pins_the_fusion_constants_it_was_produced_with(corrida):
    db, resultado = corrida
    proc = procedencia(db, sintetico=False)
    markdown = renderizar_markdown(resultado, proc, generado_en=MOMENTO, device_consulta="cpu")
    assert "RRF k = 60" in markdown
    assert "LEG_LIMIT = 50" in markdown
