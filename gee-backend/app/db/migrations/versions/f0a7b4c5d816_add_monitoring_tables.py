"""add monitoring tables

Revision ID: f0a7b4c5d816
Revises: e9f6a3b4c705
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f0a7b4c5d816"
down_revision: Union[str, None] = "e9f6a3b4c705"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    estado_sugerencia = postgresql.ENUM(
        "pendiente",
        "revisada",
        "implementada",
        "descartada",
        name="estado_sugerencia",
        create_type=False,
    )
    tipo_analisis = postgresql.ENUM(
        "inundacion",
        "vegetacion",
        "sar",
        "clasificacion",
        name="tipo_analisis",
        create_type=False,
    )

    estado_sugerencia.create(op.get_bind(), checkfirst=True)
    tipo_analisis.create(op.get_bind(), checkfirst=True)

    # sugerencias_v2 table
    op.create_table(
        "sugerencias_v2",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("categoria", sa.String(100), nullable=True),
        sa.Column(
            "estado",
            estado_sugerencia,
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column("contacto_email", sa.String(255), nullable=True),
        sa.Column("contacto_nombre", sa.String(200), nullable=True),
        sa.Column("respuesta", sa.Text(), nullable=True),
        sa.Column(
            "usuario_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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

    # analisis_gee table
    op.create_table(
        "analisis_gee",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tipo", tipo_analisis, nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=False),
        sa.Column("resultados", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("hectareas_afectadas", sa.Float(), nullable=True),
        sa.Column("porcentaje_area", sa.Float(), nullable=True),
        sa.Column("parametros", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "usuario_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
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


def downgrade() -> None:
    op.drop_table("analisis_gee")
    op.drop_table("sugerencias_v2")

    # Drop enum types
    sa.Enum(name="tipo_analisis").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="estado_sugerencia").drop(op.get_bind(), checkfirst=True)
