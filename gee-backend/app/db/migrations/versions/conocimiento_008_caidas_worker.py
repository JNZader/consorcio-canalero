"""conocimiento_008: the mailbox's bounded crash counter (audit RAG-5)

`rag_consulta.caidas_worker` — one small INTEGER column, and the reason it has
to live IN the item's row rather than in any sidecar is the same property that
made the bug it fixes possible: the claim writes no intermediate state, so the
transaction that processes an item is also the only transaction that knows it
was being processed, and a crash rolls it back ENTIRELY. A counter that lived
anywhere else would be a second thing to keep consistent with the row (and a
sidecar keyed by item id is a reaper-shaped liability this domain explicitly
refused in `buzon.py`'s "no lease column" argument). A column on the row, with
the crash path writing it from a SEPARATE committed transaction after the
rollback, keeps the invariant the claim already has: `pendiente` items carry
no processing state except this one integer, and the integer is written only
when the item did NOT finish.

**What it counts, precisely.** Worker deaths (unnamed exceptions) attributed
to this item by `rag_worker`'s crash accountant. NOT generation attempts:
a clean run that ends in `generacion_fallida` through the state machine
(`presupuesto_item_agotado`, `transporte_agotado`, …) terminalizes the item
normally and the column stays 0 — those failures are already honest. Only the
crash-loop case, where the item goes back to `pendiente` and systemd restarts
the worker into the SAME item every 10 s, consumes the count. At
`buzon.MAX_CAIDAS_WORKER` (3) the accountant terminalizes the item to
`generacion_fallida` with a `motivo` that names the count and the last cause;
the crash itself still propagates, because a poison item must not buy silence
for the bug that poisoned it.

**Why no new state and no new coupling CHECK.** The terminal state is one of
the six the design fixed (`generacion_fallida` — "the box tried and did not
finish"), so `ck_rag_consulta_estado` and both `iff` coupling CHECKs from
`conocimiento_007` are untouched: a dead-lettered item is a normal terminal
item, complete with payload and `procesada_en`. The counter is allowed to be
non-zero on a terminal item (that non-zero IS the record of why it
terminalized) and on a `pendiente` item (crashes so far), so the only CHECK
it carries is the sign — a negative count is a write bug, not a state the
schema should silently absorb.

**Why this revises `0033_one_way_profile`.** It is the tree's single head,
verified with `alembic heads` before writing this file — the same discipline
`conocimiento_005`'s docstring records. `conocimiento_007` stopped being the
tip when `lluvia_ext_001` chained onto it; a second child anywhere below
forks the tree, `alembic upgrade head` refuses, and the healthcheck becomes
the outage.

Revision ID: conocimiento_008
Revises: 0033_one_way_profile
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "conocimiento_008"
down_revision: Union[str, None] = "0033_one_way_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rag_consulta"
COLUMNS_NAME = "caidas_worker"
CONSTRAINT = "ck_rag_consulta_caidas_worker_no_negativas"


def upgrade() -> None:
    # Existing rows are items the CURRENT worker model never crashed on: 0 is
    # not a placeholder, it is the true count for every one of them.
    op.add_column(
        TABLE,
        sa.Column(COLUMNS_NAME, sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(CONSTRAINT, TABLE, f"{COLUMNS_NAME} >= 0")


def downgrade() -> None:
    # Drops the count and nothing else. A `pendiente` item loses its crash
    # history and starts the window again — honest for a rollback, which also
    # removes the accountant that would have used it.
    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.drop_column(TABLE, COLUMNS_NAME)
