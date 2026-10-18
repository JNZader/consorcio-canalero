"""Real-PG tests for migration ``0030_weld_order_caminos``.

0029 stays covered by its own fixture. This schema applies 0021, then 0029,
then 0030, so the assertions describe the welded matview only.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

RED_VIAL_MIGRATION = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")
PREVIOUS = importlib.import_module("app.db.migrations.versions.0029_add_mv_caminos_unificados")
MIGRATION = importlib.import_module("app.db.migrations.versions.0030_weld_order_caminos")

SCHEMA = "caminos_soldados_mig_test"


def _run(conn, statements) -> None:
    for statement in statements:
        conn.execute(text(statement))


@pytest.fixture(scope="module")
def welded(test_engine):
    conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
        _run(conn, RED_VIAL_MIGRATION.UPGRADE_STATEMENTS)
        _run(conn, PREVIOUS.UPGRADE_STATEMENTS)
        _run(conn, MIGRATION.UPGRADE_STATEMENTS)
        yield conn
    finally:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("SET search_path TO public"))
        conn.close()


def _soldar(conn, expresion: str):
    return conn.execute(
        text(
            "SELECT ST_GeometryType(g) AS tipo, "
            "COALESCE(ST_NumGeometries(g), 0) AS n, "
            "ST_X(ST_StartPoint(ST_GeometryN(g, 1))) AS x1, "
            "ST_Y(ST_StartPoint(ST_GeometryN(g, 1))) AS y1, "
            "ST_X(ST_EndPoint(ST_GeometryN(g, 1))) AS x1b, "
            "ST_X(ST_StartPoint(ST_GeometryN(g, 2))) AS x2, "
            "ST_Length(g::geography) AS metros "
            f"FROM (SELECT caminos_soldar_ruta({expresion}) AS g) q"
        )
    ).one()


class TestCaminosSoldarRuta:
    def test_a_three_metre_gap_becomes_one_linestring(self, welded):
        fila = _soldar(
            welded,
            """
            (SELECT ST_Collect(ARRAY[
                ST_SetSRID(ST_MakeLine(
                    ST_MakePoint(-62.5, y0),
                    ST_MakePoint(-62.5, y0 - seg)
                ), 4326),
                ST_SetSRID(ST_MakeLine(
                    ST_MakePoint(-62.5, y0 - seg - gap),
                    ST_MakePoint(-62.5, y0 - (2 * seg) - gap)
                ), 4326)
            ])
            FROM (
                SELECT -32.5::float8 AS y0,
                       (6.0 / 111320.0)::float8 AS seg,
                       (3.0 / 111320.0)::float8 AS gap
            ) p)
            """,
        )
        assert fila.tipo == "ST_LineString"
        assert 12.0 < fila.metros < 18.0

    def test_a_chain_of_gaps_does_not_collapse_to_one_point(self, welded):
        fila = _soldar(
            welded,
            """
            (SELECT ST_Collect(ARRAY[
                ST_SetSRID(ST_MakeLine(
                    ST_MakePoint(-62.5, y0),
                    ST_MakePoint(-62.5, y0 - seg)
                ), 4326),
                ST_SetSRID(ST_MakeLine(
                    ST_MakePoint(-62.5, y0 - seg - gap),
                    ST_MakePoint(-62.5, y0 - (2 * seg) - gap)
                ), 4326),
                ST_SetSRID(ST_MakeLine(
                    ST_MakePoint(-62.5, y0 - (2 * seg) - (2 * gap)),
                    ST_MakePoint(-62.5, y0 - (3 * seg) - (2 * gap))
                ), 4326)
            ])
            FROM (
                SELECT -32.5::float8 AS y0,
                       (6.0 / 111320.0)::float8 AS seg,
                       (3.0 / 111320.0)::float8 AS gap
            ) p)
            """,
        )
        assert fila.tipo == "ST_LineString"
        assert 20.0 < fila.metros < 28.0

    def test_a_real_gap_stays_ordered_from_the_western_free_end(self, welded):
        fila = _soldar(
            welded,
            """
            ST_Collect(ARRAY[
                ST_GeomFromText('LINESTRING(-62.20 -32.50, -62.10 -32.50)', 4326),
                ST_GeomFromText('LINESTRING(-62.50 -32.50, -62.40 -32.50)', 4326)
            ])
            """,
        )
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n == 2
        assert fila.x1 == pytest.approx(-62.50)
        assert fila.y1 == pytest.approx(-32.50)
        assert fila.x1b == pytest.approx(-62.40)
        assert fila.x2 == pytest.approx(-62.20)

    def test_a_branch_stays_multipart_and_starts_at_the_free_end(self, welded):
        fila = _soldar(
            welded,
            """
            ST_Collect(ARRAY[
                ST_GeomFromText('LINESTRING(-62.4 -32.50, -62.4 -32.40)', 4326),
                ST_GeomFromText(
                    'LINESTRING(-62.5 -32.50, -62.4 -32.50, -62.3 -32.50)', 4326
                )
            ])
            """,
        )
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n >= 2
        assert fila.x1 == pytest.approx(-62.5)
        assert fila.y1 == pytest.approx(-32.5)
        queda_el_ramal = welded.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM ST_Dump(caminos_soldar_ruta(ST_Collect(ARRAY[
                        ST_GeomFromText(
                            'LINESTRING(-62.4 -32.50, -62.4 -32.40)', 4326
                        ),
                        ST_GeomFromText(
                            'LINESTRING(-62.5 -32.50, -62.4 -32.50, -62.3 -32.50)',
                            4326
                        )
                    ]))) AS d
                    WHERE ST_Equals(
                        ST_StartPoint(d.geom),
                        ST_SetSRID(ST_MakePoint(-62.4, -32.40), 4326)
                    )
                    OR ST_Equals(
                        ST_EndPoint(d.geom),
                        ST_SetSRID(ST_MakePoint(-62.4, -32.40), 4326)
                    )
                )
                """
            )
        ).scalar()
        assert queda_el_ramal is True

    def test_overlap_is_counted_once(self, welded):
        fila = _soldar(
            welded,
            """
            ST_Collect(ARRAY[
                ST_GeomFromText('LINESTRING(-62.5 -32.50, -62.5 -32.60)', 4326),
                ST_GeomFromText('LINESTRING(-62.5 -32.50, -62.5 -32.60)', 4326)
            ])
            """,
        )
        assert fila.tipo == "ST_LineString"
        assert 10_000 < fila.metros < 12_000

    def test_a_single_line_is_not_reversed(self, welded):
        fila = _soldar(
            welded,
            "ST_GeomFromText('LINESTRING(-62.1 -32.5, -62.9 -32.5)', 4326)",
        )
        assert fila.tipo == "ST_LineString"
        assert fila.x1 == pytest.approx(-62.1)

    def test_the_matview_publishes_the_welded_length(self, welded):
        tipo_columna = welded.execute(
            text(
                "SELECT upper(type) FROM geometry_columns "
                "WHERE f_table_schema = :schema "
                "AND f_table_name = 'mv_caminos_unificados'"
            ),
            {"schema": SCHEMA},
        ).scalar()
        assert tipo_columna == "GEOMETRY"

        welded.execute(
            text(
                f"INSERT INTO {SCHEMA}.red_vial "
                "(id, source_id, parte, fna, gna, rtn, red, ccn, lzn, geom, geom_hash) "
                "VALUES "
                "('ov-1', 'ov-s1', 1, 'Solape', 'Camino', 'OV-1', 'Terciaria', 'CC', 11, "
                "ST_GeomFromText('LINESTRING(-62.5 -32.50, -62.5 -32.60)', 4326), 'ov1'), "
                "('ov-2', 'ov-s2', 1, 'Solape', 'Camino', 'OV-1', 'Terciaria', 'CC', 11, "
                "ST_GeomFromText('LINESTRING(-62.5 -32.50, -62.5 -32.60)', 4326), 'ov2')"
            )
        )
        welded.execute(text(f"REFRESH MATERIALIZED VIEW {SCHEMA}.mv_caminos_unificados"))
        fila = welded.execute(
            text(
                "SELECT longitud_declarada_km, longitud_geodesica_km, "
                "cantidad_tramos_fisicos, ST_GeometryType(geom) "
                f"FROM {SCHEMA}.mv_caminos_unificados WHERE ruta = 'OV-1'"
            )
        ).one()
        assert fila[0] == 22
        assert 10 < float(fila[1]) < 12
        assert fila[2] == 2
        assert fila[3] == "ST_LineString"
        assert (
            welded.execute(
                text(f"SELECT count(*) FROM {SCHEMA}.red_vial WHERE rtn = 'OV-1'")
            ).scalar()
            == 2
        )

    def test_downgrade_restores_the_multiline_wrapper(self, welded):
        welded.execute(
            text(
                f"INSERT INTO {SCHEMA}.red_vial "
                "(id, source_id, parte, fna, gna, rtn, red, ccn, lzn, geom, geom_hash) "
                "VALUES "
                "('dw-1', 'dw-s1', 1, 'T269', 'Camino', 'DW-1', 'Terciaria', 'CC', 2.5, "
                "ST_GeomFromText('LINESTRING(-62.5 -32.50, -62.5 -32.52)', 4326), 'dw1'), "
                "('dw-2', 'dw-s2', 1, 'T269', 'Camino', 'DW-1', 'Terciaria', 'CC', 3.0, "
                "ST_GeomFromText('LINESTRING(-62.5 -32.52, -62.5 -32.55)', 4326), 'dw2')"
            )
        )
        welded.execute(text(f"REFRESH MATERIALIZED VIEW {SCHEMA}.mv_caminos_unificados"))
        antes = welded.execute(
            text(
                "SELECT ST_GeometryType(geom), cantidad_tramos_fisicos "
                f"FROM {SCHEMA}.mv_caminos_unificados WHERE ruta = 'DW-1'"
            )
        ).one()
        assert antes[0] == "ST_LineString"
        assert antes[1] == 2

        try:
            _run(welded, MIGRATION.DOWNGRADE_STATEMENTS)
            welded.execute(text(f"REFRESH MATERIALIZED VIEW {SCHEMA}.mv_caminos_unificados"))
            despues = welded.execute(
                text(
                    "SELECT ST_GeometryType(geom) "
                    f"FROM {SCHEMA}.mv_caminos_unificados WHERE ruta = 'DW-1'"
                )
            ).scalar()
            assert despues == "ST_MultiLineString"
            funcion = welded.execute(
                text(
                    "SELECT 1 FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = :schema AND p.proname = 'caminos_soldar_ruta'"
                ),
                {"schema": SCHEMA},
            ).scalar()
            assert funcion is None
        finally:
            _run(welded, MIGRATION.UPGRADE_STATEMENTS)
