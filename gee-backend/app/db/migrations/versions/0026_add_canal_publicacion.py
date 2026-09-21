"""add canal_publicacion — staff catalog of what the public map shows

The KMZ/ETL names (``Canal existente (sin intervención)``) are internal.
This table is the projection the citizen map reads: which curated canal
(``canal_consorcio.id``) is published, and under which public name.

Default ``publicado = true`` and ``nombre_publico = canal_consorcio.nombre``
so the public map does not go blank on upgrade. Staff unchecks and renames.

Not a Martin source. Public access is only ``GET /geo/canales/publico``.

Revision ID: 0026_add_canal_publicacion
Revises: 0025_add_punto_interes
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0026_add_canal_publicacion"
down_revision: Union[str, None] = "0025_add_punto_interes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_CANAL_PUBLICACION: str = """
    CREATE TABLE canal_publicacion (
        canal_id TEXT PRIMARY KEY
            REFERENCES canal_consorcio(id) ON DELETE CASCADE,
        publicado BOOLEAN NOT NULL DEFAULT TRUE,
        nombre_publico TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""

SEED_FROM_CONSORCIO: str = """
    INSERT INTO canal_publicacion (canal_id, publicado, nombre_publico)
    SELECT id, TRUE, nombre FROM canal_consorcio
    ON CONFLICT (canal_id) DO NOTHING
"""

DROP_CANAL_PUBLICACION: str = "DROP TABLE IF EXISTS canal_publicacion"


def upgrade() -> None:
    op.execute(CREATE_CANAL_PUBLICACION)
    op.execute(SEED_FROM_CONSORCIO)


def downgrade() -> None:
    op.execute(DROP_CANAL_PUBLICACION)
