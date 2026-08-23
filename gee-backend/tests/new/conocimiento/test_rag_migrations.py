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

import logging
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

    # PostGIS, in the throwaway database itself. `upgrade head` walks every
    # migration above the stamped head, and those are not all RAG migrations:
    # `0021_add_red_vial` creates a `geometry(LineString, 4326)` column, which
    # fails with `type "geometry" does not exist` on a database created from
    # `template1`. `conftest.py`'s `test_engine` does exactly this for the
    # shared test database; the throwaway one needs it for the same reason.
    fresh_url = _with_dbname(base_url, dbname)
    fresh_engine = create_engine(fresh_url, isolation_level="AUTOCOMMIT")
    with fresh_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    fresh_engine.dispose()
    return fresh_url, dbname


def _drop_database(base_url: str, dbname: str) -> None:
    admin_url = _with_dbname(base_url, "postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
    admin_engine.dispose()


_PRIOR_HEAD = "lluvia_v2_005"  # the head this slice's migrations chain onto

#: The target these tests upgrade to — the conocimiento chain's own head, NOT
#: ``"head"``.
#:
#: ``"head"`` was a convenience that quietly took on the prerequisites of every
#: migration anyone later stacks on top. The fixture deliberately does not replay
#: full history (``pgrouting`` is absent from the test image), so it hands those
#: later migrations a database that is *stamped* as complete while being
#: physically empty: no ``geo_jobs``, no ``canal_consorcio``, no ``tipo_geo_job``.
#: ``0021_add_red_vial`` survived that only by having no dependencies of its own;
#: ``0022_add_cruce_camino`` legitimately references all three, so under
#: ``"head"`` these tests would fail for a reason that has nothing to do with the
#: RAG migrations they exist to check. Naming the target fixes the scope to what
#: is actually under test and stops the file breaking on unrelated work. Those
#: migrations have their own real-PG tests (``test_red_vial_migration``,
#: ``test_cruce_camino_migration``), so nothing is left unchecked.
_CONOCIMIENTO_HEAD = "conocimiento_004"


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

    command.upgrade(cfg, _CONOCIMIENTO_HEAD)

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

    command.upgrade(cfg, _CONOCIMIENTO_HEAD)  # must not raise

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
    """Seed the two row shapes migration 003's upgrade made legal, SEPARATELY.

    Both are things the real pinned corpus writes: three fuente-secundaria
    documents carry no `estado_vigencia`, and five units are `anexo-normativo`.
    Migration 003's `downgrade()` remediates them with two different DELETEs, and
    the seed deliberately gives each one its **own witness**:

    * `informe` — fuente secundaria, `estado_vigencia` NULL — owns a
      `seccion-secundaria` unit, a `tipo_chunk` that is legal under the OLD
      CHECK too. Only the "units of NULL-vigencia documents" DELETE can remove
      it, so dropping that DELETE raises NotNullViolation on the document.
    * `ley-x` — derecho aplicable, `estado_vigencia` present — owns the
      `anexo-normativo` unit. Only the `tipo_chunk` DELETE can remove it, so
      dropping that DELETE raises CheckViolation when the narrower constraint
      comes back.

    The previous seed put both properties on ONE document + ONE unit, which made
    either DELETE sufficient on its own: removing the `tipo_chunk` DELETE left
    the tests green, and the finding it was written to lock down was therefore
    only incidentally covered (ledger R3-101). Verified by removing each DELETE
    in turn and watching exactly one test fail.

    `with_corpus=False` is for re-seeding after a downgrade: 003's remediation
    removes documents and units, never the `rag_corpus` snapshot row, which no
    restored constraint touches.
    """
    sha = "a" * 40
    with engine.begin() as conn:
        if with_corpus:
            conn.execute(
                text(
                    "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
                    "articulos_declarados, activo) VALUES (:sha, 'u', '2', 0, true)"
                ),
                {"sha": sha},
            )
        conn.execute(
            text(
                "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
                "jurisdiccion, estado_vigencia, clasificacion) VALUES "
                "(:sha, 'informe', 'informe-operativo', true, 'provincial', NULL, 'privado'), "
                "(:sha, 'ley-x', 'ley-provincial', false, 'provincial', 'vigente', 'privado') "
                "ON CONFLICT (corpus_sha, documento_id) DO NOTHING"
            ),
            {"sha": sha},
        )
        conn.execute(
            text(
                "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
                "texto, texto_indexado, source_file, source_offset) VALUES "
                "(:sha, 'informe#sec-1', 'informe', 'seccion-secundaria', 't', 't', 'i.md', 0), "
                "(:sha, 'ley-x#anexo', 'ley-x', 'anexo-normativo', 't', 't', 'l.md', 0)"
            ),
            {"sha": sha},
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
    command.upgrade(cfg, _CONOCIMIENTO_HEAD)
    _seed_003_shaped_rows(engine)

    command.downgrade(cfg, "conocimiento_002")  # must not raise

    with engine.connect() as conn:
        # Both units go: `informe#sec-1` because its document has no vigencia,
        # `ley-x#anexo` because `anexo-normativo` is illegal below 003.
        assert conn.execute(text("SELECT count(*) FROM rag_unidad")).scalar_one() == 0
        # …but `ley-x` itself is perfectly legal below 003 and MUST survive:
        # remediation deletes what the restored constraints forbid, never more.
        surviving = conn.execute(
            text("SELECT documento_id FROM rag_documento ORDER BY documento_id")
        ).scalars()
        assert list(surviving) == ["ley-x"]
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
    command.upgrade(cfg, _CONOCIMIENTO_HEAD)
    _seed_003_shaped_rows(engine, with_corpus=False)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM rag_unidad")).scalar_one() == 2


def _stamp_provenance(engine) -> None:
    """Write what migration 004's columns exist to hold."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE rag_corpus SET embedding_modelo = 'BAAI/bge-m3', "
                "embedding_revision_hf = 'cafe', embedding_sintetico = false, "
                "embedding_artifact_sha256 = 'deadbeef', embeddings_loaded_at = now()"
            )
        )


def test_downgrade_004_drops_provenance_and_deletes_nothing(throwaway_db):
    """RAG3-001's migration, both directions, with its own witnesses.

    Migration 003's downgrade had to DELETE the rows its upgrade legalized, and
    the seed that proved it needed one witness per DELETE (ledger R3-101). This
    one adds five nullable columns and no constraint, so the correct remediation
    is *none* — which is a claim, not an axiom. The witnesses here are therefore
    the rows: every `rag_corpus`, `rag_documento` and `rag_unidad` row present
    before the downgrade must still be there after it, and each of the five
    columns must be individually gone.
    """
    import importlib

    cfg, engine = throwaway_db
    command.upgrade(cfg, _CONOCIMIENTO_HEAD)
    _seed_003_shaped_rows(engine)
    _stamp_provenance(engine)

    modulo_004 = importlib.import_module(
        "app.db.migrations.versions.conocimiento_004_embedding_provenance"
    )
    nombres = [nombre for nombre, _ in modulo_004.PROVENANCE_COLUMNS]
    assert len(nombres) == 5

    columnas_antes = {c["name"] for c in inspect(engine).get_columns("rag_corpus")}
    assert set(nombres) <= columnas_antes

    command.downgrade(cfg, "conocimiento_003")  # must not raise

    columnas = {c["name"] for c in inspect(engine).get_columns("rag_corpus")}
    for nombre in nombres:
        assert nombre not in columnas, f"{nombre} survived the downgrade"

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM rag_corpus")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM rag_documento")).scalar_one() == 2
        assert conn.execute(text("SELECT count(*) FROM rag_unidad")).scalar_one() == 2

    # And back up: the columns return, empty. The provenance record itself is
    # gone — recoverable only by re-running the loader, which is exactly what the
    # migration docstring promises rather than pretending otherwise.
    command.upgrade(cfg, _CONOCIMIENTO_HEAD)
    with engine.connect() as conn:
        vuelta = conn.execute(
            text("SELECT embedding_modelo, embeddings_loaded_at FROM rag_corpus")
        ).first()
    assert vuelta == (None, None)


def test_downgrade_003_to_base_drops_everything_after_ingestion(throwaway_db):
    """The documented full rollback (`downgrade base`) on a used database."""
    cfg, engine = throwaway_db
    command.upgrade(cfg, _CONOCIMIENTO_HEAD)
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


#: Created at IMPORT time, which is the only ordering under which
#: `disable_existing_loggers` can bite: it disables the loggers that already
#: exist when `fileConfig` runs, and every alembic command in this file runs
#: later, from a fixture. A logger built inside the test body would be created
#: AFTER the fixture's `command.stamp` and would witness nothing.
_TESTIGO_LOGGING = logging.getLogger("tests.alembic_logging_probe")


def test_running_alembic_in_process_does_not_disable_the_apps_loggers(throwaway_db) -> None:
    """An alembic command must not silence the rest of the suite.

    Any alembic command loads `env.py`, which calls `logging.config.fileConfig`.
    That function's default is `disable_existing_loggers=True`: it sets
    `disabled = True` on every logger that already exists, process-wide, and
    permanently. From the CLI that is invisible — the process runs one migration
    and exits. In this suite it was not: this file is the first thing in the
    repo to run alembic in-process, and it silenced
    `app.shared.celery_outbox`'s logger, so two `tests/unit/test_celery_outbox.py`
    tests asserting on `caplog.text` failed with an EMPTY log — in a file the
    RAG change never touched, and ONLY when the whole `tests/` tree ran in one
    session, which is exactly what CI runs (`.github/workflows/backend.yml:129`).

    A cross-file failure between two files with no shared code is the hardest
    kind to attribute, so the guard lives next to the cause rather than next to
    the victim. The fixture is the trigger: `throwaway_db` runs `command.stamp`,
    and asking for it here is what makes this test exercise the real path
    instead of a `Config(...)` constructor that never loads `env.py` at all.
    """
    assert _TESTIGO_LOGGING.disabled is False, (
        "env.py's fileConfig disabled the existing loggers; pass disable_existing_loggers=False"
    )
    assert logging.getLogger("app.shared.celery_outbox").disabled is False
