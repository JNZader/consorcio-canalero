"""informes_area — campo columns: token_publico + kmz_bytes + campo_paquete (PR 6).

Revision ID: zz_informes_area_campo
Revises: zz_riesgo_validacion_evento

PR 6 of the informe plan (``odd/tasks/informe-area-pr6.md``):

* ``token_publico`` — the opaque URL-safe token the PDF-cover QR encodes
  (S5/S7). Generated at CREATE time (``secrets.token_urlsafe``), so it is
  never NULL and never changes for a row; it carries no user data and is
  not derived from the informe id. UNIQUE because it is the ONLY lookup key
  of the public ``GET /api/v2/public/campo/{token}`` route — the row's
  ``vence_at`` (90 days, PR 2) is the token's lifetime and deleting the row
  (the daily retention sweep) revokes it.
* ``kmz_bytes`` — the Google Earth export (S3), built in the same task run
  as the PDF and stored in the same completion compare-and-set.
* ``campo_paquete`` — the offline field package JSON (S4, target ≤ 15 MB).

Both bytea columns follow ``pdf_bytes``: DB bytes over a geo-volume path,
deferred at the ORM layer, reclaimed by the retention sweep with the row.

NOTE (S10 / AGENTS.md): the box does NOT run Alembic — this migration is
applied manually, and that step goes in the PR description.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "zz_informes_area_campo"
down_revision: Union[str, None] = "zz_riesgo_validacion_evento"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "informes_area",
        sa.Column("token_publico", sa.String(length=64), nullable=True),
    )
    # Backfill BEFORE the NOT NULL + UNIQUE land: one random token per
    # existing row (no personal data, no derivation — exactly what create
    # generates from now on). gen_random_uuid().text is the SQL-side
    # equivalent of secrets.token_urlsafe: opaque and unique per row.
    op.execute("UPDATE informes_area SET token_publico = replace(gen_random_uuid()::text, '-', '')")
    op.alter_column("informes_area", "token_publico", nullable=False)
    op.create_index(
        "uq_informes_area_token_publico", "informes_area", ["token_publico"], unique=True
    )
    op.add_column(
        "informes_area",
        sa.Column("kmz_bytes", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "informes_area",
        sa.Column("campo_paquete", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("informes_area", "campo_paquete")
    op.drop_column("informes_area", "kmz_bytes")
    op.drop_index("uq_informes_area_token_publico", table_name="informes_area")
    op.drop_column("informes_area", "token_publico")
