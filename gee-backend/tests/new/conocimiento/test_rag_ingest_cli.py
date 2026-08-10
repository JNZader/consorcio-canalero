"""Ingestion CLI: pinning, idempotency, divergence (tasks 2.13, 2.14).

The pinning tests need only a git checkout. The idempotency tests need a real
PostgreSQL with the conocimiento schema, and the full-corpus ones additionally
need `RAG_CORPUS_PATH`.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.domains.conocimiento.repository import count_unidades
from app.domains.conocimiento.service import CorpusPinMismatch, verify_corpus_pin

from .conftest import PINNED_CORPUS_SHA, real_corpus_path, requires_real_corpus

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "rag_ingest.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("rag_ingest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


rag_ingest = _load_script()


def git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "corpus"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    (repo / "MANIFEST.md").write_text("# manifest\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "initial")
    return repo


def _key_set(db) -> set[str]:
    """Every citation key of the pinned snapshot — the thing a write would change."""
    return {
        row[0]
        for row in db.execute(
            text("SELECT citation_key FROM rag_unidad WHERE corpus_sha = :sha"),
            {"sha": PINNED_CORPUS_SHA},
        ).all()
    }


def head_of(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


class TestCorpusPinning:
    def test_pin_matches_clean_tree_is_accepted(self, tiny_repo):
        assert verify_corpus_pin(tiny_repo, head_of(tiny_repo)) == head_of(tiny_repo)

    def test_unresolvable_sha_aborts_before_writing(self, tiny_repo):
        """A wrong pin must fail before the transaction ever opens."""
        with pytest.raises(CorpusPinMismatch, match="but"):
            verify_corpus_pin(tiny_repo, "0" * 40)

    def test_dirty_tree_refused(self, tiny_repo):
        """A modified tree could rewrite a snapshot's content while its
        corpus_sha stayed the same, leaving no trace (design.md D2)."""
        (tiny_repo / "MANIFEST.md").write_text("# tampered\n", encoding="utf-8")
        with pytest.raises(CorpusPinMismatch, match="uncommitted"):
            verify_corpus_pin(tiny_repo, head_of(tiny_repo))

    def test_untracked_file_also_counts_as_dirty(self, tiny_repo):
        (tiny_repo / "extra.md").write_text("stray\n", encoding="utf-8")
        with pytest.raises(CorpusPinMismatch, match="uncommitted"):
            verify_corpus_pin(tiny_repo, head_of(tiny_repo))

    def test_non_git_directory_refused(self, tmp_path):
        with pytest.raises(CorpusPinMismatch, match="not a git checkout"):
            verify_corpus_pin(tmp_path, "0" * 40)

    def test_bad_pin_writes_nothing(self, tiny_repo, db):
        """The ordering guarantee, asserted against a real database."""
        before = db.execute(text("SELECT count(*) FROM rag_unidad")).scalar_one()
        with pytest.raises(CorpusPinMismatch):
            rag_ingest.ingest(db, tiny_repo, "0" * 40)
        assert db.execute(text("SELECT count(*) FROM rag_unidad")).scalar_one() == before


class TestMainEntryPoint:
    """`main()` through the real argparse entry — the surface an operator uses.

    Every exit code below was previously unexercised: the suite called `ingest()`
    directly, so argument handling, the abort branches, the exit codes and the
    printed report were all untested (ledger RAG2-006).
    """

    def test_missing_database_url_exits_2(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        code = rag_ingest.main(["--corpus-path", str(tmp_path), "--corpus-sha", "0" * 40])
        assert code == 2
        assert "--database-url" in capsys.readouterr().err

    def test_pin_mismatch_exits_1_without_touching_a_database(self, tiny_repo, capsys):
        """A wrong pin aborts before the transaction — `--dry-run` proves no DB
        is even reachable when it does."""
        code = rag_ingest.main(
            ["--corpus-path", str(tiny_repo), "--corpus-sha", "0" * 40, "--dry-run"]
        )
        assert code == 1
        err = capsys.readouterr().err
        assert "INGESTION ABORTED — nothing was written." in err

    def test_missing_declared_document_exits_1(self, tiny_repo, capsys):
        """HEAD resolves and the tree is clean, but it is not the pinned corpus.

        `load_corpus` iterates the declared documents and aborts on the first one
        the checkout does not contain — so this is the branch a clean-but-wrong
        checkout actually takes, ahead of the `corpus_sha` comparison.
        """
        code = rag_ingest.main(
            ["--corpus-path", str(tiny_repo), "--corpus-sha", head_of(tiny_repo), "--dry-run"]
        )
        assert code == 1
        err = capsys.readouterr().err
        assert "INGESTION ABORTED — nothing was written." in err
        assert "declared in expectations but missing" in err

    def test_verify_unchanged_difference_exits_1_and_names_all_three_classes(
        self, tmp_path, monkeypatch, capsys
    ):
        """The report must distinguish modified, added and removed keys.

        `ingest` is stubbed here on purpose: the no-write guarantee itself is
        asserted against a real database in `TestFullCorpusIngestion`, while what
        this test owns is `main()`'s own wiring — that a failed verification
        becomes exit 1 and a report naming each class, rather than exit 0.
        """
        summary = SimpleNamespace(
            corpus_sha="a" * 40,
            gates=SimpleNamespace(
                documentos=1, articulos_total=1, no_articulos_total=0, over_ceiling=[]
            ),
            unidades_escritas=0,
            unidades_eliminadas=0,
            committed=False,
            divergencias=["d#1"],
            claves_agregadas=["d#2"],
            claves_eliminadas=["d#3"],
            verificacion_fallida=True,
        )
        monkeypatch.setattr(rag_ingest, "ingest", lambda *a, **k: summary)
        monkeypatch.setattr(rag_ingest, "create_engine", lambda url: _NullEngine())

        code = rag_ingest.main(
            [
                "--corpus-path",
                str(tmp_path),
                "--corpus-sha",
                "a" * 40,
                "--database-url",
                "postgresql://unused/unused",
                "--verify-unchanged",
            ]
        )

        assert code == 1
        err = capsys.readouterr().err
        assert "VERIFICACIÓN FALLIDA" in err
        assert "contenido modificado" in err and "d#1" in err
        assert "claves agregadas" in err and "d#2" in err
        assert "claves eliminadas" in err and "d#3" in err


class _NullEngine:
    """Stands in for a SQLAlchemy Engine in `main()` tests that never query."""

    def dispose(self) -> None:
        return None


@requires_real_corpus
class TestMainAgainstRealCorpus:
    """`main()` over the pinned corpus, `--dry-run` so no database is needed."""

    def test_dry_run_over_the_real_corpus_exits_0(self, capsys):
        code = rag_ingest.main(
            [
                "--corpus-path",
                str(real_corpus_path()),
                "--corpus-sha",
                PINNED_CORPUS_SHA,
                "--dry-run",
            ]
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "articulo units       : 1383" in out
        assert "committed            : False" in out

    def test_over_ceiling_units_reach_the_printed_report(self, capsys):
        """RAG2-004: `over_ceiling` was populated and then reached no output.

        Its own docstring promised "always reported — never silently dropped",
        while nothing carried it out of the dataclass: not `GateOutcome`, not
        `IngestionSummary`, not this printout.
        """
        rag_ingest.main(
            [
                "--corpus-path",
                str(real_corpus_path()),
                "--corpus-sha",
                PINNED_CORPUS_SHA,
                "--dry-run",
            ]
        )
        out = capsys.readouterr().out
        assert "SOBRE EL CEILING DE EMBEDDING" in out
        assert "10593#1" in out and "8560#5" in out
        assert "FTS" in out, "the report must say these units stay retrievable"
        assert "nunca truncadas" in out

    def test_strict_token_ceiling_turns_them_into_a_hard_abort(self, capsys):
        """The opt-in flag is the only thing that promotes reporting to failing."""
        code = rag_ingest.main(
            [
                "--corpus-path",
                str(real_corpus_path()),
                "--corpus-sha",
                PINNED_CORPUS_SHA,
                "--dry-run",
                "--strict-token-ceiling",
            ]
        )
        assert code == 1
        err = capsys.readouterr().err
        assert "INGESTION ABORTED — nothing was written." in err
        assert "truncate" in err


@requires_real_corpus
class TestFullCorpusIngestion:
    def test_ingests_every_declared_unit(self, db):
        summary = rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        assert summary.committed
        assert summary.gates.ok
        assert summary.gates.articulos_total == 1383
        assert summary.unidades_escritas == 1383 + summary.gates.no_articulos_total
        assert count_unidades(db, PINNED_CORPUS_SHA, "articulo") == 1383

    def test_vigencia_canary_row_exists_after_ingestion(self, db):
        """The gold set's T-1/T-2 canaries require this row to exist."""
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        row = db.execute(
            text(
                "SELECT tipo_chunk, documento_id FROM rag_unidad "
                "WHERE corpus_sha = :sha AND citation_key = :key"
            ),
            {"sha": PINNED_CORPUS_SHA, "key": "10679#vigencia-de-los-fondos"},
        ).first()
        assert row is not None, "10679#vigencia-de-los-fondos must exist after ingestion"
        assert row[0] == "nota-vigencia"

    def test_idempotent_rerun_same_sha(self, db):
        """Same SHA in, byte-identical DB state out.

        The projection is the WHOLE row, not a chosen subset: `epigrafe`,
        `documento_id` and `source_file` were outside the old comparison, so a
        re-run that rewrote any of them satisfied the determinism assertion
        while changing the database (ledger RAG2-006). `tsv` is included because
        it is what FTS actually searches — a generated column that drifted would
        change retrieval with every other column identical. `rag_unidad` carries
        no timestamp or serial, so nothing has to be excluded.
        """
        first = rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        snapshot_sql = text(
            "SELECT corpus_sha, citation_key, documento_id, tipo_chunk, epigrafe, "
            "texto, texto_indexado, source_file, source_offset, tsv "
            "FROM rag_unidad WHERE corpus_sha = :sha ORDER BY citation_key"
        )
        before = db.execute(snapshot_sql, {"sha": PINNED_CORPUS_SHA}).all()

        second = rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        after = db.execute(snapshot_sql, {"sha": PINNED_CORPUS_SHA}).all()

        assert second.unidades_escritas == first.unidades_escritas
        assert second.unidades_eliminadas == 0
        assert after == before
        assert len(after) == 1383 + second.gates.no_articulos_total == 1448
        citation_keys = [row[1] for row in after]
        assert len(citation_keys) == len(set(citation_keys))

    def test_removed_unit_is_pruned_not_left_stale(self, db):
        """`ON CONFLICT DO UPDATE` alone is additive; a vanished unit would
        otherwise keep answering queries forever."""
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        db.execute(
            text(
                "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, "
                "tipo_chunk, texto, texto_indexado, source_file, source_offset) "
                "VALUES (:sha, 'ghost#1', 'ley-9750-consorcios-canaleros', "
                "'articulo', 'stale', 'stale', 'ghost.md', 0)"
            ),
            {"sha": PINNED_CORPUS_SHA},
        )
        summary = rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        assert summary.unidades_eliminadas == 1
        remaining = db.execute(
            text("SELECT 1 FROM rag_unidad WHERE corpus_sha = :sha AND citation_key = 'ghost#1'"),
            {"sha": PINNED_CORPUS_SHA},
        ).first()
        assert remaining is None

    def test_verify_unchanged_reports_divergence_instead_of_overwriting(self, db):
        """A re-emitted corpus that reused a SHA is the one case the upsert
        would rewrite without leaving a trace."""
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        db.execute(
            text(
                "UPDATE rag_unidad SET texto = 'CONTENIDO DIVERGENTE' "
                "WHERE corpus_sha = :sha AND citation_key = '9750#3'"
            ),
            {"sha": PINNED_CORPUS_SHA},
        )

        summary = rag_ingest.ingest(
            db, real_corpus_path(), PINNED_CORPUS_SHA, verify_unchanged=True
        )
        assert summary.divergencias == ["9750#3"]
        assert not summary.committed
        # Reported, NOT overwritten.
        texto = db.execute(
            text(
                "SELECT texto FROM rag_unidad WHERE corpus_sha = :sha AND citation_key = '9750#3'"
            ),
            {"sha": PINNED_CORPUS_SHA},
        ).scalar_one()
        assert texto == "CONTENIDO DIVERGENTE"

    def test_verify_unchanged_reports_removed_keys_and_writes_nothing(self, db):
        """RAG2-003: the flag compared only the key INTERSECTION.

        A key present in the database and absent from the new parse is not a
        hash mismatch, so it produced no divergence — and the run fell straight
        through to the upserts and `prune_unidades`, which DELETED it. The
        report then said `divergencias: []`, the transaction committed and the
        exit code was 0: the one operation the flag exists to prevent, performed
        silently, on rows it never even examined.
        """
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        db.execute(
            text(
                "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, "
                "tipo_chunk, texto, texto_indexado, source_file, source_offset) "
                "VALUES (:sha, 'ghost#1', 'ley-9750-consorcios-canaleros', "
                "'articulo', 'stale', 'stale', 'ghost.md', 0)"
            ),
            {"sha": PINNED_CORPUS_SHA},
        )
        before = _key_set(db)

        summary = rag_ingest.ingest(
            db, real_corpus_path(), PINNED_CORPUS_SHA, verify_unchanged=True
        )

        assert summary.claves_eliminadas == ["ghost#1"]
        assert summary.divergencias == []
        assert summary.claves_agregadas == []
        assert summary.verificacion_fallida
        assert not summary.committed
        assert summary.unidades_eliminadas == 0, "nothing may be pruned under the flag"
        assert _key_set(db) == before, "the row set must be untouched"

    def test_verify_unchanged_reports_added_keys_and_writes_nothing(self, db):
        """The mirror case: a key the parse produces that the snapshot lacks."""
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        db.execute(
            text("DELETE FROM rag_unidad WHERE corpus_sha = :sha AND citation_key = '9750#3'"),
            {"sha": PINNED_CORPUS_SHA},
        )
        before = _key_set(db)

        summary = rag_ingest.ingest(
            db, real_corpus_path(), PINNED_CORPUS_SHA, verify_unchanged=True
        )

        assert summary.claves_agregadas == ["9750#3"]
        assert summary.claves_eliminadas == []
        assert summary.divergencias == []
        assert not summary.committed
        assert _key_set(db) == before

    def test_verify_unchanged_reports_the_three_classes_separately(self, db):
        """Added, removed and content-changed are distinct facts, not one blob."""
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        db.execute(
            text(
                "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, "
                "tipo_chunk, texto, texto_indexado, source_file, source_offset) "
                "VALUES (:sha, 'ghost#1', 'ley-9750-consorcios-canaleros', "
                "'articulo', 'stale', 'stale', 'ghost.md', 0)"
            ),
            {"sha": PINNED_CORPUS_SHA},
        )
        db.execute(
            text("DELETE FROM rag_unidad WHERE corpus_sha = :sha AND citation_key = '9750#3'"),
            {"sha": PINNED_CORPUS_SHA},
        )
        db.execute(
            text(
                "UPDATE rag_unidad SET texto = 'CONTENIDO DIVERGENTE' "
                "WHERE corpus_sha = :sha AND citation_key = '9750#4'"
            ),
            {"sha": PINNED_CORPUS_SHA},
        )
        before = _key_set(db)

        summary = rag_ingest.ingest(
            db, real_corpus_path(), PINNED_CORPUS_SHA, verify_unchanged=True
        )

        assert summary.claves_eliminadas == ["ghost#1"]
        assert summary.claves_agregadas == ["9750#3"]
        assert summary.divergencias == ["9750#4"]
        assert _key_set(db) == before

    def test_verify_unchanged_on_an_identical_snapshot_still_commits(self, db):
        """The flag must not turn a genuinely unchanged re-run into a failure."""
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        summary = rag_ingest.ingest(
            db, real_corpus_path(), PINNED_CORPUS_SHA, verify_unchanged=True
        )
        assert not summary.verificacion_fallida
        assert summary.committed

    def test_verify_unchanged_is_off_by_default(self, db):
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        db.execute(
            text(
                "UPDATE rag_unidad SET texto = 'CONTENIDO DIVERGENTE' "
                "WHERE corpus_sha = :sha AND citation_key = '9750#3'"
            ),
            {"sha": PINNED_CORPUS_SHA},
        )
        summary = rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        assert summary.divergencias == []
        assert summary.committed

    def test_dry_run_writes_nothing(self, db):
        summary = rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA, dry_run=True)
        assert not summary.committed
        assert summary.gates.ok
        assert count_unidades(db, PINNED_CORPUS_SHA) == 0

    def test_relevancia_consorcio_survives_to_the_database(self, db):
        """The do-not-cite warning must be queryable, not just parsed."""
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        row = db.execute(
            text(
                "SELECT es_secundaria, relevancia_consorcio FROM rag_documento "
                "WHERE corpus_sha = :sha AND documento_id = :doc"
            ),
            {
                "sha": PINNED_CORPUS_SHA,
                "doc": "resolucion-4-2026-bioagroindustria-reglamento-11059",
            },
        ).first()
        assert row is not None
        assert row[0] is False, "derecho aplicable by tipo"
        assert "NO DERECHO APLICABLE AL CONSORCIO CANALERO" in row[1]

    def test_every_document_has_jurisdiccion(self, db):
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        missing = db.execute(
            text(
                "SELECT count(*) FROM rag_documento WHERE corpus_sha = :sha "
                "AND (jurisdiccion IS NULL OR jurisdiccion = '')"
            ),
            {"sha": PINNED_CORPUS_SHA},
        ).scalar_one()
        assert missing == 0

    def test_derecho_aplicable_always_carries_estado_vigencia(self, db):
        """The scoped CHECK from migration conocimiento_003, asserted for real."""
        rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        offenders = db.execute(
            text(
                "SELECT count(*) FROM rag_documento WHERE corpus_sha = :sha "
                "AND es_secundaria = false AND estado_vigencia IS NULL"
            ),
            {"sha": PINNED_CORPUS_SHA},
        ).scalar_one()
        assert offenders == 0
