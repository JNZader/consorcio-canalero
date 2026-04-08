"""Domain-specific PDF builder functions."""

import base64
import io
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from app.shared.pdf.base import (
    BrandedPDF,
    BrandingInfo,
    build_data_table,
    build_info_table,
    get_pdf_styles,
)


def _fmt_date(d: Any) -> str:
    """Format a date/datetime for display."""
    if d is None:
        return "—"
    if hasattr(d, "strftime"):
        return d.strftime("%d/%m/%Y")
    return str(d)


def _fmt_datetime(d: Any) -> str:
    """Format a datetime for display."""
    if d is None:
        return "—"
    if hasattr(d, "strftime"):
        return d.strftime("%d/%m/%Y %H:%M")
    return str(d)


def _fmt_money(amount: Any) -> str:
    """Format a numeric amount as currency."""
    if amount is None:
        return "—"
    try:
        return f"$ {Decimal(str(amount)):,.2f}"
    except Exception:
        return str(amount)


def _decode_data_url_image(data_url: str) -> io.BytesIO | None:
    """Decode a base64 data URL into an in-memory bytes buffer."""
    if not data_url or "," not in data_url:
        return None
    try:
        _header, encoded = data_url.split(",", 1)
        return io.BytesIO(base64.b64decode(encoded))
    except Exception:
        return None


