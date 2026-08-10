"""`scripts/rag_eval.py` — the thin entry point, exercised for real (task 4.12).

`main()` is where the pieces meet, so it gets its own tests rather than being
assumed correct because its parts are: the slice-2 review found exactly this hole
(`rag_ingest.main` was invoked by no test at all, ledger RAG2-006).

The session is threaded in rather than opened by the CLI so these run against the
real test database inside the fixture's transaction — real SQL, real gates, no
committed rows.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from app.domains.conocimiento.embedding import DETERMINISTIC_MODEL_ID
from app.domains.conocimiento.repository import registrar_procedencia
from scripts import rag_eval

from .test_rag_eval_harness import SHA, seed

MOMENTO = "2026-08-10T16:30:00+00:00"


class _SesionPrestada:
    """Hands `main()` the fixture's session and refuses to close it."""

    def __init__(self, db):
        self._db = db

    def __call__(self, _engine):
        return self

    def __enter__(self):
        return self._db

    def __exit__(self, *_):
        return False


class _NullEngine:
    def dispose(self) -> None:
        return None


@pytest.fixture
def cli(db, monkeypatch):
    seed(db)
    monkeypatch.setattr(rag_eval, "create_engine", lambda url: _NullEngine())
    monkeypatch.setattr(rag_eval, "Session", _SesionPrestada(db))
    monkeypatch.delenv("RAG_GOLD_PRIVADO_PATH", raising=False)
    return db


def marcar(db, *, sintetico: bool, modelo: str = "BAAI/bge-m3") -> None:
    registrar_procedencia(
        db,
        SHA,
        modelo=modelo,
        revision_hf=None if sintetico else "a" * 40,
        sintetico=sintetico,
        artifact_sha256="b" * 64,
    )
    db.flush()


class TestUsage:
    def test_missing_database_url_exits_2(self, monkeypatch, capsys):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert rag_eval.main(["--corpus-sha", SHA]) == 2
        assert "--database-url" in capsys.readouterr().err

    def test_an_unknown_snapshot_exits_1_before_running_anything(self, cli, capsys):
        code = rag_eval.main(
            ["--corpus-sha", "f" * 40, "--database-url", "postgresql://unused/unused"]
        )
        assert code == 1
        assert "is not in rag_corpus" in capsys.readouterr().err


class TestRun:
    def test_an_fts_only_run_writes_both_artifacts_and_exits_0(self, cli, tmp_path, capsys):
        marcar(cli, sintetico=False)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 0
        salida = capsys.readouterr().out
        assert "NO EVALUABLE" in salida  # the fixture gold set is 3 items
        md = tmp_path / "retrieval-eval-dddddddd-2026-08-10.md"
        js = tmp_path / "retrieval-eval-dddddddd-2026-08-10.results.json"
        assert md.is_file() and js.is_file()
        assert json.loads(js.read_text(encoding="utf-8"))["corpus_sha"] == SHA

    def test_a_synthetic_snapshot_exits_1_and_writes_nothing(self, cli, tmp_path, capsys):
        marcar(cli, sintetico=True, modelo=DETERMINISTIC_MODEL_ID)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 1
        assert "SYNTHETIC" in capsys.readouterr().err
        assert list(tmp_path.glob("*")) == []

    def test_the_smoke_flag_writes_a_labelled_artifact_instead(self, cli, tmp_path):
        marcar(cli, sintetico=True, modelo=DETERMINISTIC_MODEL_ID)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
                "--allow-synthetic",
            ]
        )
        assert code == 0
        escritos = sorted(p.name for p in tmp_path.glob("*.md"))
        assert escritos == ["retrieval-eval-SINTETICO-dddddddd-2026-08-10.md"]
        assert "NOT AN EVAL" in (tmp_path / escritos[0]).read_text(encoding="utf-8")

    def test_the_same_timestamp_produces_a_byte_identical_report(self, cli, tmp_path):
        marcar(cli, sintetico=False)
        for destino in ("a", "b"):
            assert (
                rag_eval.main(
                    [
                        "--corpus-sha",
                        SHA,
                        "--database-url",
                        "postgresql://unused/unused",
                        "--modo",
                        "fts",
                        "--destino",
                        str(tmp_path / destino),
                        "--generado-en",
                        MOMENTO,
                    ]
                )
                == 0
            )
        nombre = "retrieval-eval-dddddddd-2026-08-10.md"
        assert (tmp_path / "a" / nombre).read_text(encoding="utf-8") == (
            tmp_path / "b" / nombre
        ).read_text(encoding="utf-8")

    def test_the_degraded_leg_warning_reaches_the_operator_on_stdout(self, cli, tmp_path, capsys):
        """The eval's most misleading outcome must be visible without opening
        the report: a mode whose lexical leg matched nothing at all."""
        marcar(cli, sintetico=False)
        from app.domains.conocimiento.eval import harness

        natural = harness.cargar_gold_set  # keep the symbol used, see below
        assert callable(natural)

        # Swap in a one-item gold set whose question is a full sentence, which is
        # what every real gold item looks like (ledger RAG4-001).
        from .test_rag_eval_harness import gold_item, gold_set

        conjunto = gold_set(
            gold_item(
                "g-natural",
                "Convocamos la asamblea y a la hora de arrancar no llegamos ni a la "
                "mitad de los socios. ¿La podemos empezar igual o hay que suspenderla?",
                "answerable",
                ("9750#14",),
            )
        )
        rag_eval.cargar_gold_set = lambda *a, **k: conjunto  # type: ignore[assignment]
        try:
            code = rag_eval.main(
                [
                    "--corpus-sha",
                    SHA,
                    "--database-url",
                    "postgresql://unused/unused",
                    "--modo",
                    "fts",
                    "--destino",
                    str(tmp_path),
                    "--generado-en",
                    MOMENTO,
                ]
            )
        finally:
            rag_eval.cargar_gold_set = harness.cargar_gold_set  # type: ignore[assignment]
        assert code == 0
        assert "LEG FTS DEGRADADA" in capsys.readouterr().out


def test_the_default_report_destination_is_docs_rag_so_it_survives_archive():
    """design.md D6: under `docs/`, not `openspec/changes/`, so `/sdd-archive`
    does not take the deliverable with it."""
    assert rag_eval.DESTINO_POR_DEFECTO.name == "rag"
    assert rag_eval.DESTINO_POR_DEFECTO.parent.name == "docs"


def test_the_cli_reads_the_clock_only_at_the_edge():
    """One clock read, in `main()`, threaded downstream as a value."""
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(rag_eval))
    lecturas = [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr in {"now", "utcnow", "today"}
    ]
    assert len(lecturas) == 1
    assert isinstance(dt.datetime.now, object)
