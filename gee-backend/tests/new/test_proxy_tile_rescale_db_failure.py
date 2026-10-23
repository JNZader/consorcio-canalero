"""``proxy_tile`` FAILS CLOSED when the publicity DB lookup fails (audit C1).

The tile proxy loads the layer to decide whether it may be forwarded to an
anonymous client at all (publicity gate, audit C1/GEO-1). When that lookup
raises ``SQLAlchemyError`` the router cannot verify publicity, so it must NOT
forward: it answers 503 and logs a THROTTLED warning instead.

History — this suite used to pin the opposite contract ("degrade gracefully:
forward without the rescale override"), which was correct while the lookup
existed only to resolve the canonical rescale override for the layer's tipo.
C1 hoisted the same lookup into an unconditional authorization gate, and
authorization does not degrade: during a DB outage the proxy gives up the
worker's byte-cached no-override tiles (the worker's cache lookup in
``get_tile`` returns before ``_get_layer`` touches the same Postgres) rather
than forward a layer it cannot prove is public. That trade is deliberate and
documented in ``router_core.proxy_tile``.

What these tests actually pin:

  * the router answers 503 — never forwards, never 500s — when the publicity
    lookup raises ``SQLAlchemyError`` (OperationalError included);
  * the refusal is LOGGED (silent refusal is forbidden) and the warning is
    THROTTLED — this route is exempt from the rate limiter, so one emit per
    tile would be a log flood;
  * the refusal is not sticky — the next request re-attempts the lookup and
    forwards the canonical pair once the database is healthy again;
  * a healthy lookup still enforces the 404 (unpublished layer) and the 400
    (unsupported range) paths;
  * non-SQLAlchemy (programmer) exceptions are NOT swallowed.

Real PostgreSQL, transaction-per-test: the healthy paths run against a seeded
layer through the ``db`` fixture. Only the failure itself is injected, by
overriding ``get_db`` with a session whose ``query`` raises.
"""

from __future__ import annotations

import logging
import os
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, SQLAlchemyError

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-tile-rescale-db-failure")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

MONTHLY_RESCALE = {"rescale_min": 0, "rescale_max": 200}
ANNUAL_RESCALE = {"rescale_min": 0, "rescale_max": 1800}
UNSUPPORTED_PRECIP_DETAIL = "rango de rescale no soportado para la capa 'precip_normal'"


def _tile_url(layer_id: uuid.UUID, z: int = 10, x: int = 0, y: int = 0) -> str:
    return f"/api/v2/geo/layers/{layer_id}/tiles/{z}/{x}/{y}.png"


def _seed_tile_layer(db, tipo: str, fuente: str | None = None) -> uuid.UUID:
    from app.domains.geo.models import FormatoGeoLayer, GeoLayer

    layer = GeoLayer(
        nombre=f"{tipo}_{uuid.uuid4()}",
        tipo=tipo,
        fuente=fuente or ("gee" if tipo == "precip_normal" else "dem_pipeline"),
        archivo_path=f"/tmp/{tipo}.tif",
        formato=FormatoGeoLayer.GEOTIFF.value,
    )
    db.add(layer)
    db.flush()
    return layer.id


