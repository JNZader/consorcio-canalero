"""add rainfall_records table

Revision ID: y9t6u7v8w715
Revises: x8s5t6u7v604
Create Date: 2026-04-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "y9t6u7v8w715"
down_revision: Union[str, None] = "x8s5t6u7v604"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rainfall_records",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "zona_operativa_id",
            UUID(as_uuid=True),
            sa.ForeignKey("zonas_operativas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("precipitation_mm", sa.Float(), nullable=False),
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            server_default="CHIRPS",
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
        sa.UniqueConstraint(
            "zona_operativa_id",
            "date",
            "source",
            name="uq_rainfall_zona_date_source",
        ),
    )

    op.create_index(
        "ix_rainfall_records_zona_operativa_id",
        "rainfall_records",
        ["zona_operativa_id"],
    )
    op.create_index(
        "ix_rainfall_records_date",
        "rainfall_records",
        ["date"],
    )
    op.create_index(
        "ix_rainfall_records_zona_date",
        "rainfall_records",
        ["zona_operativa_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_rainfall_records_zona_date", table_name="rainfall_records")
    op.drop_index("ix_rainfall_records_date", table_name="rainfall_records")
    op.drop_index(
        "ix_rainfall_records_zona_operativa_id", table_name="rainfall_records"
    )
    op.drop_table("rainfall_records")
