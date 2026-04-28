"""drop infraestructura tables

Retires the `infraestructura` domain (assets + mantenimiento_logs + supporting
view + enum) — the asset-management feature was removed from the frontend in
the cleanup pass that split the legacy "Infraestructura" panel out of `main`.
The backend tables had no admin UI to surface them, so they accumulated
nothing useful and the FK from mantenimiento_logs cascades cleanly.

We KEEP the original `a3b7d9e1f482_add_infraestructura_tables` migration
intact so historical envs can still rebuild from scratch — this is the
standard Alembic "drop later" pattern. The vector tile view `vt_assets`
created in `v6q3r4s5t482_add_vector_tile_views` is dropped here too with
`IF EXISTS`, so re-running upgrade on a clean DB never resurrects it.

Revision ID: zz_drop_infra
Revises: zz_mgmt_indexes
Create Date: 2026-04-28
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "zz_drop_infra"
down_revision: Union[str, None] = "zz_mgmt_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the Martin vector-tile view first — it depends on the assets table.
    op.execute("DROP VIEW IF EXISTS vt_assets;")

    # Drop indexes (IF EXISTS to tolerate envs where they were never created).
    op.execute("DROP INDEX IF EXISTS ix_mantenimiento_logs_fecha_trabajo;")
    op.execute("DROP INDEX IF EXISTS ix_mantenimiento_logs_asset_id;")
    op.execute("DROP INDEX IF EXISTS ix_assets_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_assets_estado_actual;")
    op.execute("DROP INDEX IF EXISTS ix_assets_tipo;")

    # mantenimiento_logs has FK→assets ON DELETE CASCADE so order is not
    # technically required, but dropping the child first matches the create
    # migration's reverse order and reads cleaner.
    op.execute("DROP TABLE IF EXISTS mantenimiento_logs CASCADE;")
    op.execute("DROP TABLE IF EXISTS assets CASCADE;")

    # Drop the enum that backed `assets.estado_actual` — no other table uses
    # `estado_asset` so this is safe.
    op.execute("DROP TYPE IF EXISTS estado_asset;")


def downgrade() -> None:
    # Intentional one-way migration — restoring the deleted feature requires
    # re-introducing the domain code (models, router, service, repository,
    # frontend hook + modal). At that point the create migration
    # `a3b7d9e1f482_add_infraestructura_tables` should be re-applied
    # manually before this `downgrade()` is asked to recreate the view.
    raise NotImplementedError(
        "drop_infraestructura_tables is one-way. "
        "To restore, reintroduce the domain code and re-run "
        "a3b7d9e1f482_add_infraestructura_tables manually."
    )
