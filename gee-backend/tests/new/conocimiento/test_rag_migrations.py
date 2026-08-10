"""Tests for the conocimiento (RAG) Alembic migrations.

These run `alembic upgrade`/`downgrade` against a throwaway, empty database
on the SAME Postgres server the rest of the suite uses — never against the
shared `test_engine` fixture's database. That database's tables are built
via `Base.metadata.create_all()` (see `test_create_all_unaffected_by_
conocimiento_models` below), which already contains `rag_corpus` /
`rag_documento` / `rag_unidad`: running migration 001's `op.create_table`
against it would collide on "relation already exists". A fresh database
per migration test avoids that collision entirely and also proves the
migration path works standalone, the way a real deploy runs it.
"""

from __future__ import annotations

import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.config import settings
from app.core.health import ALEMBIC_INI_PATH
from app.domains.conocimiento import ddl

# Importing the models module registers RagCorpus/RagDocumento/RagUnidad on
# the shared `Base.metadata` at collection time (pytest imports every test
# module before running any fixture), which is what makes
# `test_create_all_unaffected_by_conocimiento_models` below a real
# assertion rather than an accident of import order.
from app.domains.conocimiento import models as conocimiento_models  # noqa: F401


def _with_dbname(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


def _create_throwaway_database(base_url: str) -> tuple[str, str]:
    """Create an empty database on the same server as ``base_url``.

    Returns (new_database_url, database_name). CREATE DATABASE cannot run
    inside a transaction block, so the admin connection is opened in
    autocommit mode.
    """
    dbname = f"test_rag_migrations_{uuid.uuid4().hex[:8]}"
    admin_url = _with_dbname(base_url, "postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    admin_engine.dispose()
    return _with_dbname(base_url, dbname), dbname


def _drop_database(base_url: str, dbname: str) -> None:
    admin_url = _with_dbname(base_url, "postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
    admin_engine.dispose()


_PRIOR_HEAD = "lluvia_v2_005"  # the head this slice's migrations chain onto


@pytest.fixture
def throwaway_db(monkeypatch):
    """A fresh database, stamped at the pre-conocimiento head, + an Alembic
    Config pointed at it.

    Deliberately does NOT replay the full migration history from empty.
    `w7r4s5t6u593_add_pgrouting_canal_network.py` (an existing, unrelated
    migration) runs `CREATE EXTENSION pgrouting` unconditionally — fine on
    the production image (`pgrouting/pgrouting:...`) but absent on the
    default *test* image (`postgis/postgis:16-3.4`), which has never
    needed it because every other test builds its schema via
    `Base.metadata.create_all()`, not by replaying migrations. Since
    `rag_corpus`/`rag_documento`/`rag_unidad` have zero FK dependency on
    any pre-existing table, `alembic stamp` at the prior head is
    sufficient and correctly scoped: it exercises exactly this slice's two
    migrations without depending on an environment gap in unrelated,
    pre-existing migration history.

    `env.py` reads `settings.database_sync_url`, which is derived from
    `settings.database_url` — so pointing Alembic at the throwaway
    database is a matter of monkeypatching that one field; `monkeypatch`
    restores it automatically at teardown.
    """
    fresh_url, dbname = _create_throwaway_database(settings.database_url)
    monkeypatch.setattr(settings, "database_url", fresh_url)

    cfg = Config(str(ALEMBIC_INI_PATH))
    command.stamp(cfg, _PRIOR_HEAD)
    engine = create_engine(fresh_url)

    yield cfg, engine

    engine.dispose()
    _drop_database(settings.database_url, dbname)


def test_upgrade_head_creates_three_tables(throwaway_db):
    """1.1: `alembic upgrade head` on an empty DB creates all three tables."""
    cfg, engine = throwaway_db

    command.upgrade(cfg, "head")

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert {"rag_corpus", "rag_documento", "rag_unidad"} <= table_names

    corpus_pk = inspector.get_pk_constraint("rag_corpus")
    assert corpus_pk["constrained_columns"] == ["corpus_sha"]

    unidad_pk = inspector.get_pk_constraint("rag_unidad")
    assert set(unidad_pk["constrained_columns"]) == {"corpus_sha", "citation_key"}

    unidad_columns = {c["name"] for c in inspector.get_columns("rag_unidad")}
    assert "tsv" in unidad_columns
    # `embedding` presence tracks the LIVE environment's pgvector
    # availability, never a hardcoded assumption: this test also runs
    # (unmarked, undeselected) under `TEST_POSTGRES_IMAGE=consorcio-
    # postgres:16-vector`, where migration 002 legitimately adds the
    # column. Hardcoding "always absent" here previously broke the full
    # suite the moment it ran against the vector image (caught by running
    # `pytest tests/new/ -q` under that image as part of this slice's own
    # verification, before wiring `make test-rag`).
    with engine.connect() as conn:
        expect_embedding = ddl.extension_available(conn)
    assert ("embedding" in unidad_columns) == expect_embedding

    gin_indexes = [
        ix for ix in inspector.get_indexes("rag_unidad") if ix["name"] == "ix_rag_unidad_tsv"
    ]
    assert len(gin_indexes) == 1


def test_migration_002_noop_on_vector_less_image(throwaway_db):
    """1.3: on the default (vector-less) test image, 002 no-ops without raising.

    `alembic upgrade head` includes migration 002. On the pgrouting-only
    image used by the rest of this suite (no PGDG pgvector package), the
    `pg_available_extensions` probe finds nothing, so 002 must WARN and
    no-op rather than raise `relation "vector" does not exist` or similar.

    This test is specifically ABOUT the vector-less branch (its vector-
    image counterpart is `test_migration_002_guard_symmetry_on_vector_image`
    below) — it skips itself under `TEST_POSTGRES_IMAGE=consorcio-
    postgres:16-vector` instead of asserting a false expectation there.
    """
    cfg, engine = throwaway_db

    with engine.connect() as conn:
        if ddl.extension_available(conn):
            pytest.skip(
                "This test is specifically about the vector-less no-op "
                "branch; the vector-image equivalent is "
                "test_migration_002_guard_symmetry_on_vector_image."
            )

    command.upgrade(cfg, "head")  # must not raise

    inspector = inspect(engine)
    unidad_columns = {c["name"] for c in inspector.get_columns("rag_unidad")}
    assert "embedding" not in unidad_columns

    # Downgrading the whole chain back past conocimiento_001 must also be a
    # no-op for 002's half (nothing to drop) and must not raise.
    command.downgrade(cfg, "lluvia_v2_005")

    remaining_tables = set(inspect(engine).get_table_names())
    assert "rag_corpus" not in remaining_tables
    assert "rag_documento" not in remaining_tables
    assert "rag_unidad" not in remaining_tables


def test_unresolvable_head_does_not_apply_partial_state(throwaway_db):
    """Companion boundary check: a bad target revision fails before any DDL commits.

    Not itself one of the two named RED→GREEN tests, but exercises the same
    throwaway-DB fixture with a distinct, real assertion: Alembic raises on
    an unknown revision and the database is left with zero conocimiento
    tables — never a half-migrated state.
    """
    cfg, engine = throwaway_db

    with pytest.raises(Exception):
        command.upgrade(cfg, "conocimiento_999_does_not_exist")

    table_names = set(inspect(engine).get_table_names())
    assert "rag_corpus" not in table_names
    assert "rag_unidad" not in table_names


def _seed_003_shaped_rows(engine, *, with_corpus: bool = True) -> None:
    """Seed exactly the two row shapes migration 003's upgrade made legal.

    Both are things the real pinned corpus writes: three fuente-secundaria
    documents carry no `estado_vigencia`, and four units are `anexo-normativo`.

    `with_corpus=False` is for re-seeding after a downgrade: 003's remediation
    removes documents and units, never the `rag_corpus` snapshot row, which no
    restored constraint touches.
    """
    with engine.begin() as conn:
        if with_corpus:
            conn.execute(
                text(
                    "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
                    "articulos_declarados, activo) VALUES (:sha, 'u', '2', 0, true)"
                ),
                {"sha": "a" * 40},
            )
        conn.execute(
            text(
                "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
                "jurisdiccion, estado_vigencia, clasificacion) VALUES "
                "(:sha, 'informe', 'informe-operativo', true, 'provincial', NULL, 'privado')"
            ),
            {"sha": "a" * 40},
        )
        conn.execute(
            text(
                "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
                "texto, texto_indexado, source_file, source_offset) VALUES "
                "(:sha, 'informe#anexo', 'informe', 'anexo-normativo', 't', 't', 'f.md', 0)"
            ),
            {"sha": "a" * 40},
        )


def test_downgrade_003_runs_against_an_ingested_database(throwaway_db):
    """RAG2-002: `alembic downgrade` must work on a database that was USED.

    003's upgrade relaxed `estado_vigencia` to nullable and widened the
    `tipo_chunk` CHECK; the corpus then wrote rows that only the relaxed schema
    admits. Restoring both constraints with those rows still present raises
    NotNullViolation / CheckViolation, so every documented rollback path —
    `downgrade -1`, `downgrade base`, proposal.md's ordering, the compose
    header, `make` — was unrunnable the moment the corpus had been ingested
    once. Downgrades run newest-first, so this fires before 001 drops the
    tables and takes the whole chain with it.
    """
    cfg, engine = throwaway_db
    command.upgrade(cfg, "head")
    _seed_003_shaped_rows(engine)

    command.downgrade(cfg, "conocimiento_002")  # must not raise

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM rag_documento")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM rag_unidad")).scalar_one() == 0
        # The snapshot row survives: no restored constraint touches rag_corpus,
        # so remediation must not widen into deleting what it does not have to.
        assert conn.execute(text("SELECT count(*) FROM rag_corpus")).scalar_one() == 1
        nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns WHERE "
                "table_name = 'rag_documento' AND column_name = 'estado_vigencia'"
            )
        ).scalar_one()
    assert nullable == "NO", "the blanket NOT NULL must be back after downgrading past 003"

    # And the round trip closes: re-upgrading restores the relaxed schema, so
    # re-ingesting the pinned corpus rebuilds what the downgrade deleted.
    command.upgrade(cfg, "head")
    _seed_003_shaped_rows(engine, with_corpus=False)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM rag_unidad")).scalar_one() == 1


