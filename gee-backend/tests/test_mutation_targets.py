from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

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
from app.auth import User


@dataclass
class _ReportServiceFake:
    report_id: str

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        if report_id != self.report_id:
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
    def __init__(self, name: str, store: dict[str, Any]):
        self.name = name
        self.store = store
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
        if self.name == "contact_submissions" and self.mode == "select":
            return _FakeResult([], count=0)

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
    def __init__(self):
        self.store: dict[str, Any] = {}

    def table(self, name: str):
        return _FakeTable(name, self.store)


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
