"""add notas_internas column to sugerencias_v2

The admin "Detalle de Sugerencia" panel has a textarea labelled "Notas
Internas (Consorcio)" for the operator to record private comisión
discussion (presupuesto, votación interna, etc.). Until this migration
there was no DB column for it — the frontend was happily PATCHing
`notas_comision: ...` and Pydantic was silently dropping the field
because `SugerenciaUpdate` doesn't declare it. Net effect: typing into
that textarea did nothing for months, no error reported.

This migration adds the column. The schema is updated in the same
commit so the next PATCH actually persists.

Revision ID: zz_sug_notas
Revises: zz_sug_fecha
Create Date: 2026-04-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "zz_sug_notas"
down_revision: Union[str, None] = "zz_sug_fecha"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sugerencias_v2",
        sa.Column("notas_internas", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sugerencias_v2", "notas_internas")
