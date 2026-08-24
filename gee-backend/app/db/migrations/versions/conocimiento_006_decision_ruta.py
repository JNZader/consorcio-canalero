"""conocimiento_006: the routing decision record

`rag_decision_ruta` — `(pregunta, clase, margen, umbral_vigente, ts)` plus the
surface and the motive, in the box's own Postgres (design.md:188-196,
`knowledge-question-routing` spec:85 and its scenario at :94-98).

**Why the question is a plain `text` column and not a digest.** The spec's
scenario is "a CD member reports that an operational question was answered
instead of redirected; the routing record is inspected; it shows the question,
the class assigned and the confidence". A hash satisfies none of that —
reconstructing a question from its hash is the thing hashes exist to prevent, so
a hashed column would be a record that cannot answer the only question it was
built to answer. This is not a Privacy Boundary regression: that boundary
governs what LEAVES the deployment, and this table never does. The constraints
that keep it that way are retention (90 days, ratified — tasks.md 0.6), an
admin-only read surface (G5), and the eval harness never reading this table.

**Why `superficie` is nullable and the CHECK admits NULL.** `legal` is the one
class that redirects nowhere: it proceeds to retrieval. A NOT NULL column would
force a sentinel surface onto every answered question, and a sentinel that looks
like a surface is exactly the fabricated-redirect shape the whole router is
arranged against.

**Why this revises `conocimiento_005`.** It is the tree's current single head
(verified before writing this file). Migration 005's docstring records what
happens otherwise: a second child on an already-parented revision forks the
tree, `alembic upgrade head` refuses to run, and
`check_alembic_health_sync`'s `get_current_head()` raises `MultipleHeads` —
turning the healthcheck itself into the outage.

The downgrade drops the table. That is a real data loss and it is the correct
behaviour here: the rows are an observability log with a 90-day window, not a
source of truth anything reconstructs from, and preserving them across a
downgrade would leave verbatim questions in a database whose schema no longer
declares them.

Revision ID: conocimiento_006
Revises: conocimiento_005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "conocimiento_006"
down_revision: Union[str, None] = "conocimiento_005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rag_decision_ruta"
INDEX_EDAD = "ix_rag_decision_ruta_decidida_en"

#: Mirrored in `models.py`. Widening one without the other is how a CHECK and an
#: ORM mapping start disagreeing about what is representable.
CLASES = ("legal", "operational", "geoespacial", "mixto")
SUPERFICIES = ("/tramites", "/finanzas", "/denuncias", "/mapa")


def _en(valores: Sequence[str]) -> str:
    return ", ".join(f"'{valor}'" for valor in valores)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pregunta", sa.Text(), nullable=False),
        sa.Column("clase", sa.Text(), nullable=False),
        sa.Column("superficie", sa.Text(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("margen", sa.Float(), nullable=True),
        sa.Column("umbral_vigente", sa.Float(), nullable=True),
        sa.Column(
            "decidida_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            f"clase IN ({_en(CLASES)})",
            name="ck_rag_decision_ruta_clase",
        ),
        sa.CheckConstraint(
            f"superficie IS NULL OR superficie IN ({_en(SUPERFICIES)})",
            name="ck_rag_decision_ruta_superficie",
        ),
    )
    # The retention purge scans by age and nothing else, so this is the only
    # index the table needs and the only one it gets.
    op.create_index(INDEX_EDAD, TABLE, ["decidida_en"])


def downgrade() -> None:
    op.drop_index(INDEX_EDAD, table_name=TABLE)
    op.drop_table(TABLE)
