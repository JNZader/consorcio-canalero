"""§2.6 error-contract integration tests for the ficha territorial (PR A3a-ii).

`spec geo-analysis-endpoint` › "Explicit error contract" (JD-A-006): every row of
the §2.6 table MUST have an integration test, and each failure MUST answer with the
FLAT body ``{"detail", "codigo", ...}``.

**PURELY BEHAVIORAL (TestClient), never a route-table walk** — same CI
module-identity pathology documented at length in
``test_ficha_router_contract.py``: building an app and iterating ``app.routes``
comes back EMPTY even while a ``TestClient`` on the SAME app serves the route.
So the contract is proven only by response codes/bodies from a locally built app
(``_app_de_ficha``), never by ``app.main`` and never by inspecting the route table.

**Feature flag.** The route is gated OFF by default (``settings.ficha_enabled``),
and ``enforce_ficha_enabled`` is the FIRST dependency — so a disabled deployment
answers 503 ``funcionalidad_no_disponible`` before anything else. Every test that
needs the pipeline to actually run turns the flag ON via monkeypatch.

**What is tested where (be honest about the A3a-ii boundary):**
* rows enforced on the caller-supplied polygon (413 ``cuerpo_excedido``, 429
  ``limite_de_tasa``, 422 ``tipo_desconocido`` / ``geometria_invalida`` /
  ``cap_excedido`` for buffer_m + vertices, 503 ``sobrecarga``) are exercised
  end-to-end through the wire;
* ``cap_excedido`` for ``area_ha`` is SERVER-DERIVED — it runs over a resolved
  shapely geometry in EPSG:32720, and geometry resolution is A3b/A5/A6/A7. It is
  therefore proven as a unit assertion on ``assert_within_caps`` here, and lands
  on the wire in a later slice;
* true bow-tie SELF-INTERSECTION normalization (``ST_MakeValid`` →
  ``ST_CollectionExtract``) is A5/PostGIS; the cheap schema validators own the
  MALFORMED-geometry class (unclosed ring, out-of-range coordinate, wrong type),
  which is what the wire ``geometria_invalida`` test drives now;
* the remaining rows (404 ``parcela_no_encontrada`` / ``canal_no_encontrado``,
  409 ``variante_no_disponible``, 503 ``dataset_no_cargado`` / ``raster_ilegible``)
  need geometry resolution or a raster loop and are completed in A3b/A6/A7. Their
  constructors are already unit-covered by shape in ``ficha_errors``.
"""

from __future__ import annotations

from typing import Any

import pytest

FICHA_PATH = "/api/v2/geo/analisis-zona"

# A minimal, well-formed polygon (closed ring, 4 positions, in WGS84 range). Used
# as the "otherwise valid" body so a test isolates the ONE failure it is about.
POLIGONO_OK = {
    "tipo": "poligono",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[-62.0, -32.0], [-62.0, -32.1], [-61.9, -32.1], [-62.0, -32.0]]],
    },
}


def _app_de_ficha(db: Any = None) -> Any:
    """Fresh app with ONLY the geo router mounted — never ``app.main``.

    Mirrors the two installers ``app.main`` calls (error handler + OpenAPI
    schemas), because handlers belong to an app, not to a router. See the module
    docstring of ``test_ficha_router_contract`` for why this is behavioral-only.
    """
    from fastapi import FastAPI

    from app.db.session import get_db
    from app.domains.geo.ficha_errors import install_ficha_error_handler
    from app.domains.geo.router import router as geo_router
    from app.domains.geo.router_ficha import install_ficha_openapi_schemas

    app = FastAPI()
    app.include_router(geo_router, prefix="/api/v2/geo")
    install_ficha_error_handler(app)
    install_ficha_openapi_schemas(app)
    if db is not None:
        app.dependency_overrides[get_db] = lambda: db
    return app


def _limitador_en_memoria(monkeypatch: Any) -> Any:
    """Force the ficha route onto a FRESH in-memory limiter, isolated per test.

    ``redis_url=None`` makes ``_get_redis`` return ``None`` so the sliding window
    is the per-process in-memory dict — no shared Redis state leaks between tests,
    and the counter is deterministic. Its own ``key_prefix`` keeps it clear of the
    real ``ratelimit:ficha:`` namespace.
    """
    from app.config import settings
    from app.core.rate_limit import DistributedRateLimiter
    from app.domains.geo import router_ficha

    limitador = DistributedRateLimiter(
        redis_url=None,
        max_requests=settings.ficha_rate_limit_requests,
        window_seconds=settings.ficha_rate_limit_window,
        key_prefix="ratelimit:ficha:test:",
    )
    monkeypatch.setattr(router_ficha, "get_ficha_rate_limiter", lambda: limitador)
    return limitador


