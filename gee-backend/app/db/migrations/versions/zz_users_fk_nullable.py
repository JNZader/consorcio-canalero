"""Make users-FK columns nullable where ondelete=SET NULL.

Several tables declare ``ForeignKey("users.id", ondelete="SET NULL")``
on columns that were also ``NOT NULL``. That combination is broken:
when a user is deleted, PostgreSQL tries to SET NULL and the NOT NULL
constraint rejects it, so the user row can never be deleted while it
has related records.

Decision: keep the SET NULL semantics (better for auditoria — the
gasto/tramite/reunion/historial record survives the user deletion,
just orphaned of author) and relax the columns to NULLABLE.

Affected columns (all ``usuario_id`` -> ``users.id``):

  - ``gastos_v2.usuario_id``
  - ``ingresos_v2.usuario_id``
  - ``tramites_v2.usuario_id``
  - ``tramites_seguimiento.usuario_id``
  - ``reuniones_v2.usuario_id``
  - ``denuncias_historial.usuario_id``

``denuncias.user_id`` is untouched — it was already nullable.

Revision ID: zz_users_fk_nullable
Revises: zz_email_codes
Create Date: 2026-07-04
"""

from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "zz_users_fk_nullable"
down_revision = "zz_email_codes"
branch_labels = None
depends_on = None


_COLUMNS: list[tuple[str, str]] = [
    ("gastos_v2", "usuario_id"),
    ("ingresos_v2", "usuario_id"),
    ("tramites_v2", "usuario_id"),
    ("tramites_seguimiento", "usuario_id"),
    ("reuniones_v2", "usuario_id"),
    ("denuncias_historial", "usuario_id"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=UUID(as_uuid=True),
            nullable=True,
        )


def downgrade() -> None:
    # NOTE: this will fail if any row already has a NULL usuario_id
    # (i.e. a referenced user was deleted after the upgrade). Those
    # rows must be reassigned or removed manually before downgrading.
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=UUID(as_uuid=True),
            nullable=False,
        )
