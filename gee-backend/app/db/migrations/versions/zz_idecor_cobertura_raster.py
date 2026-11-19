"""idecor_cobertura_raster — registered IDECOR land-cover rasters (PR 4, S4).

The four IDECOR layers this PR consumes are RASTER coverages (verified
live 2026-11-19: they exist as ``idecor__cobertura_uso_2024_2025`` and
``idecor__coberturas_estivales_2223/2324/2425`` WCS CoverageIds — NOT as
WFS feature types), so the ETL downloads bounded GeoTIFFs for the zona
bbox and registers them HERE.

**Why not ``geo_layers``** (deviation from the plan's "rasters registrados
en ``geo_layers``", reported in the PR): ``geo_layers.tipo`` is a CLOSED
Python enum (``TipoGeoLayer``) AND a PostgreSQL enum. Registering rows
with values the Python enum does not know breaks every ORM read that
materializes them — ``router_bundle_io.export_geo_bundle`` queries ALL
``GeoLayer`` rows unfiltered and would 500. Adding the values to the
database enum without adding them to ``app/domains/geo/models.py`` is a
trap; adding them to the Python enum is outside this PR's allowed edit
surfaces. A dedicated table gives the informe the same contract the plan
wanted from ``geo_layers`` — registered, dated, legend-carrying, and
versionable through ``created_at`` — without corrupting an existing
endpoint.

The **legend** is stored per layer because the class codings DIFFER
between campaigns (verified live: ``coberturas_estivales_2223`` codes
1=Soja/2=Maíz/3=Otros, while 2324 and 2425 code 1=Maíz temprano/
2=Maíz tardío/3=Soja/4=Maní/5=Otros). Hardcoding any single mapping
would silently mislabel two of the three campaigns.

One row per ``capa`` (UNIQUE): a re-run of the ETL replaces the row, so
"registered" always describes the newest download. ``idecor_cobertura_*``
naming would mirror the enum style; ``capa``/``tipo`` are plain TEXT with
CHECKs because nothing outside this table and the informe reads them.

NOTE (S10 / AGENTS.md): the box does NOT run Alembic — applied manually,
step goes in the PR description.

Revision ID: zz_idecor_cobertura_raster
Revises: zz_idecor_suelos_50mil
"""

from typing import Sequence, Union

from alembic import op

revision: str = "zz_idecor_cobertura_raster"
down_revision: Union[str, None] = "zz_idecor_suelos_50mil"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Module-constant DDL (the ``0022`` precedent) so the test suite runs the
# exact statements the migration runs.
CREATE_COBERTURA_RASTER: str = """
    CREATE TABLE IF NOT EXISTS idecor_cobertura_raster (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        capa            TEXT NOT NULL,
        tipo            TEXT NOT NULL,
        campania        TEXT NOT NULL,
        archivo_path    TEXT NOT NULL,
        srid            INTEGER NOT NULL DEFAULT 22174,
        leyenda         JSONB NOT NULL,
        bbox_22174      DOUBLE PRECISION[] NOT NULL,
        ancho_px        INTEGER NOT NULL,
        alto_px         INTEGER NOT NULL,
        fecha_de_bajada TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_idecor_cobertura_capa UNIQUE (capa),
        CONSTRAINT ck_idecor_cobertura_tipo CHECK (
            tipo IN ('cobertura_uso', 'cobertura_estival')
        )
    )
"""

CREATE_FECHA_INDEX: str = (
    "CREATE INDEX IF NOT EXISTS ix_idecor_cobertura_fecha "
    "ON idecor_cobertura_raster (fecha_de_bajada)"
)

UPGRADE_STATEMENTS: tuple[str, ...] = (
    CREATE_COBERTURA_RASTER,
    CREATE_FECHA_INDEX,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = ("DROP TABLE IF EXISTS idecor_cobertura_raster",)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
