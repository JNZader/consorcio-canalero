"""Operator assignment and bulk-action receipts for denuncias.

Revision ID: zz_denuncia_asignacion
Revises: zz_denuncia_idempotency_key
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "zz_denuncia_asignacion"
down_revision: Union[str, None] = "zz_denuncia_idempotency_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "denuncias",
        sa.Column("asignado_a", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_denuncias_asignado_a_users",
        "denuncias",
        "users",
        ["asignado_a"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_denuncias_asignado_a", "denuncias", ["asignado_a"])
    op.create_table(
        "denuncia_bulk_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("operador_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("resultado", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["operador_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("operador_id", "idempotency_key", name="uq_denuncia_bulk_operator_key"),
    )


def downgrade() -> None:
    op.drop_table("denuncia_bulk_receipts")
    op.drop_index("ix_denuncias_asignado_a", table_name="denuncias")
    op.drop_constraint("fk_denuncias_asignado_a_users", "denuncias", type_="foreignkey")
    op.drop_column("denuncias", "asignado_a")
