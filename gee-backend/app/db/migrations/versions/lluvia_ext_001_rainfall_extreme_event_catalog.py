"""lluvia_ext_001: the extreme-rainfall event catalog

`rainfall_extreme_event` — one detected or curated event span per row
(lluvia-eventos-extremos, design.md D2/D8/D13).

**Why the statistics are NULLABLE and the rule lives in two CHECKs.** A
`detected` row was ranked against the frozen climatology and must carry the
whole evidence set; a `curated` row is institutional memory that was NEVER
ranked. Declaring `tier`, `max_percentile`, `fired_windows`,
`sealed_detection_params`, `peak_date` and the climatology span NOT NULL would
leave exactly two ways to seed the three legacy anchors in `lluvia_ext_002`:
fabricate statistics for an unranked event — which the ratified spec forbids
outright ("No Invented Events") — or fail the migration. The
provenance-conditional pair `ck_detected_complete` / `ck_curated_unranked` says
the real rule instead, and says it for both provenances so neither can drift
into a half-populated row.

**Why the identity index is PARTIAL.** `uq_rainfall_extreme_event_identity`
covers `(source_id, scope_kind, scope_id, scope_version, detector_revision,
tier, start_date) WHERE provenance = 'detected'`. `tier` is NULL on every
curated row and in Postgres `NULL != NULL`, so a plain unique index over those
columns treats every curated row as distinct from every other: the constraint
keeps existing while it stops constraining, with nothing anywhere to notice.
Restricting it to detected rows makes it mean what it says.

**Why `tier` is in that key at all.** Both tiers are persisted and an `alta`
span is a superset of the `extrema` spans inside it, so one `start_date`
routinely hosts one row of each. The originally proposed key omitted `tier` and
would have collided on the ratified behaviour, on the first real run.

**Why `detector_revision` carries a `'curated'` SENTINEL rather than NULL.**
`uq_rainfall_extreme_event_key` — the constraint the imagery bridge resolves a
served id through — includes the revision; a NULL there would defeat it exactly
the way a NULL `tier` defeats the identity index. `ck_curated_revision_sentinel`
enforces the equivalence in both directions, which is what makes "curated rows
vanish on a revision bump" structurally impossible instead of policy-dependent.

**Why this revises `conocimiento_007`.** It is the tree's single head, verified
with `alembic heads` at apply time rather than copied from a plan. A second
child on an already-parented revision forks the tree, `alembic upgrade head`
refuses, and the healthcheck becomes the outage.

Revision ID: lluvia_ext_001
Revises: conocimiento_007
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision: str = "lluvia_ext_001"
down_revision: Union[str, None] = "conocimiento_007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rainfall_extreme_event"
INDEX_IDENTITY = "uq_rainfall_extreme_event_identity"
INDEX_SERVING = "ix_rainfall_extreme_event_serving"

#: Mirrored in `models.RainfallExtremeEvent.__table_args__`. A migration is a
#: frozen snapshot and cannot import the model, so these expressions exist
#: twice by construction; `test_rainfall_catalog.py` builds BOTH schemas
#: against real Postgres and compares `pg_get_constraintdef` output, which is
#: what stops the two copies from drifting into disagreement.
CK_DETECTED_COMPLETE = (
    "provenance <> 'detected' OR ("
    "tier IS NOT NULL AND max_percentile IS NOT NULL AND "
    "fired_windows IS NOT NULL AND sealed_detection_params IS NOT NULL AND "
    "peak_date IS NOT NULL AND climatology_span_start IS NOT NULL AND "
    "climatology_span_end IS NOT NULL AND curated_payload IS NULL)"
)
CK_CURATED_UNRANKED = (
    "provenance <> 'curated' OR ("
    "tier IS NULL AND max_percentile IS NULL AND "
    "fired_windows IS NULL AND sealed_detection_params IS NULL AND "
    "peak_date IS NULL AND climatology_span_start IS NULL AND "
    "climatology_span_end IS NULL AND curated_payload IS NOT NULL)"
)
CK_DATES_ORDERED = (
    "end_date >= start_date AND "
    "(peak_date IS NULL OR (peak_date >= start_date AND peak_date <= end_date))"
)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("scope_kind", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("scope_version", sa.String(length=128), nullable=False),
        sa.Column("detector_revision", sa.String(length=64), nullable=False),
        sa.Column("provenance", sa.String(length=16), nullable=False),
        # The SERVED id. The UUID primary key is a database key and never
        # leaves the database.
        sa.Column("event_key", sa.String(length=64), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("peak_date", sa.Date(), nullable=True),
        sa.Column("max_percentile", sa.Float(), nullable=True),
        sa.Column("fired_windows", JSON(), nullable=True),
        sa.Column("sealed_detection_params", JSON(), nullable=True),
        sa.Column("climatology_span_start", sa.Date(), nullable=True),
        sa.Column("climatology_span_end", sa.Date(), nullable=True),
        sa.Column("curated_payload", JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "source_id",
            "scope_kind",
            "scope_id",
            "scope_version",
            "detector_revision",
            "event_key",
            name="uq_rainfall_extreme_event_key",
        ),
        sa.CheckConstraint(CK_DETECTED_COMPLETE, name="ck_detected_complete"),
        sa.CheckConstraint(CK_CURATED_UNRANKED, name="ck_curated_unranked"),
        sa.CheckConstraint(
            "(provenance = 'curated') = (detector_revision = 'curated')",
            name="ck_curated_revision_sentinel",
        ),
        sa.CheckConstraint("tier IS NULL OR tier IN ('extrema', 'alta')", name="ck_tier_domain"),
        sa.CheckConstraint("provenance IN ('detected', 'curated')", name="ck_provenance_domain"),
        sa.CheckConstraint(CK_DATES_ORDERED, name="ck_dates_ordered"),
    )
    op.create_index(
        INDEX_IDENTITY,
        TABLE,
        [
            "source_id",
            "scope_kind",
            "scope_id",
            "scope_version",
            "detector_revision",
            "tier",
            "start_date",
        ],
        unique=True,
        postgresql_where=sa.text("provenance = 'detected'"),
    )
    # The serving read: one generation, optionally one tier, newest first.
    op.create_index(
        INDEX_SERVING,
        TABLE,
        ["detector_revision", "tier", sa.text("start_date DESC")],
    )


def downgrade() -> None:
    op.drop_index(INDEX_SERVING, table_name=TABLE)
    op.drop_index(INDEX_IDENTITY, table_name=TABLE)
    op.drop_table(TABLE)
