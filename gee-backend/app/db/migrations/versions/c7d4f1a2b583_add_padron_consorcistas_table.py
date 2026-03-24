"""add padron consorcistas table

Revision ID: c7d4f1a2b583
Revises: b5c2e8f3a194
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7d4f1a2b583"
down_revision: Union[str, None] = "b5c2e8f3a194"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create estado_consorcista enum
    estado_enum = postgresql.ENUM(
        "activo",
        "inactivo",
        "suspendido",
        name="estado_consorcista",
        create_type=False,
    )
    estado_enum.create(op.get_bind(), checkfirst=True)

    # Create consorcistas table
    op.create_table(
        "consorcistas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("apellido", sa.String(200), nullable=False),
        sa.Column("cuit", sa.String(13), nullable=False, unique=True),
        sa.Column("dni", sa.String(20), nullable=True),
        sa.Column("domicilio", sa.String(500), nullable=True),
        sa.Column("localidad", sa.String(200), nullable=True),
        sa.Column("telefono", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("parcela", sa.String(100), nullable=True),
        sa.Column("hectareas", sa.Float, nullable=True),
        sa.Column(
            "categoria",
            sa.String(50),
            nullable=True,
            comment="propietario, arrendatario, otro",
        ),
        sa.Column(
            "estado",
            estado_enum,
            nullable=False,
            server_default="activo",
        ),
        sa.Column("fecha_ingreso", sa.Date, nullable=True),
        sa.Column("notas", sa.Text, nullable=True),
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

    # Indexes for common queries
    op.create_index("ix_consorcistas_cuit", "consorcistas", ["cuit"], unique=True)
    op.create_index("ix_consorcistas_estado", "consorcistas", ["estado"])
    op.create_index("ix_consorcistas_categoria", "consorcistas", ["categoria"])
    op.create_index("ix_consorcistas_apellido", "consorcistas", ["apellido"])
    op.create_index("ix_consorcistas_localidad", "consorcistas", ["localidad"])


def downgrade() -> None:
    op.drop_index("ix_consorcistas_localidad")
    op.drop_index("ix_consorcistas_apellido")
    op.drop_index("ix_consorcistas_categoria")
    op.drop_index("ix_consorcistas_estado")
    op.drop_index("ix_consorcistas_cuit")
    op.drop_table("consorcistas")
    op.execute("DROP TYPE IF EXISTS estado_consorcista")
