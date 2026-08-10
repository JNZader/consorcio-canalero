"""Single source of truth for the conditional pgvector embedding DDL.

Both migration `conocimiento_002_pgvector_embeddings` and the test fixtures
in `tests/new/conftest.py` import these statements instead of duplicating
them, so the schema tests probe against is guaranteed identical to the
schema the migration actually produces (design.md D7, "DDL drift").

The embedding column is dev-only (design.md D3/D7): it lives outside
`models.py`'s SQLAlchemy mapping entirely, and every statement here is
`IF [NOT] EXISTS`-guarded in both directions so upgrade/downgrade are safe
to call repeatedly and safe to call on an image that never had the `vector`
extension available at all.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

EXTENSION_NAME = "vector"
EMBEDDING_TABLE = "rag_unidad"
EMBEDDING_COLUMN = "embedding"
EMBEDDING_DIMENSIONS = 1024
HNSW_INDEX_NAME = "ix_rag_unidad_embedding_hnsw"

# `pg_available_extensions` lists what the Postgres *image* could install
# (PGDG package present), regardless of whether `CREATE EXTENSION` has run
# yet in this specific database. That is the distinction migration 002's
# probe cares about: "is this server capable of vector at all", not
# "is vector currently active in this database" (design.md D7).
PROBE_EXTENSION_AVAILABLE_SQL = "SELECT 1 FROM pg_available_extensions WHERE name = :extension_name"

# Order matters: extension before column, column before index.
UPGRADE_STATEMENTS: tuple[str, ...] = (
    f"CREATE EXTENSION IF NOT EXISTS {EXTENSION_NAME}",
    f"ALTER TABLE {EMBEDDING_TABLE} ADD COLUMN IF NOT EXISTS "
    f"{EMBEDDING_COLUMN} vector({EMBEDDING_DIMENSIONS})",
    f"CREATE INDEX IF NOT EXISTS {HNSW_INDEX_NAME} ON {EMBEDDING_TABLE} "
    f"USING hnsw ({EMBEDDING_COLUMN} vector_cosine_ops) "
    f"WITH (m = 16, ef_construction = 64)",
)

# Reverse order of UPGRADE_STATEMENTS: the index depends on the column, the
# column's type depends on the extension. Every statement is IF EXISTS —
# safe to run unconditionally, including on an image that never installed
# the extension at all (design.md D7 guard symmetry).
DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    f"DROP INDEX IF EXISTS {HNSW_INDEX_NAME}",
    f"ALTER TABLE {EMBEDDING_TABLE} DROP COLUMN IF EXISTS {EMBEDDING_COLUMN}",
    f"DROP EXTENSION IF EXISTS {EXTENSION_NAME}",
)


def extension_available(connection: Connection) -> bool:
    """Probe whether the `vector` extension is installable on this server.

    True if `CREATE EXTENSION vector` would succeed (the extension is
    present in `pg_available_extensions`); False on the default, CI-safe
    pgrouting image where the PGDG package was never installed. Never
    raises — a probe that could fail defeats the point of probing.
    """
    row = connection.execute(
        text(PROBE_EXTENSION_AVAILABLE_SQL), {"extension_name": EXTENSION_NAME}
    ).first()
    return row is not None
