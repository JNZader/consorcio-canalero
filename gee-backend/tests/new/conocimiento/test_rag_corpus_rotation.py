"""Rotation of `rag_corpus.activo` inside the ingest transaction (audit RAG-3).

Before the fix, `upsert_corpus` wrote `activo=true` and nothing ever retired
the previous snapshot: ingesting A then B left BOTH active forever, serving
kept resolving `ORDER BY ingested_at DESC`, and "roll back by re-ingesting A"
was a silent no-op that still printed `committed:true` (the runbook's only
rollback was hand-written SQL; docs/rag/runbook-encendido.md, "Rollback").

These tests drive `repository.upsert_corpus` exactly as `rag_ingest.ingest`
does inside its single transaction — one call per ingest, `activo=True` — so
what passes here is what one committed ingest run produces. No private corpus
is needed: the scenarios are synthetic snapshots, seeded like the kernel
tests seed theirs.

The rollback scenarios seed rows with EXPLICIT `ingested_at` values. Inside
the `db` fixture's one rolled-back transaction Postgres `now()` is constant,
so server-default timestamps would tie and the serving tie-break
(`ORDER BY ingested_at DESC, corpus_sha`) would pick by sha and mask the very
bug this file exists to pin.
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text

from app.domains.conocimiento import repository

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "rag_ingest.py"

SHA_A = "a" * 40
SHA_B = "b" * 40
T_OLD = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)


def _load_script():
    spec = importlib.util.spec_from_file_location("rag_ingest_rotation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _ingest_corpus(db, sha: str) -> None:
    """The one write `rag_ingest.ingest` makes to `rag_corpus`, in its transaction."""
    repository.upsert_corpus(
        db, sha, repo_url="u", manifest_version="2", articulos_declarados=1
    )


def _seed_corpus(db, sha: str, *, activo: bool, ingested_at: datetime.datetime) -> None:
    """Raw INSERT, to reproduce pre-rotation database states exactly."""
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo, ingested_at) "
            "VALUES (:sha, 'u', '2', 1, :activo, :ingested_at)"
        ),
        {"sha": sha, "activo": activo, "ingested_at": ingested_at},
    )


def _activos(db) -> set[str]:
    return {
        row[0]
        for row in db.execute(text("SELECT corpus_sha FROM rag_corpus WHERE activo IS TRUE"))
    }


def _activo_de(db, sha: str) -> bool:
    return db.execute(
        text("SELECT activo FROM rag_corpus WHERE corpus_sha = :sha"), {"sha": sha}
    ).scalar_one()


class TestCorpusRotation:
    def test_ingest_a_then_b_leaves_exactly_one_active_row(self, db):
        _ingest_corpus(db, SHA_A)
        assert repository.corpus_activo(db) == SHA_A

        _ingest_corpus(db, SHA_B)

        assert _activos(db) == {SHA_B}
        assert repository.corpus_activo(db) == SHA_B
        assert _activo_de(db, SHA_A) is False

    def test_reingesting_a_retires_b(self, db):
        """The rollback-by-re-ingest scenario from audit RAG-3.

        Two snapshots both activo with distinct landing times is exactly the
        database state the unfixed code produced across two ingests. Before
        the fix, re-ingesting A here kept serving answering from B (A's
        `ingested_at` stayed older and nothing deactivated B) while the run
        exited 0 printing `committed:true`.
        """
        _seed_corpus(db, SHA_A, activo=True, ingested_at=T_OLD)
        _seed_corpus(
            db, SHA_B, activo=True, ingested_at=T_OLD + datetime.timedelta(days=1)
        )
        assert repository.corpus_activo(db) == SHA_B  # the unfixed serving pick

        _ingest_corpus(db, SHA_A)

        assert _activos(db) == {SHA_A}
        assert repository.corpus_activo(db) == SHA_A
        assert _activo_de(db, SHA_B) is False

    def test_reingesting_the_active_sha_rotates_nothing(self, db):
        """Idempotence: the rotation UPDATE excludes the sha being upserted, so
        re-ingesting the snapshot that is already active cannot fight itself."""
        _ingest_corpus(db, SHA_A)
        _ingest_corpus(db, SHA_B)
        _ingest_corpus(db, SHA_B)

        assert _activos(db) == {SHA_B}
        assert repository.corpus_activo(db) == SHA_B

    def test_reingest_refreshes_ingested_at(self, db):
        """`ingested_at` follows the LAST ingest, not first landing.

        Serving resolves ties with `ORDER BY ingested_at DESC` precisely
        because `activo` is not unique in the schema; a re-ingested snapshot
        that kept its original landing time could lose that defensive
        ordering to a row this same run had just retired.
        """
        _seed_corpus(db, SHA_A, activo=True, ingested_at=T_OLD)

        _ingest_corpus(db, SHA_A)

        ingested_at = db.execute(
            text("SELECT ingested_at FROM rag_corpus WHERE corpus_sha = :sha"),
            {"sha": SHA_A},
        ).scalar_one()
        assert ingested_at > T_OLD


class _NullEngine:
    """Stands in for a SQLAlchemy Engine in `main()` tests that never query."""

    def dispose(self) -> None:
        return None


class TestServedShaPrint:
    """`main()` prints the sha serving resolves to after commit, so a no-op
    rollback is visible on the console instead of a `committed:true` that
    serving contradicts.

    Stubs follow `TestMainEntryPoint` in test_rag_ingest_cli.py: `ingest` and
    `corpus_activo` never touch a database here, so what is under test is
    `main`'s own wiring — that the served sha is read inside the commit
    transaction and printed only for a committed run.
    """

    def _summary(self, *, committed: bool) -> SimpleNamespace:
        return SimpleNamespace(
            corpus_sha=SHA_A,
            gates=SimpleNamespace(
                documentos=1, articulos_total=1, no_articulos_total=0, over_ceiling=[]
            ),
            unidades_escritas=0,
            unidades_eliminadas=0,
            committed=committed,
            procedencia_olvidada=False,
            divergencias=[],
            claves_agregadas=[],
            claves_eliminadas=[],
            verificacion_fallida=False,
        )

    def _main(self, monkeypatch, tmp_path, *, dry_run: bool) -> int:
        rag_ingest = _load_script()
        summary = self._summary(committed=not dry_run)
        monkeypatch.setattr(rag_ingest, "ingest", lambda *a, **k: summary)
        monkeypatch.setattr(rag_ingest.repository, "corpus_activo", lambda _session: SHA_B)
        monkeypatch.setattr(rag_ingest, "create_engine", lambda _url: _NullEngine())
        argv = [
            "--corpus-path",
            str(tmp_path),
            "--corpus-sha",
            SHA_A,
            "--database-url",
            "postgresql://unused/unused",
        ]
        if dry_run:
            argv.append("--dry-run")
        return rag_ingest.main(argv)

    def test_committed_run_prints_the_served_sha(self, tmp_path, monkeypatch, capsys):
        code = self._main(monkeypatch, tmp_path, dry_run=False)

        assert code == 0
        out = capsys.readouterr().out
        assert f"corpus_sha           : {SHA_A}" in out
        assert f"served sha           : {SHA_B}" in out

    def test_uncommitted_run_prints_no_served_sha(self, tmp_path, monkeypatch, capsys):
        """A dry run has no committed state to report; printing a served sha
        there would claim serving moved when nothing was written."""
        code = self._main(monkeypatch, tmp_path, dry_run=True)

        assert code == 0
        out = capsys.readouterr().out
        assert "served sha" not in out