def _cuerpo_plano(respuesta: Any) -> dict[str, Any]:
    """Assert the §2.6 body is FLAT (``detail`` + ``codigo`` at top level)."""
    cuerpo = respuesta.json()
    assert "detail" in cuerpo, f"contrato §2.6 plano roto: {cuerpo}"
    assert "codigo" in cuerpo, f"contrato §2.6 plano roto: {cuerpo}"
    return cuerpo


# ── 413 cuerpo_excedido — rejected BEFORE parsing (JDB-007) ──────────────────


def test_413_cuerpo_excedido(db, monkeypatch):
    """§2.6 413 — a declared Content-Length over the cap dies before parsing."""
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", True, raising=False)
    # Shrink the cap instead of shipping a >1 MiB body: the guard reads the
    # declared Content-Length, so any real body now trips it.
    monkeypatch.setattr(settings, "ficha_max_body_bytes", 8)

    with TestClient(_app_de_ficha(db)) as cliente:
        respuesta = cliente.post(FICHA_PATH, json=POLIGONO_OK)

    assert respuesta.status_code == 413
    assert _cuerpo_plano(respuesta)["codigo"] == "cuerpo_excedido"


# ── 429 limite_de_tasa — with Retry-After (JDB-020) ──────────────────────────


def test_429_limite_de_tasa_con_retry_after(db, monkeypatch):
    """§2.6 429 — exhausting the ficha limiter yields 429 + a ``Retry-After`` header.

    ``poligono`` is priced at cost 5 (design §2.2), so 6 requests reach the 30/min
    window and the 7th tips over. The FIRST 429 must carry ``Retry-After`` and the
    ``limite_de_tasa`` code.
    """
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", False, raising=False)
    _limitador_en_memoria(monkeypatch)

    # ``raise_server_exceptions=False``: since A5 ``poligono`` is REAL compute, and
    # this test's ``db`` has no ``suelos_catastro`` seeded, the first six accepted
    # requests may answer 5xx from compute. That is irrelevant here — the limiter
    # increments in a router DEPENDENCY that runs BEFORE the handler, so the window
    # still fills and the 7th request is 429 regardless of compute outcome. Keeping
    # the assertion on the 429 (not on the earlier statuses) decouples this limiter
    # test from compute and from which tipos are placeholders in later slices.
    limitada = None
    with TestClient(_app_de_ficha(db), raise_server_exceptions=False) as cliente:
        for _ in range(8):  # cost 5 × 6 = 30 allowed; the 7th is over the window
            respuesta = cliente.post(FICHA_PATH, json=POLIGONO_OK)
            if respuesta.status_code == 429:
                limitada = respuesta
                break

    assert limitada is not None, "el limitador nunca se agoto en 8 pedidos de costo 5"
    assert _cuerpo_plano(limitada)["codigo"] == "limite_de_tasa"
    assert "retry-after" in {k.lower() for k in limitada.headers}, "falta el header Retry-After"


# ── 422 tipo_desconocido — reaches parse_ficha_body via the wire ─────────────


def test_422_tipo_desconocido_por_el_cable(db, monkeypatch):
    """§2.6 422 — an unknown ``tipo`` reaches ``parse_ficha_body`` (not just the adapter).

    The existing contract test proves the TypeAdapter rejects it; this proves the
    stable wire ``codigo`` and the flat body come back through a real request.
    """
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", True, raising=False)

    with TestClient(_app_de_ficha(db)) as cliente:
        respuesta = cliente.post(FICHA_PATH, json={"tipo": "provincia", "nomenclatura": "X"})

    assert respuesta.status_code == 422
    cuerpo = _cuerpo_plano(respuesta)
    assert cuerpo["codigo"] == "tipo_desconocido"
    assert "parcela" in cuerpo["tipos_validos"]


# ── 422 geometria_invalida — the malformed-geometry class the schema owns now ──


@pytest.mark.parametrize(
    ("motivo", "anillo"),
    [
        # Coordinate outside WGS84 range.
        ("fuera_de_rango", [[-62.0, -32.0], [999.0, -32.1], [-61.9, -32.1], [-62.0, -32.0]]),
        # Ring that does not close (first != last).
        ("no_cerrado", [[-62.0, -32.0], [-62.0, -32.1], [-61.9, -32.1]]),
    ],
)
def test_422_geometria_invalida(db, monkeypatch, motivo, anillo):
    """§2.6 422 — a malformed polygon answers ``geometria_invalida`` before any I/O.

    NOTE (A3a-ii boundary): a true bow-tie SELF-INTERSECTION is not detectable by
    the cheap schema validators — that needs ``ST_MakeValid`` +
    ``ST_CollectionExtract`` and lands in A5. What the schema owns TODAY is the
    malformed class (out-of-range coordinate, unclosed ring, wrong type), and that
    is what this asserts on the wire.
    """
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", True, raising=False)

    cuerpo = {"tipo": "poligono", "geometry": {"type": "Polygon", "coordinates": [anillo]}}
    with TestClient(_app_de_ficha(db)) as cliente:
        respuesta = cliente.post(FICHA_PATH, json=cuerpo)

    assert respuesta.status_code == 422, motivo
    assert _cuerpo_plano(respuesta)["codigo"] == "geometria_invalida"


