"""add pgrouting and canal network topology

Revision ID: w7r4s5t6u593
Revises: v6q3r4s5t482
Create Date: 2026-04-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "w7r4s5t6u593"
down_revision: Union[str, None] = "v6q3r4s5t482"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pgRouting extension
    op.execute("CREATE EXTENSION IF NOT EXISTS pgrouting CASCADE;")

    # 2. Create canal_network table for routable edges
    op.execute("""
        CREATE TABLE IF NOT EXISTS canal_network (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(255),
            tipo VARCHAR(100),
            source INTEGER,
            target INTEGER,
            cost DOUBLE PRECISION,
            reverse_cost DOUBLE PRECISION
        );
    """)

    # Add geometry columns (geom for display, the_geom for pgRouting topology)
    op.execute("""
        SELECT AddGeometryColumn('canal_network', 'geom', 4326, 'LINESTRING', 2);
    """)
    op.execute("""
        SELECT AddGeometryColumn('canal_network', 'the_geom', 4326, 'LINESTRING', 2);
    """)

    # 3. Create spatial index
    op.execute(
        "CREATE INDEX idx_canal_network_geom ON canal_network USING GIST (geom);"
    )
    op.execute(
        "CREATE INDEX idx_canal_network_the_geom ON canal_network USING GIST (the_geom);"
    )

    # 4. Create vector tile view
    op.execute("""
        CREATE OR REPLACE VIEW vt_canal_network AS
        SELECT
            id,
            nombre,
            tipo,
            source,
            target,
            cost,
            geom
        FROM canal_network;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vt_canal_network;")
    op.execute("DROP TABLE IF EXISTS canal_network_vertices_pgr CASCADE;")
    op.execute("DROP TABLE IF EXISTS canal_network CASCADE;")
    op.execute("DROP EXTENSION IF EXISTS pgrouting CASCADE;")