def _build_color_legend_table(
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


# ── Tramite PDF ───────────────────────────────────────────


def build_tramite_pdf(tramite: Any, branding: BrandingInfo) -> io.BytesIO:
    """Build a PDF ficha for a tramite with seguimiento history."""
    pdf = BrandedPDF(branding)
    styles = get_pdf_styles(branding)
    story: list = []

    # Title
    story.append(Paragraph("Ficha de Tramite", styles["title"]))
    story.append(Spacer(1, 2 * mm))

    # Info table
    info_data = [
        ("Titulo", getattr(tramite, "titulo", "")),
        ("Tipo", getattr(tramite, "tipo", "")),
        ("Estado", getattr(tramite, "estado", "")),
        ("Prioridad", getattr(tramite, "prioridad", "")),
        ("Solicitante", getattr(tramite, "solicitante", "")),
        ("Fecha Ingreso", _fmt_date(getattr(tramite, "fecha_ingreso", None))),
        ("Fecha Resolucion", _fmt_date(getattr(tramite, "fecha_resolucion", None))),
    ]
    story.append(build_info_table(info_data, branding))
    story.append(Spacer(1, 4 * mm))

    # Descripcion
    descripcion = getattr(tramite, "descripcion", None)
    if descripcion:
        story.append(Paragraph("Descripcion", styles["subtitle"]))
        story.append(Paragraph(str(descripcion), styles["body"]))
        story.append(Spacer(1, 3 * mm))

    # Resolucion
    resolucion = getattr(tramite, "resolucion", None)
    if resolucion:
        story.append(Paragraph("Resolucion", styles["subtitle"]))
        story.append(Paragraph(str(resolucion), styles["body"]))
        story.append(Spacer(1, 3 * mm))

    # Seguimiento history
    seguimiento = getattr(tramite, "seguimiento", None) or []
    if seguimiento:
        story.append(Paragraph("Historial de Seguimiento", styles["subtitle"]))
        headers = ["Fecha", "Estado Anterior", "Estado Nuevo", "Comentario"]
        rows = []
        # Show chronological (oldest first)
        for s in reversed(list(seguimiento)):
            rows.append(
                [
                    _fmt_datetime(getattr(s, "created_at", None)),
                    getattr(s, "estado_anterior", ""),
                    getattr(s, "estado_nuevo", ""),
                    getattr(s, "comentario", ""),
                ]
            )
        story.append(build_data_table(headers, rows, branding))

    return pdf.build(story, title=f"Tramite - {getattr(tramite, 'titulo', '')}")


# ── Asset PDF ─────────────────────────────────────────────


def build_asset_pdf(asset: Any, branding: BrandingInfo) -> io.BytesIO:
    """Build a ficha tecnica PDF for an infrastructure asset."""
    pdf = BrandedPDF(branding)
    styles = get_pdf_styles(branding)
    story: list = []

    # Title
    story.append(Paragraph("Ficha Tecnica de Infraestructura", styles["title"]))
    story.append(Spacer(1, 2 * mm))

    # Info table
    lat = getattr(asset, "latitud", None)
    lon = getattr(asset, "longitud", None)
    ubicacion = f"{lat}, {lon}" if lat is not None and lon is not None else "—"

    info_data = [
        ("Nombre", getattr(asset, "nombre", "")),
        ("Tipo", getattr(asset, "tipo", "")),
        ("Estado Actual", getattr(asset, "estado_actual", "")),
        ("Ubicacion (lat/lon)", ubicacion),
        ("Material", getattr(asset, "material", None) or "—"),
        ("Anio Construccion", str(getattr(asset, "anio_construccion", None) or "—")),
        ("Longitud (km)", str(getattr(asset, "longitud_km", None) or "—")),
        ("Responsable", getattr(asset, "responsable", None) or "—"),
    ]
    story.append(build_info_table(info_data, branding))
    story.append(Spacer(1, 4 * mm))

    # Descripcion
    descripcion = getattr(asset, "descripcion", None)
    if descripcion:
        story.append(Paragraph("Descripcion", styles["subtitle"]))
        story.append(Paragraph(str(descripcion), styles["body"]))
        story.append(Spacer(1, 3 * mm))

    # Mantenimiento history
    mantenimientos = getattr(asset, "mantenimientos", None) or []
    if mantenimientos:
        story.append(Paragraph("Historial de Mantenimiento", styles["subtitle"]))
        headers = ["Fecha", "Tipo Trabajo", "Descripcion", "Realizado Por", "Costo"]
        rows = []
        for m in mantenimientos:
            rows.append(
                [
                    _fmt_date(getattr(m, "fecha_trabajo", None)),
                    getattr(m, "tipo_trabajo", ""),
                    getattr(m, "descripcion", ""),
                    getattr(m, "realizado_por", ""),
                    _fmt_money(getattr(m, "costo", None)),
                ]
            )
        story.append(build_data_table(headers, rows, branding))

    return pdf.build(story, title=f"Asset - {getattr(asset, 'nombre', '')}")


# ── Reunion PDF ───────────────────────────────────────────


def build_reunion_pdf(reunion: Any, branding: BrandingInfo) -> io.BytesIO:
    """Build an agenda PDF for a reunion."""
    pdf = BrandedPDF(branding)
    styles = get_pdf_styles(branding)
    story: list = []

    # Title
    story.append(Paragraph("Agenda de Reunion", styles["title"]))
    story.append(Spacer(1, 2 * mm))

    # Info table
    info_data = [
        ("Titulo", getattr(reunion, "titulo", "")),
        ("Fecha", _fmt_datetime(getattr(reunion, "fecha_reunion", None))),
        ("Lugar", getattr(reunion, "lugar", "")),
        ("Tipo", getattr(reunion, "tipo", "")),
        ("Estado", getattr(reunion, "estado", "")),
    ]
    story.append(build_info_table(info_data, branding))
    story.append(Spacer(1, 4 * mm))

    # Descripcion
    descripcion = getattr(reunion, "descripcion", None)
    if descripcion:
        story.append(Paragraph("Descripcion", styles["subtitle"]))
        story.append(Paragraph(str(descripcion), styles["body"]))
        story.append(Spacer(1, 3 * mm))

    # Orden del dia
    orden_del_dia = getattr(reunion, "orden_del_dia_items", None) or []
    if orden_del_dia:
        story.append(Paragraph("Orden del Dia", styles["subtitle"]))
        for i, item in enumerate(orden_del_dia, 1):
            if isinstance(item, str):
                story.append(Paragraph(f"{i}. {item}", styles["body"]))
            elif isinstance(item, dict):
                story.append(
                    Paragraph(
                        f"{i}. {item.get('titulo', item.get('text', str(item)))}",
                        styles["body"],
                    )
                )
        story.append(Spacer(1, 3 * mm))

    # Agenda items
    agenda_items = getattr(reunion, "agenda_items", None) or []
    if agenda_items:
        story.append(Paragraph("Items de Agenda", styles["subtitle"]))
        headers = ["#", "Titulo", "Descripcion", "Completado"]
        rows = []
        for item in agenda_items:
            completado = "Si" if getattr(item, "completado", False) else "No"
            rows.append(
                [
                    str(getattr(item, "orden", "")),
                    getattr(item, "titulo", ""),
                    getattr(item, "descripcion", "") or "—",
                    completado,
                ]
            )
        story.append(build_data_table(headers, rows, branding))

    return pdf.build(story, title=f"Reunion - {getattr(reunion, 'titulo', '')}")


# ── Finanzas PDF ──────────────────────────────────────────


def build_finanzas_pdf(
    summary: dict,
    execution: list[dict],
    year: int,
    branding: BrandingInfo,
) -> io.BytesIO:
    """Build an annual financial summary PDF."""
    pdf = BrandedPDF(branding)
    styles = get_pdf_styles(branding)
    story: list = []

    # Title
    story.append(Paragraph(f"Informe Financiero - Ejercicio {year}", styles["title"]))
    story.append(Spacer(1, 2 * mm))

    # Summary table
    total_ingresos = summary.get("total_ingresos", 0)
    total_gastos = summary.get("total_gastos", 0)
    balance = summary.get("balance", 0)

    info_data = [
        ("Ejercicio", str(year)),
        ("Total Ingresos", _fmt_money(total_ingresos)),
        ("Total Gastos", _fmt_money(total_gastos)),
        ("Balance", _fmt_money(balance)),
    ]
    story.append(build_info_table(info_data, branding))
    story.append(Spacer(1, 6 * mm))

    # Budget execution table
    if execution:
        story.append(Paragraph("Ejecucion Presupuestaria", styles["subtitle"]))
        headers = ["Rubro", "Proyectado", "Real", "Diferencia"]
        rows = []
        for item in execution:
            proyectado = item.get("proyectado", 0)
            real = item.get("real", 0)
            try:
                diff = Decimal(str(real)) - Decimal(str(proyectado))
            except Exception:
                diff = Decimal(0)
            rows.append(
                [
                    item.get("rubro", ""),
                    _fmt_money(proyectado),
                    _fmt_money(real),
                    _fmt_money(diff),
                ]
            )
        story.append(build_data_table(headers, rows, branding))

    return pdf.build(story, title=f"Finanzas - Ejercicio {year}")


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
        ("Fecha de aprobacion", _fmt_datetime(getattr(zoning, "approved_at", None))),
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
    raster_legends = payload.get("rasterLegends") or []
    zone_summary = payload.get("zoneSummary") or []
    if title:
        story.append(Paragraph(title, styles["title"]))
        story.append(Spacer(1, 2 * mm))

    image_buffer = _decode_data_url_image(image_data_url)
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
            _build_color_legend_table("Leyenda de zonas", zone_legend, branding)
        )
        story.append(Spacer(1, 3 * mm))
    elif zone_legend or road_legend or raster_legends:
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
            _build_color_legend_table(
                "Red vial por consorcio caminero",
                road_items,
                branding,
                extra_value_key="detail",
            )
        )
        story.append(Spacer(1, 3 * mm))

    for legend_group in raster_legends:
        group_title = str(legend_group.get("label", "Leyenda raster"))
        items = legend_group.get("items") or []
        story.extend(_build_color_legend_table(group_title, items, branding))
        story.append(Spacer(1, 3 * mm))

    return pdf.build(story, title=title)
