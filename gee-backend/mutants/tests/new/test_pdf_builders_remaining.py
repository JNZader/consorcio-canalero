"""Tests for shared/pdf/builders.py — cover uncovered lines: helper functions,
approved zoning PDF, and map PDF builders.
"""

from __future__ import annotations

import base64
import io
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.shared.pdf.base import BrandingInfo


@pytest.fixture
def branding():
    return BrandingInfo(
        nombre_organizacion="Consorcio Test",
        color_primario="#1a5276",
        logo_path=None,
    )


# ---------------------------------------------------------------------------
# Helper function tests (lines 22-58)
# ---------------------------------------------------------------------------


class TestFmtDate:
    def test_none(self):
        from app.shared.pdf.builders import _fmt_date

        assert _fmt_date(None) == "—"

    def test_date_object(self):
        from app.shared.pdf.builders import _fmt_date

        assert _fmt_date(date(2025, 3, 15)) == "15/03/2025"

    def test_string_fallback(self):
        from app.shared.pdf.builders import _fmt_date

        assert _fmt_date("2025-03-15") == "2025-03-15"


class TestFmtDatetime:
    def test_none(self):
        from app.shared.pdf.builders import _fmt_datetime

        assert _fmt_datetime(None) == "—"

    def test_datetime_object(self):
        from app.shared.pdf.builders import _fmt_datetime

        assert _fmt_datetime(datetime(2025, 3, 15, 10, 30)) == "15/03/2025 10:30"

    def test_string_fallback(self):
        from app.shared.pdf.builders import _fmt_datetime

        assert _fmt_datetime("some string") == "some string"


class TestFmtMoney:
    def test_none(self):
        from app.shared.pdf.builders import _fmt_money

        assert _fmt_money(None) == "—"

    def test_integer(self):
        from app.shared.pdf.builders import _fmt_money

        result = _fmt_money(1500)
        assert "1" in result
        assert "500" in result
        assert "$" in result

    def test_decimal(self):
        from app.shared.pdf.builders import _fmt_money

        result = _fmt_money(Decimal("1234.56"))
        assert "$" in result

    def test_non_numeric_fallback(self):
        from app.shared.pdf.builders import _fmt_money

        assert _fmt_money("not a number") == "not a number"


class TestDecodeDataUrlImage:
    def test_none_input(self):
        from app.shared.pdf.builders import _decode_data_url_image

        assert _decode_data_url_image(None) is None

    def test_empty_string(self):
        from app.shared.pdf.builders import _decode_data_url_image

        assert _decode_data_url_image("") is None

    def test_no_comma(self):
        from app.shared.pdf.builders import _decode_data_url_image

        assert _decode_data_url_image("data:image/png;base64") is None

    def test_valid_data_url(self):
        from app.shared.pdf.builders import _decode_data_url_image

        # Create a small valid base64 image
        raw_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        encoded = base64.b64encode(raw_bytes).decode()
        data_url = f"data:image/png;base64,{encoded}"
        result = _decode_data_url_image(data_url)
        assert isinstance(result, io.BytesIO)

    def test_invalid_base64(self):
        from app.shared.pdf.builders import _decode_data_url_image

        result = _decode_data_url_image("data:image/png;base64,!!!invalid!!!")
        assert result is None


# ---------------------------------------------------------------------------
# Color legend table builder (lines 61-129)
# ---------------------------------------------------------------------------


class TestBuildColorLegendTable:
    def test_with_items(self, branding):
        from app.shared.pdf.builders import _build_color_legend_table

        items = [
            {"label": "Zone A", "color": "#ff0000"},
            {"label": "Zone B", "color": "#00ff00"},
        ]
        story = _build_color_legend_table("Test Legend", items, branding)
        assert len(story) >= 2  # title + table

    def test_empty_items(self, branding):
        from app.shared.pdf.builders import _build_color_legend_table

        story = _build_color_legend_table("Empty", [], branding)
        assert len(story) >= 2  # title + "Sin datos" paragraph

    def test_with_extra_value_key(self, branding):
        from app.shared.pdf.builders import _build_color_legend_table

        items = [
            {"label": "Road A", "color": "#888888", "detail": "100 km"},
        ]
        story = _build_color_legend_table(
            "Road Legend", items, branding, extra_value_key="detail"
        )
        assert len(story) >= 2


# ---------------------------------------------------------------------------
# Approved zoning PDF (lines 369-453)
# ---------------------------------------------------------------------------


