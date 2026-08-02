"""retarget canal_cuenca engine to the curated consorcio canals (A7, slice 1 rev)

The ``canal_cuenca`` ficha variant answers "what is the real upstream hydrological
catchment of this canal?" — a true watershed, not the fixed-width ``canal_buffer``
strip. The first cut of this feature (migration ``0019``) keyed the catchment on
``canal_network`` — the 13 173-edge pgRouting graph. That was wrong: the consorcio
does not route over that graph, it manages **60 curated canals** (41 relevados +
19 propuestos) shipped as GeoJSON assets. This migration retargets the storage to
those curated canals.

Two things happen here.

**1. ``canal_consorcio`` — the curated canal registry (NEW).** One row per curated
canal, keyed by the GeoJSON string id (e.g. ``canal-ne-sin-intervencion``). This
becomes the backend's source of truth for the 60 canals; the seed ETL
``python -m app.domains.geo.etl.load_canales_consorcio`` UPSERTs the two bundled
GeoJSONs into it. ``estado`` is constrained to ``relevado`` / ``propuesto`` (the
two asset families). ``geom`` is a LineString in EPSG:4326 with a GiST index.

**2. ``canal_catchment`` — REDEFINED for the curated model.** ``0019`` created
``canal_catchment`` with ``canal_id INTEGER`` (an in-spirit FK to
``canal_network``). That table is UNUSED — slice 2 (the ficha lookup) was never
merged, no code reads it, and it is EMPTY in every environment (``0019`` and
``canal_catchment`` reached ``develop`` but never prod). So it is dropped and
recreated keyed on the curated canal instead:

* ``canal_ref`` — the ``canal_consorcio.id`` string, a real FK
  (``ON DELETE CASCADE``: a canal removed from the registry takes its catchments
  with it).
* ``variante`` — kept as a column, but v1 stamps a single value (``relevado``):
  every one of the 60 catchments is computed against the base/relevado
  ``flow_dir`` raster (the one with the relevado canals burned in). The
  propuesto-against-escenario refinement is deferred.
* ``geometria`` — the dissolved catchment MultiPolygon in EPSG:4326, NULLABLE: an
  oversized basin (over ``ficha_max_area_ha``) is stored WITHOUT its geometry with
  ``oversized = true``, its ``area_ha`` kept for audit.
* ``flow_dir_layer_id`` / ``version`` — provenance + the resumability key (the id
  of the ``flow_dir`` ``geo_layers`` row the catchment derived from). A new
  terrain run mints a fresh layer id; the batch skips canals already at the
  current pointer and recomputes (UPSERT) when it changes.

``UNIQUE (canal_ref, variante)`` keeps exactly one current catchment per canal and
variante — the batch UPSERTs onto it. ``ix_canal_catchment_canal_ref`` backs the
per-canal lookup a later slice will run.

Revision ID: 0020_add_canal_consorcio
Revises: 0019_add_canal_catchment
Create Date: 2026-08-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0020_add_canal_consorcio"
down_revision: Union[str, None] = "0019_add_canal_catchment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exposed as module constants (mirroring ``0017``/``0019``) so the real-PG
# migration test and the seed/batch tests can build the same tables without
# duplicating the DDL.
CREATE_CANAL_CONSORCIO: str = """
    CREATE TABLE canal_consorcio (
        id TEXT PRIMARY KEY,
        nombre TEXT NOT NULL,
        estado TEXT NOT NULL,
        prioridad TEXT,
        longitud_m DOUBLE PRECISION,
        geom geometry(LineString, 4326) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_canal_consorcio_estado
            CHECK (estado IN ('relevado', 'propuesto'))
    )
"""

CREATE_CANAL_CONSORCIO_GEOM_INDEX: str = (
    "CREATE INDEX ix_canal_consorcio_geom ON canal_consorcio USING GIST (geom)"
)

# ``0019``'s ``canal_catchment`` is unused and empty everywhere — drop it and
# recreate keyed on the curated canal. IF EXISTS keeps the migration idempotent on
# a base that somehow never got ``0019`` (fresh installs jump straight to head).
DROP_OLD_CANAL_CATCHMENT: str = "DROP TABLE IF EXISTS canal_catchment"

CREATE_CANAL_CATCHMENT: str = """
    CREATE TABLE canal_catchment (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        canal_ref TEXT NOT NULL REFERENCES canal_consorcio(id) ON DELETE CASCADE,
        variante TEXT NOT NULL,
        geometria geometry(MultiPolygon, 4326),
        area_ha DOUBLE PRECISION,
        oversized BOOLEAN NOT NULL DEFAULT false,
        flow_dir_layer_id UUID REFERENCES geo_layers(id) ON DELETE SET NULL,
        version TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_canal_catchment_canal_ref_variante UNIQUE (canal_ref, variante)
    )
"""

CREATE_CANAL_REF_INDEX: str = (
    "CREATE INDEX ix_canal_catchment_canal_ref ON canal_catchment (canal_ref)"
)

UPGRADE_STATEMENTS: tuple[str, ...] = (
    CREATE_CANAL_CONSORCIO,
    CREATE_CANAL_CONSORCIO_GEOM_INDEX,
    DROP_OLD_CANAL_CATCHMENT,
    CREATE_CANAL_CATCHMENT,
    CREATE_CANAL_REF_INDEX,
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Rebuild ``0019``'s canal_network-keyed ``canal_catchment`` so downgrading to
    # ``0019`` lands on exactly the schema ``0019`` defined, then drop the curated
    # registry. canal_catchment goes first (its FK references canal_consorcio).
    op.execute("DROP TABLE IF EXISTS canal_catchment")
    op.execute("DROP TABLE IF EXISTS canal_consorcio")
    op.execute(
        """
        CREATE TABLE canal_catchment (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            canal_id INTEGER NOT NULL,
            variante TEXT NOT NULL,
            geometria geometry(MultiPolygon, 4326),
            area_ha DOUBLE PRECISION,
            oversized BOOLEAN NOT NULL DEFAULT false,
            flow_dir_layer_id UUID REFERENCES geo_layers(id) ON DELETE SET NULL,
            version TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_canal_catchment_canal_variante UNIQUE (canal_id, variante)
        )
        """
    )
    op.execute("CREATE INDEX ix_canal_catchment_canal_id ON canal_catchment (canal_id)")
