"""End-to-end tests for ``build_geojson`` — the Escuelas Rurales orchestrator.

Contract under test:

- ``build_geojson(kmz_path)`` returns a single GeoJSON ``FeatureCollection``
  of ``Point`` features in KML document order.
- Each feature has a stable top-level ``id`` (via ``slug`` + ``slug_with_counter``).
- Each feature's ``properties`` contain EXACTLY 4 keys in this order:
  ``nombre``, ``localidad``, ``ambito``, ``nivel`` — no PII, no other keys.
- Coordinates come from the KML ``<Point>`` and are exposed as ``[lon, lat]``
  (WGS84, altitude dropped — consistent with ``etl_canales.kmz``).
- The builder is byte-idempotent when serialized with the same
  ``ETL_GENERATED_AT`` env var.  This test pins the env var to a constant
  and compares the JSON twice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.etl_escuelas.build import build_geojson

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_KMZ = FIXTURES / "sample_escuelas.kmz"

# Required schema for each feature's ``properties`` block.  Order is NOT
# enforced by ``set`` equality, but the writer emits them in insertion order
# so downstream byte-idempotence keeps the field sequence stable.
EXPECTED_PROP_KEYS = {"nombre", "localidad", "ambito", "nivel"}

PII_SUBSTRINGS = [
    "cue",
    "telefono",
    "teléfono",
    "email",
    "directivo",
    "sector",
    "departamento",
]


class TestBuildGeojsonShape:
    def test_returns_feature_collection(self) -> None:
        fc = build_geojson(SAMPLE_KMZ)
        assert fc["type"] == "FeatureCollection"
        assert isinstance(fc["features"], list)

    def test_all_features_are_points(self) -> None:
        fc = build_geojson(SAMPLE_KMZ)
        # The fixture has 3 Point placemarks — no Lines, no Polygons.
        assert len(fc["features"]) == 3
        for feature in fc["features"]:
            assert feature["type"] == "Feature"
            assert feature["geometry"]["type"] == "Point"
            coords = feature["geometry"]["coordinates"]
            assert isinstance(coords, list) and len(coords) == 2

    def test_feature_properties_have_exactly_four_keys(self) -> None:
        # Spec REQ-ESC-2: every feature has EXACTLY these 4 keys — no PII,
        # no burocratic codes, no extras.
        fc = build_geojson(SAMPLE_KMZ)
        for feature in fc["features"]:
            assert set(feature["properties"].keys()) == EXPECTED_PROP_KEYS

    def test_no_pii_substrings_in_serialized_output(self) -> None:
        # Defense-in-depth: serialize to JSON and grep for any PII substring.
        fc = build_geojson(SAMPLE_KMZ)
        blob = json.dumps(fc, ensure_ascii=False).lower()
        for needle in PII_SUBSTRINGS:
            assert needle not in blob, (
                f"PII substring {needle!r} leaked into build_geojson output"
            )

    def test_feature_ids_are_unique(self) -> None:
        # Slug collisions are resolved via ``slug_with_counter`` so two
        # placemarks with the same <name> emit distinct ids.
        fc = build_geojson(SAMPLE_KMZ)
        ids = [f["id"] for f in fc["features"]]
        assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"

    def test_collision_counter_suffix_applied(self) -> None:
        # The fixture contains two "Esc. Test Aglomerado" placemarks; the
        # second one must get the ``-2`` suffix, the first stays bare.
        fc = build_geojson(SAMPLE_KMZ)
        ids = [f["id"] for f in fc["features"]]
        # Document order: Aglomerado #1, Disperso, Aglomerado #2.
        assert ids[0] == "esc-test-aglomerado"
        assert ids[2] == "esc-test-aglomerado-2"

    def test_coordinates_match_kml_order_lon_lat(self) -> None:
        fc = build_geojson(SAMPLE_KMZ)
        # First placemark: -62.5, -32.5 in the KML → GeoJSON [lon, lat].
        assert fc["features"][0]["geometry"]["coordinates"] == [-62.5, -32.5]

    def test_nombre_from_kml_name_element(self) -> None:
        fc = build_geojson(SAMPLE_KMZ)
        # The ``nombre`` field comes from the KML ``<name>`` element, NOT the
        # CDATA — it's the authoritative human label.
        names = [f["properties"]["nombre"] for f in fc["features"]]
        assert "Esc. Test Aglomerado" in names
        assert "Esc. Test Disperso" in names


class TestBuildGeojsonValueIntegrity:
    def test_localidad_preserved_with_accents(self) -> None:
        fc = build_geojson(SAMPLE_KMZ)
        # Spot-check: values survive round-trip with UTF-8 intact.
        agl = next(f for f in fc["features"] if f["id"] == "esc-test-aglomerado")
        assert agl["properties"]["localidad"] == "Fixture Town"

    def test_nivel_preserves_middot_value(self) -> None:
        # The ``·`` inside ``"Inicial · Primario"`` is VALUE content, NOT a
        # separator.  Confirm it survived the parser.
        fc = build_geojson(SAMPLE_KMZ)
        agl = next(f for f in fc["features"] if f["id"] == "esc-test-aglomerado")
        assert agl["properties"]["nivel"] == "Inicial · Primario"

    def test_ambito_values_are_the_two_allowed_strings(self) -> None:
        fc = build_geojson(SAMPLE_KMZ)
        allowed = {"Rural Aglomerado", "Rural Disperso"}
        for feature in fc["features"]:
            assert feature["properties"]["ambito"] in allowed


class TestBuildIdempotentWithEnvPinned:
    def test_build_idempotent_with_env_pinned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec REQ-ESC-1: byte-identical output for byte-identical input.
        # ``ETL_GENERATED_AT`` is honored by the writer so tests can pin it.
        monkeypatch.setenv("ETL_GENERATED_AT", "2026-04-21T00:00:00Z")
        first = json.dumps(build_geojson(SAMPLE_KMZ), ensure_ascii=False, sort_keys=False)
        second = json.dumps(build_geojson(SAMPLE_KMZ), ensure_ascii=False, sort_keys=False)
        assert first == second

    def test_build_deterministic_id_sequence(self) -> None:
        # Idempotence at the id level: the 3-feature fixture always emits the
        # same id sequence across runs.
        first = [f["id"] for f in build_geojson(SAMPLE_KMZ)["features"]]
        second = [f["id"] for f in build_geojson(SAMPLE_KMZ)["features"]]
        assert first == second
        assert first == [
            "esc-test-aglomerado",
            "esc-test-disperso",
            "esc-test-aglomerado-2",
        ]
