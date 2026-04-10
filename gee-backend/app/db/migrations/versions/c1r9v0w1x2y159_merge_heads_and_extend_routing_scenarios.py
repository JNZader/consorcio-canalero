"""merge heads and extend routing scenarios

Revision ID: c1r9v0w1x2y159
Revises: 0016_add_caminos_geo, 4bcb6cdb492e, bb2x9y0z1a048
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c1r9v0w1x2y159"
down_revision = ("0016_add_caminos_geo", "4bcb6cdb492e", "bb2x9y0z1a048")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "geo_routing_scenarios",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "geo_routing_scenarios",
        sa.Column(
            "previous_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "geo_routing_scenarios",
        sa.Column("approval_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "geo_routing_scenarios",
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_foreign_key(
        "fk_geo_routing_scenarios_previous_version_id",
        "geo_routing_scenarios",
        "geo_routing_scenarios",
        ["previous_version_id"],
        ["id"],
    )
    op.create_table(
        "geo_routing_scenario_approval_events",
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("acted_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["acted_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["geo_routing_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_geo_routing_scenario_approval_events_scenario_id",
        "geo_routing_scenario_approval_events",
        ["scenario_id"],
    )
    op.execute("UPDATE geo_routing_scenarios SET version = 1 WHERE version IS NULL")
    op.alter_column("geo_routing_scenarios", "version", server_default=None)
    op.alter_column("geo_routing_scenarios", "is_favorite", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_geo_routing_scenario_approval_events_scenario_id",
        table_name="geo_routing_scenario_approval_events",
    )
    op.drop_table("geo_routing_scenario_approval_events")
    op.drop_constraint(
        "fk_geo_routing_scenarios_previous_version_id",
        "geo_routing_scenarios",
        type_="foreignkey",
    )
    op.drop_column("geo_routing_scenarios", "is_favorite")
    op.drop_column("geo_routing_scenarios", "approval_note")
    op.drop_column("geo_routing_scenarios", "previous_version_id")
    op.drop_column("geo_routing_scenarios", "version")
