"""add geo tables

Revision ID: g1b8c5d6e927
Revises: f0a7b4c5d816
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "g1b8c5d6e927"
down_revision: Union[str, None] = "f0a7b4c5d816"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    tipo_geo_layer = postgresql.ENUM(
        "slope",
        "aspect",
        "flow_dir",
        "flow_acc",
        "twi",
        "hand",
        "drainage",
        "terrain_class",
        name="tipo_geo_layer",
        create_type=False,
    )
    fuente_geo_layer = postgresql.ENUM(
        "dem_pipeline",
        "gee",
        "manual",
        name="fuente_geo_layer",
        create_type=False,
    )
    formato_geo_layer = postgresql.ENUM(
        "geotiff",
        "geojson",
        name="formato_geo_layer",
        create_type=False,
    )
    tipo_geo_job = postgresql.ENUM(
        "dem_pipeline",
        "slope",
        "aspect",
        "flow_dir",
        "flow_acc",
        "twi",
        "hand",
        "drainage",
        "terrain_class",
        name="tipo_geo_job",
        create_type=False,
    )
    estado_geo_job = postgresql.ENUM(
        "pending",
        "running",
        "completed",
        "failed",
        name="estado_geo_job",
        create_type=False,
    )

    # Create enums in database
    tipo_geo_layer.create(op.get_bind(), checkfirst=True)
    fuente_geo_layer.create(op.get_bind(), checkfirst=True)
    formato_geo_layer.create(op.get_bind(), checkfirst=True)
    tipo_geo_job.create(op.get_bind(), checkfirst=True)
    estado_geo_job.create(op.get_bind(), checkfirst=True)

    # Create geo_layers table
    op.create_table(
        "geo_layers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("tipo", tipo_geo_layer, nullable=False),
        sa.Column("fuente", fuente_geo_layer, nullable=False),
        sa.Column(
            "archivo_path",
            sa.String(500),
            nullable=False,
            comment="Path to the GeoTIFF/GeoJSON file on disk",
        ),
        sa.Column(
            "formato", formato_geo_layer, nullable=False, server_default="geotiff"
        ),
        sa.Column("srid", sa.Integer, nullable=False, server_default="4326"),
        sa.Column(
            "bbox",
            postgresql.JSON,
            nullable=True,
            comment="Bounding box [minx, miny, maxx, maxy]",
        ),
        sa.Column(
            "metadata_extra",
            postgresql.JSON,
            nullable=True,
            comment="Resolution, nodata value, statistics, etc.",
        ),
        sa.Column(
            "area_id",
            sa.String(100),
            nullable=True,
            comment="Identifier for the processing area",
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

    op.create_index("ix_geo_layers_tipo", "geo_layers", ["tipo"])
    op.create_index("ix_geo_layers_fuente", "geo_layers", ["fuente"])
    op.create_index("ix_geo_layers_area_id", "geo_layers", ["area_id"])

    # Create geo_jobs table
    op.create_table(
        "geo_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tipo", tipo_geo_job, nullable=False),
        sa.Column("estado", estado_geo_job, nullable=False, server_default="pending"),
        sa.Column(
            "celery_task_id",
            sa.String(255),
            nullable=True,
            comment="Celery async result ID",
        ),
        sa.Column(
            "parametros",
            postgresql.JSON,
            nullable=True,
            comment="Input parameters for the job",
        ),
        sa.Column(
            "resultado",
            postgresql.JSON,
            nullable=True,
            comment="Output summary after completion",
        ),
        sa.Column(
            "error",
            sa.Text,
            nullable=True,
            comment="Error message if job failed",
        ),
        sa.Column(
            "progreso",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Completion percentage 0-100",
        ),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
            comment="User who submitted the job",
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

    op.create_index("ix_geo_jobs_estado", "geo_jobs", ["estado"])
    op.create_index("ix_geo_jobs_tipo", "geo_jobs", ["tipo"])
    op.create_index("ix_geo_jobs_usuario_id", "geo_jobs", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_geo_jobs_usuario_id")
    op.drop_index("ix_geo_jobs_tipo")
    op.drop_index("ix_geo_jobs_estado")
    op.drop_table("geo_jobs")

    op.drop_index("ix_geo_layers_area_id")
    op.drop_index("ix_geo_layers_fuente")
    op.drop_index("ix_geo_layers_tipo")
    op.drop_table("geo_layers")

    # Drop enum types
    sa.Enum(name="estado_geo_job").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tipo_geo_job").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="formato_geo_layer").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="fuente_geo_layer").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tipo_geo_layer").drop(op.get_bind(), checkfirst=True)
