"""create users table (fastapi-users)

Revision ID: 00a1b2c3d4e5
Revises:
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "00a1b2c3d4e5"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_role enum
    user_role = postgresql.ENUM(
        "ciudadano", "operador", "admin", name="user_role", create_type=False
    )
    user_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("nombre", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("apellido", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("telefono", sa.String(length=50), nullable=False, server_default=""),
        sa.Column(
            "role",
            postgresql.ENUM("ciudadano", "operador", "admin", name="user_role", create_type=False),
            nullable=False,
            server_default="ciudadano",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    postgresql.ENUM(name="user_role").drop(op.get_bind(), checkfirst=True)
