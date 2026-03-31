"""add versions to geo approved zonings

Revision ID: t4o1p2q3r260
Revises: s3n0p1q2r149
Create Date: 2026-03-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "t4o1p2q3r260"
down_revision: Union[str, None] = "s3n0p1q2r149"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "geo_approved_zonings",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "geo_approved_zonings",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY COALESCE(cuenca, '__null__')
                       ORDER BY approved_at ASC, created_at ASC, id ASC
                   ) AS version_number
            FROM geo_approved_zonings
        )
        UPDATE geo_approved_zonings gaz
        SET version = ranked.version_number
        FROM ranked
        WHERE gaz.id = ranked.id
        """
    )
    op.create_index(
        "ix_geo_approved_zonings_cuenca_version",
        "geo_approved_zonings",
        ["cuenca", "version"],
    )


def downgrade() -> None:
    op.drop_index("ix_geo_approved_zonings_cuenca_version")
    op.drop_column("geo_approved_zonings", "notes")
    op.drop_column("geo_approved_zonings", "version")
