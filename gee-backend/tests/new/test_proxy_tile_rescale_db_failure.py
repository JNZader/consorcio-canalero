"""``proxy_tile`` degrades gracefully when the layer-tipo DB lookup fails.

The tile proxy resolves the layer's ``tipo`` from the database only to pick the
CANONICAL rescale override for that type. Before this fix a transient
``SQLAlchemyError`` during that lookup bubbled out as a 500.

SCOPE — this suite proves a ROUTER-LEVEL contract, not end-to-end survival of a
database outage. The upstream tile client is stubbed to a fixed 200, so a
"200 + png" assertion here means "the router forwarded the request without the
rescale override", nothing more about what a real geo-worker would answer.

That distinction matters because the worker is NOT independent of this
database: ``tile_service._get_layer`` opens its own ``SessionLocal`` against the
SAME Postgres and 404s when it cannot read the row, and ``proxy_tile`` maps any
upstream ``>= 400`` to a 204. During a real outage the only requests that still
produce pixels are the ones the worker can answer from its byte cache before it
touches the database — and, since the cache key embeds the rescale token, only
the no-override (``r=-``) variant of a tile. Everything else degrades from a
500 to a blank 204: strictly no worse, but not "default rendering".

What these tests actually pin:

  * the router forwards instead of raising when the lookup fails;
  * the forwarded params OMIT the rescale override, but keep every other
    caller-supplied rendering param;
  * the degradation is LOGGED (silent degradation is forbidden) and the warning
    is THROTTLED — this route is exempt from the rate limiter, so one emit per
    tile would be a log flood;
  * degradation is not sticky — the next request re-attempts the lookup and
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

    router_core._reset_rescale_lookup_warn_throttle()
    yield
    router_core._reset_rescale_lookup_warn_throttle()


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


# ── 1. DB failure degrades to a default-rendered tile, never a 500 ───────────


@pytest.mark.parametrize(
    "exc",
    [
        OperationalError("connection refused", None, Exception("boom")),
        SQLAlchemyError("db down"),
    ],
    ids=["operational_error", "generic_sqlalchemy_error"],
)
def test_db_failure_forwards_tile_without_rescale_override(
    make_cliente, tile_client, db, exc: Exception
) -> None:
    layer_id = _seed_tile_layer(db, "precip_normal")
    session = _FailingQuerySession(db, exc)

    response = make_cliente(session).get(_tile_url(layer_id), params=MONTHLY_RESCALE)

    assert response.status_code == 200, response.text
    assert response.content == b"png"
    assert _forwarded_params(tile_client) == {}


def test_db_failure_keeps_other_rendering_params(make_cliente, tile_client, db) -> None:
    """Only the rescale override is dropped — the rest of the render is intact."""
    layer_id = _seed_tile_layer(db, "precip_normal")
    session = _FailingQuerySession(db, OperationalError("blip", None, Exception("boom")))

    response = make_cliente(session).get(
        _tile_url(layer_id),
        params={**ANNUAL_RESCALE, "colormap": "viridis", "terrain_smoothing": "on"},
    )

    assert response.status_code == 200, response.text
    assert _forwarded_params(tile_client) == {
        "colormap": "viridis",
        "terrain_smoothing": "on",
    }


# ── 2. Degradation is observable — silent degradation is forbidden ───────────


def _degraded_records(caplog) -> list:
    """The structlog event dicts emitted by the degradation branch.

    ``get_logger`` wraps the stdlib logger with structlog's
    ``ProcessorFormatter``, so ``record.msg`` is the event dict itself and the
    bound fields can be asserted directly instead of through a rendered string.
    """
    out = []
    for record in caplog.records:
        event = record.msg
        if isinstance(event, dict) and event.get("event", "").startswith("Tile rescale layer"):
            out.append(event)
    return out


def test_db_failure_is_logged_as_a_warning(make_cliente, tile_client, db, caplog) -> None:
    layer_id = _seed_tile_layer(db, "precip_normal")
    session = _FailingQuerySession(db, OperationalError("connection refused", None, None))

    with caplog.at_level(logging.WARNING, logger="app.domains.geo.router_core"):
        response = make_cliente(session).get(_tile_url(layer_id), params=MONTHLY_RESCALE)

    assert response.status_code == 200, response.text
    degraded = _degraded_records(caplog)
    assert len(degraded) == 1, caplog.text
    assert degraded[0]["layer_id"] == str(layer_id)
    assert degraded[0]["error_type"] == "OperationalError"
    # First failure after the latch reset: nothing was suppressed before it.
    assert degraded[0]["suppressed_since_last"] == 0


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
            assert cliente.get(_tile_url(layer_id), params=MONTHLY_RESCALE).status_code == 200

    # Every tile degraded, but only the first one was logged.
    assert session.query_calls == 5
    assert len(_degraded_records(caplog)) == 1, caplog.text


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
        monkeypatch.setattr(router_core, "_RESCALE_LOOKUP_WARN_INTERVAL_S", 0.0)
        cliente.get(_tile_url(layer_id), params=MONTHLY_RESCALE)  # logged again

    degraded = _degraded_records(caplog)
    assert len(degraded) == 2, caplog.text
    assert degraded[0]["suppressed_since_last"] == 0
    assert degraded[1]["suppressed_since_last"] == 1


# ── 3. Degradation is not sticky ─────────────────────────────────────────────


def test_recovered_db_forwards_the_canonical_rescale(make_cliente, tile_client, db) -> None:
    layer_id = _seed_tile_layer(db, "precip_normal")
    session = _FailingQuerySession(db, OperationalError("transient blip", None, None))
    cliente = make_cliente(session)

    degraded = cliente.get(_tile_url(layer_id), params=MONTHLY_RESCALE)
    assert degraded.status_code == 200, degraded.text
    assert _forwarded_params(tile_client) == {}

    session.heal()
    recovered = cliente.get(_tile_url(layer_id), params=MONTHLY_RESCALE)

    assert recovered.status_code == 200, recovered.text
    assert _forwarded_params(tile_client) == {"rescale_min": 0.0, "rescale_max": 200.0}
    assert session.query_calls == 2


# ── 4. The healthy paths are untouched by the degradation branch ─────────────


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


# ── 5. Programmer errors are NOT masked as default-rendered tiles ────────────


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
