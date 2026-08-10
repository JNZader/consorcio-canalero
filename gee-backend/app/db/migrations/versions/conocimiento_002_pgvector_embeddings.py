"""Conditional pgvector embedding column on rag_unidad (dev only).

Probes `pg_available_extensions` for `vector`: absent (the default,
CI-safe pgrouting image) → logs a WARNING and no-ops; present (the
`consorcio-postgres:16-vector` derivative image, opted into via
`docker-compose.pgvector.yml`) → `CREATE EXTENSION vector`, adds the
`embedding vector(1024)` column, and builds the HNSW index.

Every statement is `IF [NOT] EXISTS`-guarded in both directions, so upgrade
and downgrade are each a no-op on the branch that did not run — see
design.md D7 for the stranded-volume recovery this makes possible
(`alembic downgrade -1 && alembic upgrade head` after switching images).

Revision ID: conocimiento_002
Revises: conocimiento_001
Create Date: 2026-08-10
"""

import logging
from typing import Sequence, Union

from alembic import op

from app.domains.conocimiento import ddl

revision: str = "conocimiento_002"
down_revision: Union[str, None] = "conocimiento_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    bind = op.get_bind()
    if not ddl.extension_available(bind):
        logger.warning(
            "conocimiento_002: 'vector' extension not available on this "
            "Postgres image — skipping the embedding column and HNSW "
            "index. This is expected on the default pgrouting image; the "
            "vector column only exists on consorcio-postgres:16-vector "
            "(docker-compose.pgvector.yml), which is dev-only and opt-in."
        )
        return
    for statement in ddl.UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Every statement is IF [NOT] EXISTS-guarded at the SQL level, so this
    # is safe to run unconditionally: a no-op on an image that never had
    # the extension, a real drop on one that did (design.md D7).
    for statement in ddl.DOWNGRADE_STATEMENTS:
        op.execute(statement)
