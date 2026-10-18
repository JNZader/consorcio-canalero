"""Real-PG tests for migration ``0031_drop_covered_caminos``.

A second drawing is dropped twice. Before the snap, coverage is against one
other part, so a twin cannot be merged into an out-and-back line and a short
bridge survives. After the merge, coverage is against the remaining parts.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

RED_VIAL_MIGRATION = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")
UNIFY = importlib.import_module("app.db.migrations.versions.0029_add_mv_caminos_unificados")
WELD = importlib.import_module("app.db.migrations.versions.0030_weld_order_caminos")
MIGRATION = importlib.import_module("app.db.migrations.versions.0031_drop_covered_caminos")

SCHEMA = "caminos_dedup_mig_test"


def _run(conn, statements) -> None:
    for statement in statements:
        conn.execute(text(statement))


@pytest.fixture(scope="module")
def deduped(test_engine):
    conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
        _run(conn, RED_VIAL_MIGRATION.UPGRADE_STATEMENTS)
        _run(conn, UNIFY.UPGRADE_STATEMENTS)
        _run(conn, WELD.UPGRADE_STATEMENTS)
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
            "ST_Length(g::geography) AS metros "
            f"FROM (SELECT caminos_soldar_ruta({expresion}) AS g) q"
        )
    ).one()


def _linea_norte(metros: float) -> str:
    """Three vertices, so snapping the ends does not erase a lateral offset."""
    return (
        "ST_Transform(ST_MakeLine(ARRAY["
        "ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
        "ST_Translate(ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
        f"0, {metros / 2}), "
        "ST_Translate(ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
        f"0, {metros})]), 4326)"
    )


def _desplazada(linea_sql: str, este: float, norte: float, reversa: bool) -> str:
    copia = f"ST_Transform(ST_Translate(ST_Transform(({linea_sql}), 32720), {este}, {norte}), 4326)"
    if reversa:
        return f"ST_Reverse({copia})"
    return copia


def _copia(linea_sql: str, este: float, norte: float, reversa: bool) -> str:
    return f"ST_Collect(ARRAY[({linea_sql}), ({_desplazada(linea_sql, este, norte, reversa)})])"


class TestCaminosSinCopia:
    def test_a_two_metre_offset_copy_is_dropped(self, deduped):
        fila = _soldar(deduped, _copia(_linea_norte(200), 2, 0, False))
        assert fila.tipo == "ST_LineString"
        assert 190 < fila.metros < 210

    def test_a_reversed_two_metre_copy_is_dropped(self, deduped):
        fila = _soldar(deduped, _copia(_linea_norte(200), 2, 0, True))
        assert fila.tipo == "ST_LineString"
        assert 190 < fila.metros < 210

    def test_an_exact_copy_is_still_one_line(self, deduped):
        fila = _soldar(deduped, _copia(_linea_norte(200), 0, 0, True))
        assert fila.tipo == "ST_LineString"
        assert 190 < fila.metros < 210

    def test_a_parallel_track_thirty_metres_away_stays(self, deduped):
        fila = _soldar(deduped, _copia(_linea_norte(200), 30, 0, False))
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n == 2
        assert 380 < fila.metros < 420

    def test_a_shorter_overlapping_copy_is_the_one_dropped(self, deduped):
        larga = _linea_norte(400)
        corta = (
            "ST_Transform(ST_MakeLine("
            "ST_Translate(ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
            "2, 160), "
            "ST_Translate(ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
            "2, 240)), 4326)"
        )
        fila = _soldar(deduped, f"ST_Collect(ARRAY[({larga}), ({corta})])")
        assert fila.tipo == "ST_LineString"
        assert 390 < fila.metros < 410

    def test_a_copy_only_the_merged_line_covers_is_dropped(self, deduped):
        def trozo(norte_0: float, norte_1: float, este: float) -> str:
            return (
                "ST_Transform(ST_MakeLine(ARRAY["
                "ST_Translate(ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
                f"{este}, {norte_0}), "
                "ST_Translate(ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
                f"{este}, {(norte_0 + norte_1) / 2}), "
                "ST_Translate(ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720), "
                f"{este}, {norte_1})]), 4326)"
            )

        fila = _soldar(
            deduped,
            "ST_Collect(ARRAY["
            f"({trozo(0, 100, 0)}), ({trozo(103, 203, 0)}), ({trozo(50, 150, 2)})])",
        )
        assert fila.tipo == "ST_LineString"
        assert 195 < fila.metros < 215

    def test_a_forty_metre_spur_is_kept(self, deduped):
        fila = _soldar(
            deduped,
            """
            (SELECT ST_Collect(ARRAY[
                ST_Transform(ST_MakeLine(p, ST_Translate(p, 200, 0)), 4326),
                ST_Transform(ST_MakeLine(ST_Translate(p, 100, 0), ST_Translate(p, 100, 40)), 4326)
            ])
            FROM (
                SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-62.5, -32.5), 4326), 32720) AS p
            ) b)
            """,
        )
        assert fila.tipo == "ST_MultiLineString"
        assert fila.n >= 2
        assert 230 < fila.metros < 250

    def test_a_three_metre_chain_still_becomes_one_line(self, deduped):
        fila = _soldar(
            deduped,
            """
            (SELECT ST_Collect(ARRAY[
                ST_SetSRID(ST_MakeLine(
                    ST_MakePoint(-62.5, y0), ST_MakePoint(-62.5, y0 - seg)
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

    def test_a_real_gap_stays_two_parts_from_the_west(self, deduped):
        fila = _soldar(
            deduped,
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

    def test_the_padron_stays_and_downgrade_brings_the_copy_back(self, deduped):
        linea = _linea_norte(200)
        copia = _desplazada(linea, 2, 0, True)
        deduped.execute(
            text(
                f"INSERT INTO {SCHEMA}.red_vial "
                "(id, source_id, parte, fna, gna, rtn, red, ccn, lzn, geom, geom_hash) "
                "VALUES "
                "('dup-1', 'dup-s1', 1, 'Copia', 'Camino', 'DUP-1', 'Terciaria', 'CC', 1, "
                f"{linea}, 'dup1'), "
                "('dup-2', 'dup-s2', 1, 'Copia', 'Camino', 'DUP-1', 'Terciaria', 'CC', 1, "
                f"{copia}, 'dup2')"
            )
        )
        deduped.execute(text(f"REFRESH MATERIALIZED VIEW {SCHEMA}.mv_caminos_unificados"))
        fila = deduped.execute(
            text(
                "SELECT longitud_declarada_km, longitud_geodesica_km, "
                "cantidad_tramos_fisicos, ST_GeometryType(geom) "
                f"FROM {SCHEMA}.mv_caminos_unificados WHERE ruta = 'DUP-1'"
            )
        ).one()
        assert fila[0] == 2
        assert 0.19 < float(fila[1]) < 0.21
        assert fila[2] == 2
        assert fila[3] == "ST_LineString"
        assert (
            deduped.execute(
                text(f"SELECT count(*) FROM {SCHEMA}.red_vial WHERE rtn = 'DUP-1'")
            ).scalar()
            == 2
        )

        try:
            _run(deduped, MIGRATION.DOWNGRADE_STATEMENTS)
            deduped.execute(text(f"REFRESH MATERIALIZED VIEW {SCHEMA}.mv_caminos_unificados"))
            vuelta = deduped.execute(
                text(
                    "SELECT ST_GeometryType(geom), ST_NumGeometries(geom), "
                    "longitud_geodesica_km "
                    f"FROM {SCHEMA}.mv_caminos_unificados WHERE ruta = 'DUP-1'"
                )
            ).one()
            # 0030 snaps both ends. LineMerge then folds the pair into one
            # line that walks out and back, so the copy returns as length.
            assert vuelta[0] == "ST_LineString"
            assert vuelta[1] == 1
            assert 0.39 < float(vuelta[2]) < 0.41
        finally:
            _run(deduped, MIGRATION.UPGRADE_STATEMENTS)
