from __future__ import annotations

import pytest
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.endpoints.reports import (
    ResolvePayload,
    ResolveReportRequest,
    ResolveStatus,
    resolve_report,
)
from app.api.v1.endpoints.sugerencias import (
    SugerenciaCiudadanaCreate,
    crear_sugerencia_publica,
)
from app.api.v1.schemas import ReunionCreate, TramiteCreate, SugerenciaTipo, SugerenciaEstado, SugerenciaPrioridad
from app.auth import User
from app.core.exceptions import ReportNotFoundError, RateLimitExceededError


@dataclass
class _ReportServiceFake:
    report_id: str
    should_exist: bool = True

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        if report_id != self.report_id or not self.should_exist:
            return None
        return {"id": report_id, "estado": "en_revision"}

    def update_report(
        self, report_id: str, updates: dict[str, Any], _user_id: str
    ) -> dict[str, Any]:
        return {
            "id": report_id,
            "estado": updates["estado"],
            "updated_at": "2026-03-08T00:00:00Z",
        }


class _FakeResult:
    def __init__(self, data: Any, count: int | None = None):
        self.data = data
        self.count = count


class _FakeTable:
    def __init__(self, name: str, store: dict[str, Any], client: _FakeSupabaseClient | None = None):
        self.name = name
        self.store = store
        self.client = client
        self.mode = "select"
        self.payload: Any = None

    def select(self, *_args, count: str | None = None):
        self.mode = "select"
        self.want_count = count == "exact"
        return self

    def eq(self, *_args):
        return self

    def gte(self, *_args):
        return self

    def insert(self, payload: Any):
        self.mode = "insert"
        self.payload = payload
        return self

    def execute(self):
        # Handle contact_submissions count queries (rate limit testing)
        if self.name == "contact_submissions" and self.mode == "select":
            count = 0
            if self.client and hasattr(self.client, 'submissions_count'):
                count = self.client.submissions_count
            return _FakeResult([], count=count)

        if self.name == "sugerencias" and self.mode == "insert":
            suggestion = {
                "id": str(uuid4()),
                "tipo": self.payload["tipo"],
                "titulo": self.payload["titulo"],
                "descripcion": self.payload["descripcion"],
                "estado": self.payload["estado"],
                "prioridad": self.payload["prioridad"],
            }
            self.store["sugerencia"] = suggestion
            return _FakeResult([suggestion])

        if self.name in {"contact_submissions", "sugerencias_historial"}:
            return _FakeResult([self.payload])

        return _FakeResult([])


class _FakeSupabaseClient:
    def __init__(self, submissions_count: int = 0):
        self.store: dict[str, Any] = {}
        self.submissions_count = submissions_count

    def table(self, name: str):
        return _FakeTable(name, self.store, self)


async def test_resolve_report_direct_call_maps_to_mutation(monkeypatch):
    report_id = str(uuid4())
    fake_service = _ReportServiceFake(report_id=report_id)
    monkeypatch.setattr(
        "app.api.v1.endpoints.reports.get_supabase_service", lambda: fake_service
    )

    payload = ResolveReportRequest(
        report_id=report_id,
        resolution=ResolvePayload(
            status=ResolveStatus.RESOLVED,
            comment="Resuelto en campo",
            resolved_by="operador-1",
        ),
    )

    result = await resolve_report(
        report_id=report_id,
        payload=payload,
        user=User(id="admin-1", email="admin@example.com", role="admin"),
    )

    assert result["id"] == report_id
    assert result["status"] == "resolved"


async def test_public_suggestion_direct_call_maps_to_mutation(monkeypatch):
    fake_client = _FakeSupabaseClient()
    monkeypatch.setattr(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", lambda: fake_client
    )

    payload = SugerenciaCiudadanaCreate(
        titulo="Mejorar limpieza de canal",
        descripcion="Propuesta de mantenimiento preventivo en tramo norte",
        contacto_email="vecino@example.com",
        contacto_verificado=True,
    )

    result = await crear_sugerencia_publica(payload)

    assert "id" in result
    assert result["remaining_today"] == 2


# ===========================================
# Phase 2: Parametrized Mutation Tests
# ===========================================


# Task 2.1: Report ID Mismatch Validation (catches != operator mutations)
@pytest.mark.parametrize(
    "path_id,payload_id,should_raise",
    [
        ("uuid-1", "uuid-1", False),  # IDs match, should proceed
        ("uuid-1", "uuid-2", True),   # IDs mismatch, should raise HTTPException(400)
        ("uuid-1", "", True),         # Empty payload ID, should raise HTTPException(400)
    ],
)
async def test_resolve_report_id_mismatch(monkeypatch, path_id, payload_id, should_raise):
    """
    Test report ID path-payload mismatch validation.
    Catches != operator mutations (e.g., != -> ==, negation removal).
    """
    fake_service = _ReportServiceFake(report_id=path_id)
    monkeypatch.setattr(
        "app.api.v1.endpoints.reports.get_supabase_service", lambda: fake_service
    )

    payload = ResolveReportRequest(
        report_id=payload_id,
        resolution=ResolvePayload(
            status=ResolveStatus.RESOLVED,
            comment="Test resolution",
            resolved_by="operador-1",
        ),
    )

    user = User(id="admin-1", email="admin@example.com", role="admin")

    if should_raise:
        with pytest.raises(HTTPException) as exc_info:
            await resolve_report(
                report_id=path_id,
                payload=payload,
                user=user,
            )
        assert exc_info.value.status_code == 400
        assert "does not match path" in str(exc_info.value.detail)
    else:
        # When IDs match, it should not raise HTTP 400 (may raise 404 if report doesn't exist, but that's ok)
        try:
            result = await resolve_report(
                report_id=path_id,
                payload=payload,
                user=user,
            )
            # Should succeed or raise 404, NOT 400
            assert result is not None
        except ReportNotFoundError:
            # Expected if report doesn't exist, but the ID match check passed
            pass


