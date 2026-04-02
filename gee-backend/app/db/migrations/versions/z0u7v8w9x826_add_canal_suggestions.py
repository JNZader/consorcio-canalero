"""add canal_suggestions table

Revision ID: z0u7v8w9x826
Revises: y9t6u7v8w715
Create Date: 2026-04-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import UUID, JSON

revision: str = "z0u7v8w9x826"
down_revision: Union[str, None] = "y9t6u7v8w715"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canal_suggestions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tipo",
            sa.String(30),
            nullable=False,
            comment="hotspot | gap | route | maintenance | bottleneck",
        ),
        sa.Column(
            "geometry",
            Geometry("GEOMETRY", srid=4326),
            nullable=True,
            comment="Suggestion geometry (point, line, or polygon)",
        ),
        sa.Column(
            "score",
            sa.Float,
            nullable=False,
            comment="Relevance / priority score 0-100",
        ),
        sa.Column(
            "metadata",
            JSON,
            nullable=True,
            comment="Analysis-specific payload",
        ),
        sa.Column(
            "batch_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="Groups suggestions from the same analysis run",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Indexes for common query patterns
    op.create_index("ix_canal_suggestions_tipo", "canal_suggestions", ["tipo"])
    op.create_index("ix_canal_suggestions_batch_id", "canal_suggestions", ["batch_id"])
    op.create_index("ix_canal_suggestions_score", "canal_suggestions", ["score"])
    op.create_index(
        "ix_canal_suggestions_geometry",
        "canal_suggestions",
        ["geometry"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_canal_suggestions_geometry", table_name="canal_suggestions")
    op.drop_index("ix_canal_suggestions_score", table_name="canal_suggestions")
    op.drop_index("ix_canal_suggestions_batch_id", table_name="canal_suggestions")
    op.drop_index("ix_canal_suggestions_tipo", table_name="canal_suggestions")
    op.drop_table("canal_suggestions")
