"""Shared PDF generation module using ReportLab Platypus."""

from app.shared.pdf.base import BrandedPDF, BrandingInfo, get_branding
from app.shared.pdf.builders import (
    build_approved_zoning_map_pdf,
    build_approved_zoning_pdf,
    build_asset_pdf,
    build_finanzas_pdf,
    build_reunion_pdf,
    build_tramite_pdf,
)

__all__ = [
    "BrandedPDF",
    "BrandingInfo",
    "get_branding",
    "build_approved_zoning_map_pdf",
    "build_approved_zoning_pdf",
    "build_asset_pdf",
    "build_finanzas_pdf",
    "build_reunion_pdf",
    "build_tramite_pdf",
]
