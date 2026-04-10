"""Corridor routing PDF builders."""

from __future__ import annotations

import io
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
from app.shared.pdf.builders_common import fmt_datetime


def _fmt_coord(value: Any) -> str:
    try:
        return f"{float(value):.6f}"
    except Exception:
        return "—"


def build_corridor_routing_pdf(
    scenario: Any,
    branding: BrandingInfo,
    *,
    approved_by_name: str | None = None,
) -> io.BytesIO:
    """Build a PDF report for a saved corridor routing scenario."""
    pdf = BrandedPDF(branding)
    styles = get_pdf_styles(branding)
    story: list[Any] = []

    request_payload = getattr(scenario, "request_payload", {}) or {}
    result_payload = getattr(scenario, "result_payload", {}) or {}
    summary = (
        result_payload.get("summary", {}) if isinstance(result_payload, dict) else {}
    )
    breakdown = summary.get("cost_breakdown", {}) if isinstance(summary, dict) else {}

    story.append(Paragraph("Escenario de Corridor Routing", styles["title"]))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "Documento de referencia para analisis, comparacion y aprobacion de trazados propuestos.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 3 * mm))

    info_data = [
        ("Nombre", getattr(scenario, "name", "") or "Escenario corredor"),
        ("Modo", str(summary.get("mode", request_payload.get("mode", "network")))),
        (
            "Perfil",
            str(
                getattr(scenario, "profile", "") or request_payload.get("profile", "—")
            ),
        ),
        ("Fecha de guardado", fmt_datetime(getattr(scenario, "created_at", None))),
        ("Aprobado", "Sí" if getattr(scenario, "is_approved", False) else "No"),
        ("Fecha de aprobación", fmt_datetime(getattr(scenario, "approved_at", None))),
        ("Aprobó", approved_by_name or "—"),
    ]
    story.append(build_info_table(info_data, branding))
    story.append(Spacer(1, 4 * mm))

    request_data = [
        ("Origen lon", _fmt_coord(request_payload.get("from_lon"))),
        ("Origen lat", _fmt_coord(request_payload.get("from_lat"))),
        ("Destino lon", _fmt_coord(request_payload.get("to_lon"))),
        ("Destino lat", _fmt_coord(request_payload.get("to_lat"))),
        ("Ancho corredor (m)", str(summary.get("corridor_width_m", "—"))),
        ("Alternativas", str(len(result_payload.get("alternatives", []) or []))),
    ]
    story.append(Paragraph("Parametros", styles["subtitle"]))
    story.append(build_info_table(request_data, branding))
    story.append(Spacer(1, 4 * mm))

    result_data = [
        ("Distancia total (m)", str(summary.get("total_distance_m", "—"))),
        ("Edges", str(summary.get("edges", "—"))),
        ("Penalización", str(summary.get("penalty_factor", "—"))),
    ]
    story.append(Paragraph("Resumen del resultado", styles["subtitle"]))
    story.append(build_info_table(result_data, branding))
    story.append(Spacer(1, 4 * mm))

    if breakdown:
        story.append(Paragraph("Desglose de costo", styles["subtitle"]))
        story.append(
            build_info_table(
                [
                    ("Factor promedio", str(breakdown.get("avg_profile_factor", "—"))),
                    (
                        "Edges afectados",
                        str(breakdown.get("edge_count_with_profile_factor", "—")),
                    ),
                    (
                        "Indice hídrico medio",
                        str(breakdown.get("avg_hydric_index", "—")),
                    ),
                    ("Parcelas cercanas", str(breakdown.get("near_parcels", "—"))),
                    (
                        "Intersecciones parcelarias",
                        str(breakdown.get("parcel_intersections", "—")),
                    ),
                ],
                branding,
            )
        )
        story.append(Spacer(1, 4 * mm))

    alternatives = (
        result_payload.get("alternatives", [])
        if isinstance(result_payload, dict)
        else []
    )
    if alternatives:
        story.append(Paragraph("Alternativas", styles["subtitle"]))
        headers = ["#", "Distancia (m)", "Edges"]
        rows = [
            [
                str(item.get("rank", "—")),
                str(item.get("total_distance_m", "—")),
                str(item.get("edges", "—")),
            ]
            for item in alternatives
        ]
        story.append(build_data_table(headers, rows, branding))
        story.append(Spacer(1, 3 * mm))

    notes = getattr(scenario, "notes", None)
    if notes:
        story.append(Paragraph("Notas", styles["subtitle"]))
        story.append(Paragraph(str(notes), styles["body"]))

    return pdf.build(
        story,
        title=f"Corridor Routing - {getattr(scenario, 'name', 'escenario')}",
    )
