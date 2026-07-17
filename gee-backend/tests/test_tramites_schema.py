"""Pure Pydantic schema tests for the tramites domain (mutation target).

These run with ZERO database, zero FastAPI app boot — they exist to
feed the cosmic-ray mutation gate which invokes the suite hundreds of
times. A slow test here adds minutes to every gate run.

Coverage focus: every Field constraint (min_length / max_length /
default / required) gets at least one positive and one negative
assertion, so a mutation that flips ``min_length=5`` to
``min_length=4`` (or ``...`` to ``""``) is detected.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.domains.tramites.schemas import (
    SeguimientoCreate,
    SeguimientoResponse,
    TramiteCreate,
    TramiteCreateResponse,
    TramiteListResponse,
    TramiteResponse,
    TramiteUpdate,
)


# ---------------------------------------------------------------------------
# TramiteCreate — field bounds
# ---------------------------------------------------------------------------


class TestTramiteCreateRequired:
    def test_all_required_fields_present(self):
        t = TramiteCreate(
            tipo="obra",
            titulo="Obra de canal cuenca sur",
            descripcion="Excavar 200m del canal en cuenca sur, sector norte.",
            solicitante="Vecino del Lote 12",
        )
        assert t.tipo == "obra"
        assert t.titulo == "Obra de canal cuenca sur"
        assert t.solicitante == "Vecino del Lote 12"
        assert t.prioridad == "media"  # default
        assert t.fecha_ingreso is None  # default

    def test_rejects_missing_tipo(self):
        with pytest.raises(ValidationError) as exc:
            TramiteCreate(
                titulo="Algo válido aquí",
                descripcion="Una descripción aceptable.",
                solicitante="Solicitante",
            )  # type: ignore[call-arg]
        assert "tipo" in str(exc.value)

    def test_rejects_missing_titulo(self):
        with pytest.raises(ValidationError):
            TramiteCreate(
                tipo="obra",
                descripcion="Una descripción aceptable.",
                solicitante="Solicitante",
            )  # type: ignore[call-arg]

    def test_rejects_missing_descripcion(self):
        with pytest.raises(ValidationError):
            TramiteCreate(tipo="obra", titulo="Titulo OK x 5", solicitante="Solicitante")  # type: ignore[call-arg]

    def test_rejects_missing_solicitante(self):
        with pytest.raises(ValidationError):
            TramiteCreate(
                tipo="obra",
                titulo="Titulo OK x 5",
                descripcion="Una descripción aceptable.",
            )  # type: ignore[call-arg]


class TestTramiteCreateTituloBounds:
    """``titulo`` ∈ [5, 200] chars."""

    def test_min_length_5_just_passes(self):
        TramiteCreate(
            tipo="obra",
            titulo="ABCDE",
            descripcion="Descripcion ok longer than 10",
            solicitante="XY",
        )

    def test_min_length_4_fails(self):
        """Boundary mutation guard: shrinking ``min_length`` from 5 to 4
        would let this through."""
        with pytest.raises(ValidationError):
            TramiteCreate(
                tipo="obra",
                titulo="ABCD",
                descripcion="Descripcion ok longer than 10",
                solicitante="XY",
            )

    def test_max_length_200_just_passes(self):
        TramiteCreate(
            tipo="obra",
            titulo="A" * 200,
            descripcion="Descripcion ok longer than 10",
            solicitante="XY",
        )

    def test_max_length_201_fails(self):
        with pytest.raises(ValidationError):
            TramiteCreate(
                tipo="obra",
                titulo="A" * 201,
                descripcion="Descripcion ok longer than 10",
                solicitante="XY",
            )


class TestTramiteCreateDescripcionBounds:
    """``descripcion`` ∈ [10, 5000] chars."""

    def test_min_length_10_passes(self):
        TramiteCreate(
            tipo="obra",
            titulo="Titulo ok",
            descripcion="A" * 10,
            solicitante="XY",
        )

    def test_min_length_9_fails(self):
        with pytest.raises(ValidationError):
            TramiteCreate(
                tipo="obra",
                titulo="Titulo ok",
                descripcion="A" * 9,
                solicitante="XY",
            )

    def test_max_length_5000_passes(self):
        TramiteCreate(
            tipo="obra",
            titulo="Titulo ok",
            descripcion="A" * 5000,
            solicitante="XY",
        )

    def test_max_length_5001_fails(self):
        with pytest.raises(ValidationError):
            TramiteCreate(
                tipo="obra",
                titulo="Titulo ok",
                descripcion="A" * 5001,
                solicitante="XY",
            )


class TestTramiteCreateSolicitanteBounds:
    """``solicitante`` ∈ [2, 200] chars."""

    def test_min_length_2_passes(self):
        TramiteCreate(
            tipo="obra",
            titulo="Titulo ok",
            descripcion="Descripcion ok aquí",
            solicitante="XY",
        )

    def test_min_length_1_fails(self):
        with pytest.raises(ValidationError):
            TramiteCreate(
                tipo="obra",
                titulo="Titulo ok",
                descripcion="Descripcion ok aquí",
                solicitante="X",
            )

    def test_max_length_200_passes(self):
        TramiteCreate(
            tipo="obra",
            titulo="Titulo ok",
            descripcion="Descripcion ok aquí",
            solicitante="X" * 200,
        )

    def test_max_length_201_fails(self):
        with pytest.raises(ValidationError):
            TramiteCreate(
                tipo="obra",
                titulo="Titulo ok",
                descripcion="Descripcion ok aquí",
                solicitante="X" * 201,
            )


class TestTramiteCreateDefaults:
    def test_prioridad_defaults_to_media(self):
        t = TramiteCreate(
            tipo="obra",
            titulo="Titulo ok",
            descripcion="Descripcion ok aquí",
            solicitante="XY",
        )
        assert t.prioridad == "media"

    def test_prioridad_custom(self):
        t = TramiteCreate(
            tipo="obra",
            titulo="Titulo ok",
            descripcion="Descripcion ok aquí",
            solicitante="XY",
            prioridad="urgente",
        )
        assert t.prioridad == "urgente"

    def test_fecha_ingreso_defaults_to_none(self):
        t = TramiteCreate(
            tipo="obra",
            titulo="Titulo ok",
            descripcion="Descripcion ok aquí",
            solicitante="XY",
        )
        assert t.fecha_ingreso is None

    def test_fecha_ingreso_explicit(self):
        t = TramiteCreate(
            tipo="obra",
            titulo="Titulo ok",
            descripcion="Descripcion ok aquí",
            solicitante="XY",
            fecha_ingreso=date(2026, 5, 19),
        )
        assert t.fecha_ingreso == date(2026, 5, 19)


# ---------------------------------------------------------------------------
# TramiteUpdate — all fields optional
# ---------------------------------------------------------------------------


class TestTramiteUpdate:
    def test_all_fields_optional(self):
        u = TramiteUpdate()
        assert u.estado is None
        assert u.resolucion is None
        assert u.prioridad is None
        assert u.comentario is None

    def test_partial_update(self):
        u = TramiteUpdate(estado="en_proceso")
        assert u.estado == "en_proceso"
        assert u.resolucion is None

    def test_full_update(self):
        u = TramiteUpdate(
            estado="resuelto",
            resolucion="Obra completada según especificación.",
            prioridad="baja",
            comentario="Cerrado por el operador.",
        )
        assert u.estado == "resuelto"
        assert u.resolucion == "Obra completada según especificación."
        assert u.prioridad == "baja"
        assert u.comentario == "Cerrado por el operador."


# ---------------------------------------------------------------------------
# SeguimientoCreate — comentario ∈ [5, 5000]
# ---------------------------------------------------------------------------


class TestSeguimientoCreate:
    def test_min_length_5_passes(self):
        SeguimientoCreate(comentario="12345")

    def test_min_length_4_fails(self):
        with pytest.raises(ValidationError):
            SeguimientoCreate(comentario="1234")

    def test_max_length_5000_passes(self):
        SeguimientoCreate(comentario="A" * 5000)

    def test_max_length_5001_fails(self):
        with pytest.raises(ValidationError):
            SeguimientoCreate(comentario="A" * 5001)

    def test_required_field(self):
        with pytest.raises(ValidationError):
            SeguimientoCreate()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Response schemas — ``from_attributes=True`` lets us validate from
# objects with the right attribute names. We use SimpleNamespace stubs
# so the test stays DB-free.
# ---------------------------------------------------------------------------


class _Stub:
    """Tiny attribute bag — mimics a SQLAlchemy row object."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class TestSeguimientoResponse:
    def test_from_attributes(self):
        row = _Stub(
            id=uuid.uuid4(),
            tramite_id=uuid.uuid4(),
            estado_anterior="pendiente",
            estado_nuevo="en_proceso",
            comentario="Asignado al operador",
            usuario_id=uuid.uuid4(),
            created_at=datetime.now(tz=timezone.utc),
        )
        seg = SeguimientoResponse.model_validate(row)
        assert seg.estado_anterior == "pendiente"
        assert seg.estado_nuevo == "en_proceso"