# ── 422 cap_excedido — vertices + buffer_m on the wire, area server-derived ──


def test_422_cap_excedido_vertices_por_el_cable(db, monkeypatch):
    """§2.6 422 — a polygon over the vertex cap answers ``cap_excedido``/``vertices``."""
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", True, raising=False)

    anillo = [[-62.0 + i * 1e-6, -32.0] for i in range(settings.ficha_max_vertices + 2)]
    anillo.append(anillo[0])
    cuerpo = {"tipo": "poligono", "geometry": {"type": "Polygon", "coordinates": [anillo]}}

    with TestClient(_app_de_ficha(db)) as cliente:
        respuesta = cliente.post(FICHA_PATH, json=cuerpo)

    assert respuesta.status_code == 422
    body = _cuerpo_plano(respuesta)
    assert body["codigo"] == "cap_excedido"
    assert body["cap"] == "vertices"


def test_422_cap_excedido_buffer_m_por_el_cable(db, monkeypatch):
    """§2.6 422 — ``buffer_m`` over ``ficha_max_buffer_m`` answers ``cap_excedido``/``buffer_m``."""
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", True, raising=False)

    cuerpo = {
        "tipo": "canal_buffer",
        "canal_id": 1,
        "buffer_m": settings.ficha_max_buffer_m + 1.0,
    }
    with TestClient(_app_de_ficha(db)) as cliente:
        respuesta = cliente.post(FICHA_PATH, json=cuerpo)

    assert respuesta.status_code == 422
    body = _cuerpo_plano(respuesta)
    assert body["codigo"] == "cap_excedido"
    assert body["cap"] == "buffer_m"


def test_422_cap_excedido_area_es_server_derivado():
    """§2.6 422 — the AREA cap runs over a resolved metric geometry (unit level).

    Area cannot be checked on the wire in this slice: it needs a geometry resolved
    and projected to EPSG:32720, which is A3b/A5/A6/A7. ``assert_within_caps`` is
    that authority, so the guarantee is proven directly on a shapely square whose
    metric area exceeds ``ficha_max_area_ha`` (and stays under the envelope cap so
    the AREA branch is the one that fires).
    """
    from shapely.geometry import box

    from app.config import settings
    from app.domains.geo import ficha_service
    from app.domains.geo.ficha_errors import FichaError

    # A square of side S metres → area S²/10 000 ha. Pick S so area > area cap but
    # the (equal) envelope stays under the envelope cap.
    lado = 20_000.0  # 40 000 ha area < 60 000 ha envelope cap, > 20 000 ha area cap
    geom = box(0.0, 0.0, lado, lado)
    assert geom.area / ficha_service.M2_POR_HA > settings.ficha_max_area_ha
    assert geom.area / ficha_service.M2_POR_HA <= settings.ficha_max_envelope_ha

    with pytest.raises(FichaError) as excinfo:
        ficha_service.assert_within_caps(geom, tipo="poligono")

    assert excinfo.value.status_code == 422
    assert excinfo.value.codigo == "cap_excedido"
    assert excinfo.value.extra["cap"] == "area_ha"


# ── 503 sobrecarga — the in-flight semaphore is saturated ────────────────────


def test_503_sobrecarga_semaforo_saturado(db, monkeypatch):
    """§2.6 503 — a full compute semaphore answers ``sobrecarga`` after the timeout.

    Concurrency is pinned to 1 and the single slot is drained by the test thread,
    so the request's ``slot_de_computo`` times out and raises ``sobrecarga``. The
    audit row is written first by design (before the semaphore), which is fine —
    this asserts only the 503 code and its ``retry_after``.

    A3b boundary: ``tipo=parcela`` now resolves the catastro geometry BEFORE the
    semaphore (§2.5 order), so an unseeded parcela would 404 first. ``poligono``
    keeps the placeholder path (audit → semaphore → placeholder) and reaches the
    slot with no DB lookup, so it isolates the semaphore exactly as before.
    """
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.domains.geo import ficha_service

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", True, raising=False)
    monkeypatch.setattr(settings, "ficha_max_concurrency", 1)
    ficha_service.reset_ficha_slots()

    slots = ficha_service.get_ficha_slots()
    assert slots.acquire(blocking=False), "no se pudo drenar el unico slot"
    try:
        with TestClient(_app_de_ficha(db)) as cliente:
            respuesta = cliente.post(FICHA_PATH, json=POLIGONO_OK)
    finally:
        slots.release()
        ficha_service.reset_ficha_slots()

    assert respuesta.status_code == 503
    cuerpo = _cuerpo_plano(respuesta)
    assert cuerpo["codigo"] == "sobrecarga"
    assert cuerpo["retry_after"] >= 1


