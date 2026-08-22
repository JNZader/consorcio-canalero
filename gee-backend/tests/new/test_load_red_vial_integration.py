"""Real-PG: the whole ``red_vial`` lineage rule set, end to end.

Every property here is a data-safety property, not a convenience:

(a) **idempotence** — two loads over unchanged source keep the same PKs, so
    crossings and field surveys keep pointing at the same segment;
(b) **retire-only** — an id that leaves the source becomes ``activo = false``,
    is not removed, and its dependent rows survive;
(c) **the id-reuse split** — an id re-published with a materially different
    trace retires the old row and inserts a new one with the SAME ``source_id``
    and the next free suffixed PK, so no survey follows the id onto a road
    nobody surveyed;
(d) **a third load over the post-split source re-splits nothing** — it matches
    the active row by ``source_id`` and updates in place;
(e) the partial unique index refuses a second active row for one ``source_id``;
(f) ``ultima_carga_en`` moves on a load that changes no attribute — the load IS
    the event.

``ON DELETE RESTRICT`` is asserted in slice 2, once a real dependent table
exists. The stand-in dependent table here exists only to prove (b).
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.geo.etl import load_red_vial as loader

ATTRIBUTES = {
    "fna": "Camino Provincial T027-10",
    "gna": "Camino Provincial",
    "rtn": "T027-10",
    "fun": "6",
    "rst": "No pavimentado",
    "hct": "Camino Terciario",
    "ccn": "C.C. 027 - LEONES",
    "ccc": "CC027",
    "rcc": "19",
    "red": "Terciaria",
}


def source_feature(source_id: str, coordinates, *, geometry_type="LineString", **overrides):
    properties = {"id": source_id, "lzn": 0.5, **ATTRIBUTES, **overrides}
    return loader.SourceFeature.from_geojson(
        {
            "type": "Feature",
            "properties": properties,
            "geometry": {"type": geometry_type, "coordinates": coordinates},
        }
    )


#: Two traces of the same id. ``FAR`` is ~1.1 km away from ``NEAR``'s corridor —
#: far beyond one DEM cell — while ``NUDGED`` moves a vertex by ~9 m.
NEAR = [[-62.50, -32.50], [-62.49, -32.50]]
NUDGED = [[-62.50, -32.50], [-62.49, -32.49992]]
FAR = [[-62.50, -32.51], [-62.49, -32.51]]


@pytest.fixture
def db(test_engine):
    """Savepoint-mode session: the loader commits for real, the test still rolls back."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def dependiente(db: Session):
    """A stand-in for ``cruce_camino`` / ``relevamiento_tramo``: FK, RESTRICT."""
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS dependiente_test ("
            "  id SERIAL PRIMARY KEY,"
            "  tramo_ref TEXT NOT NULL REFERENCES red_vial(id) ON DELETE RESTRICT)"
        )
    )
    db.commit()
    yield
    db.execute(text("DROP TABLE IF EXISTS dependiente_test"))
    db.commit()


def _rows(db: Session) -> list:
    return db.execute(
        text(
            "SELECT id, source_id, parte, activo, geom_hash, ultima_carga_en "
            "FROM red_vial ORDER BY id"
        )
    ).all()


class TestIdempotence:
    def test_two_loads_over_unchanged_source_produce_the_same_rows(self, db: Session):
        features = [source_feature("28188", NEAR), source_feature("27371", FAR)]

        loader.load(db, features, dry_run=False)
        first = _rows(db)
        loader.load(
            db, [source_feature("28188", NEAR), source_feature("27371", FAR)], dry_run=False
        )
        second = _rows(db)

        assert [(r.id, r.source_id, r.activo) for r in first] == [
            ("27371", "27371", True),
            ("28188", "28188", True),
        ]
        assert [(r.id, r.source_id, r.activo) for r in second] == [
            (r.id, r.source_id, r.activo) for r in first
        ]
        assert [r.geom_hash for r in second] == [r.geom_hash for r in first]

    def test_a_load_that_changes_no_attribute_still_moves_ultima_carga_en(self, db: Session):
        """(f) The load IS the event: vertex order alone can invalidate a stored side."""
        loader.load(db, [source_feature("28188", NEAR)], dry_run=False)
        before = _rows(db)[0].ultima_carga_en

        loader.load(db, [source_feature("28188", NEAR)], dry_run=False)
        after = _rows(db)[0].ultima_carga_en

        assert after > before


