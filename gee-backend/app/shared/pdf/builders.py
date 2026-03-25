"""Domain-specific PDF builder functions."""

import io
from decimal import Decimal
from typing import Any

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

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
            rows.append([
                _fmt_datetime(getattr(s, "created_at", None)),
                getattr(s, "estado_anterior", ""),
                getattr(s, "estado_nuevo", ""),
                getattr(s, "comentario", ""),
            ])
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
            rows.append([
                _fmt_date(getattr(m, "fecha_trabajo", None)),
                getattr(m, "tipo_trabajo", ""),
                getattr(m, "descripcion", ""),
                getattr(m, "realizado_por", ""),
                _fmt_money(getattr(m, "costo", None)),
            ])
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
                    Paragraph(f"{i}. {item.get('titulo', item.get('text', str(item)))}", styles["body"])
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
            rows.append([
                str(getattr(item, "orden", "")),
                getattr(item, "titulo", ""),
                getattr(item, "descripcion", "") or "—",
                completado,
            ])
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
                diff = 0
            rows.append([
                item.get("rubro", ""),
                _fmt_money(proyectado),
                _fmt_money(real),
                _fmt_money(diff),
            ])
        story.append(build_data_table(headers, rows, branding))

    return pdf.build(story, title=f"Finanzas - Ejercicio {year}")
