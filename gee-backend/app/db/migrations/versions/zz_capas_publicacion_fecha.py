"""Agregar capas_v2.publicacion_fecha (columna huerfana en el modelo).

El modelo Capa declara ``publicacion_fecha`` desde hace tiempo pero NINGUNA
migracion la creaba: se agrego al ORM y nunca se genero el add_column. El bug
quedo latente hasta el deploy del 2026-07-27 (152 commits), cuando el codigo
nuevo empezo a SELECCIONAR la columna y ``GET /api/v2/public/layers`` revento
con 500 (UndefinedColumn). Consecuencia visible: el visor sin login no mostraba
ninguna capa publica porque la lista nunca cargaba.

Nullable, sin default: es la fecha en que una capa se publico, null mientras no
se publico. No hay backfill — las capas ya publicadas (es_publica=true) quedan
con publicacion_fecha NULL, que es exactamente "publicada en fecha desconocida"
y no rompe nada.

Revision ID: zz_capas_publicacion_fecha
Revises: zz_remove_public_denuncia_tiles
Create Date: 2026-07-27
"""

from alembic import op

revision = "zz_capas_publicacion_fecha"
down_revision = "zz_remove_public_denuncia_tiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: en alguna base la columna podria existir de un create_all
    # (los tests crean el esquema desde el ORM). En prod no existe y se crea.
    op.execute(
        "ALTER TABLE capas_v2 ADD COLUMN IF NOT EXISTS publicacion_fecha TIMESTAMP WITH TIME ZONE"
    )


def downgrade() -> None:
    op.drop_column("capas_v2", "publicacion_fecha")
