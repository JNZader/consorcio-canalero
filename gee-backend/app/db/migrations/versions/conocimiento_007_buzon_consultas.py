"""conocimiento_007: the mailbox queue

`rag_consulta` — one queued question per row (amendment A3, `design.md:1321-1366`).
The product is an ASYNCHRONOUS MAILBOX: `POST /preguntas` enqueues and returns an
id plus `pendiente`; a worker with a GPU processes items in batches; the answer
becomes visible when it exists.

**Why the six states live in a CHECK and not only in Python.** The item states are
the five of `design.md:711-749` plus `pendiente`. `RespuestaConocimiento`
already refuses to construct several illegal shapes, but a queue row is written
by a worker, read by a request and updated by neither atomically, so the
"no illegal state persists" claim has to be enforced where the state actually
lands. The two coupling CHECKs below are the part a Python validator cannot make:
`pendiente` iff no payload and no processing timestamp. A row saying
`estado='respuesta'` with `respuesta IS NULL` is an answer-shaped item with no
answer, which is exactly the card U8 must never render.

**Why `decision_ruta_id` is `ON DELETE SET NULL` and not `CASCADE`.** The routing
record has a RATIFIED 90-day retention window (`design.md:1378-1382`) and
`purgar_decisiones_ruta` executes it. Cascading would make that purge delete
answered questions — a retention rule for an observability log silently becoming
a retention rule for the mailbox. The item survives its decision record and
simply stops being traceable to one, which is what a 90-day window means.

**Why the question is stored verbatim here too, and what bounds it.** Same reason
as `conocimiento_006`: the surface has to show the CD member the question they
asked. The identical privacy consequence therefore attaches, so the identical
bound does: `repository.purgar_consultas` executes the same 90-day window. A
mailbox that kept questions forever would repeal the routing record's retention
by copying its text into a second table nobody purges.

**Why `usuario_id` is nullable with `ON DELETE SET NULL`.** The house convention
(`tramites`, `reuniones`, `finanzas`, `monitoring`). A deleted user's items stay
in the queue for the diagnostic's depth count and stop being listed by anyone,
rather than deleting rows out from under a running worker.

**Why this revises `conocimiento_006`.** It is the tree's single head, verified
with `alembic heads` before writing this file. Migration 005's docstring records
what a second child on an already-parented revision costs: the tree forks,
`alembic upgrade head` refuses, and the healthcheck becomes the outage.

Revision ID: conocimiento_007
Revises: conocimiento_006
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "conocimiento_007"
down_revision: Union[str, None] = "conocimiento_006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rag_consulta"
INDEX_PENDIENTES = "ix_rag_consulta_pendientes"
INDEX_USUARIO = "ix_rag_consulta_usuario"

#: Mirrored in `models.py` and in `schemas.RespuestaConocimiento`. Widening one
#: without the others is how a CHECK, an ORM mapping and a response contract
#: start disagreeing about what is representable.
ESTADOS = (
    "pendiente",
    "respuesta",
    "abstencion",
    "redireccion",
    "generacion_fallida",
    "no_disponible",
)


def _en(valores: Sequence[str]) -> str:
    return ", ".join(f"'{valor}'" for valor in valores)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "usuario_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pregunta", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False, server_default="pendiente"),
        sa.Column(
            "decision_ruta_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rag_decision_ruta.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("respuesta", JSONB(), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("procesada_en", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"estado IN ({_en(ESTADOS)})",
            name="ck_rag_consulta_estado",
        ),
        # The two coupling rules. `pendiente` means "not processed yet", and that
        # is a statement about three columns at once: a terminal state with no
        # payload, or a `pendiente` carrying one, is a row no reader can
        # interpret.
        sa.CheckConstraint(
            "(estado = 'pendiente') = (respuesta IS NULL)",
            name="ck_rag_consulta_payload_iff_terminal",
        ),
        sa.CheckConstraint(
            "(estado = 'pendiente') = (procesada_en IS NULL)",
            name="ck_rag_consulta_procesada_iff_terminal",
        ),
    )
    # The claim scan reads ONLY pending rows, oldest first, so the index is
    # partial: an index over every terminal item would grow without bound while
    # answering a query that never looks at one.
    op.create_index(
        INDEX_PENDIENTES,
        TABLE,
        ["creada_en"],
        postgresql_where=sa.text("estado = 'pendiente'"),
    )
    # The listing surface: one requester's items, newest first.
    op.create_index(INDEX_USUARIO, TABLE, ["usuario_id", "creada_en"])


def downgrade() -> None:
    op.drop_index(INDEX_USUARIO, table_name=TABLE)
    op.drop_index(INDEX_PENDIENTES, table_name=TABLE)
    op.drop_table(TABLE)