class TestRetireOnly:
    def test_an_absent_id_is_retired_not_removed_and_its_dependents_survive(
        self, db: Session, dependiente
    ):
        loader.load(
            db, [source_feature("28188", NEAR), source_feature("27371", FAR)], dry_run=False
        )
        db.execute(text("INSERT INTO dependiente_test (tramo_ref) VALUES ('27371')"))
        db.commit()

        # 27371 disappears from the source.
        loader.load(db, [source_feature("28188", NEAR)], dry_run=False)

        rows = {r.id: r.activo for r in _rows(db)}
        assert rows == {"28188": True, "27371": False}
        survivors = db.execute(
            text("SELECT count(*) FROM dependiente_test WHERE tramo_ref = '27371'")
        ).scalar_one()
        assert survivors == 1

    def test_the_report_names_the_retired_ids(self, db: Session):
        loader.load(
            db, [source_feature("28188", NEAR), source_feature("27371", FAR)], dry_run=False
        )
        result = loader.load(db, [source_feature("28188", NEAR)], dry_run=False)

        assert result.retired_ids == ["27371"]
        assert "27371" in result.render()

    def test_a_retired_id_that_comes_back_unchanged_is_a_new_row(self, db: Session):
        """Retirement is not reversible in place: the row that comes back is new."""
        loader.load(
            db, [source_feature("28188", NEAR), source_feature("27371", FAR)], dry_run=False
        )
        loader.load(db, [source_feature("28188", NEAR)], dry_run=False)
        loader.load(
            db, [source_feature("28188", NEAR), source_feature("27371", FAR)], dry_run=False
        )

        lineage = [(r.id, r.activo) for r in _rows(db) if r.source_id == "27371"]
        assert lineage == [("27371", False), ("27371#2", True)]


class TestIdReuseSplit:
    def test_a_materially_different_trace_splits_the_lineage(self, db: Session, dependiente):
        loader.load(db, [source_feature("28188", NEAR)], dry_run=False)
        db.execute(text("INSERT INTO dependiente_test (tramo_ref) VALUES ('28188')"))
        db.commit()

        result = loader.load(db, [source_feature("28188", FAR)], dry_run=False)

        rows = {r.id: (r.source_id, r.activo) for r in _rows(db)}
        assert rows == {"28188": ("28188", False), "28188#2": ("28188", True)}
        # (c) no dependent row transfers to the different trace.
        moved = db.execute(text("SELECT tramo_ref FROM dependiente_test")).scalars().all()
        assert moved == ["28188"]
        assert len(result.splits) == 1
        assert result.splits[0].retired_id == "28188"
        assert result.splits[0].new_id == "28188#2"
        assert "28188 → 28188#2" in result.render()

    def test_a_trivially_changed_trace_updates_in_place(self, db: Session):
        """Under one DEM cell the geometry moved, the road did not."""
        loader.load(db, [source_feature("28188", NEAR)], dry_run=False)
        before = _rows(db)[0]

        result = loader.load(db, [source_feature("28188", NUDGED)], dry_run=False)

        rows = _rows(db)
        assert [r.id for r in rows] == ["28188"]
        assert rows[0].activo is True
        assert rows[0].geom_hash != before.geom_hash  # the trace did change
        assert result.splits == []

    def test_a_third_load_over_the_post_split_source_re_splits_nothing(self, db: Session):
        """(d) The baseline is the ACTIVE row for the source id, never the PK."""
        loader.load(db, [source_feature("28188", NEAR)], dry_run=False)
        loader.load(db, [source_feature("28188", FAR)], dry_run=False)

        third = loader.load(db, [source_feature("28188", FAR)], dry_run=False)

        assert third.splits == []
        assert third.updated == 1
        assert [(r.id, r.activo) for r in _rows(db)] == [("28188", False), ("28188#2", True)]

    def test_repeated_splits_walk_the_ordinal_suffix(self, db: Session):
        loader.load(db, [source_feature("28188", NEAR)], dry_run=False)
        loader.load(db, [source_feature("28188", FAR)], dry_run=False)
        loader.load(
            db, [source_feature("28188", [[-62.60, -32.60], [-62.59, -32.60]])], dry_run=False
        )

        assert [(r.id, r.activo) for r in _rows(db)] == [
            ("28188", False),
            ("28188#2", False),
            ("28188#3", True),
        ]


class TestPartialUniqueIndexUnderLoad:
    def test_a_second_active_row_for_one_source_id_is_refused(self, db: Session):
        """(e) The invariant is enforced by the database, not only by the loader."""
        loader.load(db, [source_feature("28188", NEAR)], dry_run=False)
        with pytest.raises(Exception, match="ux_red_vial_source_activo|duplicate key"):
            db.execute(
                text(
                    "INSERT INTO red_vial (id, source_id, geom, geom_hash) VALUES "
                    "('28188#9', '28188', ST_GeomFromText('LINESTRING(-62 -32, -62.1 -32.1)', 4326), 'x')"
                )
            )
        db.rollback()


