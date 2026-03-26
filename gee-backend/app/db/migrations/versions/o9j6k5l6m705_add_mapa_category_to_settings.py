"""add mapa category to settings enum

Revision ID: o9j6k5l6m705
Revises: n8i5j4k5l694
Create Date: 2026-03-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "o9j6k5l6m705"
down_revision: Union[str, None] = "n8i5j4k5l694"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'mapa' to the categoria_settings enum
    op.execute("ALTER TYPE categoria_settings ADD VALUE IF NOT EXISTS 'mapa'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The value will remain but be unused after downgrade.
    pass