class TestBuildApprovedZoningPdf:
    def test_with_features(self, branding):
        from app.shared.pdf.builders import build_approved_zoning_pdf

        zoning = SimpleNamespace(
            nombre="Test Zoning",
            version=2,
            cuenca="norte",
            approved_at=datetime(2025, 1, 15, 10, 0),
            notes="Test notes",
            feature_collection={
                "type": "FeatureCollection",
                "features": [
                    {
                        "properties": {
                            "nombre": "Zone A",
                            "superficie_ha": 500.0,
                            "basin_count": 3,
                        }
                    },
                    {
                        "properties": {
                            "nombre": "Zone B",
                            "superficie_ha": 300.0,
                            "basin_count": 2,
                        }
                    },
                ],
            },
        )
        result = build_approved_zoning_pdf(zoning, branding, approved_by_name="Admin User")
        assert isinstance(result, io.BytesIO)
        result.seek(0)
        assert result.read(4) == b"%PDF"

    def test_without_features(self, branding):
        from app.shared.pdf.builders import build_approved_zoning_pdf

        zoning = SimpleNamespace(
            nombre="Empty Zoning",
            version=1,
            cuenca=None,
            approved_at=datetime(2025, 1, 15),
            notes=None,
            feature_collection={"type": "FeatureCollection", "features": []},
        )
        result = build_approved_zoning_pdf(zoning, branding)
        assert isinstance(result, io.BytesIO)

    def test_with_invalid_area_values(self, branding):
        from app.shared.pdf.builders import build_approved_zoning_pdf

        zoning = SimpleNamespace(
            nombre="Bad Data",
            version=1,
            cuenca=None,
            approved_at=datetime(2025, 1, 1),
            notes=None,
            feature_collection={
                "type": "FeatureCollection",
                "features": [
                    {"properties": {"nombre": "X", "superficie_ha": "invalid", "basin_count": "bad"}},
                ],
            },
        )
        result = build_approved_zoning_pdf(zoning, branding)
        assert isinstance(result, io.BytesIO)

    def test_none_feature_collection(self, branding):
        from app.shared.pdf.builders import build_approved_zoning_pdf

        zoning = SimpleNamespace(
            nombre="No FC",
            version=1,
            cuenca=None,
            approved_at=datetime(2025, 1, 1),
            notes=None,
            feature_collection=None,
        )
        result = build_approved_zoning_pdf(zoning, branding)
        assert isinstance(result, io.BytesIO)


# ---------------------------------------------------------------------------
# Map PDF (lines 456-569)
# ---------------------------------------------------------------------------


class TestBuildApprovedZoningMapPdf:
    def test_with_all_elements(self, branding):
        from app.shared.pdf.builders import build_approved_zoning_map_pdf

        # Create a tiny valid PNG for the map image
        import struct
        import zlib

        def _make_tiny_png():
            width, height = 2, 2
            raw_data = b""
            for _ in range(height):
                raw_data += b"\x00" + b"\xff\x00\x00" * width
            compressed = zlib.compress(raw_data)

            def _chunk(chunk_type, data):
                c = chunk_type + data
                crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
                return struct.pack(">I", len(data)) + c + crc

            sig = b"\x89PNG\r\n\x1a\n"
            ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
            return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")

        png_bytes = _make_tiny_png()
        encoded = base64.b64encode(png_bytes).decode()
        data_url = f"data:image/png;base64,{encoded}"

        payload = {
            "title": "Map Report",
            "subtitle": "Sub",
            "mapImageDataUrl": data_url,
            "zoneLegend": [{"label": "Zone A", "color": "#ff0000"}],
            "roadLegend": [{"label": "Road 1", "color": "#888888", "detail": "50km"}],
            "rasterLegends": [
                {"label": "Elevation", "items": [{"label": "Low", "color": "#0000ff"}]}
            ],
            "zoneSummary": [
                {"name": "Zone A", "subcuencas": 3, "areaHa": "500.0", "color": "#ff0000"}
            ],
        }
        result = build_approved_zoning_map_pdf(payload, branding)
        assert isinstance(result, io.BytesIO)
        result.seek(0)
        assert result.read(4) == b"%PDF"

    def test_without_image(self, branding):
        from app.shared.pdf.builders import build_approved_zoning_map_pdf

        payload = {
            "title": "No Image Map",
            "mapImageDataUrl": "",
            "zoneLegend": [],
            "roadLegend": [],
            "rasterLegends": [],
            "zoneSummary": [],
        }
        result = build_approved_zoning_map_pdf(payload, branding)
        assert isinstance(result, io.BytesIO)

    def test_zone_legend_without_summary(self, branding):
        from app.shared.pdf.builders import build_approved_zoning_map_pdf

        payload = {
            "title": "Legend Only",
            "mapImageDataUrl": "",
            "zoneLegend": [{"label": "Z1", "color": "#ff0000"}],
            "roadLegend": [],
            "rasterLegends": [],
            "zoneSummary": [],
        }
        result = build_approved_zoning_map_pdf(payload, branding)
        assert isinstance(result, io.BytesIO)

    def test_road_legend_only(self, branding):
        from app.shared.pdf.builders import build_approved_zoning_map_pdf

        payload = {
            "title": "Roads Only",
            "mapImageDataUrl": "",
            "zoneLegend": [],
            "roadLegend": [{"label": "R1", "color": "#00ff00", "detail": "10km"}],
            "rasterLegends": [],
            "zoneSummary": [],
        }
        result = build_approved_zoning_map_pdf(payload, branding)
        assert isinstance(result, io.BytesIO)

    def test_empty_title(self, branding):
        from app.shared.pdf.builders import build_approved_zoning_map_pdf

        payload = {
            "title": "",
            "mapImageDataUrl": "",
            "zoneLegend": [],
            "roadLegend": [],
            "rasterLegends": [],
            "zoneSummary": [],
        }
        result = build_approved_zoning_map_pdf(payload, branding)
        assert isinstance(result, io.BytesIO)
