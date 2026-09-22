"""add canal_publicacion_aprhi — opt-in staff catalog of APRHI existentes

APRHI ``canales_existentes`` is the base inventory to improve, not the
source of truth and not 406 pgRouting edges. One catalog row per grouped
``nombre`` (empty/blank → ``(sin nombre APRHI)``). Geometry is dissolved
at read time with ``ST_LineMerge(ST_Union(geom))``.

``canal_id`` is ``aprhi-`` + an ASCII slug of that group key
(``Canal Viejo`` → ``aprhi-canal-viejo``). No ``?`` in the id, no FK onto
``canal_network.id``.

Default ``publicado = FALSE`` so ``GET /geo/canales/publico`` stays the
KMZ-60 catalog until staff turns a canal on.

Revision ID: 0027_add_canal_publicacion_aprhi
Revises: 0026_add_canal_publicacion
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0027_add_canal_publicacion_aprhi"
down_revision: Union[str, None] = "0026_add_canal_publicacion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with gee-backend/app/domains/geo/canales_publicacion/service.py
_APRHI_NOMBRE = "COALESCE(NULLIF(trim(cn.nombre), ''), '(sin nombre APRHI)')"
_HULL = "(SELECT ST_ConvexHull(ST_Collect(c.geom)) FROM canal_consorcio c)"
_SLUG = """
    'aprhi-' || COALESCE(
      NULLIF(
        trim(both '-' from regexp_replace(
          lower(translate(
            nombre_origen,
            'ÁÀÂÄÃÅáàâäãåÉÈÊËéèêëÍÌÎÏíìîïÓÒÔÖÕóòôöõÚÙÛÜúùûüÑñÇç',
            'AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuNnCc'
          )),
          '[^a-z0-9]+', '-', 'g'
        )),
        ''
      ),
      'unnamed'
    )
"""

CREATE_CANAL_PUBLICACION_APRHI: str = """
    CREATE TABLE canal_publicacion_aprhi (
        canal_id TEXT PRIMARY KEY,
        nombre_origen TEXT NOT NULL UNIQUE,
        publicado BOOLEAN NOT NULL DEFAULT FALSE,
        nombre_publico TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""

SEED_FROM_NETWORK: str = f"""
    WITH names AS (
        SELECT DISTINCT {_APRHI_NOMBRE} AS nombre_origen
        FROM canal_network cn
        WHERE cn.tipo = 'canales_existentes'
          AND ST_Intersects(cn.geom, {_HULL})
    ),
    slugged AS (
        SELECT nombre_origen, {_SLUG} AS base_slug
        FROM names
    ),
    ranked AS (
        SELECT
            nombre_origen,
            base_slug,
            ROW_NUMBER() OVER (PARTITION BY base_slug ORDER BY nombre_origen) AS rn
        FROM slugged
    )
    INSERT INTO canal_publicacion_aprhi (
        canal_id, nombre_origen, publicado, nombre_publico
    )
    SELECT
        CASE WHEN rn = 1 THEN base_slug
             ELSE base_slug || '-' || (rn - 1)::text
        END,
        nombre_origen,
        FALSE,
        nombre_origen
    FROM ranked
    ON CONFLICT (nombre_origen) DO NOTHING
"""

DROP_CANAL_PUBLICACION_APRHI: str = "DROP TABLE IF EXISTS canal_publicacion_aprhi"


def upgrade() -> None:
    op.execute(CREATE_CANAL_PUBLICACION_APRHI)
    op.execute(SEED_FROM_NETWORK)


def downgrade() -> None:
    op.execute(DROP_CANAL_PUBLICACION_APRHI)