def test_downgrade_003_to_base_drops_everything_after_ingestion(throwaway_db):
    """The documented full rollback (`downgrade base`) on a used database."""
    cfg, engine = throwaway_db
    command.upgrade(cfg, "head")
    _seed_003_shaped_rows(engine)

    command.downgrade(cfg, _PRIOR_HEAD)  # must not raise

    remaining = set(inspect(engine).get_table_names())
    assert {"rag_corpus", "rag_documento", "rag_unidad"}.isdisjoint(remaining)


def test_create_all_unaffected_by_conocimiento_models(test_engine):
    """1.9: `Base.metadata.create_all` on the vector-less test image succeeds
    and never creates an `embedding` column anywhere.

    `test_engine` is the SAME session-scoped fixture every other test in
    the suite (1917+ tests as of this change) relies on. If mapping
    `embedding` on `RagUnidad` broke `create_all` on the default PostGIS
    image, the entire suite would fail at session setup, not just this
    test — this assertion is the narrow, named proof of design.md D7's
    core claim.
    """
    inspector = inspect(test_engine)
    table_names = set(inspector.get_table_names())
    assert {"rag_corpus", "rag_documento", "rag_unidad"} <= table_names

    for table in ("rag_corpus", "rag_documento", "rag_unidad"):
        columns = {c["name"] for c in inspector.get_columns(table)}
        assert "embedding" not in columns, f"{table} must never map the vector column"


