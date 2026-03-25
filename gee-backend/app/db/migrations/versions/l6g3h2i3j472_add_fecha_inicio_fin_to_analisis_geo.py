"""add fecha_inicio fecha_fin to analisis_geo

Revision ID: l6g3h2i3j472
Revises: k5f2g1h2i361
Create Date: 2026-03-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "l6g3h2i3j472"
down_revision: Union[str, None] = "k5f2g1h2i361"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add fecha_inicio and fecha_fin columns
    op.add_column(
        "geo_analisis_gee",
        sa.Column(
            "fecha_inicio",
            sa.DateTime(),
            nullable=True,
            comment="Analysis period start date",
        ),
    )
    op.add_column(
        "geo_analisis_gee",
        sa.Column(
            "fecha_fin",
            sa.DateTime(),
            nullable=True,
            comment="Analysis period end date",
        ),
    )

    # Add 'classification' to tipo_analisis_geo enum
    op.execute("ALTER TYPE tipo_analisis_geo ADD VALUE IF NOT EXISTS 'classification'")


def downgrade() -> None:
    op.drop_column("geo_analisis_gee", "fecha_fin")
    op.drop_column("geo_analisis_gee", "fecha_inicio")
    # Note: PostgreSQL does not support removing values from enums.
    # The 'classification' value will remain in tipo_analisis_geo.
