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


class TestBulkAtomicity:
    """Issue #696 (part 1): a mid-batch non-HTTP failure must leave NOTHING
    applied and write no receipt — all-or-nothing — while the error still
    surfaces as a 500 exactly as before. Before the fix each item committed
    inside ``update()``, so a SQLAlchemyError (outbox savepoint, dropped
    connection, DataError) escaping the loop kept earlier items applied
    with no receipt, and a retry with the same key re-ran everything."""

    def test_non_http_error_mid_batch_applies_nothing(
        self, app_client, seeded, db_session_factory, monkeypatch
    ):
        from sqlalchemy import select
        from sqlalchemy.exc import SQLAlchemyError

        from app.domains.denuncias import notify as notify_module
        from app.domains.denuncias.models import DenunciaBulkReceipt

        app, _client = app_client
        operator_id, ids = seeded
        _as_operator(app, operator_id)

        # The service imports maybe_enqueue_status_email at call time, so
        # patching the module attribute is the seam: raise a generic
        # SQLAlchemyError on the SECOND item's update (first item already
        # flushed, batch half-way through).
        real_enqueue = notify_module.maybe_enqueue_status_email
        calls = {"n": 0}

        def flaky_enqueue(db, denuncia, *, became_attended):
            calls["n"] += 1
            if calls["n"] == 2:
                raise SQLAlchemyError("boom mid-batch")
            return real_enqueue(db, denuncia, became_attended=became_attended)

        monkeypatch.setattr(notify_module, "maybe_enqueue_status_email", flaky_enqueue)

        key = f"key-{uuid.uuid4().hex[:12]}"
        quiet_client = TestClient(app, raise_server_exceptions=False)
        quiet_client.headers.update({"Host": "localhost"})
        response = quiet_client.post(
            "/api/v2/denuncias/bulk",
            json={
                "ids": [str(i) for i in ids],
                "estado": "en_revision",
                "idempotency_key": key,
            },
        )
        # The error propagates as today: unhandled → 500.
        assert response.status_code == 500
        assert calls["n"] == 2

        # All-or-nothing: every denuncia is still pendiente (item 1's flush
        # was rolled back with the batch savepoint) and no receipt exists,
        # so a retry with the same key starts from a clean slate.
        session = db_session_factory()
        try:
            estados = (
                session.execute(select(Denuncia.estado).where(Denuncia.id.in_(ids))).scalars().all()
            )
            assert len(estados) == 3
            assert all(e == EstadoDenuncia.PENDIENTE for e in estados)
            receipts = (
                session.execute(
                    select(DenunciaBulkReceipt.idempotency_key).where(
                        DenunciaBulkReceipt.idempotency_key == key
                    )
                )
                .scalars()
                .all()
            )
            assert receipts == []
        finally:
            session.close()

    def test_retry_same_key_after_mid_batch_failure_applies_full_batch(
        self, app_client, seeded, monkeypatch
    ):
        from sqlalchemy.exc import SQLAlchemyError

        from app.domains.denuncias import notify as notify_module

        app, client = app_client
        operator_id, ids = seeded
        _as_operator(app, operator_id)

        real_enqueue = notify_module.maybe_enqueue_status_email
        calls = {"n": 0}

        # Fails once, on the second item of the FIRST attempt (item 1
        # already flushed — the half-applied-batch scenario). The retry's
        # calls land on 3-5 and pass through.
        def flaky_once(db, denuncia, *, became_attended):
            calls["n"] += 1
            if calls["n"] == 2:
                raise SQLAlchemyError("boom mid-batch")
            return real_enqueue(db, denuncia, became_attended=became_attended)

        monkeypatch.setattr(notify_module, "maybe_enqueue_status_email", flaky_once)

        key = f"key-{uuid.uuid4().hex[:12]}"
        payload = {
            "ids": [str(i) for i in ids],
            "estado": "en_revision",
            "idempotency_key": key,
        }

        quiet_client = TestClient(app, raise_server_exceptions=False)
        quiet_client.headers.update({"Host": "localhost"})
        failed = quiet_client.post("/api/v2/denuncias/bulk", json=payload)
        assert failed.status_code == 500

        # Retry with the SAME key: nothing was applied and no receipt was
        # written by the failed attempt, so the batch runs clean end-to-end
        # and the receipt finally exists.
        retried = client.post("/api/v2/denuncias/bulk", json=payload)
        assert retried.status_code == 200
        rows = retried.json()["resultados"]
        assert len(rows) == 3
        assert all(row["ok"] for row in rows)


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
