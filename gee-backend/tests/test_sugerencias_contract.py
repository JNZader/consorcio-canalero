"""Integration-style tests for sugerencias contract using a fake Supabase client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.api.v1.schemas import SugerenciaEstado, SugerenciaPrioridad, SugerenciaTipo


@dataclass
class FakeResult:
    data: Any
    count: int | None = None


class FakeTable:
    def __init__(self, name: str, store: dict[str, Any]):
        self.name = name
        self.store = store
        self.filters: dict[str, Any] = {}
        self.payload: Any = None
        self.mode = "select"
        self.want_count = False
        self.single_result = False

    def select(self, *_args, count: str | None = None):
        self.mode = "select"
        self.want_count = count == "exact"
        return self

    def eq(self, key: str, value: Any):
        self.filters[key] = value
        return self

    def gte(self, _key: str, _value: Any):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def single(self):
        self.single_result = True
        return self

    def insert(self, payload: Any):
        self.mode = "insert"
        self.payload = payload
        return self

    def update(self, payload: Any):
        self.mode = "update"
        self.payload = payload
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def execute(self):
        if self.name == "contact_submissions" and self.mode == "select":
            return FakeResult(data=[], count=self.store.get("contact_submissions_count", 0))

        if self.name == "sugerencias" and self.mode == "insert":
            now = datetime.now(timezone.utc).isoformat()
            created = {
                "id": str(uuid4()),
                "tipo": self.payload["tipo"],
                "titulo": self.payload["titulo"],
                "descripcion": self.payload["descripcion"],
                "categoria": self.payload.get("categoria"),
                "contacto_nombre": self.payload.get("contacto_nombre"),
                "contacto_email": self.payload.get("contacto_email"),
                "contacto_telefono": self.payload.get("contacto_telefono"),
                "estado": self.payload.get("estado", SugerenciaEstado.PENDIENTE.value),
                "prioridad": self.payload.get(
                    "prioridad", SugerenciaPrioridad.NORMAL.value
                ),
                "fecha_reunion": None,
                "notas_comision": None,
                "resolucion": None,
                "cuenca_id": self.payload.get("cuenca_id"),
                "autor_id": self.payload.get("autor_id"),
                "created_at": now,
                "updated_at": now,
            }
            self.store["sugerencia"] = created
            return FakeResult(data=[created])

        if self.name == "sugerencias" and self.mode == "select":
            item = self.store.get("sugerencia")
            if self.single_result:
                return FakeResult(data=item)
            return FakeResult(data=[item] if item else [], count=1 if item else 0)

        if self.name == "sugerencias" and self.mode == "update":
            item = self.store["sugerencia"]
            item.update(self.payload)
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            return FakeResult(data=[item])

        if self.name == "sugerencias" and self.mode == "delete":
            item = self.store.pop("sugerencia", None)
            return FakeResult(data=[item] if item else [])

        return FakeResult(data=[])


class FakeSupabaseClient:
    def __init__(self):
        self.store: dict[str, Any] = {
            "contact_submissions_count": 0,
            "sugerencia": {
                "id": str(uuid4()),
                "tipo": SugerenciaTipo.INTERNA.value,
                "titulo": "Tema actual",
                "descripcion": "Descripcion",
                "categoria": "infraestructura",
                "contacto_nombre": None,
                "contacto_email": None,
                "estado": SugerenciaEstado.PENDIENTE.value,
                "prioridad": SugerenciaPrioridad.NORMAL.value,
                "fecha_reunion": None,
                "notas_comision": None,
                "resolucion": None,
                "cuenca_id": None,
                "autor_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    def table(self, name: str):
        return FakeTable(name, self.store)


def test_create_public_suggestion_contract(client, monkeypatch):
    fake = FakeSupabaseClient()
    monkeypatch.setattr("app.api.v1.endpoints.sugerencias.get_supabase_client", lambda: fake)

    response = client.post(
        "/api/v1/sugerencias/public",
        json={
            "titulo": "Mejora de compuertas",
            "descripcion": "Propuesta para mejorar control de caudal",
            "contacto_email": "vecino@example.com",
            "contacto_verificado": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "id" in body
    assert body["remaining_today"] == 2


def test_update_suggestion_enforces_enum_contract(
    client, admin_auth, auth_headers, monkeypatch
):
    fake = FakeSupabaseClient()
    suggestion_id = fake.store["sugerencia"]["id"]
    monkeypatch.setattr("app.api.v1.endpoints.sugerencias.get_supabase_client", lambda: fake)

    response = client.put(
        f"/api/v1/sugerencias/{suggestion_id}",
        headers=auth_headers,
        json={
            "estado": SugerenciaEstado.EN_AGENDA.value,
            "prioridad": SugerenciaPrioridad.ALTA.value,
            "notas_comision": "Se agenda para la proxima reunion",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["estado"] == SugerenciaEstado.EN_AGENDA.value
    assert payload["prioridad"] == SugerenciaPrioridad.ALTA.value


def test_delete_suggestion_contract(client, admin_auth, auth_headers, monkeypatch):
    fake = FakeSupabaseClient()
    suggestion_id = fake.store["sugerencia"]["id"]
    monkeypatch.setattr("app.api.v1.endpoints.sugerencias.get_supabase_client", lambda: fake)

    response = client.delete(
        f"/api/v1/sugerencias/{suggestion_id}",
        headers={**auth_headers, "Content-Type": "application/json"},
    )

    assert response.status_code == 204
