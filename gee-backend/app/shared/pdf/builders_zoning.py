"""Approved zoning PDF builders."""

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import cm, mm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from app.shared.pdf.base import (
    BrandedPDF,
    BrandingInfo,
    build_data_table,
    build_info_table,
    get_pdf_styles,
)
from app.shared.pdf.builders_common import (
    build_color_legend_table,
    decode_data_url_image,
    fmt_datetime,
)

# A4 width (210mm) minus BrandedPDF's left+right margins (1.5cm each) →
# 180mm of usable content width. Kept as a module constant so the canales
# table defaults to the same width the `SimpleDocTemplate` actually renders.
_DEFAULT_CONTENT_WIDTH_MM = (A4[0] - 2 * 1.5 * cm) / mm


def build_canales_detail_table(
    title: str,
    canal_items: list[dict[str, Any]],
    branding: BrandingInfo,
    available_width_mm: float,
) -> list:
    """Wide "Canales existentes (Pilar Azul)" detail table.

    Dedicated helper separate from `build_color_legend_table` — the canales
    block has specific requirements that the roads table does NOT share:

      - 3 columns with fixed-narrow km + flex label (NOT 8/92/28mm fixed)
      - Uses the FULL PDF content width (width-aware via ``available_width_mm``)
      - Appends a TOTAL row with the summed km (computed server-side)
      - No ' km' suffix in data cells — the header supplies the unit

    Column layout: [swatch 8mm | label flex | km 16mm].

    The TOTAL row: empty swatch cell, bold "TOTAL" label, bold right-aligned
    summed km.
    """
    styles = get_pdf_styles(branding)
    story: list = [Paragraph(title, styles["subtitle"])]

    if not canal_items:
        story.append(Paragraph("Sin datos para mostrar.", styles["small"]))
        return story

    swatch_width_mm = 8.0
    km_width_mm = 16.0
    label_width_mm = max(available_width_mm - swatch_width_mm - km_width_mm, 40.0)

    header_cell_style = styles["table_header"]
    body_cell_style = styles["table_cell"]
    # Bold body style for the TOTAL row.
    from reportlab.lib.styles import ParagraphStyle

    bold_font = (
        "DejaVuSans-Bold"
        if body_cell_style.fontName == "DejaVuSans"
        else "Helvetica-Bold"
    )
    bold_cell_style = ParagraphStyle(
        "PDFTableCellBold",
        parent=body_cell_style,
        fontName=bold_font,
    )

    rows: list[list[Any]] = [
        [
            Paragraph("", header_cell_style),
            Paragraph("Canal", header_cell_style),
            Paragraph("km", header_cell_style),
        ]
    ]
    color_commands: list[tuple[Any, ...]] = []

    total_km = 0.0
    for idx, item in enumerate(canal_items, start=1):
        label = str(item.get("label", "—"))
        color = str(item.get("color", "#cccccc"))
        try:
            km_value = float(item.get("km", 0) or 0)
        except (TypeError, ValueError):
            km_value = 0.0
        total_km += km_value

        rows.append(
            [
                "",
                Paragraph(label, body_cell_style),
                Paragraph(f"{km_value:.1f}", body_cell_style),
            ]
        )
        color_commands.extend(
            [
                ("BACKGROUND", (0, idx), (0, idx), colors.HexColor(color)),
                ("TEXTCOLOR", (0, idx), (0, idx), colors.HexColor(color)),
            ]
        )

    total_row_idx = len(rows)
    rows.append(
        [
            "",
            Paragraph("TOTAL", bold_cell_style),
            Paragraph(f"{total_km:.1f}", bold_cell_style),
        ]
    )

    table = Table(
        rows,
        colWidths=[
            swatch_width_mm * mm,
            label_width_mm * mm,
            km_width_mm * mm,
        ],
        repeatRows=1,
    )
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
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.8, 0.8, 0.8)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("WORDWRAP", (0, 0), (-1, -1), "CJK"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                # km column right-aligned (data + TOTAL rows).
                ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
                # TOTAL row emphasis: light-grey band + bold (bold comes from the
                # cell's paragraph style; the top-border visually separates it).
                (
                    "BACKGROUND",
                    (1, total_row_idx),
                    (-1, total_row_idx),
                    colors.Color(0.95, 0.95, 0.95),
                ),
                (
                    "LINEABOVE",
                    (0, total_row_idx),
                    (-1, total_row_idx),
                    0.75,
                    colors.Color(0.6, 0.6, 0.6),
                ),
                *color_commands,
            ]
        )
    )
    story.append(table)
    return story

