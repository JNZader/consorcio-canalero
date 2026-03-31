"""add geometry to sugerencias_v2

Revision ID: u5p2q3r4s371
Revises: t4o1p2q3r260
Create Date: 2026-03-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "u5p2q3r4s371"
down_revision: Union[str, None] = "t4o1p2q3r260"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sugerencias_v2",
        sa.Column("geometry", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sugerencias_v2", "geometry")
