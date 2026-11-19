"""informes_area — the informe de área tracking table (PR 2, T1).

Revision ID: zz_informes_area
Revises: zz_denuncia_asignacion

One row per background informe. PRIVATE by construction (S11, decision L2):
``usuario_id`` is NOT NULL and every read path filters on it first; the admin
view is an explicit service-level branch, never a missing WHERE clause.

Estado reuses the EXISTING ``estado_geo_job`` enum (pending/running/
completed/failed) — the informe is a geo-queue job like any other, and a
second status vocabulary would split what the job tooling already knows how
to read. No values are added to that type here.

``tipo_geo_job`` DOES get ``informe_area``: nothing writes it into
``geo_jobs`` in T1 (the informe tracks itself here), but the value exists so
the enum can name these runs the moment an operator-facing job listing wants
them. Same ``IF NOT EXISTS`` + permanent-residue contract as ``0022`` /
``0023``: PostgreSQL cannot remove an enum value, so the downgrade leaves it.

Cache identity is STORED, not recomputed: ``hash_seleccion`` (sha256 of the
normalized union geometry + sorted zona ids, S4) and ``version_clave`` (that
hash + per-layer versions + ``version_plantilla``). The compound
``(usuario_id, version_clave)`` index is the cache probe; ``vence_at`` is the
daily retention sweep's scan key (S11, 90 days).

NOTE (S10 / AGENTS.md): the box does NOT run Alembic — this migration is
applied manually, and that step goes in the PR description.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "zz_informes_area"
down_revision: Union[str, None] = "zz_denuncia_asignacion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADD_ENUM_VALUE = "ALTER TYPE tipo_geo_job ADD VALUE IF NOT EXISTS 'informe_area'"


def upgrade() -> None:
    # The enum value first and on its own: ``ALTER TYPE ... ADD VALUE``
    # cannot run in the same transaction as a statement that uses the new
    # value on older PostgreSQL (same ordering as ``0023``).
    op.execute(ADD_ENUM_VALUE)
    op.create_table(
        "informes_area",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column(
            "estado",
            # ``create_type=False``: ``estado_geo_job`` ALREADY exists (born
            # with ``geo_jobs``); without this Alembic emits a duplicate
            # ``CREATE TYPE`` that aborts the migration.
            postgresql.ENUM(
                "pending",
                "running",
                "completed",
                "failed",
                name="estado_geo_job",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("hash_seleccion", sa.String(length=64), nullable=False),
        sa.Column("version_clave", sa.String(length=600), nullable=False),
        sa.Column("parametros", postgresql.JSONB(), nullable=True),
        sa.Column("resultado", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("progreso", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("vence_at", sa.DateTime(timezone=True), nullable=False),
        # T2: the rendered PDF lives IN the row (bytea, deferred at the ORM
        # layer) — ≤5 MB per S9, deleted with the row by the retention sweep,
        # visible to worker and API without volume coupling.
        sa.Column("pdf_bytes", postgresql.BYTEA(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_informes_area_usuario_id", "informes_area", ["usuario_id"])
    op.create_index(
        "ix_informes_area_usuario_version", "informes_area", ["usuario_id", "version_clave"]
    )
    op.create_index("ix_informes_area_vence_at", "informes_area", ["vence_at"])


def downgrade() -> None:
    # The table drops; the enum value stays (PostgreSQL has no DROP VALUE) —
    # same documented permanent residue as 0022/0023.
    op.drop_index("ix_informes_area_vence_at", table_name="informes_area")
    op.drop_index("ix_informes_area_usuario_version", table_name="informes_area")
    op.drop_index("ix_informes_area_usuario_id", table_name="informes_area")
    op.drop_table("informes_area")
