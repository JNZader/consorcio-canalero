"""Real-PG tests for migration ``0032_keep_gap_direction``.

The walk flips a part only when the chosen end is within 8 m of the cursor.
Snap still uses ``8/111320`` degrees, about 6.7 m east-west at this
latitude, so a 7.5 m east gap stays two parts and still turns. A 20 m gap
does not. A spur that meets the middle of a line, far from the cursor,
keeps the direction it was drawn.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

RED_VIAL_MIGRATION = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")
UNIFY = importlib.import_module("app.db.migrations.versions.0029_add_mv_caminos_unificados")
WELD = importlib.import_module("app.db.migrations.versions.0030_weld_order_caminos")
DEDUP = importlib.import_module("app.db.migrations.versions.0031_drop_covered_caminos")
MIGRATION = importlib.import_module("app.db.migrations.versions.0032_keep_gap_direction")

SCHEMA = "caminos_gap_dir_test"
_P = "ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720)"


def _run(conn, statements) -> None:
    for statement in statements:
        conn.execute(text(statement))


@pytest.fixture(scope="module")
def directed(test_engine):
    conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
        _run(conn, RED_VIAL_MIGRATION.UPGRADE_STATEMENTS)
        _run(conn, UNIFY.UPGRADE_STATEMENTS)
        _run(conn, WELD.UPGRADE_STATEMENTS)
        _run(conn, DEDUP.UPGRADE_STATEMENTS)
        _run(conn, MIGRATION.UPGRADE_STATEMENTS)
        yield conn
    finally:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("SET search_path TO public"))
        conn.close()


def _hueco(conn, segunda: str, arranque: str, extremo: str):
    primera = "ST_Transform(ST_MakeLine(ST_Translate(p, -200, 0), p), 4326)"
    return conn.execute(
        text(
            "SELECT ST_GeometryType(q.g) AS tipo, "
            "COALESCE(ST_NumGeometries(q.g), 0) AS n, "
            "ST_Distance(ST_StartPoint(ST_GeometryN(q.g, 2))::geography, "
            "ST_Transform(q.arranque, 4326)::geography) AS al_arranque, "
            "ST_Distance(ST_StartPoint(ST_GeometryN(q.g, 2))::geography, "
            "ST_Transform(q.extremo, 4326)::geography) AS al_extremo, "
            "ST_Length(q.g::geography) AS metros "
            "FROM ("
            f"SELECT caminos_soldar_ruta(ST_Collect(ARRAY[({primera}), ({segunda})])) AS g, "
            f"{arranque} AS arranque, {extremo} AS extremo "
            f"FROM (SELECT {_P} AS p) base"
            ") q"
        )
    ).one()


def _veinte(conn):
    return _hueco(
        conn,
        "ST_Transform(ST_MakeLine(ST_Translate(p, 80, 0), ST_Translate(p, 20, 0)), 4326)",
        "ST_Translate(p, 80, 0)",
        "ST_Translate(p, 20, 0)",
    )


class TestSentidoDelHueco:
    def test_a_twenty_metre_gap_keeps_the_drawn_direction(self, directed):
        fila = _veinte(directed)
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n == 2
        assert fila.al_arranque < 1.0
        assert fila.al_extremo > 50.0
        assert 250 < fila.metros < 270

    def test_a_seven_metre_east_gap_still_turns_and_stays_split(self, directed):
        fila = _hueco(
            directed,
            "ST_Transform(ST_MakeLine(ST_Translate(p, 80, 0), ST_Translate(p, 7.5, 0)), 4326)",
            "ST_Translate(p, 80, 0)",
            "ST_Translate(p, 7.5, 0)",
        )
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n == 2
        assert fila.al_extremo < 1.0
        assert fila.al_arranque > 50.0
        assert 265 < fila.metros < 280

    def test_a_spur_that_stops_short_keeps_the_direction_it_was_drawn(self, directed):
        # 30 m short of the principal. Nothing is shared, so the line merge
        # leaves the principal whole and the cursor finishes at its far end.
        fila = directed.execute(
            text(
                "SELECT ST_GeometryType(q.g) AS tipo, "
                "COALESCE(ST_NumGeometries(q.g), 0) AS n, "
                "ST_Distance(ST_StartPoint(ST_GeometryN(q.g, 2))::geography, "
                "ST_Transform(q.punta, 4326)::geography) AS al_punta, "
                "ST_Length(q.g::geography) AS metros "
                "FROM ("
                "SELECT caminos_soldar_ruta(ST_Collect(ARRAY["
                "ST_Transform(ST_MakeLine(ARRAY[p, ST_Translate(p, 200, 0), "
                "ST_Translate(p, 400, 0)]), 4326), "
                "ST_Transform(ST_MakeLine(ST_Translate(p, 200, 80), "
                "ST_Translate(p, 200, 30)), 4326)"
                "])) AS g, "
                "ST_Translate(p, 200, 80) AS punta "
                f"FROM (SELECT {_P} AS p) base"
                ") q"
            )
        ).one()
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n == 2
        assert fila.al_punta < 1.0
        assert 440 < fila.metros < 460

    def test_a_touching_spur_turns_out_from_the_joint(self, directed):
        # ST_UnaryUnion splits the principal at the shared vertex. The spur
        # meets that vertex, so the walk turns it and leaves toward the tip.
        # The east half then starts again at the joint.
        filas = directed.execute(
            text(
                "SELECT ST_Length(d.geom::geography) AS metros, "
                "ST_Distance(ST_StartPoint(d.geom)::geography, "
                "ST_Transform(punta, 4326)::geography) AS al_punta, "
                "ST_Distance(ST_EndPoint(d.geom)::geography, "
                "ST_Transform(punta, 4326)::geography) AS fin_punta "
                "FROM ("
                "SELECT caminos_soldar_ruta(ST_Collect(ARRAY["
                "ST_Transform(ST_MakeLine(ARRAY[p, ST_Translate(p, 200, 0), "
                "ST_Translate(p, 400, 0)]), 4326), "
                "ST_Transform(ST_MakeLine(ST_Translate(p, 200, 80), "
                "ST_Translate(p, 200, 0)), 4326)"
                "])) AS g, "
                "ST_Translate(p, 200, 80) AS punta, p "
                f"FROM (SELECT {_P} AS p) base"
                ") q, LATERAL ST_Dump(q.g) AS d "
                "ORDER BY d.path"
            )
        ).all()
        assert len(filas) == 3
        assert filas[0].metros == pytest.approx(200, abs=1)
        assert filas[0].fin_punta == pytest.approx(80, abs=1)
        assert filas[1].metros == pytest.approx(80, abs=1)
        assert filas[1].al_punta == pytest.approx(80, abs=1)
        assert filas[1].fin_punta < 1.0
        assert filas[2].metros == pytest.approx(200, abs=1)
        assert filas[2].al_punta == pytest.approx(80, abs=1)

    def test_a_real_gap_still_starts_from_the_west(self, directed):
        fila = directed.execute(
            text(
                "SELECT ST_GeometryType(g) AS tipo, "
                "COALESCE(ST_NumGeometries(g), 0) AS n, "
                "ST_X(ST_StartPoint(ST_GeometryN(g, 1))) AS x1, "
                "ST_X(ST_StartPoint(ST_GeometryN(g, 2))) AS x2 "
                "FROM (SELECT caminos_soldar_ruta(ST_Collect(ARRAY["
                "ST_GeomFromText('LINESTRING(-62.20 -32.50, -62.10 -32.50)', 4326), "
                "ST_GeomFromText('LINESTRING(-62.50 -32.50, -62.40 -32.50)', 4326)"
                "])) AS g) q"
            )
        ).one()
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n == 2
        assert fila.x1 == pytest.approx(-62.50)
        assert fila.x2 == pytest.approx(-62.20)

    def test_a_two_metre_copy_is_still_dropped(self, directed):
        linea = (
            "ST_Transform(ST_MakeLine(ARRAY["
            "ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
            "ST_Translate(ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
            "0, 100), "
            "ST_Translate(ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
            "0, 200)]), 4326)"
        )
        copia = (
            f"ST_Reverse(ST_Transform(ST_Translate(ST_Transform(({linea}), 32720), 2, 0), 4326))"
        )
        fila = directed.execute(
            text(
                "SELECT ST_GeometryType(g) AS tipo, ST_Length(g::geography) AS metros "
                f"FROM (SELECT caminos_soldar_ruta(ST_Collect(ARRAY[({linea}), ({copia})])) AS g) q"
            )
        ).one()
        assert fila.tipo == "ST_LineString"
        assert 190 < fila.metros < 210

    def test_a_three_metre_chain_still_becomes_one_line(self, directed):
        fila = directed.execute(
            text(
                "SELECT ST_GeometryType(g) AS tipo, ST_Length(g::geography) AS metros "
                "FROM (SELECT caminos_soldar_ruta(ST_Collect(ARRAY["
                "ST_SetSRID(ST_MakeLine(ST_MakePoint(-62.5, y0), "
                "ST_MakePoint(-62.5, y0 - seg)), 4326), "
                "ST_SetSRID(ST_MakeLine(ST_MakePoint(-62.5, y0 - seg - gap), "
                "ST_MakePoint(-62.5, y0 - (2 * seg) - gap)), 4326), "
                "ST_SetSRID(ST_MakeLine("
                "ST_MakePoint(-62.5, y0 - (2 * seg) - (2 * gap)), "
                "ST_MakePoint(-62.5, y0 - (3 * seg) - (2 * gap))), 4326)"
                "])) AS g FROM ("
                "SELECT -32.5::float8 AS y0, (6.0 / 111320.0)::float8 AS seg, "
                "(3.0 / 111320.0)::float8 AS gap"
                ") p) q"
            )
        ).one()
        assert fila.tipo == "ST_LineString"
        assert 20.0 < fila.metros < 28.0

    def test_downgrade_flips_the_twenty_metre_gap_again(self, directed):
        try:
            _run(directed, MIGRATION.DOWNGRADE_STATEMENTS)
            fila = _veinte(directed)
            assert fila.tipo == "ST_MultiLineString"
            assert fila.n == 2
            assert fila.al_extremo < 1.0
            assert fila.al_arranque > 50.0
        finally:
            _run(directed, MIGRATION.UPGRADE_STATEMENTS)
