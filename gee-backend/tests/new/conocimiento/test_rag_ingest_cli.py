"""Ingestion CLI: pinning, idempotency, divergence (tasks 2.13, 2.14).

The pinning tests need only a git checkout. The idempotency tests need a real
PostgreSQL with the conocimiento schema, and the full-corpus ones additionally
need `RAG_CORPUS_PATH`.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

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
        """Same SHA in, byte-identical DB state out (modulo timestamps)."""
        first = rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        snapshot_sql = text(
            "SELECT citation_key, tipo_chunk, texto, texto_indexado, source_offset "
            "FROM rag_unidad WHERE corpus_sha = :sha ORDER BY citation_key"
        )
        before = db.execute(snapshot_sql, {"sha": PINNED_CORPUS_SHA}).all()

        second = rag_ingest.ingest(db, real_corpus_path(), PINNED_CORPUS_SHA)
        after = db.execute(snapshot_sql, {"sha": PINNED_CORPUS_SHA}).all()

        assert second.unidades_escritas == first.unidades_escritas
        assert second.unidades_eliminadas == 0
        assert after == before
        assert len(after) == len({row[0] for row in after})

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
