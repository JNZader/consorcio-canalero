"""idecor_suelos_50mil — IDECOR 1:50.000 soils cartography (PR 4, S3).

One row per cartographic unit polygon of the WFS layer
``idecor:carta_suelo_50mil_2025`` (endpoint verified live 2026-11-18,
1.555 features province-wide; the ETL pulls only the zona bbox). The
informe de área's section 4 switches from ``suelos_cu`` (catastro INTA
capability classes) to this table, which carries what GeoCuenca-style
reporting needs and ``suelos_catastro`` lacks: consociation series with
their share of the unit, productivity index (IP) and available water at
1 / 1.5 / 2 m depth.

Column names mirror the WFS property names VERBATIM (``cu``, ``au_1m``,
``au_1_5m``, ``serie_1..8``, ``porc_1..4``, ...) so the ETL is a
pass-through mapping, not a renaming exercise someone has to re-derive
from a decoder. The plan's column list stops at ``porc_1..4``: the source
also exposes ``fase_N`` and ``pdf_serieN``/``pdf_simbolo`` — the
IDECOR-per-series descriptive-memo identifiers — which ARE stored (the
plan asks for "links a PDF"), while ``fase_N`` is not: no informe surface
renders it and the memo id already encodes the phase distinction.

``id`` is the WFS feature id (INTEGER): a NATURAL primary key, which is
what makes the load idempotent — re-running the ETL converges on the
same rows regardless of insert order. ``fecha_de_bajada`` stamps the
download run on every row (S3: "guardar con fecha de bajada"), replacing
any previous stamp, so the newest run's date is what Fuentes reports.

NOTE (S10 / AGENTS.md): the box does NOT run Alembic — this migration is
applied manually, and that step goes in the PR description.

Revision ID: zz_idecor_suelos_50mil
Revises: zz_informes_area
"""

from typing import Sequence, Union

from alembic import op

revision: str = "zz_idecor_suelos_50mil"
down_revision: Union[str, None] = "zz_informes_area"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exposed as module constants (the ``0022_add_cruce_camino`` precedent) so
# the real-PG test suite runs the very same DDL instead of a re-typed copy
# that can drift.
CREATE_SUELOS_IDECOR: str = """
    CREATE TABLE IF NOT EXISTS idecor_suelos_50mil (
        id              INTEGER PRIMARY KEY,
        simbolo         TEXT NOT NULL,
        cu              TEXT,
        clase           TEXT,
        subclase        TEXT,
        ip              INTEGER,
        au_1m           INTEGER,
        au_1_5m         INTEGER,
        au_2m           INTEGER,
        serie_1         TEXT,
        serie_2         TEXT,
        serie_3         TEXT,
        serie_4         TEXT,
        serie_5         TEXT,
        serie_6         TEXT,
        serie_7         TEXT,
        serie_8         TEXT,
        porc_1          INTEGER,
        porc_2          INTEGER,
        porc_3          INTEGER,
        porc_4          INTEGER,
        nombre          TEXT,
        tipo_unida      TEXT,
        pdf_simbolo     TEXT,
        pdf_serie_1     TEXT,
        pdf_serie_2     TEXT,
        pdf_serie_3     TEXT,
        pdf_serie_4     TEXT,
        pdf_serie_5     TEXT,
        pdf_serie_6     TEXT,
        pdf_serie_7     TEXT,
        pdf_serie_8     TEXT,
        geometria       geometry(MULTIPOLYGON, 4326) NOT NULL,
        fecha_de_bajada TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_idecor_suelos_ip CHECK (ip IS NULL OR (ip >= 0 AND ip <= 100)),
        CONSTRAINT ck_idecor_suelos_porc CHECK (
            (porc_1 IS NULL OR (porc_1 >= 0 AND porc_1 <= 100)) AND
            (porc_2 IS NULL OR (porc_2 >= 0 AND porc_2 <= 100)) AND
            (porc_3 IS NULL OR (porc_3 >= 0 AND porc_3 <= 100)) AND
            (porc_4 IS NULL OR (porc_4 >= 0 AND porc_4 <= 100))
        )
    )
"""

CREATE_GEOM_INDEX: str = (
    "CREATE INDEX IF NOT EXISTS ix_idecor_suelos_50mil_geom "
    "ON idecor_suelos_50mil USING GIST (geometria)"
)

CREATE_FECHA_INDEX: str = (
    "CREATE INDEX IF NOT EXISTS ix_idecor_suelos_50mil_fecha "
    "ON idecor_suelos_50mil (fecha_de_bajada)"
)

UPGRADE_STATEMENTS: tuple[str, ...] = (
    CREATE_SUELOS_IDECOR,
    CREATE_GEOM_INDEX,
    CREATE_FECHA_INDEX,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = ("DROP TABLE IF EXISTS idecor_suelos_50mil",)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
