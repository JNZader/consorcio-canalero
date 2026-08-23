"""``GET /api/v2/geo/intelligence/cruces-camino`` is operator-and-admin only.

RFA-R6: reading, computing and re-computing road flow results requires an
authenticated user holding the operator or administrator role, and a denial
**must disclose no crossing geometry, contributing area or ranking**.

That last clause is what the body assertions below are for. The dependency
rejects before the service runs, so there is no partial payload to leak — but
"there is nothing to leak because the handler never ran" is a claim worth
checking rather than assuming, and the checks are cheap.

The other half of the requirement is structural and lives elsewhere: this
capability publishes nothing, so there is no anonymous tile path to test. That is
asserted in ``test_cruce_camino_migration`` (no view, no matview) and in
``test_cruces_camino_no_regression`` (the Martin config and reader grants have an
empty diff).
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-cruces-auth")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

ENDPOINT = "/api/v2/geo/intelligence/cruces-camino"
AREA = "zona_principal"

#: Anything that would betray a crossing. Checked against the raw response body,
#: so a leak through an error detail or a validation echo is caught too.
FORBIDDEN_IN_A_DENIAL = (
    "orden_ranking",
    "area_aporte_ha",
    "direccion_flujo_deg",
    "lado_cruce",
    "FeatureCollection",
    "coordinates",
    "tramo_ref",
)


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


def _as_role(app, role: str) -> None:
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(role=UserRole(role))


class TestReadAuthorization:
    @pytest.mark.parametrize("role", ["operador", "admin"])
    def test_an_operator_or_admin_gets_the_results(self, app_client, role: str):
        app, client = app_client
        _as_role(app, role)

        response = client.get(ENDPOINT, params={"area_id": AREA})

        assert response.status_code == 200
        body = response.json()
        assert body["area_id"] == AREA
        assert body["features"]["type"] == "FeatureCollection"

    def test_a_citizen_is_denied_and_the_body_discloses_nothing(self, app_client):
        app, client = app_client
        _as_role(app, "ciudadano")

        response = client.get(ENDPOINT, params={"area_id": AREA})

        assert response.status_code == 403
        raw = response.text
        for token in FORBIDDEN_IN_A_DENIAL:
            assert token not in raw, f"a denial must not disclose {token!r}"

    def test_an_unauthenticated_visitor_is_denied(self, app_client):
        _app, client = app_client

        response = client.get(ENDPOINT, params={"area_id": AREA})

        assert response.status_code == 401
        raw = response.text
        for token in FORBIDDEN_IN_A_DENIAL:
            assert token not in raw


class TestRecomputeAuthorization:
    """The recompute trigger carries the same dependency as the read."""

    def test_an_operator_can_trigger_a_recompute(self, app_client, monkeypatch):
        """Only the BROKER publish is stubbed; the outbox row is really written.

        Left unstubbed, publication spends ~20 s retrying a result backend that
        is not running — which would make an auth test fail for a reason that has
        nothing to do with authorization. The stub is placed at the publish step
        rather than at ``.delay()`` on purpose: the durable outbox row and the
        ``geo_jobs`` row are written in the same transaction BEFORE it, so this
        still exercises the real dispatch path and a deferred publication is a
        supported outcome rather than a failure.
        """
        from app.domains.geo import service as geo_service

        monkeypatch.setattr(geo_service, "try_publish_celery_task", lambda _id: False)

        app, client = app_client
        _as_role(app, "operador")

        response = client.post(f"{ENDPOINT}/recalcular", json={"area_id": AREA})

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "submitted"
        assert response.json()["task_id"]

    def test_the_recompute_dispatches_through_the_durable_outbox(self, app_client, monkeypatch):
        """A tipo dispatched outside the allowlist would be a hole in the guarantee.

        ``_get_task_key_map`` is asserted to cover EVERY ``TipoGeoJob``
        (``test_geo_bugfixes.py``), and the map is what turns a job row into a
        persisted publication intent in the same transaction. A bare ``.delay()``
        here would have created a ``geo_jobs`` row whose dispatch could be lost
        to a broker hiccup with nothing left to retry from.
        """
        from app.domains.geo.models import TipoGeoJob
        from app.domains.geo.service import _get_task_key_map
        from app.shared.celery_outbox import CeleryTaskKey

        assert (
            _get_task_key_map()[TipoGeoJob.ROAD_FLOW_CROSSINGS]
            == CeleryTaskKey.COMPUTE_ROAD_FLOW_CROSSINGS
        )

    def test_a_citizen_cannot_trigger_a_recompute(self, app_client):
        app, client = app_client
        _as_role(app, "ciudadano")

        response = client.post(f"{ENDPOINT}/recalcular", json={"area_id": AREA})

        assert response.status_code == 403

    def test_an_unauthenticated_visitor_cannot_trigger_a_recompute(self, app_client):
        _app, client = app_client

        response = client.post(f"{ENDPOINT}/recalcular", json={"area_id": AREA})

        assert response.status_code == 401


class TestNoHydraulicQuantityIsOffered:
    """RFA: no volume, flow rate, depth, cuneta size or return period.

    Asserted against the SCHEMA rather than against one response, so a field
    added later fails here even if no fixture happens to populate it.
    """

    @pytest.mark.parametrize(
        "forbidden",
        [
            "volumen",
            "caudal",
            "profundidad",
            "cuneta",
            "periodo_retorno",
            "recurrencia",
            "m3",
            "litros",
        ],
    )
    def test_the_response_schema_names_no_hydraulic_quantity(self, forbidden: str):
        """Checked against the FIELD NAMES, not the whole serialized schema.

        The descriptions deliberately say "no cuneta size is presented", and a
        grep that cannot tell a field from a sentence explaining its absence
        would force the reason for the rule out of the file that obeys it — the
        same defect as grepping a docstring for a forbidden layer name. What
        would violate the requirement is a *field* offering the quantity.
        """
        from app.domains.geo.intelligence.schemas import CrucesCaminoResponse

        field_names = " ".join(CrucesCaminoResponse.model_fields).lower()
        assert forbidden not in field_names, (
            f"the response must offer no hydraulic quantity — found a field naming {forbidden!r}"
        )

    @pytest.mark.parametrize(
        "forbidden", ["volumen", "caudal", "profundidad", "cuneta", "periodo_retorno"]
    )
    def test_no_crossing_property_names_a_hydraulic_quantity(self, app_client, forbidden: str):
        """The same rule one level down, on the GeoJSON feature properties.

        The schema above types ``features`` as a plain dict, so the properties a
        feature really carries would otherwise go unchecked.
        """
        app, client = app_client
        _as_role(app, "operador")

        body = client.get(ENDPOINT, params={"area_id": AREA}).json()
        for feature in body["features"]["features"]:
            for key in feature["properties"]:
                assert forbidden not in key.lower()

    def test_the_response_carries_the_rank_denominator_separately(self, app_client):
        """``N.º de M`` needs M = the flujo_natural count, never the total.

        A rank whose denominator moved with DEM coverage rather than with the
        network would be meaningless, so the two counts are separate fields and
        the UI is never left to compute one from the other.
        """
        app, client = app_client
        _as_role(app, "operador")

        body = client.get(ENDPOINT, params={"area_id": AREA}).json()

        assert "total_flujo_natural" in body
        assert "total_canal" in body

    def test_the_response_carries_provenance_and_the_recorded_parameters(self, app_client):
        """A rank list can never be read without the parameters that produced it."""
        app, client = app_client
        _as_role(app, "operador")

        body = client.get(ENDPOINT, params={"area_id": AREA}).json()

        assert "calculada_en" in body
        assert "desactualizado" in body
        assert "excluidos" in body
        assert "variante" in body
        assert "segmentos_parcialmente_cubiertos" in body
        assert "parametros" in body
