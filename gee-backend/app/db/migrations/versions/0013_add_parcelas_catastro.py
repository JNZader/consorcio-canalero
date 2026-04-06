"""add parcelas_catastro table

Revision ID: 0013_add_parcelas_catastro
Revises: a1b2c3d4e5f6
Create Date: 2026-04-06
"""

from typing import Sequence, Union

import geoalchemy2
from alembic import op
import sqlalchemy as sa

revision: str = "0013_add_parcelas_catastro"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "parcelas_catastro",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "nomenclatura",
            sa.String(50),
            nullable=False,
            comment="IDECOR parcel identifier — links to consorcistas.parcela",
        ),
        sa.Column(
            "geometria",
            geoalchemy2.types.Geometry(geometry_type="POLYGON", srid=4326),
            nullable=False,
        ),
        sa.Column("tipo_parcela", sa.String(50), nullable=True),
        sa.Column("desig_oficial", sa.String(100), nullable=True),
        sa.Column("departamento", sa.String(100), nullable=True),
        sa.Column("pedania", sa.String(100), nullable=True),
        sa.Column(
            "superficie_ha",
            sa.Float,
            nullable=True,
            comment="Area in hectares (Superficie_Tierra_Rural / 10000)",
        ),
        sa.Column("nro_cuenta", sa.String(50), nullable=True),
        sa.Column("par_idparcela", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_parcelas_catastro_nomenclatura",
        "parcelas_catastro",
        ["nomenclatura"],
        unique=True,
    )

    op.execute(
        "CREATE INDEX ix_parcelas_catastro_geom ON parcelas_catastro USING GIST (geometria)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_parcelas_catastro_geom")
    op.drop_index("ix_parcelas_catastro_nomenclatura", table_name="parcelas_catastro")
    op.drop_table("parcelas_catastro")
