"""HTTP tests for the new denuncia router endpoints (CI-04 coverage floor).

Exercises GET /denuncias/operadores, POST /denuncias/bulk, and the sort
parameter on GET /denuncias — the endpoints added by the roadmap DS stage 4.
"""

import uuid

# Eager imports: the conftest's create_all only sees models registered
# with Base.metadata BEFORE the test_engine fixture runs. These imports
# at module level ensure the denuncias and users tables exist.
from app.auth.models import User, UserRole  # noqa: F401
from app.domains.denuncias.models import (  # noqa: F401
    Denuncia,
    EstadoDenuncia,
)

import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace

import os

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-denuncia-router")


@pytest.fixture
def app_client(db_session_factory):
    from app.db.session import get_db
    from app.main import app

    def _get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    yield app, client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(db_session_factory):
    """One operator and three denuncias in pendiente."""
    # Los modelos ya están importados a nivel de módulo (líneas 12-17)
    # para que Base.metadata los registre antes del create_all.

    session = db_session_factory()
    try:
        operator = User(
            email=f"op-{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="!test",
            nombre="Operador",
            apellido="Uno",
            role=UserRole.OPERADOR,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        session.add(operator)
        session.commit()

        ids = []
        for i in range(3):
            d = Denuncia(
                id=uuid.uuid4(),
                tipo="agua",
                descripcion=f"test-{i}",
                estado=EstadoDenuncia.PENDIENTE,
                user_id=operator.id,
                latitud=-32.6,
                longitud=-62.3,
            )
            session.add(d)
            ids.append(d.id)
        session.commit()
        return operator.id, ids
    finally:
        session.close()


def _as_operator(app, user_id):
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(
        id=user_id, role=UserRole.OPERADOR
    )


class TestOperadoresEndpoint:
    def test_returns_operator_with_name(self, app_client, seeded):
        app, client = app_client
        operator_id, _ = seeded
        _as_operator(app, operator_id)

        response = client.get("/api/v2/denuncias/operadores")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        entry = next(row for row in body if row["id"] == str(operator_id))
        assert "Operador Uno" in entry["nombre"]
        assert "teléfono" not in entry and "telefono" not in entry


class TestBulkEndpoint:
    def test_bulk_passes_to_en_revision(self, app_client, seeded):
        app, client = app_client
        operator_id, ids = seeded
        _as_operator(app, operator_id)

        response = client.post(
            "/api/v2/denuncias/bulk",
            json={
                "ids": [str(i) for i in ids],
                "estado": "en_revision",
                "idempotency_key": f"key-{uuid.uuid4().hex[:12]}",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["resultados"]) == 3
        assert all(row["ok"] for row in body["resultados"])

    def test_same_key_same_batch_returns_receipt(self, app_client, seeded):
        app, client = app_client
        operator_id, ids = seeded
        _as_operator(app, operator_id)
        key = f"key-{uuid.uuid4().hex[:12]}"

        first = client.post(
            "/api/v2/denuncias/bulk",
            json={"ids": [str(ids[0])], "estado": "en_revision", "idempotency_key": key},
        )
        second = client.post(
            "/api/v2/denuncias/bulk",
            json={"ids": [str(ids[0])], "estado": "en_revision", "idempotency_key": key},
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()

    def test_same_key_different_batch_409(self, app_client, seeded):
        app, client = app_client
        operator_id, ids = seeded
        _as_operator(app, operator_id)
        key = f"key-{uuid.uuid4().hex[:12]}"

        first = client.post(
            "/api/v2/denuncias/bulk",
            json={"ids": [str(ids[0])], "estado": "en_revision", "idempotency_key": key},
        )
        conflict = client.post(
            "/api/v2/denuncias/bulk",
            json={"ids": [str(ids[1])], "estado": "en_revision", "idempotency_key": key},
        )
        assert first.status_code == 200
        assert conflict.status_code == 409


class TestSortParameter:
    def test_sort_by_estado_returns_200(self, app_client, seeded):
        app, client = app_client
        operator_id, _ = seeded
        _as_operator(app, operator_id)

        response = client.get("/api/v2/denuncias?sort=estado&order=asc")
        assert response.status_code == 200

    def test_invalid_sort_returns_400(self, app_client, seeded):
        app, client = app_client
        operator_id, _ = seeded
        _as_operator(app, operator_id)

        response = client.get("/api/v2/denuncias?sort=invalid_column")
        assert response.status_code == 400

    def test_invalid_order_returns_400(self, app_client, seeded):
        app, client = app_client
        operator_id, _ = seeded
        _as_operator(app, operator_id)

        response = client.get("/api/v2/denuncias?sort=estado&order=sideways")
        assert response.status_code == 400
