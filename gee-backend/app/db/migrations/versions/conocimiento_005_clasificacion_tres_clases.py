"""conocimiento_005: admit `institucional`, and record WHY a document is shippable

Two changes, one purpose: make the three-class privacy boundary representable.

**The CHECK.** `rag_documento` was born with `CHECK (clasificacion IN ('publico',
'privado'))` (`conocimiento_001_rag_corpus_schema.py:85-86`, mirrored at
`models.py:156-157`), which was correct while `documento_row_from_frontmatter`
hard-coded `privado` for every document and nothing promoted one. The ratified
three-class rule adds `institucional` — the consorcio's own normative
instruments, cleared for the answer path — and against the narrow CHECK that
value is an `IntegrityError`. Ingest runs in ONE transaction
(`scripts/rag_ingest.py:170`, `:219-232`), so a single `institucional` row would
roll the whole re-ingest back. This migration is therefore a hard prerequisite
of the runbook's re-ingest step, not a tidy-up that can follow it.

**The evidence column.** `clasificacion_evidencia` is nullable Text holding the
string the ingest rule derived the class FROM — the matched host for `publico`,
`tipo:registro-administrativo ∈ TIPOS_INSTITUCIONALES` for `institucional`,
`es_secundaria` or `sin host en FUENTES_PUBLICAS` for `privado`. Without it,
"why is this document shippable?" is answerable only by re-running the rule
against a corpus checkout the box may not have; with it, the answer is a
`SELECT`. It is evidence, never an input: nothing reads it back to decide
anything, which is why it is nullable and why NULL is a perfectly normal state
(a snapshot ingested below this revision has no evidence to show).

**The downgrade demotes before it narrows.** Migration 003's lesson (ledger
R3-101) applied to this shape: re-creating the narrow CHECK over a database that
has been *used* raises `CheckViolation` on exactly the rows the upgrade existed
to legalize. So `institucional` rows are demoted to `privado` FIRST. Demotion
rather than deletion, and toward the *less* shippable class: a document that
stops reaching the provider is a smaller failure than a rollback that cannot
run. What is lost is the class and its evidence, both rebuilt by re-running
ingest — the same recovery path migration 004 documents for its provenance
columns.

**Why this revises `0022_add_cruce_camino` and not `conocimiento_004`.** The
conocimiento chain is not the only thing stacked on `conocimiento_004`:
`0021_add_red_vial` already chains onto it and `0022_add_cruce_camino` onto
`0021`. Pointing this revision at `conocimiento_004` too would fork the tree into
two heads (`0022_add_cruce_camino` and `conocimiento_005`), and a forked tree is
not a cosmetic problem — `alembic upgrade head` refuses to run against multiple
heads, and `ScriptDirectory.get_current_head()` (which
`app.core.health.check_alembic_health_sync` and its test rely on) raises. So this
revision chains onto the current tip of the whole tree, wherever that tip lives.

Revision ID: conocimiento_005
Revises: 0023_add_relevamiento_tramo
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "conocimiento_005"
down_revision: Union[str, None] = "0023_add_relevamiento_tramo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rag_documento"
CHECK_NAME = "ck_rag_documento_clasificacion"
EVIDENCIA_COLUMN = "clasificacion_evidencia"

#: The widened set. Written out in both directions rather than built from a
#: shared constant, because a downgrade whose narrow set is derived from the
#: wide one silently follows every future widening.
CLASES_ANCHAS = ("publico", "institucional", "privado")
CLASES_ESTRECHAS = ("publico", "privado")


def _check_sql(clases: Sequence[str]) -> str:
    valores = ", ".join(f"'{clase}'" for clase in clases)
    return f"clasificacion IN ({valores})"


def upgrade() -> None:
    op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    op.create_check_constraint(CHECK_NAME, TABLE, _check_sql(CLASES_ANCHAS))
    op.add_column(TABLE, sa.Column(EVIDENCIA_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    """Demote every `institucional` row, then restore the narrow CHECK.

    The order is load-bearing and is the whole reason this function is longer
    than one line.
    """
    op.execute(
        sa.text(
            f"UPDATE {TABLE} SET clasificacion = 'privado' WHERE clasificacion = 'institucional'"
        )
    )
    op.drop_column(TABLE, EVIDENCIA_COLUMN)
    op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    op.create_check_constraint(CHECK_NAME, TABLE, _check_sql(CLASES_ESTRECHAS))
