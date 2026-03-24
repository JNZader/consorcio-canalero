"""add infraestructura tables

Revision ID: a3b7d9e1f482
Revises: 51f85c264771
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = "a3b7d9e1f482"
down_revision: Union[str, None] = "51f85c264771"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create estado_asset enum
    estado_enum = postgresql.ENUM(
        "bueno",
        "regular",
        "malo",
        "critico",
        name="estado_asset",
        create_type=False,
    )
    estado_enum.create(op.get_bind(), checkfirst=True)

    # Create assets table
    op.create_table(
        "assets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("tipo", sa.String(100), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column(
            "estado_actual",
            estado_enum,
            nullable=False,
            server_default="bueno",
        ),
        sa.Column("latitud", sa.Float, nullable=False),
        sa.Column("longitud", sa.Float, nullable=False),
        sa.Column(
            "geom",
            Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("longitud_km", sa.Float, nullable=True),
        sa.Column("material", sa.String(100), nullable=True),
        sa.Column("anio_construccion", sa.Integer, nullable=True),
        sa.Column("responsable", sa.String(200), nullable=True),
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

    # Create mantenimiento_logs table
    op.create_table(
        "mantenimiento_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo_trabajo", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column("costo", sa.Float, nullable=True),
        sa.Column("fecha_trabajo", sa.Date, nullable=False),
        sa.Column("realizado_por", sa.String(200), nullable=False),
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

    # Indexes for common queries
    op.create_index("ix_assets_tipo", "assets", ["tipo"])
    op.create_index("ix_assets_estado_actual", "assets", ["estado_actual"])
    op.create_index("ix_assets_created_at", "assets", ["created_at"])
    op.create_index(
        "ix_mantenimiento_logs_asset_id",
        "mantenimiento_logs",
        ["asset_id"],
    )
    op.create_index(
        "ix_mantenimiento_logs_fecha_trabajo",
        "mantenimiento_logs",
        ["fecha_trabajo"],
    )


def downgrade() -> None:
    op.drop_index("ix_mantenimiento_logs_fecha_trabajo")
    op.drop_index("ix_mantenimiento_logs_asset_id")
    op.drop_index("ix_assets_created_at")
    op.drop_index("ix_assets_estado_actual")
    op.drop_index("ix_assets_tipo")
    op.drop_table("mantenimiento_logs")
    op.drop_table("assets")
    op.execute("DROP TYPE IF EXISTS estado_asset")
