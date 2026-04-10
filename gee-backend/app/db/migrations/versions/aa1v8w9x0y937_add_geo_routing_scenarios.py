"""add geo routing scenarios

Revision ID: aa1v8w9x0y937
Revises: z0u7v8w9x826_add_canal_suggestions
Create Date: 2026-04-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "aa1v8w9x0y937"
down_revision: Union[str, None] = "z0u7v8w9x826"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geo_routing_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("profile", sa.String(length=50), nullable=False),
        sa.Column(
            "request_payload", postgresql.JSON(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "result_payload", postgresql.JSON(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_geo_routing_scenarios_created_at",
        "geo_routing_scenarios",
        ["created_at"],
    )
    op.create_index(
        "ix_geo_routing_scenarios_profile",
        "geo_routing_scenarios",
        ["profile"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_geo_routing_scenarios_profile", table_name="geo_routing_scenarios"
    )
    op.drop_index(
        "ix_geo_routing_scenarios_created_at", table_name="geo_routing_scenarios"
    )
    op.drop_table("geo_routing_scenarios")
