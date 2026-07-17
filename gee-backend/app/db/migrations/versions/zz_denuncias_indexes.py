"""Add denuncias indexes — user_id btree + geom GIST.

The denuncias table grew without indexes on either:
  - ``user_id`` — read every time a citizen hits ``GET /denuncias/mine``
    (one row per their own denuncia, with an ORDER BY created_at).
    Without the index, that's a sequential scan per page-load.
  - ``geom`` — used by the map clipping queries and any future
    bbox/intersection query in the admin map. PostGIS spatial queries
    fall apart without a GIST index even on a few thousand rows.

Both indexes are CREATE INDEX IF NOT EXISTS so re-running the migration
on a database that already has them (e.g. from a manual ad-hoc fix)
doesn't fail.

Revision ID: zz_denuncias_indexes
Revises: zz_sug_notas
Create Date: 2026-05-19
"""

from alembic import op


revision = "zz_denuncias_indexes"
down_revision = "zz_sug_notas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_denuncias_user_id ON denuncias (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_denuncias_geom ON denuncias USING GIST (geom)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_denuncias_geom")
    op.execute("DROP INDEX IF EXISTS ix_denuncias_user_id")
