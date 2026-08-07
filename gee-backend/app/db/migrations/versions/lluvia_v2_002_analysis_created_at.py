"""Add authoritative creation order to immutable rainfall analysis revisions."""

import sqlalchemy as sa
from alembic import op

revision = "lluvia_v2_002"
down_revision = "lluvia_v2_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rainfall_analysis_revision",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_rainfall_analysis_revision_current",
        "rainfall_analysis_revision",
        ["request_fingerprint", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_rainfall_analysis_revision_current", table_name="rainfall_analysis_revision")
    op.drop_column("rainfall_analysis_revision", "created_at")
