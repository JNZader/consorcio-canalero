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


# ---------------------------------------------------------------------------
# canalLegend — Canales existentes (Pilar Azul) table
# ---------------------------------------------------------------------------


class TestBuildApprovedZoningMapPdfCanalLegend:
    """Symmetric with roadLegend: the map PDF must render a "Canales existentes"
    detail table when `canalLegend` is supplied.

    Imports use the canonical path `app.shared.pdf.builders_zoning` to avoid
    the pre-existing broken imports in this file (the other classes in this
    module import from `app.shared.pdf.builders`, which does NOT re-export the
    zoning builders — those live in `builders_zoning` and are only aggregated
    via the package `__init__.py`).
    """

    def _base_payload(self) -> dict:
        return {
            "title": "Canales test",
            "mapImageDataUrl": "",
            "zoneLegend": [],
            "roadLegend": [],
            "rasterLegends": [],
            "zoneSummary": [],
        }

    def test_without_canal_legend_produces_valid_pdf(self, branding):
        from app.shared.pdf.builders_zoning import build_approved_zoning_map_pdf

        result = build_approved_zoning_map_pdf(self._base_payload(), branding)
        assert isinstance(result, io.BytesIO)
        result.seek(0)
        assert result.read(4) == b"%PDF"

    def test_with_canal_legend_renders_without_error(self, branding):
        """Per-canal payload is now `{label, color, km: float}` — no more `detail`
        string. The builder renders a 3-column table (swatch / label / km) with a
        TOTAL row appended at the bottom."""
        from app.shared.pdf.builders_zoning import build_approved_zoning_map_pdf

        payload = self._base_payload()
        payload["canalLegend"] = [
            {"label": "Canal Norte SMS", "color": "#1D4ED8", "km": 8.2},
            {"label": "Canal Sur", "color": "#3B82F6", "km": 12.5},
        ]
        result = build_approved_zoning_map_pdf(payload, branding)
        assert isinstance(result, io.BytesIO)
        result.seek(0)
        assert result.read(4) == b"%PDF"

    def test_with_canal_legend_produces_larger_pdf_than_without(self, branding):
        """Soft proxy for 'table is rendered': the Canales block adds a title
        Paragraph + a Table flowable (now with swatch + nombre + km + TOTAL row),
        so the byte output MUST be strictly larger than the same payload without
        `canalLegend`. PDF content streams are compressed, so we can't grep the
        title text directly; comparing sizes is the standard pytest-friendly
        check for ReportLab output.
        """
        from app.shared.pdf.builders_zoning import build_approved_zoning_map_pdf

        baseline_payload = self._base_payload()
        with_canales_payload = self._base_payload()
        with_canales_payload["canalLegend"] = [
            {"label": "Canal Norte SMS", "color": "#1D4ED8", "km": 8.2},
            {"label": "Canal Sur", "color": "#3B82F6", "km": 12.5},
        ]

        baseline = build_approved_zoning_map_pdf(baseline_payload, branding).getvalue()
        with_canales = build_approved_zoning_map_pdf(with_canales_payload, branding).getvalue()

        assert len(with_canales) > len(baseline), (
            "Expected the PDF with canalLegend to be larger than the baseline "
            f"(baseline={len(baseline)} bytes, with_canales={len(with_canales)} bytes). "
            "If they match, the canales block was NOT appended to the story."
        )

    def test_empty_canal_legend_matches_no_canal_legend(self, branding):
        """`canalLegend: []` and the absence of the key MUST behave identically
        (defensive — mirrors the roadLegend early-out)."""
        from app.shared.pdf.builders_zoning import build_approved_zoning_map_pdf

        without_key = build_approved_zoning_map_pdf(self._base_payload(), branding).getvalue()
        empty_list_payload = self._base_payload()
        empty_list_payload["canalLegend"] = []
        with_empty = build_approved_zoning_map_pdf(empty_list_payload, branding).getvalue()

        # Byte-for-byte equality is brittle (PDFs embed timestamps via xref),
        # but sizes must match when no optional block was appended.
        assert abs(len(without_key) - len(with_empty)) < 200, (
            f"Expected similar sizes when canalLegend is absent vs empty; "
            f"got without={len(without_key)}, with_empty={len(with_empty)}."
        )


# ---------------------------------------------------------------------------
# build_canales_detail_table — dedicated wide table with km column + TOTAL row
# ---------------------------------------------------------------------------


