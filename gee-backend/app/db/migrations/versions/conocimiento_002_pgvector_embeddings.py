"""Conditional pgvector embedding column on rag_unidad (dev only).

Probes `pg_available_extensions` for `vector`: absent (the default,
CI-safe pgrouting image) → logs a WARNING and no-ops; present (the
`consorcio-postgres:16-vector` derivative image, opted into via
`docker-compose.pgvector.yml`) → `CREATE EXTENSION vector`, adds the
`embedding vector(1024)` column, and builds the HNSW index.

Every statement is `IF [NOT] EXISTS`-guarded in both directions, so upgrade
and downgrade are each a no-op on the branch that did not run.

**Stranded volume: do NOT reach for `alembic downgrade`.** If this migration
no-opped on the vector-less image and the volume later moved to the vector one,
alembic has 002 recorded as applied and there is nothing left to upgrade. The
recovery is to execute `ddl.UPGRADE_STATEMENTS` DIRECTLY (design.md D7 has the
command): they are the statements below, guarded, so they need no version-table
surgery and delete nothing.

Two earlier revisions of that runbook said `alembic downgrade -1 && alembic
upgrade head` and then `alembic downgrade conocimiento_002 && alembic upgrade
head`. Both are wrong. `downgrade <rev>` reverts *to* that revision — you end up
standing AT it — so `downgrade conocimiento_002` runs 004's and 003's downgrades
and stops, leaving 002 applied: THIS FUNCTION NEVER RUNS AGAIN and the column is
still missing, while 003's downgrade has deleted rows on the way past. Verified
on a throwaway `consorcio-postgres:16-vector` container. The destructive
fallback, if one is really needed, targets `conocimiento_001`.

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