# ── Zonificacion aprobada PDF ────────────────────────────


def build_approved_zoning_pdf(
    zoning: Any,
    branding: BrandingInfo,
    *,
    approved_by_name: str | None = None,
) -> io.BytesIO:
    """Build a PDF report for an approved zoning version."""
    pdf = BrandedPDF(branding)
    styles = get_pdf_styles(branding)
    story: list = []

    story.append(Paragraph("Informe de Zonificacion Aprobada", styles["title"]))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "Documento de referencia para la zonificacion operativa vigente del consorcio.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 3 * mm))

    info_data = [
        ("Nombre", getattr(zoning, "nombre", "") or "Zonificacion aprobada"),
        ("Version", str(getattr(zoning, "version", "—") or "—")),
        ("Cuenca", getattr(zoning, "cuenca", None) or "General"),
        ("Fecha de aprobacion", fmt_datetime(getattr(zoning, "approved_at", None))),
        ("Aprobo", approved_by_name or "—"),
    ]
    story.append(build_info_table(info_data, branding))
    story.append(Spacer(1, 4 * mm))

    notes = getattr(zoning, "notes", None)
    if notes:
        story.append(Paragraph("Comentario", styles["subtitle"]))
        story.append(Paragraph(str(notes), styles["body"]))
        story.append(Spacer(1, 3 * mm))

    feature_collection = getattr(zoning, "feature_collection", None) or {}
    features = (
        feature_collection.get("features", [])
        if isinstance(feature_collection, dict)
        else []
    )
    if features:
        total_area = 0.0
        total_subcuencas = 0
        for feature in features:
            props = feature.get("properties", {}) if isinstance(feature, dict) else {}
            try:
                total_area += float(props.get("superficie_ha", 0) or 0)
            except Exception:
                pass
            try:
                total_subcuencas += int(props.get("basin_count", 0) or 0)
            except Exception:
                pass

        story.append(Paragraph("Resumen ejecutivo", styles["subtitle"]))
        story.append(
            build_info_table(
                [
                    ("Cantidad de zonas", str(len(features))),
                    ("Total de subcuencas", str(total_subcuencas)),
                    ("Superficie total (ha)", f"{total_area:,.1f}"),
                ],
                branding,
            )
        )
        story.append(Spacer(1, 4 * mm))

        story.append(Paragraph("Resumen de zonas", styles["subtitle"]))
        headers = ["Zona", "Subcuencas", "Superficie (ha)"]
        rows = []
        for feature in features:
            props = feature.get("properties", {}) if isinstance(feature, dict) else {}
            area = props.get("superficie_ha", 0) or 0
            try:
                area_value = float(area)
            except Exception:
                area_value = 0.0
            rows.append(
                [
                    str(props.get("nombre", "Zona")),
                    str(props.get("basin_count", "—")),
                    f"{area_value:,.1f}",
                ]
            )
        rows.append(["TOTAL", "", f"{total_area:,.1f}"])
        story.append(build_data_table(headers, rows, branding))

    return pdf.build(story, title=f"Zonificacion - {getattr(zoning, 'nombre', '')}")


