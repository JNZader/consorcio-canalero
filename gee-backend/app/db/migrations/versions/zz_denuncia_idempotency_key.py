"""Add a per-user idempotency key on denuncias.

A lost HTTP response used to make the citizen retry create a second row
(F2). The key is unique among live rows of the same user. A soft-deleted
row releases the key so an ARCO cancellation does not block a new report.

Revision ID: zz_denuncia_idempotency_key
Revises: zz_dom_wave3
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "zz_denuncia_idempotency_key"
down_revision: Union[str, None] = "zz_dom_wave3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "denuncias",
        sa.Column("idempotency_key", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "uq_denuncias_user_idempotency",
        "denuncias",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_denuncias_user_idempotency", table_name="denuncias")
    op.drop_column("denuncias", "idempotency_key")
