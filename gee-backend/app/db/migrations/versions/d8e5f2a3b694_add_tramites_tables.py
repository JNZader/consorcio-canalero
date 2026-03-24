"""add tramites tables

Revision ID: d8e5f2a3b694
Revises: c7d4f1a2b583
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8e5f2a3b694"
down_revision: Union[str, None] = "c7d4f1a2b583"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    tipo_tramite = postgresql.ENUM(
        "obra", "permiso", "habilitacion", "reclamo", "otro",
        name="tipo_tramite",
        create_type=False,
    )
    estado_tramite = postgresql.ENUM(
        "ingresado", "en_tramite", "aprobado", "rechazado", "archivado",
        name="estado_tramite",
        create_type=False,
    )
    prioridad_tramite = postgresql.ENUM(
        "baja", "media", "alta", "urgente",
        name="prioridad_tramite",
        create_type=False,
    )

    # Create enums in database
    tipo_tramite.create(op.get_bind(), checkfirst=True)
    estado_tramite.create(op.get_bind(), checkfirst=True)
    prioridad_tramite.create(op.get_bind(), checkfirst=True)

    # Create tramites_v2 table
    op.create_table(
        "tramites_v2",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tipo",
            tipo_tramite,
            nullable=False,
        ),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column("solicitante", sa.String(200), nullable=False),
        sa.Column(
            "estado",
            estado_tramite,
            nullable=False,
            server_default="ingresado",
        ),
        sa.Column(
            "prioridad",
            prioridad_tramite,
            nullable=False,
            server_default="media",
        ),
        sa.Column(
            "fecha_ingreso",
            sa.Date,
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("fecha_resolucion", sa.Date, nullable=True),
        sa.Column("resolucion", sa.Text, nullable=True),
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

    # Create tramites_seguimiento table
    op.create_table(
        "tramites_seguimiento",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tramite_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tramites_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("estado_anterior", sa.String(50), nullable=False),
        sa.Column("estado_nuevo", sa.String(50), nullable=False),
        sa.Column("comentario", sa.Text, nullable=False),
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
    )

    # Indexes for common queries
    op.create_index("ix_tramites_v2_estado", "tramites_v2", ["estado"])
    op.create_index("ix_tramites_v2_tipo", "tramites_v2", ["tipo"])
    op.create_index("ix_tramites_v2_prioridad", "tramites_v2", ["prioridad"])
    op.create_index("ix_tramites_v2_usuario_id", "tramites_v2", ["usuario_id"])
    op.create_index("ix_tramites_v2_fecha_ingreso", "tramites_v2", ["fecha_ingreso"])
    op.create_index(
        "ix_tramites_seguimiento_tramite_id",
        "tramites_seguimiento",
        ["tramite_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tramites_seguimiento_tramite_id")
    op.drop_index("ix_tramites_v2_fecha_ingreso")
    op.drop_index("ix_tramites_v2_usuario_id")
    op.drop_index("ix_tramites_v2_prioridad")
    op.drop_index("ix_tramites_v2_tipo")
    op.drop_index("ix_tramites_v2_estado")
    op.drop_table("tramites_seguimiento")
    op.drop_table("tramites_v2")

    # Drop enum types
    sa.Enum(name="prioridad_tramite").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="estado_tramite").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tipo_tramite").drop(op.get_bind(), checkfirst=True)
