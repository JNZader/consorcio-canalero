"""add performance indexes on management tables

Revision ID: zz_mgmt_indexes
Revises: z0u7v8w9x826
Create Date: 2026-04-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "zz_mgmt_indexes"
down_revision: Union[str, None] = "z0u7v8w9x826"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # denuncias
    op.execute("CREATE INDEX IF NOT EXISTS idx_denuncias_estado ON denuncias(estado)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_denuncias_fecha_creacion ON denuncias(fecha_creacion)")

    # sugerencias
    op.execute("CREATE INDEX IF NOT EXISTS idx_sugerencias_estado ON sugerencias(estado)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sugerencias_categoria ON sugerencias(categoria)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sugerencias_prioridad ON sugerencias(prioridad)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sugerencias_fecha_creacion ON sugerencias(fecha_creacion)")

    # tramites
    op.execute("CREATE INDEX IF NOT EXISTS idx_tramites_estado ON tramites(estado)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tramites_tipo ON tramites(tipo)")

    # reuniones
    op.execute("CREATE INDEX IF NOT EXISTS idx_reuniones_estado ON reuniones(estado)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reuniones_fecha ON reuniones(fecha)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_reuniones_fecha")
    op.execute("DROP INDEX IF EXISTS idx_reuniones_estado")
    op.execute("DROP INDEX IF EXISTS idx_tramites_tipo")
    op.execute("DROP INDEX IF EXISTS idx_tramites_estado")
    op.execute("DROP INDEX IF EXISTS idx_sugerencias_fecha_creacion")
    op.execute("DROP INDEX IF EXISTS idx_sugerencias_prioridad")
    op.execute("DROP INDEX IF EXISTS idx_sugerencias_categoria")
    op.execute("DROP INDEX IF EXISTS idx_sugerencias_estado")
    op.execute("DROP INDEX IF EXISTS idx_denuncias_fecha_creacion")
    op.execute("DROP INDEX IF EXISTS idx_denuncias_estado")