class _FailingQuerySession:
    """Wraps the real session but raises on ``query`` until it is healed.

    Mirrors a transient database outage: the very first ``query`` call blows up,
    and once ``heal()`` is called the wrapper delegates to the real session
    again, so the recovery assertion still runs against real PostgreSQL.
    """

    def __init__(self, real, exc: Exception, failures: int = 1) -> None:
        self._real = real
        self._exc = exc
        self._remaining = failures
        self.query_calls = 0

    def heal(self) -> None:
        self._remaining = 0

    def query(self, *args, **kwargs):
        self.query_calls += 1
        if self._remaining > 0:
            self._remaining -= 1
            raise self._exc
        return self._real.query(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture(autouse=True)
def _reset_warn_throttle():
    """The warning latch is module-global — isolate every test from the others."""
    from app.domains.geo import router_core

    router_core._reset_publicity_lookup_warn_throttle()
    yield
    router_core._reset_publicity_lookup_warn_throttle()


@pytest.fixture
def tile_client(monkeypatch):
    """Recording stub for the internal geo-worker tile client."""
    from app.domains.geo import router_core

    stub = type("RecordingTileClient", (), {})()
    stub.get = AsyncMock(
        return_value=type("TileResponse", (), {"status_code": 200, "content": b"png"})()
    )
    monkeypatch.setattr(router_core, "_get_tile_client", lambda: stub)
    return stub


@pytest.fixture
def make_cliente(db):
    """Builds a ``TestClient`` bound to a caller-chosen session object."""
    from app.db.session import get_db
    from app.main import app

    created: list[TestClient] = []

    def _build(session=None) -> TestClient:
        app.dependency_overrides[get_db] = lambda: session if session is not None else db
        client = TestClient(app)
        client.headers.update({"Host": "localhost"})
        created.append(client)
        return client

    yield _build
    app.dependency_overrides.clear()


def _forwarded_params(tile_client) -> dict:
    return tile_client.get.await_args.kwargs["params"]


# ── 1. DB failure fails closed: 503, no forward, never a 500 ──────────────────


@pytest.mark.parametrize(
    "exc",
    [
        OperationalError("connection refused", None, Exception("boom")),
        SQLAlchemyError("db down"),
    ],
    ids=["operational_error", "generic_sqlalchemy_error"],
)
@pytest.mark.parametrize("params", [{}, MONTHLY_RESCALE], ids=["no_rescale", "rescale"])
def test_db_failure_fails_closed_503(
    make_cliente, tile_client, db, exc: Exception, params: dict
) -> None:
    """Unverifiable publicity → do NOT forward, whatever the query shape.

    The no-rescale variant is the C1 regression: before the gate existed the
    default request shape never ran the lookup at all.
    """
    layer_id = _seed_tile_layer(db, "precip_normal")
    session = _FailingQuerySession(db, exc)

    response = make_cliente(session).get(_tile_url(layer_id), params=params)

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": "Capa no disponible temporalmente"}
    tile_client.get.assert_not_awaited()


# ── 2. The refusal is observable — silent fail-closed is forbidden ───────────


def _refusal_records(caplog) -> list:
    """The structlog event dicts emitted by the fail-closed branch.

    ``get_logger`` wraps the stdlib logger with structlog's
    ``ProcessorFormatter``, so ``record.msg`` is the event dict itself and the
    bound fields can be asserted directly instead of through a rendered string.
    """
    out = []
    for record in caplog.records:
        event = record.msg
        if isinstance(event, dict) and event.get("event", "").startswith(
            "Tile publicity lookup unavailable"
        ):
            out.append(event)
    return out


def test_db_failure_is_logged_as_a_warning(make_cliente, tile_client, db, caplog) -> None:
    layer_id = _seed_tile_layer(db, "precip_normal")
    session = _FailingQuerySession(db, OperationalError("connection refused", None, None))

    with caplog.at_level(logging.WARNING, logger="app.domains.geo.router_core"):
        response = make_cliente(session).get(_tile_url(layer_id), params=MONTHLY_RESCALE)

    assert response.status_code == 503, response.text
    refusals = _refusal_records(caplog)
    assert len(refusals) == 1, caplog.text
    assert refusals[0]["layer_id"] == str(layer_id)
    assert refusals[0]["error_type"] == "OperationalError"
    # First failure after the latch reset: nothing was suppressed before it.
    assert refusals[0]["suppressed_since_last"] == 0


def test_repeated_db_failures_emit_at_most_one_warning_per_interval(
    make_cliente, tile_client, db, caplog
) -> None:
    """The route is exempt from the rate limiter — the warning must not flood."""
    layer_id = _seed_tile_layer(db, "precip_normal")
    session = _FailingQuerySession(
        db, OperationalError("connection refused", None, None), failures=5
    )
    cliente = make_cliente(session)

    with caplog.at_level(logging.WARNING, logger="app.domains.geo.router_core"):
        for _ in range(5):
            assert cliente.get(_tile_url(layer_id), params=MONTHLY_RESCALE).status_code == 503

    # Every tile was refused, but only the first one was logged.
    assert session.query_calls == 5
    assert len(_refusal_records(caplog)) == 1, caplog.text


def test_warning_resumes_after_the_throttle_interval(
    make_cliente, tile_client, db, caplog, monkeypatch
) -> None:
    """Once the window elapses, the next failure logs and reports the backlog."""
    from app.domains.geo import router_core

    layer_id = _seed_tile_layer(db, "precip_normal")
    session = _FailingQuerySession(
        db, OperationalError("connection refused", None, None), failures=3
    )
    cliente = make_cliente(session)

    with caplog.at_level(logging.WARNING, logger="app.domains.geo.router_core"):
        cliente.get(_tile_url(layer_id), params=MONTHLY_RESCALE)  # logged
        cliente.get(_tile_url(layer_id), params=MONTHLY_RESCALE)  # suppressed
        # Collapse the window instead of sleeping through a real minute.
        monkeypatch.setattr(router_core, "_PUBLICITY_LOOKUP_WARN_INTERVAL_S", 0.0)
        cliente.get(_tile_url(layer_id), params=MONTHLY_RESCALE)  # logged again

    refusals = _refusal_records(caplog)
    assert len(refusals) == 2, caplog.text
    assert refusals[0]["suppressed_since_last"] == 0
    assert refusals[1]["suppressed_since_last"] == 1


# ── 3. The refusal is not sticky ──────────────────────────────────────────────


def test_recovered_db_forwards_the_canonical_rescale(make_cliente, tile_client, db) -> None:
    layer_id = _seed_tile_layer(db, "precip_normal")
    session = _FailingQuerySession(db, OperationalError("transient blip", None, None))
    cliente = make_cliente(session)

    refused = cliente.get(_tile_url(layer_id), params=MONTHLY_RESCALE)
    assert refused.status_code == 503, refused.text
    tile_client.get.assert_not_awaited()

    session.heal()
    recovered = cliente.get(_tile_url(layer_id), params=MONTHLY_RESCALE)

    assert recovered.status_code == 200, recovered.text
    assert _forwarded_params(tile_client) == {"rescale_min": 0.0, "rescale_max": 200.0}
    assert session.query_calls == 2


# ── 4. The healthy paths never enter the fail-closed branch ─────────────────


def test_healthy_lookup_still_forwards_the_canonical_rescale(make_cliente, tile_client, db) -> None:
    layer_id = _seed_tile_layer(db, "precip_normal")

    response = make_cliente().get(_tile_url(layer_id), params=ANNUAL_RESCALE)

    assert response.status_code == 200, response.text
    assert _forwarded_params(tile_client) == {"rescale_min": 0.0, "rescale_max": 1800.0}


def test_healthy_lookup_still_hides_an_unpublished_layer(make_cliente, tile_client, db) -> None:
    layer_id = _seed_tile_layer(db, "precip_normal", "manual")

    response = make_cliente().get(_tile_url(layer_id), params=MONTHLY_RESCALE)

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Geo layer no encontrado"}
    tile_client.get.assert_not_awaited()


def test_healthy_lookup_still_rejects_an_unsupported_range(make_cliente, tile_client, db) -> None:
    layer_id = _seed_tile_layer(db, "precip_normal")

    response = make_cliente().get(
        _tile_url(layer_id), params={"rescale_min": 0, "rescale_max": 100}
    )

    assert response.status_code == 400, response.text
    assert response.json() == {"detail": UNSUPPORTED_PRECIP_DETAIL}
    tile_client.get.assert_not_awaited()


# ── 5. Programmer errors are NOT masked as outages ────────────────────────────


async def test_non_sqlalchemy_exception_is_not_swallowed(tile_client, db) -> None:
    """A programmer error must still reach the caller as a 500, not a stub tile.

    Driven at the ROUTER-FUNCTION level (the house pattern in
    ``test_geo_visualization_router.py``) rather than through ``TestClient``.
    Any exception escaping the ASGI app deadlocks this app's four stacked
    ``BaseHTTPMiddleware`` layers — verified to hang identically on an
    untouched route, so it is a harness property, not a proxy_tile behaviour.
    """
    from app.domains.geo import router_core

    class _NotADbError(Exception):
        pass

    layer_id = _seed_tile_layer(db, "precip_normal")
    session = _FailingQuerySession(db, _NotADbError("logic bug"))

    with pytest.raises(_NotADbError):
        await router_core.proxy_tile(
            layer_id=layer_id,
            z=10,
            x=0,
            y=0,
            colormap=None,
            encoding=None,
            hide_classes=None,
            hide_ranges=None,
            terrain_smoothing=None,
            rescale_min="0",
            rescale_max="200",
            db=session,
        )

    tile_client.get.assert_not_awaited()
