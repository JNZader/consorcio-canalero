"""allow cruce_camino.tipo = conduccion — along-road conveyance (unranked)

O.1 stored only transverse D8 crossings (``flujo_natural``) and canal×road
intersections (``canal``). Flow running *alongside* a road (θ < 22.5°) was
dropped as ``flujo_paralelo``. That discarded event is the road conveying
water in the ditch — a different object from a crossing, not a failed one.

This revision widens ``ck_cruce_tipo`` and adds ``ck_cruce_conduccion``:

* ``orden_ranking`` is NULL (ranking stays defined over ``flujo_natural``).
* ``direccion_flujo_deg`` and ``rumbo_camino_deg`` are required so an arrow
  can be drawn.
* ``canal_ref`` is optional: the nearest downhill canal crossing on the same
  segment, when one exists. ``ck_cruce_flujo_sin_canal`` is unchanged — only
  ``flujo_natural`` is forbidden from carrying a canal.

Nothing is published. Martin, ``vt_`` views and the dashboard matview are
untouched.

Revision ID: 0024_add_cruce_conduccion
Revises: lluvia_ext_002
Create Date: 2026-09-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0024_add_cruce_conduccion"
down_revision: Union[str, None] = "lluvia_ext_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DROP_TIPO: str = "ALTER TABLE cruce_camino DROP CONSTRAINT ck_cruce_tipo"

ADD_TIPO: str = """
    ALTER TABLE cruce_camino
        ADD CONSTRAINT ck_cruce_tipo
        CHECK (tipo IN ('flujo_natural', 'canal', 'conduccion'))
"""

ADD_CONDUCCION: str = """
    ALTER TABLE cruce_camino
        ADD CONSTRAINT ck_cruce_conduccion
        CHECK (
            tipo <> 'conduccion' OR (
                orden_ranking IS NULL
                AND direccion_flujo_deg IS NOT NULL
                AND rumbo_camino_deg IS NOT NULL
            )
        )
"""

DROP_CONDUCCION: str = "ALTER TABLE cruce_camino DROP CONSTRAINT ck_cruce_conduccion"

RESTORE_TIPO: str = """
    ALTER TABLE cruce_camino
        ADD CONSTRAINT ck_cruce_tipo
        CHECK (tipo IN ('flujo_natural', 'canal'))
"""

UPGRADE_STATEMENTS: tuple[str, ...] = (DROP_TIPO, ADD_TIPO, ADD_CONDUCCION)
DOWNGRADE_STATEMENTS: tuple[str, ...] = (DROP_CONDUCCION, DROP_TIPO, RESTORE_TIPO)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DELETE FROM cruce_camino WHERE tipo = 'conduccion'")
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
