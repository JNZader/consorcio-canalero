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
    # denuncias (bare table, no _v2 suffix)
    op.execute("CREATE INDEX IF NOT EXISTS idx_denuncias_estado ON denuncias(estado)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_denuncias_created_at ON denuncias(created_at)"
    )

    # sugerencias_v2 (no `prioridad` column — skipped)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sugerencias_v2_estado ON sugerencias_v2(estado)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sugerencias_v2_categoria ON sugerencias_v2(categoria)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sugerencias_v2_created_at ON sugerencias_v2(created_at)"
    )

    # tramites_v2 (ix_tramites_v2_estado / ix_tramites_v2_tipo already exist as btree;
    # IF NOT EXISTS guards so this is a no-op in practice)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tramites_v2_estado ON tramites_v2(estado)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_tramites_v2_tipo ON tramites_v2(tipo)")

    # reuniones_v2 (column is `fecha_reunion`, not `fecha`;
    # ix_reuniones_v2_estado / ix_reuniones_v2_fecha_reunion already exist)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reuniones_v2_estado ON reuniones_v2(estado)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reuniones_v2_fecha_reunion ON reuniones_v2(fecha_reunion)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_reuniones_v2_fecha_reunion")
    op.execute("DROP INDEX IF EXISTS idx_reuniones_v2_estado")
    op.execute("DROP INDEX IF EXISTS idx_tramites_v2_tipo")
    op.execute("DROP INDEX IF EXISTS idx_tramites_v2_estado")
    op.execute("DROP INDEX IF EXISTS idx_sugerencias_v2_created_at")
    op.execute("DROP INDEX IF EXISTS idx_sugerencias_v2_categoria")
    op.execute("DROP INDEX IF EXISTS idx_sugerencias_v2_estado")
    op.execute("DROP INDEX IF EXISTS idx_denuncias_created_at")
    op.execute("DROP INDEX IF EXISTS idx_denuncias_estado")
