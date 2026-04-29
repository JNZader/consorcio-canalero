"""add fecha_reunion column to sugerencias_v2

Brings the model into line with the admin UI: SugerenciasPanel has a
"Agendar para Reunion" button that POSTs `{fecha_reunion}` to
`/sugerencias/{id}/agendar`. Until this migration there was no DB
column to store the date, so the endpoint had no row to update.

Nullable on purpose — most sugerencias never get scheduled (they get
descartadas or implementadas instead). When set, the operator picked a
specific reunión date in `dd/mm/YYYY` and the citizen sees it in their
"Mis sugerencias" detail.

Revision ID: zz_sug_fecha
Revises: zz_drop_infra
Create Date: 2026-04-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "zz_sug_fecha"
down_revision: Union[str, None] = "zz_drop_infra"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sugerencias_v2",
        sa.Column("fecha_reunion", sa.Date(), nullable=True),
    )
    # Index so the admin "próxima reunión" query stays fast as the table
    # grows — `WHERE fecha_reunion >= today() ORDER BY fecha_reunion ASC`
    # is the natural shape we hit from the proxima-reunion endpoint.
    op.create_index(
        "ix_sugerencias_v2_fecha_reunion",
        "sugerencias_v2",
        ["fecha_reunion"],
    )


def downgrade() -> None:
    op.drop_index("ix_sugerencias_v2_fecha_reunion", table_name="sugerencias_v2")
    op.drop_column("sugerencias_v2", "fecha_reunion")
