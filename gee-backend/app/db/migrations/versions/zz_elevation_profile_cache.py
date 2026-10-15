"""add elevation_profile_cache — stored longitudinal profiles

Derived data, keyed by sha256(geometry + sampled-raster identity) so a new DEM
run or a re-mosaicked MDE-Ar invalidates by construction. See
``docs/ALTIMETRIA-FUENTES.md`` for the contract and the new-source procedure.

Revision ID: zz_elevation_profile_cache
Revises: zz_audit_v6_db
"""

from typing import Sequence, Union

from alembic import op

revision: str = "zz_elevation_profile_cache"
down_revision: Union[str, None] = "zz_audit_v6_db"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS elevation_profile_cache (
        cache_key TEXT PRIMARY KEY,
        source_identity TEXT NOT NULL,
        payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""

CREATE_INDEX = """
    CREATE INDEX IF NOT EXISTS ix_elevation_profile_cache_created_at
        ON elevation_profile_cache (created_at)
"""


def upgrade() -> None:
    op.execute(CREATE_TABLE)
    op.execute(CREATE_INDEX)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS elevation_profile_cache")
