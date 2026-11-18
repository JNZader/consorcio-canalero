"""PR 0: los PDF salen en castellano correcto — tildes, coma decimal, folio.

Extracción real de texto con pypdf sobre PDFs construidos con los builders
de producción (DejaVuSans subset incluido — zlib plano no alcanza).
Auditado 2026-11-18: el pie decía "Pagina {n}" sin tilde y sin total, y las
tablas de zonificación usaban ":,.1f" inglés.
"""

from __future__ import annotations

import io
from datetime import datetime
from types import SimpleNamespace

import pytest

pypdf = pytest.importorskip("pypdf")

from app.shared.pdf.base import BrandedPDF, BrandingInfo  # noqa: E402
from app.shared.pdf.builders_zoning import build_approved_zoning_pdf  # noqa: E402


def _branding() -> BrandingInfo:
    return BrandingInfo(
        nombre_organizacion="Consorcio Canalero 10 de Mayo",
        logo_path=None,
        color_primario="#0b7285",
    )


def _texto(pdf: io.BytesIO) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf.getvalue()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _zoning_con_superficies(*superficies: float) -> SimpleNamespace:
    return SimpleNamespace(
        nombre="Test Zoning",
        version=2,
        cuenca="norte",
        approved_at=datetime(2025, 1, 15, 10, 0),
        notes=None,
        feature_collection={
            "type": "FeatureCollection",
            "features": [
                {"properties": {"nombre": f"Zona {i}", "superficie_ha": s, "basin_count": 1}}
                for i, s in enumerate(superficies, start=1)
            ],
        },
    )


def test_el_folio_dice_pagina_x_de_y_en_todas_las_hojas() -> None:
    from reportlab.platypus import Paragraph

    from app.shared.pdf.base import get_pdf_styles

    branding = _branding()
    styles = get_pdf_styles(branding)
    pdf = BrandedPDF(branding)
    # Story largo: fuerza varias páginas.
    story = [Paragraph(f"Párrafo de relleno número {i} " * 8, styles["body"]) for i in range(80)]
    buffer = pdf.build(story, "Test de folio")

    reader = pypdf.PdfReader(io.BytesIO(buffer.getvalue()))
    total = len(reader.pages)
    assert total >= 2, "el story de relleno tiene que forzar varias hojas"
    first = reader.pages[0].extract_text() or ""
    last = reader.pages[-1].extract_text() or ""
    assert f"Página 1 de {total}" in first
    assert f"Página {total} de {total}" in last
    # El folio viejo, sin tilde y sin total, no puede volver a aparecer.
    todo = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Pagina " not in todo


def test_zonificacion_lleva_tilde_en_titulos() -> None:
    buffer = build_approved_zoning_pdf(_zoning_con_superficies(100.0), _branding())
    texto = _texto(buffer)
    assert "Zonificación" in texto
    assert "Zonificacion" not in texto


def test_superficies_con_coma_decimal_y_punto_de_miles() -> None:
    buffer = build_approved_zoning_pdf(_zoning_con_superficies(5000.25, 300.5), _branding())
    texto = _texto(buffer)
    # Total 5300.75 → es-AR "5.300,8"; inglés habría sido "5,300.8".
    assert "5.300,8" in texto
    assert "5,300.8" not in texto
    # Ni un número con punto decimal inglés en la tabla de superficies.
    assert "300.5" not in texto


def test_pie_de_organizacion_con_tilde() -> None:
    buffer = build_approved_zoning_pdf(_zoning_con_superficies(100.0), _branding())
    texto = _texto(buffer)
    assert "Sistema de Gestión" in texto
    assert "Sistema de Gestion" not in texto