def build_approved_zoning_map_pdf(
    payload: dict[str, Any],
    branding: BrandingInfo,
) -> io.BytesIO:
    """Build a cartographic PDF with a clean map capture and external legends."""
    pdf = BrandedPDF(branding)
    styles = get_pdf_styles(branding)
    story: list = []

    title = str(payload.get("title") or "Mapa del Consorcio")
    image_data_url = str(payload.get("mapImageDataUrl") or "")
    zone_legend = payload.get("zoneLegend") or []
    road_legend = payload.get("roadLegend") or []
    canal_legend = payload.get("canalLegend") or []
    raster_legends = payload.get("rasterLegends") or []
    zone_summary = payload.get("zoneSummary") or []
    if title:
        story.append(Paragraph(title, styles["title"]))
        story.append(Spacer(1, 2 * mm))

    image_buffer = decode_data_url_image(image_data_url)
    if image_buffer is not None:
        image_reader = ImageReader(image_buffer)
        img_width, img_height = image_reader.getSize()
        max_width = 170 * mm
        max_height = 100 * mm
        scale = min(max_width / img_width, max_height / img_height)
        image_buffer.seek(0)
        story.append(
            Image(
                image_buffer,
                width=img_width * scale,
                height=img_height * scale,
            )
        )
        story.append(Spacer(1, 3 * mm))

    if zone_summary:
        story.append(Paragraph("Resumen de zonas", styles["subtitle"]))
        rows: list[list[Any]] = [["", "Zona", "Subcuencas", "Superficie (ha)"]]
        color_commands: list[tuple[Any, ...]] = []
        for idx, item in enumerate(zone_summary, start=1):
            color = str(item.get("color", "#cccccc"))
            rows.append(
                [
                    "",
                    str(item.get("name", "Zona")),
                    str(item.get("subcuencas", "—")),
                    str(item.get("areaHa", "—")),
                ]
            )
            color_commands.extend(
                [
                    ("BACKGROUND", (0, idx), (0, idx), colors.HexColor(color)),
                    ("TEXTCOLOR", (0, idx), (0, idx), colors.HexColor(color)),
                ]
            )

        zone_table = Table(
            rows, colWidths=[8 * mm, 82 * mm, 35 * mm, 35 * mm], repeatRows=1
        )
        zone_table.setStyle(
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
                    ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
                    *color_commands,
                ]
            )
        )
        story.append(zone_table)
        story.append(Spacer(1, 3 * mm))

    if zone_legend and not zone_summary:
        story.append(Paragraph("Leyendas", styles["subtitle"]))
        story.extend(
            build_color_legend_table("Leyenda de zonas", zone_legend, branding)
        )
        story.append(Spacer(1, 3 * mm))
    elif zone_legend or road_legend or canal_legend or raster_legends:
        story.append(Paragraph("Leyendas", styles["subtitle"]))

    if road_legend:
        road_items = [
            {
                "label": str(item.get("label", "—")),
                "color": str(item.get("color", "#888888")),
                "detail": str(item.get("detail", "—")),
            }
            for item in road_legend
        ]
        story.extend(
            build_color_legend_table(
                "Red vial por consorcio caminero",
                road_items,
                branding,
                extra_value_key="detail",
            )
        )
        story.append(Spacer(1, 3 * mm))

    if canal_legend:
        canal_items = []
        for item in canal_legend:
            try:
                km_value = float(item.get("km", 0) or 0)
            except (TypeError, ValueError):
                km_value = 0.0
            canal_items.append(
                {
                    "label": str(item.get("label", "—")),
                    "color": str(item.get("color", "#1971c2")),
                    "km": km_value,
                }
            )
        story.extend(
            build_canales_detail_table(
                "Canales existentes (Pilar Azul)",
                canal_items,
                branding,
                available_width_mm=_DEFAULT_CONTENT_WIDTH_MM,
            )
        )
        story.append(Spacer(1, 3 * mm))

    for legend_group in raster_legends:
        group_title = str(legend_group.get("label", "Leyenda raster"))
        items = legend_group.get("items") or []
        story.extend(build_color_legend_table(group_title, items, branding))
        story.append(Spacer(1, 3 * mm))

    return pdf.build(story, title=title)
