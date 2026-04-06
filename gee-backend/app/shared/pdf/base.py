"""Base PDF infrastructure: branding, fonts, header/footer, and document builder."""

import io
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.domains.settings.service import SettingsService

# ── Font Registration ─────────────────────────────────────

_FONT_REGISTERED = False
_FONT_NAME = "Helvetica"  # fallback


def _register_fonts() -> str:
    """Register DejaVuSans for UTF-8 support, fallback to Helvetica."""
    global _FONT_REGISTERED, _FONT_NAME  # noqa: PLW0603
    if _FONT_REGISTERED:
        return _FONT_NAME

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        # Common paths for DejaVuSans on Linux
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ]
        for path in font_paths:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont("DejaVuSans", path))
                _FONT_NAME = "DejaVuSans"
                break

        # Also try bold variant
        bold_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ]
        for path in bold_paths:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", path))
                break
    except Exception:
        _FONT_NAME = "Helvetica"

    _FONT_REGISTERED = True
    return _FONT_NAME


# ── Branding ──────────────────────────────────────────────


@dataclass
class BrandingInfo:
    """Organization branding data for PDF headers."""

    nombre_organizacion: str
    logo_path: Optional[str]
    color_primario: str


def get_branding(db: Session) -> BrandingInfo:
    """Fetch branding info from SettingsService."""
    svc = SettingsService()
    nombre = svc.get_setting(
        db, "general/nombre_organizacion", default="Consorcio Canalero"
    )
    logo_url = svc.get_setting(db, "branding/logo_url", default=None)
    color = svc.get_setting(db, "branding/color_primario", default="#1976D2")

    # Resolve logo path relative to static dir
    logo_path = None
    if logo_url:
        # logo_url is like "/static/logo.png" — resolve to filesystem
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        candidate = os.path.join(base_dir, logo_url.lstrip("/"))
        if os.path.exists(candidate):
            logo_path = candidate

    return BrandingInfo(
        nombre_organizacion=nombre,
        logo_path=logo_path,
        color_primario=color,
    )


# ── Styles ────────────────────────────────────────────────


