"""add capas table

Revision ID: e9f6a3b4c705
Revises: d8e5f2a3b694
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e9f6a3b4c705"
down_revision: Union[str, None] = "d8e5f2a3b694"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    tipo_capa = postgresql.ENUM(
        "polygon", "line", "point", "raster", "tile",
        name="tipo_capa",
        create_type=False,
    )
    fuente_capa = postgresql.ENUM(
        "local", "gee", "upload",
        name="fuente_capa",
        create_type=False,
    )

    # Create enums in database
    tipo_capa.create(op.get_bind(), checkfirst=True)
    fuente_capa.create(op.get_bind(), checkfirst=True)

    # Create capas_v2 table
    op.create_table(
        "capas_v2",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=True),
        sa.Column("tipo", tipo_capa, nullable=False),
        sa.Column("fuente", fuente_capa, nullable=False),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("geojson_data", postgresql.JSON, nullable=True),
        sa.Column(
            "estilo",
            postgresql.JSON,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "visible",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "orden",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "es_publica",
            sa.Boolean,
            nullable=False,
            server_default="false",
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
    op.create_index("ix_capas_v2_orden", "capas_v2", ["orden"])
    op.create_index("ix_capas_v2_tipo", "capas_v2", ["tipo"])
    op.create_index("ix_capas_v2_es_publica", "capas_v2", ["es_publica"])
    op.create_index("ix_capas_v2_visible", "capas_v2", ["visible"])


def downgrade() -> None:
    op.drop_index("ix_capas_v2_visible")
    op.drop_index("ix_capas_v2_es_publica")
    op.drop_index("ix_capas_v2_tipo")
    op.drop_index("ix_capas_v2_orden")
    op.drop_table("capas_v2")

    # Drop enum types
    sa.Enum(name="fuente_capa").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tipo_capa").drop(op.get_bind(), checkfirst=True)
