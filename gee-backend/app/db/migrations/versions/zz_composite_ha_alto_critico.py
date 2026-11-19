"""composite_zonal_stats: legend-derived ha_alto / ha_critico (PR 5, S9 / #738).

Decision #738, Option A with breakdown: the high-risk statistic derives from
``class_breaks.RANGE_CONFIGS`` — hectares counted from the start of the
legend's "Alto" class (55 for flood_risk, 50 for drainage_need), split into
``ha_alto`` ([alto_min, critico_min)) and ``ha_critico`` ([critico_min, max]).

``area_high_risk_ha`` SURVIVES as a compatibility column (its consumers
include ``ficha_service._ALTO_CRITICO_SQL``, outside this PR's edit
surfaces): from now on every writer (the DEM pipeline and the recompute task
this PR adds) stores ``ha_alto + ha_critico`` in it. Existing rows keep the
pre-#738 ``score > 70`` figure until ``geo.intelligence.recompute_composite_stats``
re-runs over the registered rasters — a migration cannot derive hectares from
a raster it has no guarantee exists, so the honest statement is "stale until
recompute", not a fabricated split.

The new columns are NULLABLE on purpose: NULL is the marker for "not yet
measured under the legend", which readers surface as an absent figure («—»),
never as a confident 0 %.

NOTE (AGENTS.md): the box does NOT run Alembic — applied manually, step goes
in the PR description.

Revision ID: zz_composite_ha_alto_critico
Revises: zz_idecor_cobertura_raster
"""

from typing import Sequence, Union

from alembic import op

revision: str = "zz_composite_ha_alto_critico"
down_revision: Union[str, None] = "zz_idecor_cobertura_raster"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "composite_zonal_stats"

# Module-constant DDL (the 0022 precedent) so the test suite can run the
# exact statements the migration runs.
UPGRADE_STATEMENTS: tuple[str, ...] = (
    f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS ha_alto DOUBLE PRECISION",
    f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS ha_critico DOUBLE PRECISION",
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS ha_critico",
    f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS ha_alto",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
