"""add canal dimensions to assets

Revision ID: 0014_add_canal_dimensions
Revises: 0013_add_parcelas_catastro
Create Date: 2026-04-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_add_canal_dimensions"
down_revision: Union[str, None] = "0013_add_parcelas_catastro"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column(
            "ancho_m",
            sa.Float,
            nullable=True,
            comment="Canal top width in meters (Manning section)",
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "profundidad_m",
            sa.Float,
            nullable=True,
            comment="Canal depth / normal depth in meters (Manning section)",
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "talud",
            sa.Float,
            nullable=True,
            comment="Side slope ratio (H:V). 0 = rectangular, 1 = 1:1 trapezoidal",
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "coef_manning",
            sa.Float,
            nullable=True,
            comment="Manning roughness coefficient n (e.g. 0.014 concrete, 0.025 earth)",
        ),
    )


def downgrade() -> None:
    op.drop_column("assets", "coef_manning")
    op.drop_column("assets", "talud")
    op.drop_column("assets", "profundidad_m")
    op.drop_column("assets", "ancho_m")
