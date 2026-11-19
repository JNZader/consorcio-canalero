"""riesgo_validacion_evento — observed water per flood_risk class (PR 5, S4).

Plan columns, verbatim: ``evento_key, fecha, clase, ha_clase, ha_con_agua,
pct_con_agua, lluvia_30d_mm, sensor, escena_id, version_flood_risk,
created_at``. One row per anchor event × legend class for the WHOLE zone —
the validation is of the index itself, so the informe presents it at zone
scale; a per-selection clip is not derivable from these aggregates and is
never fabricated.

The UNIQUE (evento_key, clase) is the idempotency guard: the ETL replaces an
event's rows on every run, so a re-run with the same scene and the same
registered raster produces the same rows. ``sentinel1`` is an accepted sensor
value because S5 marks the SAR fallback apart (``sensor`` IS the marker);
its CHECK set mirrors ``rainfall_event_imagery_candidate``.

NOTE (AGENTS.md): the box does NOT run Alembic — applied manually, step goes
in the PR description.

Revision ID: zz_riesgo_validacion_evento
Revises: zz_composite_ha_alto_critico
"""

from typing import Sequence, Union

from alembic import op

revision: str = "zz_riesgo_validacion_evento"
down_revision: Union[str, None] = "zz_composite_ha_alto_critico"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_RIESGO_VALIDACION: str = """
    CREATE TABLE IF NOT EXISTS riesgo_validacion_evento (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        evento_key          VARCHAR(64) NOT NULL,
        fecha               DATE NOT NULL,
        clase               VARCHAR(20) NOT NULL,
        ha_clase            DOUBLE PRECISION NOT NULL,
        ha_con_agua         DOUBLE PRECISION NOT NULL,
        pct_con_agua        DOUBLE PRECISION NOT NULL,
        lluvia_30d_mm       DOUBLE PRECISION,
        sensor              VARCHAR(16) NOT NULL,
        escena_id           VARCHAR(256) NOT NULL,
        version_flood_risk  VARCHAR(64) NOT NULL,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_riesgo_validacion_evento_clase UNIQUE (evento_key, clase),
        CONSTRAINT ck_riesgo_validacion_sensor CHECK (
            sensor IN ('sentinel2', 'sentinel1', 'landsat9', 'landsat8',
                       'landsat7', 'landsat5')
        ),
        CONSTRAINT ck_riesgo_validacion_pct CHECK (
            pct_con_agua >= 0.0 AND pct_con_agua <= 100.0
        ),
        CONSTRAINT ck_riesgo_validacion_ha CHECK (
            ha_clase >= 0.0 AND ha_con_agua >= 0.0 AND ha_con_agua <= ha_clase
        ),
        CONSTRAINT ck_riesgo_validacion_clase CHECK (
            clase IN ('Bajo', 'Medio', 'Alto', 'Crítico')
        )
    )
"""

CREATE_EVENTO_INDEX: str = (
    "CREATE INDEX IF NOT EXISTS ix_riesgo_validacion_evento "
    "ON riesgo_validacion_evento (evento_key)"
)

UPGRADE_STATEMENTS: tuple[str, ...] = (
    CREATE_RIESGO_VALIDACION,
    CREATE_EVENTO_INDEX,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = ("DROP TABLE IF EXISTS riesgo_validacion_evento",)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
