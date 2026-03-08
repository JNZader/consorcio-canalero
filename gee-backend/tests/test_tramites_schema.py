"""Schema validation tests for canonico tramites states."""

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import TramiteCreate, TramiteUpdate, TramiteAvanceCreate


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