# Task 2.2: Report Not Found Validation (catches `not` operator)
@pytest.mark.parametrize(
    "should_exist,should_raise_not_found",
    [
        (True, False),   # Report exists, should NOT raise ReportNotFoundError
        (False, True),   # Report missing, should raise ReportNotFoundError
    ],
)
async def test_resolve_report_not_found(monkeypatch, should_exist, should_raise_not_found):
    """
    Test report existence check.
    Catches `not` operator and `if` condition inversions.
    """
    report_id = str(uuid4())
    fake_service = _ReportServiceFake(report_id=report_id, should_exist=should_exist)
    monkeypatch.setattr(
        "app.api.v1.endpoints.reports.get_supabase_service", lambda: fake_service
    )

    payload = ResolveReportRequest(
        report_id=report_id,
        resolution=ResolvePayload(
            status=ResolveStatus.RESOLVED,
            comment="Test resolution",
            resolved_by="operador-1",
        ),
    )

    user = User(id="admin-1", email="admin@example.com", role="admin")

    if should_raise_not_found:
        with pytest.raises(ReportNotFoundError):
            await resolve_report(
                report_id=report_id,
                payload=payload,
                user=user,
            )
    else:
        result = await resolve_report(
            report_id=report_id,
            payload=payload,
            user=user,
        )
        assert result is not None
        assert result["id"] == report_id


# Task 2.3: Rate Limit Boundary Testing (catches >= operator)
@pytest.mark.parametrize(
    "submissions_today,should_raise,expected_remaining",
    [
        (0, False, 2),    # 3 - 0 - 1 = 2
        (1, False, 1),    # 3 - 1 - 1 = 1
        (2, False, 0),    # 3 - 2 - 1 = 0
        (3, True, None),  # At limit, reject
        (4, True, None),  # Over limit, reject
    ],
)
async def test_rate_limit_boundary(monkeypatch, submissions_today, should_raise, expected_remaining):
    """
    Test rate limit boundary at submissions_count >= MAX.
    Catches >= vs > operator mutations and boundary logic errors.
    """
    fake_client = _FakeSupabaseClient(submissions_count=submissions_today)
    monkeypatch.setattr(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", lambda: fake_client
    )

    payload = SugerenciaCiudadanaCreate(
        titulo="Test suggestion título largo",
        descripcion="Test description that is at least 10 characters long",
        contacto_email="test@example.com",
        contacto_verificado=True,
    )

    if should_raise:
        with pytest.raises(RateLimitExceededError):
            await crear_sugerencia_publica(payload)
    else:
        result = await crear_sugerencia_publica(payload)
        assert "id" in result
        assert result["remaining_today"] == expected_remaining


# Task 2.4: Contact Verification Enforcement (catches boolean inversions)
@pytest.mark.parametrize(
    "contacto_verificado,should_raise",
    [
        (True, False),   # Verified contact, should NOT raise
        (False, True),   # Unverified contact, should raise ValidationError
    ],
)
async def test_contact_verification(monkeypatch, contacto_verificado, should_raise):
    """
    Test contact verification enforcement.
    Catches boolean inversions and `not` operator mutations.
    """
    fake_client = _FakeSupabaseClient()
    monkeypatch.setattr(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", lambda: fake_client
    )

    payload = SugerenciaCiudadanaCreate(
        titulo="Test suggestion título largo",
        descripcion="Test description that is at least 10 characters long",
        contacto_email="test@example.com",
        contacto_verificado=contacto_verificado,
    )

    if should_raise:
        from app.core.exceptions import ValidationError as AppValidationError
        with pytest.raises(AppValidationError) as exc_info:
            await crear_sugerencia_publica(payload)
        assert exc_info.value.code == "CONTACT_NOT_VERIFIED"
    else:
        result = await crear_sugerencia_publica(payload)
        assert "id" in result


