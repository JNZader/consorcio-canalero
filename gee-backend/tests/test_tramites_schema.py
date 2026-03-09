"""Schema validation tests for canonico tramites states."""

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import (
    TramiteCreate,
    TramiteUpdate,
    TramiteAvanceCreate,
    ReunionCreate,
    ReunionUpdate,
)


def test_tramite_create_accepts_canonical_state():
    model = TramiteCreate(titulo="Alta de canal", tipo="obra", estado="pendiente")

    assert model.estado == "pendiente"


def test_tramite_create_rejects_non_canonical_state():
    with pytest.raises(ValidationError):
        TramiteCreate(titulo="Alta de canal", tipo="obra", estado="iniciado")


def test_tramite_update_rejects_non_canonical_state():
    with pytest.raises(ValidationError):
        TramiteUpdate(estado="detenido")


def test_tramite_avance_rejects_non_canonical_state():
    with pytest.raises(ValidationError):
        TramiteAvanceCreate(
            tramite_id="9d5ed678-fe57-4f88-b30f-9df72f3f27d2",
            descripcion="Se presenta nota",
            nuevo_estado="finalizado",
        )


def test_reunion_create_accepts_orden_del_dia_items():
    model = ReunionCreate(
        titulo="Reunion mensual",
        fecha_reunion="2026-03-09T10:00:00Z",
        descripcion="Temas generales",
        orden_del_dia_items=["  Balance  ", "Obras", "   "],
    )

    assert model.orden_del_dia_items == ["Balance", "Obras"]


def test_reunion_create_requires_non_empty_checklist():
    with pytest.raises(ValidationError):
        ReunionCreate(
            titulo="Reunion mensual",
            fecha_reunion="2026-03-09T10:00:00Z",
            orden_del_dia_items=["", "   "],
        )


def test_reunion_update_accepts_partial_orden_del_dia_items():
    model = ReunionUpdate(orden_del_dia_items=[" Revision de mantenimiento ", ""])

    assert model.orden_del_dia_items == ["Revision de mantenimiento"]
