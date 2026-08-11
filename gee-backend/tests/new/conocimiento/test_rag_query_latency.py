"""Query-latency harness (task 3.10).

The NUMBER this script produces needs the real model and is the owner's to
measure. What is tested here is the harness itself — question loading, the
percentile arithmetic, the conditions it records, and the fact that a synthetic
run announces that it measured nothing. Slice 2 shipped a `main()` no test ever
invoked (ledger RAG2-006); a measurement script whose reporting path is
unexercised is the same mistake with a worse blast radius, because its output
lands in a report.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.domains.conocimiento.embedding import DeterministicEmbedder

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "rag_query_latency.py"


def _load():
    spec = importlib.util.spec_from_file_location("rag_query_latency", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


latencia = _load()


class TestQuestionLoading:
    def test_reads_one_question_per_line_ignoring_blanks_and_comments(self, tmp_path):
        path = tmp_path / "preguntas.txt"
        path.write_text(
            "# comentario\n\n¿Quién mantiene el canal?\n  \n¿Qué es el FDA?\n",
            encoding="utf-8",
        )
        assert latencia.leer_preguntas(path) == ["¿Quién mantiene el canal?", "¿Qué es el FDA?"]

    def test_empty_file_is_refused(self, tmp_path):
        path = tmp_path / "vacio.txt"
        path.write_text("# solo comentarios\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no questions"):
            latencia.leer_preguntas(path)

    def test_gold_set_is_read_when_it_exists(self, tmp_path):
        """Slice 4's artifact, read by the same harness rather than a second one."""
        path = tmp_path / "gold_set.yaml"
        path.write_text(
            "items:\n"
            "  - id: g1\n    pregunta: ¿Quién mantiene el canal N°5?\n"
            "  - id: g2\n    pregunta: ¿Hasta cuándo rige el FDA?\n",
            encoding="utf-8",
        )
        assert latencia.leer_gold_set(path) == [
            "¿Quién mantiene el canal N°5?",
            "¿Hasta cuándo rige el FDA?",
        ]


class TestMeasurement:
    def test_percentiles_are_ordered_and_the_sample_size_is_what_it_claims(self):
        preguntas = ["a", "b", "c", "d"]
        metricas = latencia.medir(DeterministicEmbedder(dims=8), preguntas)

        assert metricas["n"] == len(preguntas) * latencia.REPETICIONES
        assert metricas["min_ms"] <= metricas["p50_ms"] <= metricas["p95_ms"]
        assert metricas["p95_ms"] <= metricas["max_ms"]
        assert metricas["media_ms"] > 0

    def test_warmups_are_excluded_from_the_sample(self):
        """A cold first call is model-loading time, not query time."""
        metricas = latencia.medir(DeterministicEmbedder(dims=8), ["a"])
        assert metricas["n"] == latencia.REPETICIONES


class TestMainEntryPoint:
    def _preguntas(self, tmp_path):
        path = tmp_path / "preguntas.txt"
        path.write_text("¿Quién mantiene el canal?\n¿Qué es el FDA?\n", encoding="utf-8")
        return path

    def test_reports_conditions_not_just_a_number(self, tmp_path, capsys):
        code = latencia.main(
            [
                "--preguntas",
                str(self._preguntas(tmp_path)),
                "--embedder",
                "deterministic",
                "--etiqueta",
                "ESTIMATE",
            ]
        )
        assert code == 0
        salida = capsys.readouterr()
        for campo in ("p50_ms", "p95_ms", "cpu_count", "device", "etiqueta", "modelo"):
            assert campo in salida.out
        assert "ESTIMATE" in salida.out
        # A synthetic run must say it measured the harness, not the model.
        assert "ADVERTENCIA" in salida.err

    def test_json_output_is_machine_readable(self, tmp_path, capsys):
        destino = tmp_path / "out" / "latencia.json"
        latencia.main(
            [
                "--preguntas",
                str(self._preguntas(tmp_path)),
                "--embedder",
                "deterministic",
                "--json",
                str(destino),
            ]
        )
        capsys.readouterr()

        reporte = json.loads(destino.read_text(encoding="utf-8"))
        assert reporte["sintetico"] is True
        assert reporte["preguntas"] == 2
        assert reporte["p95_ms"] >= reporte["p50_ms"]

    def test_a_question_source_is_required(self, tmp_path):
        with pytest.raises(SystemExit):
            latencia.main(["--embedder", "deterministic"])
