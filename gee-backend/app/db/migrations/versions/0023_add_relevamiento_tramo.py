"""add relevamiento_tramo + tramo_clasificacion_candidata (flujo-caminos S3, Fase B)

The field survey of a road segment, and — in a **separate table** — what the DEM
guessed about that same segment. Two tables rather than one nullable column,
because the spec requires the candidate be stored in a place distinct from the
confirmed value: a column on the same row is one careless ``INSERT … SELECT``
from becoming the confirmed value, and the provenance belongs to the DEM run, not
to the operator (design D4).

**Append-only.** There is no UPDATE and no DELETE path: a correction is a new
row, and the previous one stays retrievable. ``relevado_por NOT NULL`` plus the
absence of an update path is the whole of RSS-R1's "no record without an
identified author; the author is not alterable afterwards" — there is no code
path that can rewrite it.

**``version BIGSERIAL`` is the ordering key, not ``relevado_en``.**
``relevado_en DEFAULT now()`` is **transaction-start** time in PostgreSQL, so two
surveys of the same segment written from overlapping transactions can be stamped
in the opposite order to their commits — or identically — and ``id`` is a random
UUIDv4, whose tie-break is lexicographic accident. Two operators surveying the
same segment minutes apart and syncing together is not an exotic case. The
sequence is assigned at INSERT and unique by construction, so "current" is
``ORDER BY version DESC``: a genuine total order with no tie to break.
``relevado_en`` stays for **display** — it is what the operator recognises as
"when I surveyed it" — and never decides which record wins. (Sequence gaps from
rolled-back transactions are irrelevant: only the ordering matters.)

**The cuneta combination rule is a table-level CHECK**, not a service rule:
``estado_cuneta`` is NULL **iff** ``tiene_cuneta = 'no'``. A rule enforced only in
the service is a rule psql and any future ETL bypass.

**The candidate table is keyed ``(tramo_ref, geo_job_id)``.** ``dem_layer_id`` is
not a run identifier: ``upsert_layer`` looks a layer up by name and mutates the
row in place while the **UUID stays the same**
(``geo_repository_jobs_layers.py:207-243``), so two DEM runs a month apart over
different terrain data produce the same id — keying on it would make the second
run's candidate silently overwrite the first's. And ``delete_layers_by_area_id``
(``:245-250``) wipes those rows outright, so the id is not even guaranteed to
survive. ``geo_jobs.id`` is created fresh per run and never reused; it is the
honest key, and it is the same provenance token the crossing rows carry.
``dem_layer_id`` is kept as **informational** provenance with **no FK**, allowed
to dangle: a candidate whose job's layers were wiped is a recorded past
computation, not a live pointer, and deleting it would destroy the only record of
what the DEM once suggested.

**Nothing here is published.** ``relevamiento_tramo_vigente`` is an internal
current-state query, not a ``vt_`` view: survey rows carry ``relevado_por`` and
Martin's hostname is public (``martin/config.yaml:11-14``), so RSS-R7 is
satisfied by construction — no published view reads these tables.

**No dimension column exists on either table.** RSS-R6: this capability records
what the operator sees, never what it measures.

**Downgrade caveat, the same one ``0021`` carries.** ``downgrade()`` drops the
view and both tables, and that **destroys field-collected survey data**. It never
CASCADEs: failing loudly beats taking dependents down silently. The operational
answer to a bad deploy is to stop using the feature, not to downgrade.

Revision ID: 0023_add_relevamiento_tramo
Revises: 0022_add_cruce_camino
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0023_add_relevamiento_tramo"
down_revision: Union[str, None] = "0022_add_cruce_camino"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exposed as module constants (the ``0017`` / ``0019`` / ``0020`` / ``0021`` /
# ``0022`` precedent) so the real-PG migration test runs the very same DDL
# instead of a re-typed copy that can drift.
CREATE_RELEVAMIENTO_TRAMO: str = """
    CREATE TABLE relevamiento_tramo (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tramo_ref             TEXT NOT NULL REFERENCES red_vial(id) ON DELETE RESTRICT,
        nivel_relativo        TEXT NOT NULL,
        tiene_cuneta          TEXT NOT NULL,
        estado_cuneta         TEXT,
        observaciones         TEXT,
        relevado_por          UUID NOT NULL REFERENCES users(id),
        relevado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
        version               BIGSERIAL NOT NULL,
        nivel_desde_candidata BOOLEAN NOT NULL DEFAULT false,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_relevamiento_version UNIQUE (version),
        CONSTRAINT ck_relevamiento_nivel_relativo CHECK (
            nivel_relativo IN ('menor', 'igual', 'mayor')
        ),
        CONSTRAINT ck_relevamiento_tiene_cuneta CHECK (
            tiene_cuneta IN ('si', 'no', 'parcial')
        ),
        CONSTRAINT ck_relevamiento_estado_cuneta_valores CHECK (
            estado_cuneta IS NULL OR estado_cuneta IN ('limpia', 'colmatada')
        ),
        CONSTRAINT ck_relevamiento_cuneta_combinacion CHECK (
            (tiene_cuneta = 'no' AND estado_cuneta IS NULL)
            OR (tiene_cuneta <> 'no' AND estado_cuneta IS NOT NULL)
        )
    )
