"""add cruce_camino — road crossing points, dedicated and UNPUBLISHED (flujo-caminos S2)

Crossings between a road segment and either the natural drainage or a canal get a
**dedicated table**. Reusing ``puntos_conflicto`` was considered and withdrawn
(design D1): that table has **no area column**, so the per-area re-run this
feature needs — ``DELETE ... WHERE area_id = :area_id`` — was literally
unimplementable there, and its ``NOT NULL`` ``severidad`` / ``pendiente_valor``
would have fabricated a risk grade on every single crossing
(``clasificar_severidad_conflicto_impl``'s first branch is
``acumulacion > 5000 or pendiente < 0.5``, so a zero-filled slope grades every
row ``'alta'``). A dedicated table costs one migration and makes all of that
disappear by construction.

**Nothing here is published.** No view is created, no view is redefined, no
materialized view is re-created, ``martin/config.yaml`` gains no source and no
property. Martin serves only the views named under ``tables:`` with
``auto_publish: false``, so ``cruce_camino`` has no public surface at all — which
is how the operator-only requirement is satisfied structurally rather than by a
``WHERE`` clause somebody has to keep correct.

**Column types come from the tables they mirror, not from a remembered
precedent.**

* ``area_id`` is ``VARCHAR(100)``, matching ``GeoLayer.area_id``'s
  ``String(100)`` (``geo/models.py:155-159``). ``geo_jobs`` has no area column at
  all — the area lives inside its ``parametros`` JSON — so there is no UUID
  precedent to follow, and a UUID column would turn the staleness comparison into
  a cast that raises on a legal non-UUID area identifier. It stays un-FK'd for
  the same reason ``geo_layer``'s is: there is no areas table to point at.
* ``canal_ref`` is ``TEXT REFERENCES canal_consorcio(id)``, because
  ``canal_consorcio.id`` is ``TEXT PRIMARY KEY``
  (``0020_add_canal_consorcio.py:65-66``). A UUID column could never have
  referenced it and would therefore have accepted any value at all.

**The four CHECKs** carry the per-``tipo`` rules. A ``flujo_natural`` row without
a derivable direction, road bearing, side, area or rank is not storable; a
``canal`` row never carries a rank, because ranking is defined over the
natural-drainage set only; and the two one-sided closures shut the gaps the first
pair left — a ``flujo_natural`` row can no longer carry a ``canal_ref`` (which
would make it two things at once) nor be stored without its ``confianza`` band.

**Downgrade caveat, intended and permanent.** ``downgrade()`` drops the table and
**leaves the ``tipo_geo_job`` enum value ``'road_flow_crossings'`` in place**:
PostgreSQL cannot remove an enum value. The precedent is explicit —
``q1l8m7n8o927``'s ``downgrade()`` is a bare ``pass`` with the same note. The
residue is harmless (nothing reads it once the table is gone) but it is
permanent, and a re-upgrade's ``ADD VALUE IF NOT EXISTS`` is then a no-op rather
than a fresh add. Written down here so nobody reports it as corruption.

Revision ID: 0022_add_cruce_camino
Revises: 0021_add_red_vial
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0022_add_cruce_camino"
down_revision: Union[str, None] = "0021_add_red_vial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exposed as module constants (the ``0017`` / ``0019`` / ``0020`` / ``0021``
# precedent) so the real-PG migration test runs the very same DDL instead of a
# re-typed copy that can drift.
CREATE_CRUCE_CAMINO: str = """
    CREATE TABLE cruce_camino (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        area_id             VARCHAR(100) NOT NULL,
        tramo_ref           TEXT NOT NULL REFERENCES red_vial(id) ON DELETE RESTRICT,
        tipo                TEXT NOT NULL,
        geometria           geometry(Point, 4326) NOT NULL,
        direccion_flujo_deg DOUBLE PRECISION,
        rumbo_camino_deg    DOUBLE PRECISION,
        lado_cruce          TEXT,
        area_aporte_ha      DOUBLE PRECISION,
        orden_ranking       INTEGER,
        confianza           TEXT,
        nota                TEXT,
        canal_ref           TEXT REFERENCES canal_consorcio(id) ON DELETE RESTRICT,
        geo_job_id          UUID NOT NULL REFERENCES geo_jobs(id),
        calculada_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_cruce_tipo CHECK (tipo IN ('flujo_natural', 'canal')),
        CONSTRAINT ck_cruce_confianza_valores CHECK (
            confianza IS NULL OR confianza IN ('alta', 'baja')
        ),
        CONSTRAINT ck_cruce_flujo_completo CHECK (
            tipo <> 'flujo_natural' OR (
                direccion_flujo_deg IS NOT NULL AND rumbo_camino_deg IS NOT NULL
                AND lado_cruce IS NOT NULL
                AND area_aporte_ha IS NOT NULL AND orden_ranking IS NOT NULL
            )
        ),
        CONSTRAINT ck_cruce_canal_sin_rank CHECK (
            tipo <> 'canal' OR (orden_ranking IS NULL AND canal_ref IS NOT NULL)
        ),
        CONSTRAINT ck_cruce_flujo_sin_canal CHECK (
            tipo <> 'flujo_natural' OR canal_ref IS NULL
        ),
        CONSTRAINT ck_cruce_flujo_confianza CHECK (
            tipo <> 'flujo_natural' OR confianza IS NOT NULL
        )
    )
"""

CREATE_GEOM_INDEX: str = "CREATE INDEX ix_cruce_camino_geom ON cruce_camino USING GIST (geometria)"

#: The read path is always "this area's crossings, of this kind" — the ranked
#: list and the canal set are two separate queries over the same area.
CREATE_AREA_INDEX: str = "CREATE INDEX ix_cruce_camino_area ON cruce_camino (area_id, tipo)"

#: The survey join (S3) and the ``ON DELETE RESTRICT`` check both read by segment.
CREATE_TRAMO_INDEX: str = "CREATE INDEX ix_cruce_camino_tramo ON cruce_camino (tramo_ref)"

#: ``IF NOT EXISTS`` because a downgrade cannot take the value back off the type,
#: so a re-upgrade has to be a no-op rather than a duplicate-value error.
#: Precedent: ``q1l8m7n8o927_add_dem_pipeline_enum_values``.
ADD_ENUM_VALUE: str = "ALTER TYPE tipo_geo_job ADD VALUE IF NOT EXISTS 'road_flow_crossings'"

UPGRADE_STATEMENTS: tuple[str, ...] = (
    CREATE_CRUCE_CAMINO,
    CREATE_GEOM_INDEX,
    CREATE_AREA_INDEX,
    CREATE_TRAMO_INDEX,
)

#: The enum value is deliberately NOT here: PostgreSQL cannot remove one. See the
#: module docstring — the residue is permanent, harmless and documented.
DOWNGRADE_STATEMENTS: tuple[str, ...] = ("DROP TABLE cruce_camino",)


def upgrade() -> None:
    # The enum value first and on its own: ``ALTER TYPE ... ADD VALUE`` cannot run
    # in the same transaction as a statement that uses the new value on older
    # PostgreSQL, and running it first keeps the ordering obvious.
    op.execute(ADD_ENUM_VALUE)
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
