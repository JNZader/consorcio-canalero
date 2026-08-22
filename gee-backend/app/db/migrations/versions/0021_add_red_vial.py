"""add red_vial — the provincial road network as PostGIS segments (flujo-caminos S1)

The road network the consorcio reasons about lives today only as a Google Earth
Engine asset, so nothing in the platform can hang per-segment data off it. This
migration lands it in PostGIS with **one row per connected part of a native
source feature** — the layer already arrives split into short line features, and
that native segmentation IS the segment for both the flow ranking (Fase A) and
the field survey (Fase B). Nothing is merged and nothing is re-split by length.

**Three identifiers, on purpose.**

* ``id TEXT PRIMARY KEY`` — the row identity later tables point at
  (``cruce_camino.tramo_ref``, ``relevamiento_tramo.tramo_ref``). Equal to the
  source id for the first row of a lineage, ordinal-suffixed (``28188#2``,
  ``28188#3``, …) for later ones. Never reused, never rewritten.
* ``source_id TEXT NOT NULL`` — the identifier the source publishes. Every row
  of a lineage shares it.
* ``parte SMALLINT NOT NULL DEFAULT 1`` — which connected part of that source
  feature the row carries *(added by owner decision, 2026-08-22)*. Almost every
  source feature is a single line and stays at ``parte = 1``; a feature whose
  ``MultiGeometry`` holds several **disconnected** lines is admitted as N rows of
  one lineage rather than aborted: refusing the whole network over one such
  feature helps nobody, and the shipped source has exactly one (``13680``, two
  parts, measured — the earlier rule turned it into a load that could never
  complete).

The **partial** unique index
``ux_red_vial_source_activo ON red_vial (source_id, parte) WHERE activo`` is what
makes "two active rows for the same part of one source feature" unrepresentable.
Keyed on ``(source_id, parte)`` and not on ``source_id`` alone precisely because
the N parts of one feature are all active at the same time; within a part the
invariant is unchanged. A plain (non-partial) unique index would forbid the
lineage split the loader performs when the source re-publishes an id with a
materially different trace.

``geom_hash`` (sha256 of the WKB of the stored part geometry) is what lets the
loader tell "same road, re-published" from "different road, same id"; combined
with a Hausdorff distance over one DEM cell (30 m) it decides update-in-place vs
retire-and-insert. ``activo`` carries the retire-only rule: **the loader never
issues a DELETE**, an id that disappears from the source is flipped to
``activo = false`` with its dependents intact. ``ultima_carga_en`` is written by
every UPSERT — including the one that changes no attribute, because the load
itself is the event that can invalidate a stored crossing side.

**Downgrade caveat, intended behaviour.** ``downgrade()`` is
``DROP TABLE red_vial``, and it **fails while any dependent row exists**: slice 2
and slice 3 reference ``red_vial(id)`` with ``ON DELETE RESTRICT``, so the
database refuses to orphan crossings or field surveys. Their own down-migrations
must run first. That means **downgrading past ``0021`` destroys field-collected
survey data**; the operational answer to a bad deploy is to stop using the
feature, not to downgrade.

Revision ID: 0021_add_red_vial
Revises: conocimiento_004
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0021_add_red_vial"
# Verified at implementation time: ``alembic heads`` returns exactly one head,
# ``conocimiento_004``. The numeric ``0021`` filename is a naming convention, not
# a lineage — the versions tree has been split and re-merged, so the parent is
# taken from the real head, never from the filename sequence.
down_revision: Union[str, None] = "conocimiento_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exposed as module constants (the ``0017`` / ``0019`` / ``0020`` precedent) so the
# real-PG migration test runs the very same DDL instead of a re-typed copy.
CREATE_RED_VIAL: str = """
    CREATE TABLE red_vial (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        parte SMALLINT NOT NULL DEFAULT 1,
        fna TEXT,
        gna TEXT,
        rtn TEXT,
        fun TEXT,
        rst TEXT,
        hct TEXT,
        ccn TEXT,
        ccc TEXT,
        rcc TEXT,
        red TEXT,
        lzn DOUBLE PRECISION,
        geom geometry(LineString, 4326) NOT NULL,
        geom_hash TEXT NOT NULL,
        activo BOOLEAN NOT NULL DEFAULT true,
        ultima_carga_en TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""

CREATE_GEOM_INDEX: str = "CREATE INDEX ix_red_vial_geom ON red_vial USING GIST (geom)"

CREATE_CCC_INDEX: str = "CREATE INDEX ix_red_vial_ccc ON red_vial (ccc)"

CREATE_HCT_INDEX: str = "CREATE INDEX ix_red_vial_hct ON red_vial (hct)"

#: Lineage lookups ("every row that ever carried this source id") read the whole
#: lineage, retired rows included, so they need a non-partial index too.
CREATE_SOURCE_ID_INDEX: str = "CREATE INDEX ix_red_vial_source_id ON red_vial (source_id)"

#: The lineage key. PARTIAL on purpose: at most one ACTIVE row per (source id,
#: part), while retired rows of the same lineage stay addressable. ``parte`` is
#: in the key because the N disconnected parts of one source feature are all
#: active simultaneously.
CREATE_SOURCE_ACTIVO_UNIQUE: str = (
    "CREATE UNIQUE INDEX ux_red_vial_source_activo ON red_vial (source_id, parte) WHERE activo"
)

UPGRADE_STATEMENTS: tuple[str, ...] = (
    CREATE_RED_VIAL,
    CREATE_GEOM_INDEX,
    CREATE_CCC_INDEX,
    CREATE_HCT_INDEX,
    CREATE_SOURCE_ID_INDEX,
    CREATE_SOURCE_ACTIVO_UNIQUE,
)

#: NOT ``DROP TABLE IF EXISTS ... CASCADE``: a CASCADE here would silently take
#: dependent crossing and survey rows with it. Failing loudly is the point.
DOWNGRADE_STATEMENTS: tuple[str, ...] = ("DROP TABLE red_vial",)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
