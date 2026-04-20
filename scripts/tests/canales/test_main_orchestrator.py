"""Integration tests for the main orchestrator (``run_etl``).

We feed ``run_etl`` fixture KMZ paths + a tmp output dir and assert it writes
the three expected files with the right counts, handles Polygon-skip cleanly,
and honours the parse-failure threshold exit code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.etl_canales.main import (
    EXIT_INPUT_MISSING,
    EXIT_OK,
    EXIT_PARSE_FAILED,
    run_etl,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestHappyPath:
    def test_runs_against_sample_kmzs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ETL_GENERATED_AT", "2026-04-20T00:00:00Z")
        code = run_etl(
            relevados_kmz=FIXTURES / "sample_relevados.kmz",
            propuestas_kmz=FIXTURES / "sample_propuestas.kmz",
            output_dir=tmp_path,
        )
        assert code == EXIT_OK

        rel = json.loads((tmp_path / "relevados.geojson").read_text("utf-8"))
        prop = json.loads((tmp_path / "propuestas.geojson").read_text("utf-8"))
        idx = json.loads((tmp_path / "index.json").read_text("utf-8"))

        # Polygon "Las Tres del Norte" MUST be skipped.  Sample relevados has
        # 5 LineStrings + 1 Polygon → 5 relevado features.
        assert len(rel["features"]) == 5
        # Sample propuestas has 2 LineStrings.
        assert len(prop["features"]) == 2
        # Index counts must agree with the geojson file counts.
        assert idx["counts"]["relevados"] == 5
        assert idx["counts"]["propuestas"] == 2
        assert idx["counts"]["total"] == 7

    def test_slug_uniqueness(self, tmp_path: Path):
        run_etl(
            relevados_kmz=FIXTURES / "sample_relevados.kmz",
            propuestas_kmz=FIXTURES / "sample_propuestas.kmz",
            output_dir=tmp_path,
        )
        rel = json.loads((tmp_path / "relevados.geojson").read_text("utf-8"))
        prop = json.loads((tmp_path / "propuestas.geojson").read_text("utf-8"))
        ids = [f["properties"]["id"] for f in rel["features"]] + [
            f["properties"]["id"] for f in prop["features"]
        ]
        assert len(ids) == len(set(ids)), f"duplicate slug ids detected: {ids}"

    def test_relevados_never_have_prioridad(self, tmp_path: Path):
        run_etl(
            relevados_kmz=FIXTURES / "sample_relevados.kmz",
            propuestas_kmz=FIXTURES / "sample_propuestas.kmz",
            output_dir=tmp_path,
        )
        rel = json.loads((tmp_path / "relevados.geojson").read_text("utf-8"))
        for f in rel["features"]:
            assert f["properties"]["prioridad"] is None, (
                f"relevado {f['properties']['id']} has prioridad"
                f" {f['properties']['prioridad']!r} — should be None"
            )

    def test_propuestas_have_computed_longitud(self, tmp_path: Path):
        run_etl(
            relevados_kmz=FIXTURES / "sample_relevados.kmz",
            propuestas_kmz=FIXTURES / "sample_propuestas.kmz",
            output_dir=tmp_path,
        )
        prop = json.loads((tmp_path / "propuestas.geojson").read_text("utf-8"))
        for f in prop["features"]:
            assert f["properties"]["longitud_m"] > 0.0


class TestInputMissing:
    def test_missing_relevados_exits_3(self, tmp_path: Path):
        code = run_etl(
            relevados_kmz=tmp_path / "nope.kmz",
            propuestas_kmz=FIXTURES / "sample_propuestas.kmz",
            output_dir=tmp_path / "out",
        )
        assert code == EXIT_INPUT_MISSING
        # No output files should exist.
        assert not (tmp_path / "out" / "relevados.geojson").exists()

    def test_missing_propuestas_exits_3(self, tmp_path: Path):
        code = run_etl(
            relevados_kmz=FIXTURES / "sample_relevados.kmz",
            propuestas_kmz=tmp_path / "nope.kmz",
            output_dir=tmp_path / "out",
        )
        assert code == EXIT_INPUT_MISSING


class TestParseFailureThreshold:
    def test_threshold_exceeded_exits_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Build a synthetic "all structured, all fail" KMZ and feed it with a
        # 0% threshold so we force the failure path.  We use the sample KMZ
        # (which has at least one structured-intent parse-failure candidate
        # if we tighten the rules) — the easier reliable test: patch the
        # counting logic to always fail, and assert the exit code flows.
        #
        # Simpler path: inject a monkeypatched placemark list via
        # ``_process_kmz`` replacement with synthetic data.
        import scripts.etl_canales.main as main_mod

        def fake_process(kmz_path, estado):
            # 2 linestrings, both "structured intent" with no recovery.
            return [], 2, 2  # 100% parse-failure rate

        monkeypatch.setattr(main_mod, "_process_kmz", fake_process)
        monkeypatch.setattr(main_mod, "PARSE_WARN_THRESHOLD_PCT", 10.0)

        code = run_etl(
            relevados_kmz=FIXTURES / "sample_relevados.kmz",
            propuestas_kmz=FIXTURES / "sample_propuestas.kmz",
            output_dir=tmp_path,
        )
        assert code == EXIT_PARSE_FAILED
        # All-or-nothing — no outputs should be written.
        assert not (tmp_path / "relevados.geojson").exists()
        assert not (tmp_path / "propuestas.geojson").exists()
        assert not (tmp_path / "index.json").exists()
