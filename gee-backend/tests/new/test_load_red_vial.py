"""Parsing, fidelity pins and the granularity report of the ``red_vial`` loader.

Two halves, deliberately:

* **Pure parsing** — in-memory GeoJSON fixtures, no database. Everything the
  loader decides *before* it touches PostgreSQL: the feature-count pin
  (assertion 0), attribute coercion, the duplicate/missing/wrong-type rejections,
  and ``geom_hash`` stability.
* **The granularity report (assertion 5)** — real PG, because it is measured with
  ``ST_Length(geom::geography)``. It reports and never corrects: a 12 km feature
  is flagged as an outlier requiring an explicit decision, is still loaded, and
  its geometry comes back identical to the source. The loader never re-segments.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pytest
from sqlalchemy import text

from app.domains.geo.etl import load_red_vial as loader

#: sha256 of ``gee/red_vial/caminoss.kml``, the file the package data was
#: converted from. Duplicated here on purpose: the loader's docstring is the
#: audit trail, and this test is what keeps the audit trail honest.
KML_SHA256 = "c53ca6f3d0b3f785b41b76d2919a81ea7e4dd340b688d395a1311d786323c836"

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — minimal GeoJSON, shaped like the shipped conversion
# ─────────────────────────────────────────────────────────────────────────────

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


def feature(
    source_id: str,
    coordinates: list[list[float]] | None = None,
    *,
    lzn: float | None = 0.488,
    geometry_type: str = "LineString",
    **overrides: object,
) -> dict:
    properties: dict[str, object] = {"id": source_id, **ATTRIBUTES}
    if lzn is not None:
        properties["lzn"] = lzn
    properties.update(overrides)
    coordinates = coordinates or [[-62.39, -32.53], [-62.38, -32.54]]
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": geometry_type, "coordinates": coordinates},
    }


def collection(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def parse(*features: dict, expected_count: int | None = None):
    """Parse without the shipped pin getting in the way of a 2-feature fixture."""
    return loader.parse_features(
        collection(*features),
        expected_count=len(features) if expected_count is None else expected_count,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Assertion 0 — the feature-count pin
# ─────────────────────────────────────────────────────────────────────────────


class TestProvenanceAndInvariants:
    def test_the_docstring_records_the_source_kml_and_its_sha256(self):
        docstring = loader.__doc__ or ""
        assert "gee/red_vial/caminoss.kml" in docstring
        assert KML_SHA256 in docstring
        assert "red_vial_provincial.kml" in docstring  # the file that is NOT the source

    def test_the_recorded_sha256_matches_the_repository_kml(self):
        kml = Path(__file__).resolve().parents[3] / "gee" / "red_vial" / "caminoss.kml"
        if not kml.exists():  # pragma: no cover — the container ships no gee/ tree
            pytest.skip("gee/red_vial/caminoss.kml is not present in this checkout")
        assert hashlib.sha256(kml.read_bytes()).hexdigest() == KML_SHA256

    def test_the_loader_issues_no_delete(self):
        """Retire-only is a property of the source text, not only of the tests.

        The whole file, docstrings included — the same literal check the task
        states (``rg -n '\\bDELETE\\b' load_red_vial.py`` returns nothing), so
        prose about deleting cannot mask a statement that deletes.
        """
        source = Path(loader.__file__).read_text(encoding="utf-8")
        assert not re.search(r"\bDELETE\b", source, flags=re.IGNORECASE)

    def test_the_module_is_a_python_m_entry_point(self):
        assert loader.main.__module__ == "app.domains.geo.etl.load_red_vial"
        assert "python -m app.domains.geo.etl.load_red_vial" in (loader.__doc__ or "")


class TestFeatureCountPin:
    def test_shipped_pin_matches_the_shipped_package_data(self):
        """The constant is a claim about the source; the shipped file must honour it."""
        path = loader.resolve_source()
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        assert len(payload["features"]) == loader.RED_VIAL_FEATURE_COUNT

    def test_a_truncated_source_aborts(self):
        with pytest.raises(loader.EtlAssertionError, match="380|cantidad de features"):
            loader.parse_features(collection(feature("1")), expected_count=380)

    def test_an_oversized_source_aborts(self):
        with pytest.raises(loader.EtlAssertionError, match="cantidad de features"):
            loader.parse_features(collection(feature("1"), feature("2")), expected_count=1)


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────


class TestParsing:
    def test_every_source_attribute_is_carried_verbatim(self):
        parsed = parse(feature("28188"))[0]
        assert parsed.source_id == "28188"
        assert parsed.attributes == ATTRIBUTES
        assert parsed.lzn == pytest.approx(0.488)

    def test_missing_lzn_is_none_not_zero(self):
        parsed = parse(feature("28188", lzn=None))[0]
        assert parsed.lzn is None

    def test_lzn_as_string_is_coerced(self):
        parsed = parse(feature("28188", lzn="2.097"))[0]
        assert parsed.lzn == pytest.approx(2.097)

    def test_absent_attribute_is_none(self):
        raw = feature("28188")
        del raw["properties"]["rtn"]
        parsed = parse(raw)[0]
        assert parsed.attributes["rtn"] is None

    def test_multilinestring_is_parsed_and_kept_whole(self):
        """Not split here: the DB decides via ``ST_LineMerge``, and aborts if it survives."""
        raw = feature(
            "13680",
            coordinates=[
                [[-62.69, -32.58], [-62.69, -32.59]],
                [[-62.68, -32.59], [-62.68, -32.59]],
            ],
            geometry_type="MultiLineString",
        )
        parsed = parse(raw)[0]
        assert json.loads(parsed.geometry_json)["type"] == "MultiLineString"

    def test_duplicate_source_id_aborts(self):
        with pytest.raises(loader.EtlAssertionError, match="duplicad"):
            parse(feature("28188"), feature("28188"))

    def test_missing_geometry_aborts_naming_the_id(self):
        raw = feature("28188")
        raw["geometry"] = None
        with pytest.raises(loader.EtlAssertionError, match="28188"):
            parse(raw)

    def test_missing_id_aborts(self):
        raw = feature("28188")
        del raw["properties"]["id"]
        with pytest.raises(loader.EtlAssertionError, match="sin id"):
            parse(raw)

    def test_non_line_geometry_aborts_naming_the_id(self):
        raw = feature("28188", coordinates=[-62.39, -32.53], geometry_type="Point")
        with pytest.raises(loader.EtlAssertionError, match="28188"):
            parse(raw)

    def test_not_a_feature_collection_aborts(self):
        with pytest.raises(loader.EtlAssertionError, match="FeatureCollection"):
            loader.parse_features({"type": "Nope", "features": []}, expected_count=0)


# ─────────────────────────────────────────────────────────────────────────────
# geom_hash — the material-change discriminator
# ─────────────────────────────────────────────────────────────────────────────


class TestGeomHash:
    def test_is_stable_across_two_parses_of_the_same_feature(self):
        first = parse(feature("28188"))[0]
        second = parse(feature("28188"))[0]
        assert first.geom_hash == second.geom_hash
        assert len(first.geom_hash) == 64  # sha256 hex

    def test_differs_when_a_vertex_moves(self):
        base = parse(feature("28188"))[0]
        moved = parse(feature("28188", coordinates=[[-62.39, -32.53], [-62.30, -32.54]]))[0]
        assert base.geom_hash != moved.geom_hash

    def test_ignores_the_attributes(self):
        base = parse(feature("28188"))[0]
        renamed = parse(feature("28188", fna="otro nombre"))[0]
        assert base.geom_hash == renamed.geom_hash

    def test_vertex_order_is_part_of_the_hash(self):
        """A reversed trace is the same line but not the same digitization."""
        base = parse(feature("28188"))[0]
        reversed_ = parse(feature("28188", coordinates=[[-62.38, -32.54], [-62.39, -32.53]]))[0]
        assert base.geom_hash != reversed_.geom_hash


# ─────────────────────────────────────────────────────────────────────────────
# The stored-geometry assertions (2–4), unit-tested off the DB round trip
# ─────────────────────────────────────────────────────────────────────────────


class TestStoredGeometryAssertions:
    def test_accepts_a_valid_linestring(self):
        loader.assert_stored_geometry(
            "28188", valid=True, empty=False, srid=4326, geom_type="LINESTRING"
        )

    def test_a_surviving_multilinestring_aborts_naming_its_id(self):
        with pytest.raises(loader.EtlAssertionError, match="13680"):
            loader.assert_stored_geometry(
                "13680", valid=True, empty=False, srid=4326, geom_type="MULTILINESTRING"
            )

    def test_an_irreparable_geometry_aborts(self):
        with pytest.raises(loader.EtlAssertionError, match="28188"):
            loader.assert_stored_geometry(
                "28188", valid=True, empty=True, srid=4326, geom_type="LINESTRING"
            )

    def test_an_invalid_geometry_aborts(self):
        with pytest.raises(loader.EtlAssertionError, match="28188"):
            loader.assert_stored_geometry(
                "28188", valid=False, empty=False, srid=4326, geom_type="LINESTRING"
            )

    def test_a_wrong_srid_aborts(self):
        with pytest.raises(loader.EtlAssertionError, match="4326"):
            loader.assert_stored_geometry(
                "28188", valid=True, empty=False, srid=32720, geom_type="LINESTRING"
            )

    def test_the_upsert_collapses_the_multigeometry_wrapper(self):
        """The wrapper collapse is SQL, so pin the SQL that performs it."""
        assert "ST_LineMerge(ST_MakeValid(" in loader.GEOM_EXPRESSION
        assert "ST_SetSRID" in loader.GEOM_EXPRESSION


# ─────────────────────────────────────────────────────────────────────────────
# The next free PK of a lineage
# ─────────────────────────────────────────────────────────────────────────────


class TestNextFreePk:
    def test_unused_source_id_is_used_as_is(self):
        assert loader.next_free_pk("28188", set()) == "28188"

    def test_first_collision_becomes_hash_two(self):
        assert loader.next_free_pk("28188", {"28188"}) == "28188#2"

    def test_the_suffix_is_derived_from_what_exists(self):
        assert loader.next_free_pk("28188", {"28188", "28188#2", "28188#3"}) == "28188#4"

    def test_the_lowest_free_ordinal_wins(self):
        """The suffix is the next FREE ordinal, not the highest seen plus one.

        A gap cannot arise in practice — the loader never deletes, so every PK a
        lineage ever used is still there — but the rule has to be total anyway.
        """
        assert loader.next_free_pk("28188", {"28188", "28188#3"}) == "28188#2"


# ─────────────────────────────────────────────────────────────────────────────
# Assertion 5 — the granularity report (real PG: it is measured in metres)
# ─────────────────────────────────────────────────────────────────────────────


def _straight_line(km: float) -> list[list[float]]:
    """A west-east line of roughly ``km`` kilometres at latitude -32.5."""
    degrees = km / (111.320 * 0.8434)  # cos(32.5°)
    return [[-62.5, -32.5], [-62.5 + degrees, -32.5]]


@pytest.fixture
def db(test_engine):
    """A session whose ``commit()`` is a savepoint release, rolled back after the test.

    The loader commits for real (that is the behaviour under test), so the plain
    ``db`` fixture's outer-transaction rollback would not survive it — same
    ``join_transaction_mode="create_savepoint"`` trick as
    ``test_load_canales_consorcio``'s ``canales_db``.
    """
    from sqlalchemy.orm import Session as OrmSession

    connection = test_engine.connect()
    transaction = connection.begin()
    session = OrmSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


class TestGranularityReport:
    def test_a_twelve_km_feature_is_reported_as_an_outlier_and_still_loaded(self, db):
        features = [
            loader.SourceFeature.from_geojson(feature(str(i), _straight_line(0.5)))
            for i in range(1, 20)
        ]
        long_one = loader.SourceFeature.from_geojson(
            feature("largo", _straight_line(12.0), lzn=12.0)
        )
        features.append(long_one)

        result = loader.load(db, features, dry_run=True)

        assert "largo" in result.granularity.outlier_ids
        assert "OUTLIER — requiere decisión explícita" in result.render()
        # Reported, not corrected: the feature is loaded whole.
        assert result.granularity.feature_count == 20
        assert result.granularity.max_m == pytest.approx(12_000, rel=0.02)

    def test_the_outlier_geometry_is_not_re_segmented(self, db):
        source = loader.SourceFeature.from_geojson(feature("largo", _straight_line(12.0), lzn=12.0))
        loader.load(db, [source], dry_run=False)
        stored = db.execute(
            text(
                # 15 digits: the default 9 rounds, and this test is about the
                # geometry being stored untouched.
                "SELECT ST_AsGeoJSON(geom, 15) AS geojson, GeometryType(geom) AS geom_type "
                "FROM red_vial WHERE id = 'largo'"
            )
        ).one()
        assert stored.geom_type == "LINESTRING"
        assert (
            json.loads(stored.geojson)["coordinates"]
            == json.loads(source.geometry_json)["coordinates"]
        )

    def test_declared_lzn_disagreements_are_counted_not_fatal(self, db):
        honest = loader.SourceFeature.from_geojson(feature("honesto", _straight_line(1.0), lzn=1.0))
        liar = loader.SourceFeature.from_geojson(feature("mentiroso", _straight_line(1.0), lzn=5.0))

        result = loader.load(db, [honest, liar], dry_run=True)

        assert result.granularity.lzn_mismatch_count == 1
        assert "mentiroso" in result.granularity.lzn_mismatch_ids

    def test_the_report_names_the_length_distribution(self, db):
        features = [
            loader.SourceFeature.from_geojson(feature(str(i), _straight_line(1.0)))
            for i in range(1, 11)
        ]
        result = loader.load(db, features, dry_run=True)
        rendered = result.render()
        for label in ("min", "mediana", "p90", "max"):
            assert label in rendered
        assert result.granularity.median_m == pytest.approx(1000, rel=0.02)
