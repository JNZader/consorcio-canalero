"""Shared PDF generation module using ReportLab Platypus."""

from app.shared.pdf.base import BrandedPDF, BrandingInfo, get_branding
from app.shared.pdf.builders import (
    build_asset_pdf,
    build_finanzas_pdf,
    build_reunion_pdf,
    build_tramite_pdf,
)

__all__ = [
    "BrandedPDF",
    "BrandingInfo",
    "get_branding",
    "build_asset_pdf",
    "build_finanzas_pdf",
    "build_reunion_pdf",
    "build_tramite_pdf",
]
