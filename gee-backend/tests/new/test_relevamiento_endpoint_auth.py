"""Every survey route is operator-and-admin only, on EVERY verb.

RSS-R5: creating, editing and reading segment survey records requires an
authenticated operator or administrator; a citizen and an anonymous visitor are
denied, and the denial **must not disclose recorded values, authorship or the
survey history**. Those last three are what the body assertions are for — the
dependency rejects before the service runs, so there is nothing to leak, but
"there is nothing to leak because the handler never ran" is a claim worth
checking rather than assuming.

The other half is structural and lives in the migration test: no view over survey
data is published, so there is no anonymous tile path to test. Operator identity
never reaches a public surface because no public surface reads these tables.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-relevamiento-auth")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

BASE = "/api/v2/geo/relevamiento"
TRAMO = "auth-tramo-1"

#: Anything that would betray a record, its author or its history.
FORBIDDEN_IN_A_DENIAL = (
    "nivel_relativo",
    "tiene_cuneta",
    "estado_cuneta",
    "relevado_por",
    "relevado_en",
    "historial",
    "vigente",
    "candidata",
)

PAYLOAD = {
    "tramo_ref": TRAMO,
    "nivel_relativo": "mayor",
    "tiene_cuneta": "si",
    "estado_cuneta": "limpia",
}


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
    """One active segment and the operator identity the writes are attributed to."""
    import uuid

    from sqlalchemy import text

    from app.auth.models import User, UserRole

    session = db_session_factory()
    try:
        user = User(
            email=f"operator-auth-{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="fakehash",
            nombre="Operador",
            apellido="Auth",
            role=UserRole.OPERADOR,
        )
        session.add(user)
        session.execute(
            text(
                "INSERT INTO red_vial (id, source_id, geom, geom_hash) VALUES "
                "(:id, :id, ST_GeomFromText('LINESTRING(-62 -32.5, -62.01 -32.51)', 4326), 'h')"
            ),
            {"id": TRAMO},
        )
        session.commit()
        return user.id
    finally:
        session.close()


def _as_role(app, role: str, user_id=None) -> None:
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(
        id=user_id, role=UserRole(role)
    )


class TestAnOperatorCanRecordAndRead:
    @pytest.mark.parametrize("role", ["operador", "admin"])
    def test_a_survey_can_be_created_and_read_back(self, app_client, seeded, role: str):
        app, client = app_client
        _as_role(app, role, seeded)

        creado = client.post(f"{BASE}/tramos", json=PAYLOAD)
        assert creado.status_code == 200, creado.text
        assert creado.json()["relevado_por"] == str(seeded)

        detalle = client.get(f"{BASE}/tramos/{TRAMO}")
        assert detalle.status_code == 200
        cuerpo = detalle.json()
        assert cuerpo["vigente"]["nivel_relativo"] == "mayor"
        assert cuerpo["vigente"]["es_vigente"] is True
        assert len(cuerpo["historial"]) == 1

    def test_the_three_read_fields_are_named_and_separate(self, app_client, seeded):
        app, client = app_client
        _as_role(app, "operador", seeded)

        cuerpo = client.get(f"{BASE}/tramos/{TRAMO}").json()

        assert set(cuerpo) == {"tramo_ref", "vigente", "historial", "candidata"}, (
            "the DEM guess keeps its own field: merging it into the survey is "
            "exactly how a candidate becomes an authoritative value"
        )

    def test_the_author_of_a_survey_is_the_authenticated_operator(self, app_client, seeded):
        """Not a field of the request: a client-supplied author is not an author."""
        app, client = app_client
        _as_role(app, "operador", seeded)

        respuesta = client.post(f"{BASE}/tramos", json={**PAYLOAD, "relevado_por": str(seeded)})

        assert respuesta.status_code == 422, (
            "relevado_por is not an accepted input — extra='forbid' refuses it by name"
        )


class TestThereIsNoEditPath:
    @pytest.mark.parametrize("verb", ["PUT", "PATCH", "DELETE"])
    def test_no_mutating_verb_is_routed(self, verb: str):
        """Asserted against the ROUTE TABLE, not against a status code.

        A request with a mutating verb comes back ``415`` here — a middleware
        rejects it on content type before routing ever happens — so a status
        assertion would pass just as happily against a router that *did* declare
        a ``DELETE``. What the requirement is about is whether the route exists,
        and the router object is where that question has an answer. (The app's
        own route table cannot be walked: ``api_v2_router`` is mounted lazily
        behind FastAPI's ``_IncludedRouter``, and ``/openapi.json`` is disabled.)
        """
        from app.domains.geo.relevamiento.router import router as survey_router

        rutas = [
            (route.path, metodo)
            for route in survey_router.routes
            for metodo in sorted(getattr(route, "methods", set()) or set())
        ]

        assert rutas, "the survey routes must be declared, or this proves nothing"
        assert not [r for r in rutas if r[1] == verb], (
            f"{verb} must not exist: a correction is a new version, and the "
            "record it corrects stays retrievable"
        )

    def test_the_router_source_declares_no_mutating_verb(self):
        import re
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "app"
            / "domains"
            / "geo"
            / "relevamiento"
            / "router.py"
        ).read_text(encoding="utf-8")

        assert re.search(r"@router\.(put|patch|delete)", source) is None


class TestACitizenAndAnAnonymousVisitorAreDenied:
    @pytest.mark.parametrize(
        "metodo,ruta,cuerpo",
        [
            ("get", f"{BASE}/tramos/{TRAMO}", None),
            ("post", f"{BASE}/tramos", PAYLOAD),
            ("get", f"{BASE}/cobertura", None),
        ],
    )
    def test_a_citizen_is_denied_on_every_route(
        self, app_client, seeded, metodo: str, ruta: str, cuerpo
    ):
        app, client = app_client
        _as_role(app, "ciudadano", seeded)

        respuesta = getattr(client, metodo)(ruta, **({"json": cuerpo} if cuerpo else {}))

        assert respuesta.status_code == 403
        for token in FORBIDDEN_IN_A_DENIAL:
            assert token not in respuesta.text, f"a denial must not disclose {token!r}"

    @pytest.mark.parametrize(
        "metodo,ruta,cuerpo",
        [
            ("get", f"{BASE}/tramos/{TRAMO}", None),
            ("post", f"{BASE}/tramos", PAYLOAD),
            ("get", f"{BASE}/cobertura", None),
        ],
    )
    def test_an_unauthenticated_visitor_is_denied_on_every_route(
        self, app_client, seeded, metodo: str, ruta: str, cuerpo
    ):
        _app, client = app_client

        respuesta = getattr(client, metodo)(ruta, **({"json": cuerpo} if cuerpo else {}))

        assert respuesta.status_code == 401
        for token in FORBIDDEN_IN_A_DENIAL:
            assert token not in respuesta.text


class TestNoDimensionIsAcceptedOverTheWire:
    @pytest.mark.parametrize("campo", ["ancho_cuneta", "profundidad", "capacidad"])
    def test_a_dimension_field_is_refused_naming_it(self, app_client, seeded, campo: str):
        app, client = app_client
        _as_role(app, "operador", seeded)

        respuesta = client.post(f"{BASE}/tramos", json={**PAYLOAD, campo: 1.5})

        assert respuesta.status_code == 422
        assert campo in respuesta.text
