"""add reuniones tables

Revision ID: m7h4i3j4k583
Revises: l6g3h2i3j472
Create Date: 2026-03-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "m7h4i3j4k583"
down_revision: Union[str, None] = "l6g3h2i3j472"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    tipo_reunion = postgresql.ENUM(
        "ordinaria", "extraordinaria", "urgente",
        name="tipo_reunion",
        create_type=False,
    )
    estado_reunion = postgresql.ENUM(
        "planificada", "en_curso", "finalizada", "cancelada",
        name="estado_reunion",
        create_type=False,
    )

    # Create enums in database
    tipo_reunion.create(op.get_bind(), checkfirst=True)
    estado_reunion.create(op.get_bind(), checkfirst=True)

    # Create reuniones_v2 table
    op.create_table(
        "reuniones_v2",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column(
            "fecha_reunion",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "lugar",
            sa.String(200),
            nullable=False,
            server_default="Sede Consorcio",
        ),
        sa.Column("descripcion", sa.Text, nullable=True),
        sa.Column("tipo", tipo_reunion, nullable=False, server_default="ordinaria"),
        sa.Column("estado", estado_reunion, nullable=False, server_default="planificada"),
        sa.Column(
            "orden_del_dia_items",
            postgresql.JSON,
            nullable=False,
            server_default="[]",
        ),
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

    # Create agenda_items_v2 table
    op.create_table(
        "agenda_items_v2",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "reunion_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reuniones_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=True),
        sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "completado",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Create agenda_referencias_v2 table
    op.create_table(
        "agenda_referencias_v2",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "agenda_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agenda_items_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entidad_tipo", sa.String(50), nullable=False),
        sa.Column(
            "entidad_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("metadata_json", postgresql.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Indexes for common queries
    op.create_index("ix_reuniones_v2_estado", "reuniones_v2", ["estado"])
    op.create_index("ix_reuniones_v2_fecha_reunion", "reuniones_v2", ["fecha_reunion"])
    op.create_index("ix_reuniones_v2_usuario_id", "reuniones_v2", ["usuario_id"])
    op.create_index(
        "ix_agenda_items_v2_reunion_id",
        "agenda_items_v2",
        ["reunion_id"],
    )
    op.create_index(
        "ix_agenda_referencias_v2_agenda_item_id",
        "agenda_referencias_v2",
        ["agenda_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agenda_referencias_v2_agenda_item_id")
    op.drop_index("ix_agenda_items_v2_reunion_id")
    op.drop_index("ix_reuniones_v2_usuario_id")
    op.drop_index("ix_reuniones_v2_fecha_reunion")
    op.drop_index("ix_reuniones_v2_estado")
    op.drop_table("agenda_referencias_v2")
    op.drop_table("agenda_items_v2")
    op.drop_table("reuniones_v2")

    # Drop enum types
    sa.Enum(name="estado_reunion").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tipo_reunion").drop(op.get_bind(), checkfirst=True)