"""

#: The current-state read is always "this segment, newest first", and the view
#: below is a ``DISTINCT ON`` over exactly this ordering.
CREATE_TRAMO_VERSION_INDEX: str = (
    "CREATE INDEX ix_relevamiento_tramo_version ON relevamiento_tramo (tramo_ref, version DESC)"
)

#: Current state is a QUERY, not a flag. An ``es_vigente BOOLEAN`` was rejected:
#: it needs two writes per survey (demote, insert) guarded by a partial unique
#: index, and a half-applied pair leaves two current rows or none. ``DISTINCT ON``
#: cannot desynchronize because there is nothing to synchronize.
CREATE_VIGENTE_VIEW: str = """
    CREATE VIEW relevamiento_tramo_vigente AS
    SELECT DISTINCT ON (tramo_ref)
           id, tramo_ref, nivel_relativo, tiene_cuneta, estado_cuneta, observaciones,
           relevado_por, relevado_en, version, nivel_desde_candidata,
           created_at, updated_at
      FROM relevamiento_tramo
     ORDER BY tramo_ref, version DESC
"""

CREATE_TRAMO_CANDIDATA: str = """
    CREATE TABLE tramo_clasificacion_candidata (
        tramo_ref              TEXT NOT NULL REFERENCES red_vial(id) ON DELETE RESTRICT,
        geo_job_id             UUID NOT NULL REFERENCES geo_jobs(id),
        dem_layer_id           UUID,
        clasificacion_candidata TEXT NOT NULL,
        confianza_m            DOUBLE PRECISION NOT NULL,
        calculada_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (tramo_ref, geo_job_id),
        CONSTRAINT ck_candidata_clasificacion CHECK (
            clasificacion_candidata IN ('terraplen', 'canal', 'neutro')
        )
    )
"""

#: The pre-fill reads the NEWEST candidate for a segment — multiple runs now
#: legitimately coexist, so "the" candidate is not a thing.
CREATE_CANDIDATA_INDEX: str = (
    "CREATE INDEX ix_tramo_candidata_reciente "
    "ON tramo_clasificacion_candidata (tramo_ref, calculada_en DESC)"
)

#: The classification run needs a ``geo_jobs`` row of its own, because the
#: candidate table is keyed by the run that produced it. ``geo_jobs.tipo`` is a
#: NOT NULL enum, so the run has to be nameable: borrowing ``dem_pipeline``
#: would label a classification as something it is not, and the job list is how
#: an operator sees what actually ran.
#:
#: ``IF NOT EXISTS`` because a downgrade cannot take an enum value back off the
#: type — PostgreSQL has no ``DROP VALUE``. Same permanent, harmless, documented
#: residue as ``0022``'s ``road_flow_crossings``; a re-upgrade is then a no-op
#: rather than a duplicate-value error.
ADD_ENUM_VALUE: str = "ALTER TYPE tipo_geo_job ADD VALUE IF NOT EXISTS 'tramo_classification'"

UPGRADE_STATEMENTS: tuple[str, ...] = (
    CREATE_RELEVAMIENTO_TRAMO,
    CREATE_TRAMO_VERSION_INDEX,
    CREATE_VIGENTE_VIEW,
    CREATE_TRAMO_CANDIDATA,
    CREATE_CANDIDATA_INDEX,
)

#: The enum value is deliberately NOT here: PostgreSQL cannot remove one.
#:
#: The view first: ``DROP TABLE`` under a dependent view fails. NOT ``CASCADE``
#: — see the module docstring; this drop destroys field-collected survey data and
#: it is meant to be loud about what it takes with it.
DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    "DROP VIEW relevamiento_tramo_vigente",
    "DROP TABLE tramo_clasificacion_candidata",
    "DROP TABLE relevamiento_tramo",
)


def upgrade() -> None:
    # The enum value first and on its own: ``ALTER TYPE ... ADD VALUE`` cannot
    # run in the same transaction as a statement that uses the new value on
    # older PostgreSQL, and running it first keeps the ordering obvious.
    op.execute(ADD_ENUM_VALUE)
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
