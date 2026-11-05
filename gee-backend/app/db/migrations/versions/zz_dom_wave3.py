"""DOM wave-3: analisis_gee.usuario_id nullable, ingreso consorcista FK.

``analisis_gee.usuario_id`` was created with ``ON DELETE SET NULL`` and
``NOT NULL`` (``f0a7b4c5d816``). ``zz_users_fk_nullable`` relaxed the sister
columns and left this one out, so deleting a user who owns a GEE analysis
fails the NOT NULL check.

``ingresos_v2.consorcista_id`` was a bare UUID. Orphan ids that do not match
``consorcistas`` are cleared, then the column becomes a real FK with
``ON DELETE SET NULL`` so an ingreso survives the consorcista.

Revision ID: zz_dom_wave3
Revises: conocimiento_008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "zz_dom_wave3"
down_revision: Union[str, None] = "conocimiento_008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "analisis_gee",
        "usuario_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.execute(
        sa.text(
            """
            UPDATE ingresos_v2
            SET consorcista_id = NULL
            WHERE consorcista_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM consorcistas c
                  WHERE c.id = ingresos_v2.consorcista_id
              )
            """
        )
    )
    op.create_foreign_key(
        "fk_ingresos_v2_consorcista_id",
        "ingresos_v2",
        "consorcistas",
        ["consorcista_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ingresos_v2_consorcista_id",
        "ingresos_v2",
        type_="foreignkey",
    )
    # Fails if a referenced user was deleted and the column is already NULL.
    op.alter_column(
        "analisis_gee",
        "usuario_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