# ── Enforcement ORDER: 413 before 429, 429 before 422 ────────────────────────


def test_413_precede_a_429(db, monkeypatch):
    """Order — an oversized body is 413 and the limiter is NEVER consulted.

    ``enforce_body_limit`` (413) is an earlier dependency than
    ``enforce_ficha_rate_limit`` (429), so the body guard short-circuits before the
    limiter is ever consulted. The fresh limiter's ``check`` is wrapped with a spy;
    a 413 with the spy untouched is the ordering proof (no cross-loop prefill).
    """
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", False, raising=False)
    monkeypatch.setattr(settings, "ficha_max_body_bytes", 8)

    limitador = _limitador_en_memoria(monkeypatch)
    consultado = {"veces": 0}
    real_check = limitador.check

    async def check_espia(identifier, cost=1):
        consultado["veces"] += 1
        return await real_check(identifier, cost)

    monkeypatch.setattr(limitador, "check", check_espia)

    with TestClient(_app_de_ficha(db)) as cliente:
        respuesta = cliente.post(FICHA_PATH, json=POLIGONO_OK)

    assert respuesta.status_code == 413, "413 debe ganarle a 429 (dependencia mas temprana)"
    assert _cuerpo_plano(respuesta)["codigo"] == "cuerpo_excedido"
    assert consultado["veces"] == 0, "el limitador se consulto pese al 413 (orden roto)"


def test_429_precede_a_422(db, monkeypatch):
    """Order — an exhausted limiter is 429 even when the body is an unknown ``tipo``.

    ``enforce_ficha_rate_limit`` (429) is a router dependency; ``parse_ficha_body``
    (422) runs as a handler parameter, i.e. after all dependencies. So a
    rate-limited request never reaches the parser: unknown-``tipo`` → 429, not 422.
    The limiter is exhausted with real ``poligono`` POSTs (cost 5 × 6 = 30) inside
    the SAME TestClient loop — no cross-loop async prefill.
    """
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", False, raising=False)
    _limitador_en_memoria(monkeypatch)

    # Same decoupling as ``test_429_limite_de_tasa_con_retry_after``: since A5 made
    # ``poligono`` real compute, the six accepted requests only need to be NOT
    # rate-limited (whatever compute answers on an unseeded DB is beside the point);
    # the claim under test is that the SEVENTH — an unknown tipo — is 429 (limiter,
    # a dependency) rather than 422 (parser, a handler param).
    with TestClient(_app_de_ficha(db), raise_server_exceptions=False) as cliente:
        for _ in range(6):  # cost 5 × 6 = 30 → fills the window exactly
            assert cliente.post(FICHA_PATH, json=POLIGONO_OK).status_code != 429
        # An unknown tipo would be 422 at the parser — but the limiter (now full)
        # runs first and answers 429 before the parser is ever reached.
        respuesta = cliente.post(FICHA_PATH, json={"tipo": "provincia", "nomenclatura": "X"})

    assert respuesta.status_code == 429, "429 debe ganarle a 422 (dependencia antes del parser)"
    assert _cuerpo_plano(respuesta)["codigo"] == "limite_de_tasa"


# ── A3a.9 limiter isolation — the ficha limiter never throttles its siblings ──


def test_el_limitador_de_ficha_no_estrangula_a_las_hermanas(db, monkeypatch):
    """spec › "Existing geo endpoints unaffected" (JDB-003) — behavioral.

    The ficha limiter lives on the dedicated ficha router only. Exhausting it (via
    real ficha POSTs, same loop) must NOT throttle a sibling ``/api/v2/geo`` route.
    A public sibling is used so no 401 masks the check; ``raise_server_exceptions=
    False`` because a sibling can 500 on a table absent from the test schema — that
    is not a 429, which is the only thing this asserts.
    """
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", False, raising=False)
    _limitador_en_memoria(monkeypatch)

    hermana = "/api/v2/geo/layers/public"
    with TestClient(_app_de_ficha(db), raise_server_exceptions=False) as cliente:
        # Drive the ficha limiter past its window (cost 5, so ≥7 POSTs → 429).
        limitada = False
        for _ in range(8):
            if cliente.post(FICHA_PATH, json=POLIGONO_OK).status_code == 429:
                limitada = True
                break
        assert limitada, "prep: la ficha deberia haberse limitado en 8 pedidos"
        # The sibling must not be throttled by the same exhausted ficha limiter.
        rs = cliente.get(hermana)

    assert rs.status_code != 429, (
        f"{hermana} fue estrangulada por el limitador de la ficha (dio 429)"
    )
