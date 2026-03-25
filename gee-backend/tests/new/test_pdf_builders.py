"""Unit tests for PDF builder functions.

These tests verify that each builder produces valid PDF bytes
without requiring a database connection. Mock objects simulate
domain models.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from app.shared.pdf.base import BrandedPDF, BrandingInfo, get_pdf_styles
from app.shared.pdf.builders import (
    build_asset_pdf,
    build_finanzas_pdf,
    build_reunion_pdf,
    build_tramite_pdf,
)


# ── Mock Data Fixtures ───────────────────────────────────


def _branding() -> BrandingInfo:
    return BrandingInfo(
        nombre_organizacion="Consorcio Canalero 10 de Mayo",
        logo_path=None,
        color_primario="#1976D2",
    )


@dataclass
class MockSeguimiento:
    created_at: datetime = datetime(2026, 1, 15, 10, 30)
    estado_anterior: str = "ingresado"
    estado_nuevo: str = "en_tramite"
    comentario: str = "Se inicio el tramite"
    usuario_id: str = "user-1"


@dataclass
class MockTramite:
    id: str = "t-001"
    titulo: str = "Permiso de obra canal norte"
    tipo: str = "permiso"
    estado: str = "en_tramite"
    prioridad: str = "alta"
    solicitante: str = "Juan Perez"
    descripcion: str = "Solicitud de permiso para obra de ampliacion del canal norte"
    fecha_ingreso: date = date(2026, 1, 10)
    fecha_resolucion: Optional[date] = None
    resolucion: Optional[str] = None
    seguimiento: list = field(default_factory=lambda: [MockSeguimiento()])


@dataclass
class MockMantenimiento:
    fecha_trabajo: date = date(2026, 2, 20)
    tipo_trabajo: str = "Limpieza"
    descripcion: str = "Limpieza general del canal"
    realizado_por: str = "Equipo Tecnico"
    costo: float = 15000.50


@dataclass
class MockAsset:
    id: str = "a-001"
    nombre: str = "Canal Norte Principal"
    tipo: str = "canal"
    estado_actual: str = "bueno"
    latitud: float = -33.75
    longitud: float = -63.85
    material: str = "Hormigon"
    anio_construccion: int = 1998
    longitud_km: float = 12.5
    responsable: str = "Ing. Garcia"
    descripcion: str = "Canal principal de riego zona norte"
    mantenimientos: list = field(default_factory=lambda: [MockMantenimiento()])


@dataclass
class MockAgendaItem:
    orden: int = 1
    titulo: str = "Aprobacion de actas anteriores"
    descripcion: str = "Lectura y aprobacion de acta anterior"
    completado: bool = False


@dataclass
class MockReunion:
    id: str = "r-001"
    titulo: str = "Reunion Ordinaria Marzo 2026"
    fecha_reunion: datetime = datetime(2026, 3, 15, 14, 0)
    lugar: str = "Sede Consorcio"
    tipo: str = "ordinaria"
    estado: str = "planificada"
    descripcion: str = "Reunion mensual ordinaria"
    orden_del_dia_items: list = field(default_factory=lambda: ["Lectura de actas", "Informes"])
    agenda_items: list = field(default_factory=lambda: [MockAgendaItem()])


# ── PDF Validity Helper ──────────────────────────────────


def _assert_valid_pdf(pdf_bytes):
    """Assert that the buffer contains valid PDF data."""
    data = pdf_bytes.read()
    assert len(data) > 0, "PDF buffer is empty"
    assert data[:5] == b"%PDF-", f"Not a valid PDF: starts with {data[:10]!r}"
    # Check for EOF marker
    assert b"%%EOF" in data[-128:], "PDF missing %%EOF marker"


# ── Tests ─────────────────────────────────────────────────


class TestBrandedPDF:
    """Tests for the base BrandedPDF builder."""

    def test_build_produces_valid_pdf(self):
        """BrandedPDF.build() with empty flowables produces valid PDF."""
        from reportlab.platypus import Paragraph

        branding = _branding()
        pdf = BrandedPDF(branding)
        styles = get_pdf_styles(branding)
        story = [Paragraph("Test content", styles["body"])]
        result = pdf.build(story, title="Test")
        _assert_valid_pdf(result)

    def test_build_with_empty_story(self):
        """BrandedPDF.build() with empty story still produces valid PDF."""
        from reportlab.platypus import Spacer

        branding = _branding()
        pdf = BrandedPDF(branding)
        # SimpleDocTemplate needs at least one flowable
        result = pdf.build([Spacer(1, 1)], title="Empty")
        _assert_valid_pdf(result)


class TestTramitePDF:
    """Tests for build_tramite_pdf."""

    def test_produces_valid_pdf(self):
        result = build_tramite_pdf(MockTramite(), _branding())
        _assert_valid_pdf(result)

    def test_with_resolucion(self):
        tramite = MockTramite(
            estado="aprobado",
            fecha_resolucion=date(2026, 2, 1),
            resolucion="Aprobado con condiciones de seguridad",
        )
        result = build_tramite_pdf(tramite, _branding())
        _assert_valid_pdf(result)

    def test_with_empty_seguimiento(self):
        tramite = MockTramite(seguimiento=[])
        result = build_tramite_pdf(tramite, _branding())
        _assert_valid_pdf(result)

    def test_with_multiple_seguimientos(self):
        seguimientos = [
            MockSeguimiento(
                estado_anterior="ingresado",
                estado_nuevo="en_tramite",
                comentario="Inicio",
                created_at=datetime(2026, 1, 10, 9, 0),
            ),
            MockSeguimiento(
                estado_anterior="en_tramite",
                estado_nuevo="aprobado",
                comentario="Aprobado por directorio",
                created_at=datetime(2026, 2, 15, 16, 0),
            ),
        ]
        tramite = MockTramite(seguimiento=seguimientos)
        result = build_tramite_pdf(tramite, _branding())
        _assert_valid_pdf(result)


class TestAssetPDF:
    """Tests for build_asset_pdf."""

    def test_produces_valid_pdf(self):
        result = build_asset_pdf(MockAsset(), _branding())
        _assert_valid_pdf(result)

    def test_with_no_mantenimientos(self):
        asset = MockAsset(mantenimientos=[])
        result = build_asset_pdf(asset, _branding())
        _assert_valid_pdf(result)

    def test_with_optional_fields_missing(self):
        asset = MockAsset(
            material=None,
            anio_construccion=None,
            longitud_km=None,
            responsable=None,
        )
        result = build_asset_pdf(asset, _branding())
        _assert_valid_pdf(result)

    def test_with_zero_cost_maintenance(self):
        mant = MockMantenimiento(costo=0)
        asset = MockAsset(mantenimientos=[mant])
        result = build_asset_pdf(asset, _branding())
        _assert_valid_pdf(result)


class TestReunionPDF:
    """Tests for build_reunion_pdf."""

    def test_produces_valid_pdf(self):
        result = build_reunion_pdf(MockReunion(), _branding())
        _assert_valid_pdf(result)

    def test_with_no_agenda_items(self):
        reunion = MockReunion(agenda_items=[])
        result = build_reunion_pdf(reunion, _branding())
        _assert_valid_pdf(result)

    def test_with_empty_orden_del_dia(self):
        reunion = MockReunion(orden_del_dia_items=[])
        result = build_reunion_pdf(reunion, _branding())
        _assert_valid_pdf(result)

    def test_with_no_descripcion(self):
        reunion = MockReunion(descripcion=None)
        result = build_reunion_pdf(reunion, _branding())
        _assert_valid_pdf(result)

    def test_with_completed_agenda_items(self):
        items = [
            MockAgendaItem(orden=1, titulo="Item 1", completado=True),
            MockAgendaItem(orden=2, titulo="Item 2", completado=False),
        ]
        reunion = MockReunion(agenda_items=items)
        result = build_reunion_pdf(reunion, _branding())
        _assert_valid_pdf(result)

    def test_with_dict_orden_del_dia(self):
        """orden_del_dia_items can contain dicts with titulo key."""
        reunion = MockReunion(
            orden_del_dia_items=[
                {"titulo": "Punto 1"},
                {"titulo": "Punto 2"},
            ]
        )
        result = build_reunion_pdf(reunion, _branding())
        _assert_valid_pdf(result)


class TestFinanzasPDF:
    """Tests for build_finanzas_pdf."""

    def test_produces_valid_pdf(self):
        summary = {
            "total_ingresos": Decimal("500000.00"),
            "total_gastos": Decimal("350000.00"),
            "balance": Decimal("150000.00"),
        }
        execution = [
            {"rubro": "Obras", "proyectado": Decimal("200000"), "real": Decimal("180000")},
            {"rubro": "Personal", "proyectado": Decimal("150000"), "real": Decimal("170000")},
        ]
        result = build_finanzas_pdf(summary, execution, 2026, _branding())
        _assert_valid_pdf(result)

    def test_with_empty_execution(self):
        summary = {
            "total_ingresos": Decimal("100000"),
            "total_gastos": Decimal("80000"),
            "balance": Decimal("20000"),
        }
        result = build_finanzas_pdf(summary, [], 2026, _branding())
        _assert_valid_pdf(result)

    def test_with_zero_values(self):
        summary = {
            "total_ingresos": Decimal("0"),
            "total_gastos": Decimal("0"),
            "balance": Decimal("0"),
        }
        result = build_finanzas_pdf(summary, [], 2025, _branding())
        _assert_valid_pdf(result)

    def test_with_negative_balance(self):
        summary = {
            "total_ingresos": Decimal("100000"),
            "total_gastos": Decimal("200000"),
            "balance": Decimal("-100000"),
        }
        result = build_finanzas_pdf(summary, [], 2026, _branding())
        _assert_valid_pdf(result)


class TestBrandingIntegration:
    """Tests for branding applied to PDFs."""

    def test_custom_color(self):
        branding = BrandingInfo(
            nombre_organizacion="Test Org",
            logo_path=None,
            color_primario="#FF5722",
        )
        result = build_tramite_pdf(MockTramite(), branding)
        _assert_valid_pdf(result)

    def test_invalid_color_fallback(self):
        branding = BrandingInfo(
            nombre_organizacion="Test Org",
            logo_path=None,
            color_primario="invalid",
        )
        result = build_tramite_pdf(MockTramite(), branding)
        _assert_valid_pdf(result)

    def test_nonexistent_logo_path(self):
        branding = BrandingInfo(
            nombre_organizacion="Test Org",
            logo_path="/nonexistent/logo.png",
            color_primario="#1976D2",
        )
        result = build_tramite_pdf(MockTramite(), branding)
        _assert_valid_pdf(result)

    def test_get_branding_from_settings(self):
        """get_branding fetches from SettingsService correctly."""
        mock_db = MagicMock()
        with patch("app.shared.pdf.base.SettingsService") as MockService:
            instance = MockService.return_value
            instance.get_setting.side_effect = lambda db, key, default=None: {
                "general/nombre_organizacion": "Mi Consorcio",
                "branding/logo_url": None,
                "branding/color_primario": "#333333",
            }.get(key, default)

            from app.shared.pdf.base import get_branding

            branding = get_branding(mock_db)
            assert branding.nombre_organizacion == "Mi Consorcio"
            assert branding.color_primario == "#333333"
            assert branding.logo_path is None
