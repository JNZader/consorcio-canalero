"""add pre_authorized_emails table

Revision ID: n8i5j4k5l694
Revises: m7h4i3j4k583
Create Date: 2026-03-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "n8i5j4k5l694"
down_revision: Union[str, None] = "m7h4i3j4k583"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pre_authorized_emails",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(
                "ciudadano",
                "operador",
                "admin",
                name="user_role",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("invited_by", sa.UUID(), nullable=False),
        sa.Column(
            "claimed", sa.Boolean(), nullable=False, server_default=sa.text("false")
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.UniqueConstraint("email"),
    )
    op.create_index(
        "ix_pre_authorized_emails_email", "pre_authorized_emails", ["email"]
    )


def downgrade() -> None:
    op.drop_index("ix_pre_authorized_emails_email", table_name="pre_authorized_emails")
    op.drop_table("pre_authorized_emails")
