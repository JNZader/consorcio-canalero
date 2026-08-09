"""rainfall_outbox_request_fingerprint

Revision ID: lluvia_v2_005
Revises: lluvia_v2_004
Create Date: 2026-08-09 00:00:00.000000

Adds a nullable ``request_fingerprint`` column to ``rainfall_outbox`` so an
outbox row can be linked back to the analysis request that enqueued it
(design.md decision 4). Also adds a non-unique index on the outbox key plus
``completed_at`` (decision 6): the existing ``ix_rainfall_outbox_pending_unique``
index is ``pending``-only and cannot serve a "most recent done row for this
key" lookup — this index gives ``recent_done`` a seek and gives the
current-year revisit sweep its ``DISTINCT ON (key) ... ORDER BY key,
completed_at DESC`` ordering for free.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "lluvia_v2_005"
down_revision: Union[str, Sequence[str], None] = "lluvia_v2_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable request_fingerprint column and the done-lookup index."""
    op.add_column(
        "rainfall_outbox",
        sa.Column("request_fingerprint", sa.String(128), nullable=True),
    )
    op.create_index(
        "ix_rainfall_outbox_done_lookup",
        "rainfall_outbox",
        ["source_id", "role", "scope_kind", "scope_id", "scope_version", "year", "completed_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the done-lookup index and the request_fingerprint column."""
    op.drop_index("ix_rainfall_outbox_done_lookup", table_name="rainfall_outbox")
    op.drop_column("rainfall_outbox", "request_fingerprint")
