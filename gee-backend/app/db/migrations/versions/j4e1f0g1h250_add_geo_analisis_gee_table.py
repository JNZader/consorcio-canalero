"""add geo_analisis_gee table

Revision ID: j4e1f0g1h250
Revises: i3d0e8f9g149
Create Date: 2026-03-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "j4e1f0g1h250"
down_revision: Union[str, None] = "i3d0e8f9g149"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type for analysis tipo
    tipo_analisis_geo = postgresql.ENUM(
        "flood",
        "vegetation",
        "ndvi",
        "custom",
        name="tipo_analisis_geo",
        create_type=False,
    )
    tipo_analisis_geo.create(op.get_bind(), checkfirst=True)

    # Reuse existing estado_geo_job enum (already created in geo tables migration)

    op.create_table(
        "geo_analisis_gee",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tipo", tipo_analisis_geo, nullable=False),
        sa.Column("fecha_analisis", sa.Date, nullable=False),
        sa.Column(
            "parametros",
            postgresql.JSON,
            nullable=True,
            comment="Input params: date range, region, thresholds, method",
        ),
        sa.Column(
            "resultado",
            postgresql.JSON,
            nullable=True,
            comment="Output: stats, metrics, tile URLs, classification %",
        ),
        sa.Column(
            "estado",
            postgresql.ENUM(
                "pending",
                "running",
                "completed",
                "failed",
                name="estado_geo_job",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "error",
            sa.Text,
            nullable=True,
            comment="Error message if analysis failed",
        ),
        sa.Column(
            "celery_task_id",
            sa.String(255),
            nullable=True,
            comment="Celery async result ID",
        ),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
            comment="User who requested the analysis",
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

    op.create_index("ix_geo_analisis_gee_tipo", "geo_analisis_gee", ["tipo"])
    op.create_index("ix_geo_analisis_gee_estado", "geo_analisis_gee", ["estado"])
    op.create_index("ix_geo_analisis_gee_fecha", "geo_analisis_gee", ["fecha_analisis"])


def downgrade() -> None:
    op.drop_index("ix_geo_analisis_gee_fecha")
    op.drop_index("ix_geo_analisis_gee_estado")
    op.drop_index("ix_geo_analisis_gee_tipo")
    op.drop_table("geo_analisis_gee")

    sa.Enum(name="tipo_analisis_geo").drop(op.get_bind(), checkfirst=True)
