"""conocimiento_004: record WHICH embedder produced a snapshot's vectors

Slice 3 read the artifact sidecar — model id, HF revision, `sintetico`, the
dump's sha256 — gated the load on parts of it, and then discarded all of it.
What reached the database was `rag_unidad.embedding` and nothing else. Three
consequences, each one a way to end up with a corpus whose vectors are not what
anyone thinks they are:

1. **The surviving pre-check is dimension-only.** `dims == 1024` passes for any
   1024-dimensional model. `intfloat/multilingual-e5-large` is 1024 and is
   prefix-asymmetric (it needs `query:` / `passage:`), so loading an e5 dump
   over a BGE-M3 corpus type-checks perfectly and degrades retrieval totally,
   with no error anywhere.
2. **`sintetico` lived only in argv.** `--allow-synthetic` let hash noise into
   the column, and once the artifact was overwritten nothing on the machine
   recorded that the vectors in the database were noise. An eval run over them
   produces a report shaped exactly like a real one.
3. **The artifact path is `vectors-{sha[:8]}.copy`.** A second batch over the
   same corpus SHA overwrites the first one's dump AND its sidecar, so "read
   the sidecar" is not a recovery path — the file that described what was
   loaded no longer exists.

So the provenance travels into the row that owns the snapshot. Five nullable
columns on `rag_corpus`, written in the SAME transaction as the `UPDATE` that
sets the vectors (`scripts/rag_load_vectors.py`): either both land or neither
does. NULL is meaningful and is the normal state after slices 1-2 — it means no
artifact was ever loaded into this snapshot, which is exactly what
`service.recuperar` must refuse to answer a vector query on.

**Nullable is what makes the downgrade honest.** Migration 003 legalized row
shapes that its own downgrade had to DELETE to restore the old constraints. This
one adds no constraint and forbids no row: dropping the five columns loses the
provenance record and nothing else — no row is deleted, no snapshot becomes
un-representable. The witness test still exists (`test_rag_migrations.py`),
because "this downgrade needs no remediation" is a claim to be verified, not
assumed (ledger R3-101's lesson, applied to the case where the answer is "none").

Revision ID: conocimiento_004
Revises: conocimiento_003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "conocimiento_004"
down_revision: Union[str, None] = "conocimiento_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rag_corpus"

#: `(name, type)` — the single source of truth for both directions, so a column
#: added here and forgotten in `downgrade()` is impossible.
PROVENANCE_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("embedding_modelo", sa.Text()),
    ("embedding_revision_hf", sa.Text()),
    ("embedding_sintetico", sa.Boolean()),
    ("embedding_artifact_sha256", sa.Text()),
    ("embeddings_loaded_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    for nombre, tipo in PROVENANCE_COLUMNS:
        op.add_column(TABLE, sa.Column(nombre, tipo, nullable=True))


def downgrade() -> None:
    """Drop the five columns. No remediation needed, and that is verified.

    Every column is nullable and carries no constraint, so no row in
    `rag_corpus`, `rag_documento` or `rag_unidad` becomes illegal below this
    revision — unlike migration 003, whose downgrade had to delete the rows its
    own upgrade had made legal. What is lost is the provenance record itself,
    which is recoverable the only way it ever was: by re-running
    `scripts/rag_load_vectors.py` with the artifact.
    """
    for nombre, _ in reversed(PROVENANCE_COLUMNS):
        op.drop_column(TABLE, nombre)
