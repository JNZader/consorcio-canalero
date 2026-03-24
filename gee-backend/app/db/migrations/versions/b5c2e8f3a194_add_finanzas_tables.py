"""add finanzas tables

Revision ID: b5c2e8f3a194
Revises: a3b7d9e1f482
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b5c2e8f3a194"
down_revision: Union[str, None] = "a3b7d9e1f482"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create gastos_v2 table
    op.create_table(
        "gastos_v2",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("categoria", sa.String(50), nullable=False),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("comprobante_url", sa.String(500), nullable=True),
        sa.Column("proveedor", sa.String(200), nullable=True),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
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
    )

    # Create ingresos_v2 table
    op.create_table(
        "ingresos_v2",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("categoria", sa.String(50), nullable=False),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column(
            "consorcista_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("comprobante_url", sa.String(500), nullable=True),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
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
    )

    # Create presupuestos_v2 table
    op.create_table(
        "presupuestos_v2",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("anio", sa.Integer, nullable=False),
        sa.Column("rubro", sa.String(100), nullable=False),
        sa.Column("monto_proyectado", sa.Numeric(12, 2), nullable=False),
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
    op.create_index("ix_gastos_v2_categoria", "gastos_v2", ["categoria"])
    op.create_index("ix_gastos_v2_fecha", "gastos_v2", ["fecha"])
    op.create_index("ix_gastos_v2_usuario_id", "gastos_v2", ["usuario_id"])
    op.create_index("ix_ingresos_v2_categoria", "ingresos_v2", ["categoria"])
    op.create_index("ix_ingresos_v2_fecha", "ingresos_v2", ["fecha"])
    op.create_index("ix_ingresos_v2_usuario_id", "ingresos_v2", ["usuario_id"])
    op.create_index(
        "ix_presupuestos_v2_anio_rubro",
        "presupuestos_v2",
        ["anio", "rubro"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_presupuestos_v2_anio_rubro")
    op.drop_index("ix_ingresos_v2_usuario_id")
    op.drop_index("ix_ingresos_v2_fecha")
    op.drop_index("ix_ingresos_v2_categoria")
    op.drop_index("ix_gastos_v2_usuario_id")
    op.drop_index("ix_gastos_v2_fecha")
    op.drop_index("ix_gastos_v2_categoria")
    op.drop_table("presupuestos_v2")
    op.drop_table("ingresos_v2")
    op.drop_table("gastos_v2")
