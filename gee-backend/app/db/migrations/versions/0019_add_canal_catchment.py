"""add canal_catchment table (A7 canal_cuenca precompute engine, slice 1)

The ``canal_cuenca`` ficha variant answers "what is the real upstream hydrological
catchment of this canal?" — a true watershed, not the fixed-width ``canal_buffer``
strip. Computing it on the request path is far too heavy (rasterize the trace,
run WBT ``watershed`` against the D8 pointer, polygonize, dissolve), so it is
precomputed offline per ``canal × variante`` by
``python -m app.domains.geo.etl.generate_canal_catchments`` and looked up at
request time (slice 2 wires the lookup into ``ficha_service``).

This migration only creates the storage. Table shape:

* ``canal_id`` — FK-in-spirit to ``canal_network.id`` (a ``SERIAL`` int; the canal
  table is migration-only raw SQL — ``w7r4s5t6u593`` — so this stays a plain
  ``INTEGER`` rather than a declared FK, matching how the rest of the code joins
  canal_network by id).
* ``variante`` — ``natural`` (drainage WITHOUT the canal network burned in) or
  ``relevado`` (with the current network burned in). The precompute MUST run
  against the matching ``flow_dir`` raster; the two never share a catchment.
* ``geometria`` — the dissolved catchment MultiPolygon in EPSG:4326, NULLABLE:
  an oversized basin (over ``ficha_max_area_ha``) is stored WITHOUT its geometry
  (multi-MB polygons the ficha would reject anyway) with ``oversized = true``.
* ``area_ha`` — catchment area, measured in EPSG:32720 (the projection the whole
  ficha uses), kept even when the geometry is dropped so the oversized case is
  still auditable.
* ``flow_dir_layer_id`` / ``version`` — provenance + the resumability key. A new
  ``flow_dir`` run mints a fresh ``geo_layers`` row (new UUID); the batch stamps
  ``version`` with that id, so re-running skips canals already computed for the
  current pointer and a changed pointer recomputes (UPSERT on the unique key).

``UNIQUE (canal_id, variante)`` keeps exactly one *current* catchment per canal
and variante — the batch UPSERTs onto it. ``ix_canal_catchment_canal_id`` backs
the per-canal lookup slice 2 will run.

Revision ID: 0019_add_canal_catchment
Revises: 0018_add_precip_normal_geo_layer
Create Date: 2026-08-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0019_add_canal_catchment"
down_revision: Union[str, None] = "0018_add_precip_normal_geo_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exposed as a module constant (mirroring ``0017``'s ``UPGRADE_STATEMENTS``) so the
# real-PG migration test and the batch test can build the same table without
# duplicating the DDL.
CREATE_CANAL_CATCHMENT: str = """
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

CREATE_CANAL_ID_INDEX: str = (
    "CREATE INDEX ix_canal_catchment_canal_id ON canal_catchment (canal_id)"
)

UPGRADE_STATEMENTS: tuple[str, ...] = (CREATE_CANAL_CATCHMENT, CREATE_CANAL_ID_INDEX)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS canal_catchment")