class TestStoredGeometry:
    def test_a_connected_multigeometry_collapses_to_a_linestring(self, db: Session):
        connected = [[[-62.50, -32.50], [-62.49, -32.50]], [[-62.49, -32.50], [-62.48, -32.50]]]
        loader.load(
            db,
            [source_feature("13680", connected, geometry_type="MultiLineString")],
            dry_run=False,
        )
        rows = db.execute(
            text("SELECT id, parte, GeometryType(geom) AS geom_type FROM red_vial")
        ).all()
        assert [(r.id, r.parte, r.geom_type) for r in rows] == [("13680", 1, "LINESTRING")]


class TestMultiPartAdmission:
    """Owner decision, 2026-08-22 (exit B): a disconnected MultiGeometry is N segments.

    The earlier rule aborted the whole load naming the id. The field reality the
    owner brought is that several such features exist, and an abort on the first
    one hides all the others — so the parts are admitted as N rows of ONE
    lineage, each with its own suffixed PK, and the load reports them.
    """

    #: Two lines ~9 km apart: `ST_LineMerge` cannot join them.
    DISCONNECTED = [
        [[-62.50, -32.50], [-62.49, -32.50]],
        [[-62.40, -32.40], [-62.39, -32.40]],
    ]

    def test_a_disconnected_feature_becomes_one_row_per_part(self, db: Session):
        result = loader.load(
            db,
            [source_feature("13680", self.DISCONNECTED, geometry_type="MultiLineString")],
            dry_run=False,
        )

        rows = db.execute(
            text(
                "SELECT id, source_id, parte, activo, GeometryType(geom) AS geom_type "
                "FROM red_vial ORDER BY parte"
            )
        ).all()
        assert [(r.id, r.source_id, r.parte, r.activo, r.geom_type) for r in rows] == [
            ("13680", "13680", 1, True, "LINESTRING"),
            ("13680#2", "13680", 2, True, "LINESTRING"),
        ]
        assert result.inserted == 2
        assert result.rows_after == 2

    def test_the_load_reports_every_multi_part_feature(self, db: Session):
        result = loader.load(
            db,
            [source_feature("13680", self.DISCONNECTED, geometry_type="MultiLineString")],
            dry_run=False,
        )
        assert result.multipart == [("13680", 2)]
        assert "MULTIPARTE" in result.render()
        assert "13680" in result.render()

    def test_each_part_keeps_its_own_geometry_verbatim(self, db: Session):
        loader.load(
            db,
            [source_feature("13680", self.DISCONNECTED, geometry_type="MultiLineString")],
            dry_run=False,
        )
        stored = db.execute(
            text("SELECT parte, ST_AsGeoJSON(geom, 15) AS geojson FROM red_vial ORDER BY parte")
        ).all()
        loaded = [json.loads(r.geojson)["coordinates"] for r in stored]
        # Part order is derived from the geometry (start point, lexicographic),
        # not from the source's part order — so the same two lines always land on
        # the same two identities.
        assert sorted(loaded) == sorted(self.DISCONNECTED)

    def test_part_identity_survives_the_source_reordering_its_parts(self, db: Session):
        """Ordering by start point is what makes the identity stable.

        With source-order indexing, a source that emitted the same two lines in
        the other order would swap two segments' identities — and every field
        survey attached to them.
        """
        loader.load(
            db,
            [source_feature("13680", self.DISCONNECTED, geometry_type="MultiLineString")],
            dry_run=False,
        )
        before = {r.id: r.geom_hash for r in db.execute(text("SELECT id, geom_hash FROM red_vial"))}

        reordered = list(reversed(self.DISCONNECTED))
        result = loader.load(
            db,
            [source_feature("13680", reordered, geometry_type="MultiLineString")],
            dry_run=False,
        )

        after = {r.id: r.geom_hash for r in db.execute(text("SELECT id, geom_hash FROM red_vial"))}
        assert after == before
        assert result.splits == []
        assert result.inserted == 0

    def test_a_second_load_of_the_same_multi_part_feature_is_idempotent(self, db: Session):
        feature = source_feature("13680", self.DISCONNECTED, geometry_type="MultiLineString")
        loader.load(db, [feature], dry_run=False)
        first = [(r.id, r.source_id, r.activo) for r in _rows(db)]

        result = loader.load(db, [feature], dry_run=False)

        assert [(r.id, r.source_id, r.activo) for r in _rows(db)] == first
        assert result.inserted == 0
        assert result.updated == 2

    def test_a_part_that_disappears_is_retired_not_removed(self, db: Session):
        """From two parts to one: the vanished part follows the retire-only rule."""
        loader.load(
            db,
            [source_feature("13680", self.DISCONNECTED, geometry_type="MultiLineString")],
            dry_run=False,
        )

        result = loader.load(db, [source_feature("13680", self.DISCONNECTED[0])], dry_run=False)

        rows = {r.id: r.activo for r in _rows(db)}
        assert rows == {"13680": True, "13680#2": False}
        assert result.retired_ids == ["13680#2"]

    def test_a_part_that_comes_back_reactivates_as_a_new_row(self, db: Session):
        loader.load(
            db,
            [source_feature("13680", self.DISCONNECTED, geometry_type="MultiLineString")],
            dry_run=False,
        )
        loader.load(db, [source_feature("13680", self.DISCONNECTED[0])], dry_run=False)
        loader.load(
            db,
            [source_feature("13680", self.DISCONNECTED, geometry_type="MultiLineString")],
            dry_run=False,
        )

        rows = [(r.id, r.activo) for r in _rows(db)]
        assert rows == [("13680", True), ("13680#2", False), ("13680#3", True)]

    def test_the_suffix_space_is_shared_with_the_lineage_split(self, db: Session):
        """Parts and splits draw from ONE ordinal space, so no PK is ever reused."""
        loader.load(
            db,
            [source_feature("13680", self.DISCONNECTED, geometry_type="MultiLineString")],
            dry_run=False,
        )
        moved = [self.DISCONNECTED[0], [[-62.30, -32.30], [-62.29, -32.30]]]
        loader.load(
            db, [source_feature("13680", moved, geometry_type="MultiLineString")], dry_run=False
        )

        rows = [(r.id, r.activo) for r in _rows(db)]
        assert ("13680#3", True) in rows
        assert ("13680#2", False) in rows

    #: Sorts BEFORE both `DISCONNECTED` parts by start-point x — the case that
    #: shifted every ordinal when identity was positional.
    LOWEST = [[-62.90, -32.90], [-62.89, -32.90]]

    def _load(self, db: Session, parts: list) -> object:
        return loader.load(
            db, [source_feature("13680", parts, geometry_type="MultiLineString")], dry_run=False
        )

    def test_gaining_a_part_that_sorts_first_leaves_the_survivors_untouched(self, db: Session):
        """RDD review R4: identity is geometric, so a new part cannot renumber the others."""
        self._load(db, self.DISCONNECTED)
        before = {r.id: (r.parte, r.geom_hash) for r in _rows(db)}

        result = self._load(db, [self.LOWEST, *self.DISCONNECTED])

        after = {r.id: (r.parte, r.geom_hash, r.activo) for r in _rows(db)}
        for row_id, (parte, geom_hash) in before.items():
            assert after[row_id] == (parte, geom_hash, True), row_id
        assert (result.retired_ids, result.splits) == ([], [])
        assert (result.inserted, result.updated, len(after)) == (1, 2, 3)

    def test_losing_the_lowest_sorting_part_retires_only_that_part(self, db: Session):
        """The mirror case: the survivor keeps its PK, its ordinal and its history."""
        self._load(db, [self.LOWEST, *self.DISCONNECTED])
        before = {r.id: (r.parte, r.geom_hash) for r in _rows(db)}
        lowest_id = min(_rows(db), key=lambda r: r.parte).id

        result = self._load(db, self.DISCONNECTED)

        assert result.retired_ids == [lowest_id]
        assert (result.inserted, result.splits) == (0, [])
        survivors = {r.id: (r.parte, r.geom_hash) for r in _rows(db) if r.activo}
        assert survivors == {k: v for k, v in before.items() if k != lowest_id}

    def test_a_three_part_feature_lands_as_three_rows(self, db: Session):
        three = [
            [[-62.50, -32.50], [-62.49, -32.50]],
            [[-62.40, -32.40], [-62.39, -32.40]],
            [[-62.30, -32.30], [-62.29, -32.30]],
        ]
        result = loader.load(
            db, [source_feature("13680", three, geometry_type="MultiLineString")], dry_run=False
        )
        assert result.multipart == [("13680", 3)]
        assert [r.id for r in _rows(db)] == ["13680", "13680#2", "13680#3"]


class TestDryRun:
    def test_dry_run_writes_nothing(self, db: Session):
        result = loader.load(db, [source_feature("28188", NEAR)], dry_run=True)
        assert result.committed is False
        assert _rows(db) == []
