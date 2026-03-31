"""add geo approved zonings table

Revision ID: s3n0p1q2r149
Revises: r2m9n8o9p038
Create Date: 2026-03-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "s3n0p1q2r149"
down_revision: Union[str, None] = "r2m9n8o9p038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geo_approved_zonings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("cuenca", sa.String(100), nullable=True),
        sa.Column(
            "feature_collection",
            postgresql.JSON,
            nullable=False,
            comment="Approved dissolved zoning as GeoJSON FeatureCollection",
        ),
        sa.Column(
            "assignments",
            postgresql.JSON,
            nullable=True,
            comment="Optional draft basin->zone assignments used to build the zoning",
        ),
        sa.Column(
            "zone_names",
            postgresql.JSON,
            nullable=True,
            comment="Optional human-friendly names per approved zone",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "approved_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_geo_approved_zonings_cuenca",
        "geo_approved_zonings",
        ["cuenca"],
    )
    op.create_index(
        "ix_geo_approved_zonings_is_active",
        "geo_approved_zonings",
        ["is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_geo_approved_zonings_is_active")
    op.drop_index("ix_geo_approved_zonings_cuenca")
    op.drop_table("geo_approved_zonings")