@pytest.mark.pgvector
def test_migration_002_guard_symmetry_on_vector_image(throwaway_db):
    """1.4: on the vector-enabled image, upgrade/downgrade repeated twice
    each are no-ops after the first — none of the four calls raises.

    Calls migration 002's `upgrade()`/`downgrade()` functions directly
    (bound via `alembic.operations.Operations.context`) so the guard
    symmetry is exercised independently of Alembic's own version-table
    bookkeeping, which would otherwise refuse to "downgrade" a revision
    that is not the current one.
    """
    import importlib

    cfg, engine = throwaway_db
    command.upgrade(cfg, "conocimiento_001")  # tables exist, no embedding column yet

    module_002 = importlib.import_module(
        "app.db.migrations.versions.conocimiento_002_pgvector_embeddings"
    )

    with engine.connect() as conn:
        assert ddl.extension_available(conn) is True, (
            "This test is marked pgvector and must only run against "
            "consorcio-postgres:16-vector; the extension_available probe "
            "should be True here."
        )
        migration_ctx = MigrationContext.configure(conn)
        op_ctx = Operations(migration_ctx)
        with Operations.context(op_ctx):
            module_002.upgrade()
            module_002.upgrade()  # idempotent — must not raise
            module_002.downgrade()
            module_002.downgrade()  # idempotent — must not raise
            module_002.upgrade()  # leave the DB in the "head" shape
        conn.commit()

    inspector = inspect(engine)
    unidad_columns = {c["name"] for c in inspector.get_columns("rag_unidad")}
    assert "embedding" in unidad_columns

    hnsw_indexes = [
        ix for ix in inspector.get_indexes("rag_unidad") if ix["name"] == ddl.HNSW_INDEX_NAME
    ]
    assert len(hnsw_indexes) == 1