def _hex_to_color(hex_str: str) -> colors.Color:
    """Convert hex color string to ReportLab Color."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) != 6:
        return colors.HexColor("#1976D2")
    return colors.HexColor(f"#{hex_str}")


def get_pdf_styles(branding: BrandingInfo) -> dict[str, ParagraphStyle]:
    """Build a dictionary of named paragraph styles."""
    font = _register_fonts()
    font_bold = "DejaVuSans-Bold" if font == "DejaVuSans" else "Helvetica-Bold"
    primary = _hex_to_color(branding.color_primario)
    base = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "PDFTitle",
            parent=base["Title"],
            fontName=font_bold,
            fontSize=18,
            textColor=primary,
            spaceAfter=6 * mm,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "PDFSubtitle",
            parent=base["Heading2"],
            fontName=font_bold,
            fontSize=13,
            textColor=primary,
            spaceBefore=4 * mm,
            spaceAfter=3 * mm,
        ),
        "body": ParagraphStyle(
            "PDFBody",
            parent=base["Normal"],
            fontName=font,
            fontSize=10,
            leading=14,
        ),
        "small": ParagraphStyle(
            "PDFSmall",
            parent=base["Normal"],
            fontName=font,
            fontSize=8,
            leading=10,
            textColor=colors.grey,
        ),
        "table_header": ParagraphStyle(
            "PDFTableHeader",
            parent=base["Normal"],
            fontName=font_bold,
            fontSize=9,
            textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "PDFTableCell",
            parent=base["Normal"],
            fontName=font,
            fontSize=9,
            leading=12,
        ),
    }


# ── Table Builder ─────────────────────────────────────────


def build_info_table(
    data: list[tuple[str, str]],
    branding: BrandingInfo,
    col_widths: Optional[tuple[float, float]] = None,
) -> Table:
    """Build a two-column key-value info table."""
    styles = get_pdf_styles(branding)

    rows = []
    for label, value in data:
        rows.append([
            Paragraph(f"<b>{label}</b>", styles["table_cell"]),
            Paragraph(str(value) if value else "—", styles["table_cell"]),
        ])

    if not col_widths:
        col_widths = (5 * cm, 12 * cm)

    table = Table(rows, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.95, 0.95, 0.95)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.8, 0.8, 0.8)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def build_data_table(
    headers: list[str],
    rows: list[list],
    branding: BrandingInfo,
    col_widths: Optional[list[float]] = None,
) -> Table:
    """Build a multi-column data table with header row."""
    styles = get_pdf_styles(branding)
    primary = _hex_to_color(branding.color_primario)

    # Header row
    header_row = [Paragraph(h, styles["table_header"]) for h in headers]
    # Data rows
    data_rows = []
    for row in rows:
        data_rows.append([
            Paragraph(str(cell) if cell is not None else "—", styles["table_cell"])
            for cell in row
        ])

    all_rows = [header_row] + data_rows
    table = Table(all_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        # Header styling
        ("BACKGROUND", (0, 0), (-1, 0), primary),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        # Alternating row colors
        *[
            ("BACKGROUND", (0, i), (-1, i), colors.Color(0.95, 0.95, 0.97))
            for i in range(2, len(all_rows), 2)
        ],
        ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.8, 0.8, 0.8)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


# ── BrandedPDF Document Builder ───────────────────────────


class BrandedPDF:
    """Wraps SimpleDocTemplate with branded header and footer."""

    def __init__(self, branding: BrandingInfo) -> None:
        self.branding = branding
        self.styles = get_pdf_styles(branding)
        self._primary = _hex_to_color(branding.color_primario)
        self._font = _register_fonts()
        self._font_bold = (
            "DejaVuSans-Bold" if self._font == "DejaVuSans" else "Helvetica-Bold"
        )

    def _header_footer(self, canvas, doc):
        """Draw header and footer on each page."""
        canvas.saveState()
        width, height = A4

        # ── Header ──
        # Logo (if available)
        x_text = 2 * cm
        if self.branding.logo_path and os.path.exists(self.branding.logo_path):
            try:
                canvas.drawImage(
                    self.branding.logo_path,
                    1.5 * cm,
                    height - 2 * cm,
                    width=1.2 * cm,
                    height=1.2 * cm,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                x_text = 3.2 * cm
            except Exception:
                pass

        # Org name
        canvas.setFont(self._font_bold, 10)
        canvas.setFillColor(self._primary)
        canvas.drawString(x_text, height - 1.3 * cm, self.branding.nombre_organizacion)

        # Date
        canvas.setFont(self._font, 8)
        canvas.setFillColor(colors.grey)
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        canvas.drawRightString(width - 1.5 * cm, height - 1.3 * cm, fecha)

        # Header line
        canvas.setStrokeColor(self._primary)
        canvas.setLineWidth(1)
        canvas.line(1.5 * cm, height - 2.2 * cm, width - 1.5 * cm, height - 2.2 * cm)

        # ── Footer ──
        canvas.setFont(self._font, 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(
            1.5 * cm,
            1 * cm,
            "Generado por Sistema de Gestion - Consorcio Canalero",
        )
        canvas.drawRightString(
            width - 1.5 * cm,
            1 * cm,
            f"Pagina {doc.page}",
        )

        # Footer line
        canvas.setStrokeColor(colors.Color(0.8, 0.8, 0.8))
        canvas.setLineWidth(0.5)
        canvas.line(1.5 * cm, 1.5 * cm, width - 1.5 * cm, 1.5 * cm)

        canvas.restoreState()

    def build(self, flowables: list, title: str) -> io.BytesIO:
        """Build a PDF document from flowables and return as BytesIO."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            title=title,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
        )
        doc.build(flowables, onFirstPage=self._header_footer, onLaterPages=self._header_footer)
        buffer.seek(0)
        return buffer
