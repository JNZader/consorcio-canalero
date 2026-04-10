"""add geo routing scenario approval fields

Revision ID: bb2x9y0z1a048
Revises: aa1v8w9x0y937
Create Date: 2026-04-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "bb2x9y0z1a048"
down_revision = "aa1v8w9x0y937"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "geo_routing_scenarios",
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "geo_routing_scenarios",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "geo_routing_scenarios",
        sa.Column(
            "approved_by_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_geo_routing_scenarios_approved_by_id_users",
        "geo_routing_scenarios",
        "users",
        ["approved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_geo_routing_scenarios_approved_by_id_users",
        "geo_routing_scenarios",
        type_="foreignkey",
    )
    op.drop_column("geo_routing_scenarios", "approved_by_id")
    op.drop_column("geo_routing_scenarios", "approved_at")
    op.drop_column("geo_routing_scenarios", "is_approved")
