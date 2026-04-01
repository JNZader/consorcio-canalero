"""add vector tile views for Martin

Revision ID: v6q3r4s5t482
Revises: u5p2q3r4s371
Create Date: 2026-04-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "v6q3r4s5t482"
down_revision: Union[str, None] = "u5p2q3r4s371"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Zonas Operativas (polygons) ─────────────────────
    op.execute("""
        CREATE OR REPLACE VIEW vt_zonas_operativas AS
        SELECT
            id,
            nombre,
            cuenca,
            superficie_ha,
            geometria
        FROM zonas_operativas;
    """)

    # ── Puntos de Conflicto (points) ────────────────────
    op.execute("""
        CREATE OR REPLACE VIEW vt_puntos_conflicto AS
        SELECT
            id,
            tipo,
            severidad,
            descripcion,
            acumulacion_valor,
            pendiente_valor,
            geometria
        FROM puntos_conflicto;
    """)

    # ── Denuncias ciudadanas (points) ───────────────────
    op.execute("""
        CREATE OR REPLACE VIEW vt_denuncias AS
        SELECT
            id,
            tipo,
            estado,
            cuenca,
            created_at,
            geom
        FROM denuncias
        WHERE geom IS NOT NULL;
    """)

    # ── Assets de infraestructura (points) ──────────────
    op.execute("""
        CREATE OR REPLACE VIEW vt_assets AS
        SELECT
            id,
            nombre,
            tipo,
            estado_actual,
            material,
            geom
        FROM assets
        WHERE geom IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vt_assets;")
    op.execute("DROP VIEW IF EXISTS vt_denuncias;")
    op.execute("DROP VIEW IF EXISTS vt_puntos_conflicto;")
    op.execute("DROP VIEW IF EXISTS vt_zonas_operativas;")
