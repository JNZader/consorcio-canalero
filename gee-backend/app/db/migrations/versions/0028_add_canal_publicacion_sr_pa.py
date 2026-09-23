"""add canal_publicacion_sr_pa — opt-in staff catalog of official SR PA works

Staff pick individual CA codes in /admin/canales. Default unpublished so
GET /geo/canales/publico stays KMZ (+ any existentes already opted in).

Geometry stays in consorcio-web/public/capas/aprhi_sr_pa.geojson; this table
is only the publish switch.

Revision ID: 0028_add_canal_publicacion_sr_pa
Revises: 0027_add_canal_publicacion_aprhi
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0028_add_canal_publicacion_sr_pa"
down_revision: Union[str, None] = "0027_add_canal_publicacion_aprhi"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_TABLE = """
    CREATE TABLE canal_publicacion_sr_pa (
        canal_id TEXT PRIMARY KEY,
        publicado BOOLEAN NOT NULL DEFAULT FALSE,
        nombre_publico TEXT NOT NULL,
        estado_registro TEXT NOT NULL DEFAULT '',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""


def upgrade() -> None:
    op.execute(CREATE_TABLE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS canal_publicacion_sr_pa")
