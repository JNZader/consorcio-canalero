"""Real-PG tests for migration ``0033_one_way_profile``.

The walk enters every part at the nearer end. Kilometer zero is the
western extremity of that chain. Snap still uses ``8/111320`` degrees, so
a 7.5 m east gap stays two parts. A 20 m gap also stays two parts and now
turns. Downgrade restores the 0032 drawn-direction gate.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

RED_VIAL_MIGRATION = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")
UNIFY = importlib.import_module("app.db.migrations.versions.0029_add_mv_caminos_unificados")
WELD = importlib.import_module("app.db.migrations.versions.0030_weld_order_caminos")
DEDUP = importlib.import_module("app.db.migrations.versions.0031_drop_covered_caminos")
GAP = importlib.import_module("app.db.migrations.versions.0032_keep_gap_direction")
MIGRATION = importlib.import_module("app.db.migrations.versions.0033_one_way_profile")

SCHEMA = "caminos_one_way_test"
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
        _run(conn, GAP.UPGRADE_STATEMENTS)
        _run(conn, MIGRATION.UPGRADE_STATEMENTS)
        yield conn
    finally:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("SET search_path TO public"))
        conn.close()


def _hueco(conn, segunda: str, arranque: str, extremo: str):
    primera = "ST_Transform(ST_MakeLine(ST_Translate(p, -200, 0), p), 4326)"
    oeste = "ST_Translate(p, -200, 0)"
    return conn.execute(
        text(
            "SELECT ST_GeometryType(q.g) AS tipo, "
            "COALESCE(ST_NumGeometries(q.g), 0) AS n, "
            "ST_Distance(ST_StartPoint(ST_GeometryN(q.g, 1))::geography, "
            "ST_Transform(q.oeste, 4326)::geography) AS al_oeste, "
            "ST_Distance(ST_StartPoint(ST_GeometryN(q.g, 2))::geography, "
            "ST_Transform(q.arranque, 4326)::geography) AS al_arranque, "
            "ST_Distance(ST_StartPoint(ST_GeometryN(q.g, 2))::geography, "
            "ST_Transform(q.extremo, 4326)::geography) AS al_extremo, "
            "ST_Length(q.g::geography) AS metros, "
            "ST_OrderingEquals(q.g, caminos_soldar_ruta(q.g)) AS estable "
            "FROM ("
            f"SELECT caminos_soldar_ruta(ST_Collect(ARRAY[({primera}), ({segunda})])) AS g, "
            f"{arranque} AS arranque, {extremo} AS extremo, {oeste} AS oeste "
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


class TestUnSentido:
    def test_a_twenty_metre_gap_is_entered_at_the_near_end(self, directed):
        fila = _veinte(directed)
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n == 2
        assert fila.al_oeste < 1.0
        assert fila.al_extremo < 1.0
        assert fila.al_arranque > 50.0
        assert 250 < fila.metros < 270
        assert fila.estable is True

    def test_a_seven_metre_east_gap_still_turns_and_stays_split(self, directed):
        fila = _hueco(
            directed,
            "ST_Transform(ST_MakeLine(ST_Translate(p, 80, 0), ST_Translate(p, 7.5, 0)), 4326)",
            "ST_Translate(p, 80, 0)",
            "ST_Translate(p, 7.5, 0)",
        )
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n == 2
        assert fila.al_oeste < 1.0
        assert fila.al_extremo < 1.0
        assert fila.al_arranque > 50.0
        assert 265 < fila.metros < 280

    def test_a_spur_that_stops_short_starts_at_the_tip(self, directed):
        filas = directed.execute(
            text(
                "SELECT ST_Length(d.geom::geography) AS metros, "
                "ST_Distance(ST_StartPoint(d.geom)::geography, "
                "ST_Transform(punta, 4326)::geography) AS al_punta, "
                "ST_Distance(ST_EndPoint(d.geom)::geography, "
                "ST_Transform(punta, 4326)::geography) AS fin_punta, "
                "ST_X(ST_StartPoint(d.geom)) AS x0, "
                "ST_X(ST_EndPoint(d.geom)) AS x1 "
                "FROM ("
                "SELECT caminos_soldar_ruta(ST_Collect(ARRAY["
                "ST_Transform(ST_MakeLine(ARRAY[p, ST_Translate(p, 200, 0), "
                "ST_Translate(p, 400, 0)]), 4326), "
                "ST_Transform(ST_MakeLine(ST_Translate(p, 200, 80), "
                "ST_Translate(p, 200, 30)), 4326)"
                "])) AS g, "
                "ST_Translate(p, 200, 80) AS punta "
                f"FROM (SELECT {_P} AS p) base"
                ") q, LATERAL ST_Dump(q.g) AS d "
                "ORDER BY d.path"
            )
        ).all()
        assert len(filas) == 2
        assert filas[0].metros == pytest.approx(50, abs=1)
        assert filas[0].al_punta < 1.0
        assert filas[0].fin_punta == pytest.approx(50, abs=1)
        assert filas[1].metros == pytest.approx(400, abs=1)
        assert filas[1].x0 < filas[1].x1

    def test_a_touching_spur_starts_at_the_tip(self, directed):
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
                "ST_Translate(p, 200, 80) AS punta "
                f"FROM (SELECT {_P} AS p) base"
                ") q, LATERAL ST_Dump(q.g) AS d "
                "ORDER BY d.path"
            )
        ).all()
        assert len(filas) == 3
        assert filas[0].metros == pytest.approx(80, abs=1)
        assert filas[0].al_punta < 1.0
        assert filas[0].fin_punta == pytest.approx(80, abs=1)
        assert filas[1].metros == pytest.approx(200, abs=1)
        assert filas[1].al_punta == pytest.approx(215, abs=2)
        assert filas[1].fin_punta == pytest.approx(80, abs=1)
        assert filas[2].metros == pytest.approx(200, abs=1)
        assert filas[2].al_punta == pytest.approx(80, abs=1)
        assert filas[2].fin_punta == pytest.approx(215, abs=2)

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

    def test_the_south_tip_is_kilometer_zero(self, directed):
        fila = directed.execute(
            text(
                "SELECT ST_GeometryType(g) AS tipo, "
                "COALESCE(ST_NumGeometries(g), 0) AS n, "
                "ST_X(ST_StartPoint(ST_GeometryN(g, 1))) AS x0, "
                "ST_Y(ST_StartPoint(ST_GeometryN(g, 1))) AS y0, "
                "bool_and(ST_Y(ST_EndPoint(d.geom)) > ST_Y(ST_StartPoint(d.geom))) "
                "AS al_norte, "
                "ST_OrderingEquals(g, caminos_soldar_ruta(g)) AS estable "
                "FROM ("
                "SELECT caminos_soldar_ruta(ST_Collect(ARRAY["
                "ST_GeomFromText('LINESTRING(-62.50 -32.64, -62.48 -32.70)', 4326), "
                "ST_GeomFromText('LINESTRING(-62.47 -32.60, -62.48 -32.62)', 4326), "
                "ST_GeomFromText('LINESTRING(-62.47 -32.59, -62.35 -32.41)', 4326)"
                "])) AS g"
                ") q, LATERAL ST_Dump(q.g) AS d "
                "GROUP BY g"
            )
        ).one()
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n == 3
        assert fila.x0 == pytest.approx(-62.48)
        assert fila.y0 == pytest.approx(-32.70)
        assert fila.al_norte is True
        assert fila.estable is True

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

    def test_downgrade_restores_the_drawn_direction(self, directed):
        try:
            _run(directed, MIGRATION.DOWNGRADE_STATEMENTS)
            fila = _veinte(directed)
            assert fila.tipo == "ST_MultiLineString"
            assert fila.n == 2
            assert fila.al_arranque < 1.0
            assert fila.al_extremo > 50.0
        finally:
            _run(directed, MIGRATION.UPGRADE_STATEMENTS)
