"""Tests for ``kml_to_geojson``.

The ZONA CC AMPLIADA KML has a simple structure: single Placemark with a
Polygon / outerBoundaryIs / LinearRing / coordinates pair.  We parse that into
a GeoJSON FeatureCollection with exactly one Polygon feature.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.etl_pilar_verde.kml import kml_to_geojson

FIXTURES = Path(__file__).parent / "fixtures"


class TestKmlToGeoJson:
    def test_returns_feature_collection(self):
        result = kml_to_geojson(FIXTURES / "zona_ampliada_tiny.kml")
        assert result["type"] == "FeatureCollection"
        assert "features" in result
        assert isinstance(result["features"], list)

    def test_contains_exactly_one_polygon(self):
        result = kml_to_geojson(FIXTURES / "zona_ampliada_tiny.kml")
        assert len(result["features"]) == 1
        geom = result["features"][0]["geometry"]
        assert geom["type"] == "Polygon"

    def test_polygon_is_closed_ring(self):
        result = kml_to_geojson(FIXTURES / "zona_ampliada_tiny.kml")
        ring = result["features"][0]["geometry"]["coordinates"][0]
        # LinearRings must close: first == last.
        assert ring[0] == ring[-1]

    def test_polygon_has_expected_corners(self):
        # Fixture corners: -62.7,-32.6 / -62.3,-32.6 / -62.3,-32.4 / -62.7,-32.4
        result = kml_to_geojson(FIXTURES / "zona_ampliada_tiny.kml")
        ring = result["features"][0]["geometry"]["coordinates"][0]
        # Each coordinate is [lon, lat] (GeoJSON order — reverse of KML order
        # which is lon,lat,alt).
        lons = {round(c[0], 4) for c in ring}
        lats = {round(c[1], 4) for c in ring}
        assert lons == {-62.7, -62.3}
        assert lats == {-32.6, -32.4}

    def test_coords_are_floats(self):
        result = kml_to_geojson(FIXTURES / "zona_ampliada_tiny.kml")
        ring = result["features"][0]["geometry"]["coordinates"][0]
        for coord in ring:
            assert isinstance(coord[0], float)
            assert isinstance(coord[1], float)

    def test_real_kml_has_642_vertices(self):
        # Sanity — the real production KML must match the exploration count.
        real_kml = Path(__file__).resolve().parents[2] / "gee" / "zona_cc_ampliada" / "CC 10 de mayo ampliado2.kml"
        if not real_kml.exists():
            pytest.skip("real KML not available in test environment")
        result = kml_to_geojson(real_kml)
        assert len(result["features"]) == 1
        ring = result["features"][0]["geometry"]["coordinates"][0]
        assert len(ring) == 642

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises((FileNotFoundError, OSError)):
            kml_to_geojson(tmp_path / "does_not_exist.kml")
