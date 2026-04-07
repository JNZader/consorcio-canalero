"""add flood_events and flood_labels tables

Revision ID: x8s5t6u7v604
Revises: w7r4s5t6u593
Create Date: 2026-04-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision: str = "x8s5t6u7v604"
down_revision: Union[str, None] = "w7r4s5t6u593"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "flood_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Optional notes about this event",
        ),
        sa.Column(
            "satellite_source",
            sa.String(100),
            nullable=False,
            server_default="COPERNICUS/S2_SR_HARMONIZED",
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

    op.create_table(
        "flood_labels",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            sa.ForeignKey("flood_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "zona_id",
            UUID(as_uuid=True),
            sa.ForeignKey("zonas_operativas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_flooded", sa.Boolean(), nullable=False),
        sa.Column(
            "ndwi_value",
            sa.Float(),
            nullable=True,
            comment="NDWI value at event date for this zone",
        ),
        sa.Column(
            "extracted_features",
            JSON,
            nullable=True,
            comment="DEM-based features: {hand_mean, twi_mean, slope_mean, flow_acc_mean}",
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
        sa.UniqueConstraint("event_id", "zona_id", name="uq_flood_label_event_zona"),
    )

    op.create_index("ix_flood_events_event_date", "flood_events", ["event_date"])
    op.create_index("ix_flood_labels_event_id", "flood_labels", ["event_id"])
    op.create_index("ix_flood_labels_zona_id", "flood_labels", ["zona_id"])


def downgrade() -> None:
    op.drop_index("ix_flood_labels_zona_id", table_name="flood_labels")
    op.drop_index("ix_flood_labels_event_id", table_name="flood_labels")
    op.drop_index("ix_flood_events_event_date", table_name="flood_events")
    op.drop_table("flood_labels")
    op.drop_table("flood_events")