class TestBuildCanalesDetailTable:
    """The wide 3-column canales table is a NEW helper separate from
    `build_color_legend_table` (which keeps fixed 8/92/28mm widths for roads).

    Contract:
      - 3 columns: [color swatch 8mm | label flex | km narrow ~16mm]
      - Width-aware: receives `available_width_mm` and uses the full content width
      - Includes a TOTAL row at the end with the summed km (computed server-side)
      - Returns a list of flowables: [title Paragraph, Table] (or [title, fallback]
        when items is empty)
    """

    def _branding(self) -> BrandingInfo:
        return BrandingInfo(
            nombre_organizacion="Consorcio Test",
            color_primario="#1a5276",
            logo_path=None,
        )

    def test_returns_title_and_table_flowables(self):
        from reportlab.platypus import Paragraph, Table

        from app.shared.pdf.builders_zoning import build_canales_detail_table

        items = [
            {"label": "Canal Norte SMS", "color": "#1D4ED8", "km": 8.2},
            {"label": "Canal Sur", "color": "#3B82F6", "km": 12.5},
        ]
        story = build_canales_detail_table(
            "Canales existentes (Pilar Azul)",
            items,
            self._branding(),
            available_width_mm=180.0,
        )
        assert len(story) >= 2
        assert isinstance(story[0], Paragraph)
        assert isinstance(story[-1], Table)

    def test_empty_items_returns_placeholder_paragraph(self):
        from app.shared.pdf.builders_zoning import build_canales_detail_table

        story = build_canales_detail_table(
            "Canales existentes (Pilar Azul)",
            [],
            self._branding(),
            available_width_mm=180.0,
        )
        # Title + "Sin datos" paragraph — no Table flowable
        assert len(story) >= 2

    def test_table_has_total_row_with_summed_km(self):
        """The TOTAL row is the LAST data row. Header + N items + 1 TOTAL row."""
        from reportlab.platypus import Table

        from app.shared.pdf.builders_zoning import build_canales_detail_table

        items = [
            {"label": "Canal A", "color": "#1D4ED8", "km": 8.2},
            {"label": "Canal B", "color": "#3B82F6", "km": 12.5},
            {"label": "Canal C", "color": "#60A5FA", "km": 4.3},
        ]
        story = build_canales_detail_table(
            "Canales existentes (Pilar Azul)",
            items,
            self._branding(),
            available_width_mm=180.0,
        )
        # Last flowable is the Table — reach into its _cellvalues.
        table = story[-1]
        assert isinstance(table, Table)
        # pylint: disable=protected-access
        rows = table._cellvalues
        # header + 3 items + TOTAL = 5 rows
        assert len(rows) == 5
        # Last row (TOTAL) — first cell empty (no swatch), second "TOTAL",
        # third row contains the summed km = 25.0 (8.2 + 12.5 + 4.3).
        last_row = rows[-1]
        assert len(last_row) == 3
        # swatch cell is empty (no color on TOTAL row)
        # second cell contains "TOTAL" (may be wrapped in a Paragraph)
        total_label = last_row[1]
        total_label_text = (
            total_label.getPlainText() if hasattr(total_label, "getPlainText") else str(total_label)
        )
        assert "TOTAL" in total_label_text
        # km cell contains the sum — 25.0 rendered as "25.0"
        total_km_cell = last_row[2]
        total_km_text = (
            total_km_cell.getPlainText() if hasattr(total_km_cell, "getPlainText") else str(total_km_cell)
        )
        assert "25.0" in total_km_text

    def test_table_uses_full_available_width(self):
        """The table's total colWidths should equal `available_width_mm` so the
        table stretches across the full content area (NOT the fixed 128mm from
        `build_color_legend_table`)."""
        from reportlab.lib.units import mm
        from reportlab.platypus import Table

        from app.shared.pdf.builders_zoning import build_canales_detail_table

        items = [{"label": "Canal A", "color": "#1D4ED8", "km": 8.2}]
        available = 180.0  # A4 minus 1.5cm margins
        story = build_canales_detail_table(
            "Canales existentes (Pilar Azul)",
            items,
            self._branding(),
            available_width_mm=available,
        )
        table = story[-1]
        assert isinstance(table, Table)
        # Sum of column widths must equal the requested width (± 0.5mm slack).
        # pylint: disable=protected-access
        total_w = sum(table._colWidths)
        expected = available * mm
        assert abs(total_w - expected) < 0.5 * mm

    def test_km_cells_are_numeric_strings(self):
        """Cell displays just the number (no ' km' suffix — header supplies the unit)."""
        from reportlab.platypus import Table

        from app.shared.pdf.builders_zoning import build_canales_detail_table

        items = [
            {"label": "Canal A", "color": "#1D4ED8", "km": 8.2},
            {"label": "Canal B", "color": "#3B82F6", "km": 12.5},
        ]
        story = build_canales_detail_table(
            "Canales existentes (Pilar Azul)",
            items,
            self._branding(),
            available_width_mm=180.0,
        )
        table = story[-1]
        assert isinstance(table, Table)
        # pylint: disable=protected-access
        rows = table._cellvalues
        # header row is rows[0] → item rows start at 1
        first_km_cell = rows[1][2]
        first_km_text = (
            first_km_cell.getPlainText() if hasattr(first_km_cell, "getPlainText") else str(first_km_cell)
        )
        # Must contain the number but NOT the "km" string (unit is in the header).
        assert "8.2" in first_km_text
        assert "km" not in first_km_text.lower()
