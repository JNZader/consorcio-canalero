"""Tests for the KMZ unzipper + KML Placemark extractor.

The KMZ itself is just a zip with a single ``doc.kml`` entry.  We extract
each ``<Placemark>`` as a ``RawPlacemark`` carrying:

- the raw ``<name>`` string (parsing happens later via
  ``scripts.etl_canales.parse_name.parse_name``),
- the ``styleUrl`` minus the ``#`` prefix,
- the ``/``-joined folder hierarchy for grouping in UI,
- the geometry type (``LineString`` | ``Polygon`` | ``Point``) so the caller
  can skip non-linestring placemarks,
- the raw coordinates as ``(lon, lat)`` tuples (altitude dropped).

Polygons are EXTRACTED with geometry_type=Polygon so the caller can log them
and skip — we do NOT filter inside the extractor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.etl_canales.kmz import RawPlacemark, extract_placemarks

FIXTURES = Path(__file__).parent / "fixtures"


class TestExtractLinestringPlacemark:
    def test_extracts_linestring(self):
        placemarks = extract_placemarks(FIXTURES / "sample_relevados.kmz")
        line_pms = [p for p in placemarks if p.geometry_type == "LineString"]
        # sample_relevados has 5 LineString placemarks.
        assert len(line_pms) == 5

    def test_first_placemark_basic_fields(self):
        placemarks = extract_placemarks(FIXTURES / "sample_relevados.kmz")
        first = placemarks[0]
        assert isinstance(first, RawPlacemark)
        assert first.name == "Canal NE (sin intervención)"
        assert first.style_url == "sin_obra"
        assert first.geometry_type == "LineString"
        assert first.coords == [(-62.45, -32.58), (-62.44, -32.57), (-62.43, -32.57)]

    def test_folder_path_single_level(self):
        placemarks = extract_placemarks(FIXTURES / "sample_relevados.kmz")
        first = placemarks[0]
        # Canal NE is directly under <Folder>Canales existentes</Folder>.
        assert first.folder_path == "Canales existentes"

    def test_folder_path_nested(self):
        placemarks = extract_placemarks(FIXTURES / "sample_relevados.kmz")
        # N4 lives under Canales existentes > Canal Norte.
        n4 = next(p for p in placemarks if p.name.startswith("N4"))
        assert n4.folder_path == "Canales existentes/Canal Norte"

    def test_placemark_without_styleurl(self):
        placemarks = extract_placemarks(FIXTURES / "sample_relevados.kmz")
        # E21 is defined without a <styleUrl>.
        e21 = next(p for p in placemarks if p.name.startswith("E21"))
        assert e21.style_url is None


class TestExtractPolygonPlacemark:
    def test_polygon_still_returned_with_type_polygon(self):
        placemarks = extract_placemarks(FIXTURES / "sample_relevados.kmz")
        poly_pms = [p for p in placemarks if p.geometry_type == "Polygon"]
        assert len(poly_pms) == 1
        poly = poly_pms[0]
        assert poly.name == "Las Tres del Norte"
        assert poly.style_url == "poligono_traslucido"
        # Coordinates from the outer LinearRing.
        assert poly.coords[0] == (-62.55, -32.42)

    def test_total_placemark_count_includes_polygon(self):
        placemarks = extract_placemarks(FIXTURES / "sample_relevados.kmz")
        # 5 LineString + 1 Polygon = 6 total.
        assert len(placemarks) == 6


class TestPropuestasSample:
    def test_extracts_nested_folders(self):
        placemarks = extract_placemarks(FIXTURES / "sample_propuestas.kmz")
        assert len(placemarks) == 2
        norte = next(p for p in placemarks if p.name.startswith("N3"))
        assert norte.folder_path == "Propuestas/Norte"
        candil = next(p for p in placemarks if p.name.startswith("S5"))
        assert candil.folder_path == "Propuestas/Candil"
        assert candil.style_url == "prio_Media_Alta"


class TestMissingInput:
    def test_missing_kmz_raises(self, tmp_path: Path):
        with pytest.raises((FileNotFoundError, OSError)):
            extract_placemarks(tmp_path / "nope.kmz")

    def test_kmz_without_doc_kml_raises(self, tmp_path: Path):
        import zipfile

        bad = tmp_path / "bad.kmz"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("not-doc.kml", "<kml/>")
        with pytest.raises(FileNotFoundError):
            extract_placemarks(bad)
