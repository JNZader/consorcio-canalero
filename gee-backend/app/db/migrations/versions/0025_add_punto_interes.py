"""add punto_interes — staff notepad pins, dedicated and UNPUBLISHED

Operators need a private pin on the 2D map (culvert, raised section, blockage,
or a free note). This is not a denuncia, not a relevamiento_tramo, and not a
puntos_conflicto row: those tables carry other contracts and other audiences.

**Nothing here is published.** No view is created, no view is redefined, no
materialized view is created, ``martin/config.yaml`` gains no source. Same
structural privacy as ``cruce_camino`` (``0022_add_cruce_camino``): Martin
serves only the views named under ``tables:`` with ``auto_publish: false``, so
``punto_interes`` has no public surface at all.

``created_by`` stores the staff user id and is **not** a foreign key to
``users``. Auth tests override ``current_active_user`` with a
``SimpleNamespace``; an FK would make a successful POST require a real users
row for no gain.

Revision ID: 0025_add_punto_interes
Revises: 0024_add_cruce_conduccion
Create Date: 2026-09-19
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0025_add_punto_interes"
down_revision: Union[str, None] = "0024_add_cruce_conduccion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exposed as module constants (the ``0022`` / ``0024`` precedent) so the real-PG
# migration test runs the very same DDL instead of a re-typed copy that can drift.
CREATE_PUNTO_INTERES: str = """
    CREATE TABLE punto_interes (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        geometria   geometry(Point, 4326) NOT NULL,
        titulo      TEXT NOT NULL,
        nota        TEXT,
        tipo        TEXT NOT NULL,
        created_by  UUID,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_punto_interes_titulo_len CHECK (
            char_length(titulo) BETWEEN 1 AND 120
        ),
        CONSTRAINT ck_punto_interes_nota_len CHECK (
            nota IS NULL OR char_length(nota) <= 2000
        ),
        CONSTRAINT ck_punto_interes_tipo CHECK (
            tipo IN ('alcantarilla', 'alteo', 'taponamiento', 'otro')
        )
    )
"""

CREATE_GEOM_INDEX: str = (
    "CREATE INDEX ix_punto_interes_geom ON punto_interes USING GIST (geometria)"
)

UPGRADE_STATEMENTS: tuple[str, ...] = (CREATE_PUNTO_INTERES, CREATE_GEOM_INDEX)
DOWNGRADE_STATEMENTS: tuple[str, ...] = ("DROP TABLE punto_interes",)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