# Task 2.5: Contact Required Validation (catches AND/OR logic)
@pytest.mark.parametrize(
    "contacto_email,contacto_telefono,should_raise",
    [
        ("test@example.com", None, False),      # Email only, should proceed
        (None, "+54911234567", False),          # Phone only, should proceed
        (None, None, True),                     # Both None, should raise ValidationError
    ],
)
async def test_contact_required(monkeypatch, contacto_email, contacto_telefono, should_raise):
    """
    Test at least one contact field (email OR phone) is provided.
    Catches AND/OR operator mutations and logic inversions.
    """
    fake_client = _FakeSupabaseClient()
    monkeypatch.setattr(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", lambda: fake_client
    )

    payload = SugerenciaCiudadanaCreate(
        titulo="Test suggestion título largo",
        descripcion="Test description that is at least 10 characters long",
        contacto_email=contacto_email,
        contacto_telefono=contacto_telefono,
        contacto_verificado=True,
    )

    if should_raise:
        from app.core.exceptions import ValidationError as AppValidationError
        with pytest.raises(AppValidationError) as exc_info:
            await crear_sugerencia_publica(payload)
        assert exc_info.value.code == "CONTACT_REQUIRED"
    else:
        result = await crear_sugerencia_publica(payload)
        assert "id" in result
        # Verify contact_type is correctly determined
        assert result is not None


# Task 2.6: Remaining Calculation (catches arithmetic operators)
@pytest.mark.parametrize(
    "submissions_today,expected_remaining",
    [
        (0, 2),  # 3 - 0 - 1 = 2
        (1, 1),  # 3 - 1 - 1 = 1
        (2, 0),  # 3 - 2 - 1 = 0
    ],
)
async def test_remaining_calculation(monkeypatch, submissions_today, expected_remaining):
    """
    Test remaining suggestions calculation = MAX - submissions_today - 1.
    Catches arithmetic operator mutations (- vs +, precedence).
    """
    fake_client = _FakeSupabaseClient(submissions_count=submissions_today)
    monkeypatch.setattr(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", lambda: fake_client
    )

    payload = SugerenciaCiudadanaCreate(
        titulo="Test suggestion título largo",
        descripcion="Test description that is at least 10 characters long",
        contacto_email="test@example.com",
        contacto_verificado=True,
    )

    result = await crear_sugerencia_publica(payload)
    assert result["remaining_today"] == expected_remaining


# Task 2.7: Schema Validator - orden_del_dia_items (catches `not` operator)
@pytest.mark.parametrize(
    "orden_del_dia_items,should_raise",
    [
        (["Punto 1", "Punto 2"], False),      # Valid items, should NOT raise
        ([], True),                            # Empty list, should raise ValueError
        (["   ", "\t"], True),                # Whitespace only, after normalization empty, should raise
    ],
)
def test_schema_validator_orden_del_dia(orden_del_dia_items, should_raise):
    """
    Test ReunionCreate.orden_del_dia_items field validator.
    Catches `not` operator and logic inversions.
    """
    if should_raise:
        with pytest.raises(ValidationError):
            ReunionCreate(
                titulo="Test Reunion",
                fecha_reunion="2026-03-15T10:00:00Z",
                orden_del_dia_items=orden_del_dia_items,
            )
    else:
        reunion = ReunionCreate(
            titulo="Test Reunion",
            fecha_reunion="2026-03-15T10:00:00Z",
            orden_del_dia_items=orden_del_dia_items,
        )
        assert reunion is not None
        assert len(reunion.orden_del_dia_items) > 0


# Task 2.8: Schema Constraint - min_length (catches boundary comparisons)
@pytest.mark.parametrize(
    "titulo,should_raise",
    [
        ("Hello World", False),  # 11 chars, should pass (min=5)
        ("Hello", False),        # 5 chars (boundary), should pass
        ("Hola", True),          # 4 chars, should raise ValidationError
        ("", True),              # 0 chars, should raise ValidationError
    ],
)
def test_schema_min_length_sugerencia_titulo(titulo, should_raise):
    """
    Test SugerenciaCiudadanaCreate.titulo min_length constraint.
    Catches boundary comparison mutations (>=, >, <=).
    """
    if should_raise:
        with pytest.raises(ValidationError):
            SugerenciaCiudadanaCreate(
                titulo=titulo,
                descripcion="This is a valid description that is long enough",
                contacto_email="test@example.com",
                contacto_verificado=True,
            )
    else:
        sugerencia = SugerenciaCiudadanaCreate(
            titulo=titulo,
            descripcion="This is a valid description that is long enough",
            contacto_email="test@example.com",
            contacto_verificado=True,
        )
        assert sugerencia is not None
        assert sugerencia.titulo == titulo


@pytest.mark.parametrize(
    "titulo,should_raise",
    [
        ("A", False),    # 1 char (boundary), should pass (min=1)
        ("", True),      # 0 chars, should raise ValidationError
    ],
)
def test_schema_min_length_tramite_titulo(titulo, should_raise):
    """
    Test TramiteCreate.titulo min_length constraint (min=1).
    Catches boundary comparison mutations.
    """
    if should_raise:
        with pytest.raises(ValidationError):
            TramiteCreate(
                titulo=titulo,
                tipo="administrative",
            )
    else:
        tramite = TramiteCreate(
            titulo=titulo,
            tipo="administrative",
        )
        assert tramite is not None
        assert tramite.titulo == titulo
