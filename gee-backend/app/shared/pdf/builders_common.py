"""Shared PDF builder helpers."""

import base64
import io
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle

from app.shared.pdf.base import BrandingInfo, get_pdf_styles


def fmt_date(d: Any) -> str:
    """Format a date/datetime for display."""
    if d is None:
        return "—"
    if hasattr(d, "strftime"):
        return d.strftime("%d/%m/%Y")
    return str(d)


def fmt_datetime(d: Any) -> str:
    """Format a datetime for display."""
    if d is None:
        return "—"
    if hasattr(d, "strftime"):
        return d.strftime("%d/%m/%Y %H:%M")
    return str(d)


def fmt_money(amount: Any) -> str:
    """Format a numeric amount as currency."""
    if amount is None:
        return "—"
    try:
        return f"$ {Decimal(str(amount)):,.2f}"
    except Exception:
        return str(amount)


def decode_data_url_image(data_url: str) -> io.BytesIO | None:
    """Decode a base64 data URL into an in-memory bytes buffer."""
    if not data_url or "," not in data_url:
        return None
    try:
        _header, encoded = data_url.split(",", 1)
        return io.BytesIO(base64.b64decode(encoded))
    except Exception:
        return None


def build_color_legend_table(
    title: str,
    items: list[dict[str, Any]],
    branding: BrandingInfo,
    *,
    extra_value_key: str | None = None,
) -> list:
    """Build a legend block with a title and a simple color table."""
    styles = get_pdf_styles(branding)
    story: list = [Paragraph(title, styles["subtitle"])]

    if not items:
        story.append(Paragraph("Sin datos para mostrar.", styles["small"]))
        return story

    headers = ["", "Elemento"]
    if extra_value_key:
        headers.append("Detalle")

    rows: list[list[Any]] = [headers]
    color_commands: list[tuple[Any, ...]] = []

    for idx, item in enumerate(items, start=1):
        label = str(item.get("label", "—"))
        color = str(item.get("color", "#cccccc"))
        row: list[Any] = ["", label]
        if extra_value_key:
            row.append(str(item.get(extra_value_key, "—")))
        rows.append(row)
        color_commands.extend(
            [
                ("BACKGROUND", (0, idx), (0, idx), colors.HexColor(color)),
                ("TEXTCOLOR", (0, idx), (0, idx), colors.HexColor(color)),
            ]
        )

    col_widths = [8 * mm, 92 * mm]
    if extra_value_key:
        col_widths.append(28 * mm)

    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor(branding.color_primario),
                ),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.8, 0.8, 0.8)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("WORDWRAP", (0, 0), (-1, -1), "CJK"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                *color_commands,
            ]
        )
    )
    if extra_value_key:
        table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
    story.append(table)
    return story
