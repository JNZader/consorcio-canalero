"""add system settings table

Revision ID: i3d0e8f9g149
Revises: h2c9d7e8f038
Create Date: 2026-03-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "i3d0e8f9g149"
down_revision: Union[str, None] = "h2c9d7e8f038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type
    categoria_enum = postgresql.ENUM(
        "general",
        "branding",
        "territorio",
        "analisis",
        "contacto",
        name="categoria_settings",
        create_type=True,
    )
    categoria_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "system_settings",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("clave", sa.String(200), nullable=False),
        sa.Column("valor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "categoria",
            sa.Enum(
                "general",
                "branding",
                "territorio",
                "analisis",
                "contacto",
                name="categoria_settings",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("descripcion", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("clave"),
    )
    op.create_index("ix_system_settings_clave", "system_settings", ["clave"])


def downgrade() -> None:
    op.drop_index("ix_system_settings_clave", table_name="system_settings")
    op.drop_table("system_settings")
    op.execute("DROP TYPE IF EXISTS categoria_settings")
