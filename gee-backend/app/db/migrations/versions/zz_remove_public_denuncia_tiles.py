"""Remove exact citizen denuncia locations from the public tile surface.

Revision ID: zz_remove_public_denuncia_tiles
Revises: zz_celery_task_outbox
Create Date: 2026-07-21
"""

from alembic import op


revision = "zz_remove_public_denuncia_tiles"
down_revision = "zz_celery_task_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dropping the view also removes any reader ACL attached to that object.
    # Authenticated backend routes continue to query the base denuncias table.
    op.execute("DROP VIEW IF EXISTS public.vt_denuncias")


def downgrade() -> None:
    # Restore the legacy application-owned projection for rollback tooling, but
    # exclude cancelled rows. Public Martin configs and reader provisioning do
    # not publish or grant this view.
    op.execute(
        """
        CREATE VIEW public.vt_denuncias AS
        SELECT
            id,
            tipo,
            estado,
            cuenca,
            created_at,
            geom
        FROM public.denuncias
        WHERE geom IS NOT NULL
          AND deleted_at IS NULL
        """
    )
