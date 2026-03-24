"""add denuncias tables

Revision ID: 51f85c264771
Revises:
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = "51f85c264771"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure PostGIS extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # Create estado_denuncia enum
    estado_enum = postgresql.ENUM(
        "pendiente",
        "en_revision",
        "resuelto",
        "descartado",
        name="estado_denuncia",
        create_type=False,
    )
    estado_enum.create(op.get_bind(), checkfirst=True)

    # Create denuncias table
    op.create_table(
        "denuncias",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tipo", sa.String(100), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column("latitud", sa.Float, nullable=False),
        sa.Column("longitud", sa.Float, nullable=False),
        sa.Column(
            "geom",
            Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("cuenca", sa.String(100), nullable=True),
        sa.Column(
            "estado",
            estado_enum,
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column("contacto_telefono", sa.String(50), nullable=True),
        sa.Column("contacto_email", sa.String(255), nullable=True),
        sa.Column("foto_url", sa.String(500), nullable=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("respuesta", sa.Text, nullable=True),
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

    # Create denuncias_historial table
    op.create_table(
        "denuncias_historial",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "denuncia_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("denuncias.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("estado_anterior", sa.String(50), nullable=False),
        sa.Column("estado_nuevo", sa.String(50), nullable=False),
        sa.Column("comentario", sa.Text, nullable=True),
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
    op.create_index("ix_denuncias_estado", "denuncias", ["estado"])
    op.create_index("ix_denuncias_cuenca", "denuncias", ["cuenca"])
    op.create_index("ix_denuncias_created_at", "denuncias", ["created_at"])
    op.create_index(
        "ix_denuncias_historial_denuncia_id",
        "denuncias_historial",
        ["denuncia_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_denuncias_historial_denuncia_id")
    op.drop_index("ix_denuncias_created_at")
    op.drop_index("ix_denuncias_cuenca")
    op.drop_index("ix_denuncias_estado")
    op.drop_table("denuncias_historial")
    op.drop_table("denuncias")
    op.execute("DROP TYPE IF EXISTS estado_denuncia")