class TestTramiteResponseDefaults:
    def test_seguimiento_defaults_to_empty_list(self):
        row = _Stub(
            id=uuid.uuid4(),
            tipo="obra",
            titulo="Obra",
            descripcion="Descripción de la obra",
            solicitante="Solicitante",
            estado="pendiente",
            prioridad="media",
            fecha_ingreso=date(2026, 5, 19),
            fecha_resolucion=None,
            resolucion=None,
            usuario_id=uuid.uuid4(),
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        # Note: ``_Stub`` has no ``seguimiento`` attribute — the default
        # must kick in.
        t = TramiteResponse.model_validate(row)
        assert t.seguimiento == []


class TestTramiteListResponseShape:
    def test_no_descripcion_no_resolucion(self):
        """The list response omits heavy fields; if a future mutation
        adds them this test still passes (Pydantic ignores extras by
        default), but the OpenAPI surface is what we lock down."""
        fields = set(TramiteListResponse.model_fields.keys())
        assert "descripcion" not in fields
        assert "resolucion" not in fields
        assert "seguimiento" not in fields


class TestTramiteCreateResponse:
    def test_required_fields(self):
        r = TramiteCreateResponse(
            id=uuid.uuid4(),
            message="OK",
            estado="pendiente",
        )
        assert r.message == "OK"
        assert r.estado == "pendiente"
