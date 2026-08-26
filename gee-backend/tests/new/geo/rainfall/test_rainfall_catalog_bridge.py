"""The imagery BRIDGE, catalog-backed (lluvia-eventos-extremos, B2b).

BLOCKER-1 in one sentence: `get_historic_flood_tiles_impl` used to resolve an
id by scanning the `HISTORIC_FLOODS` module literal, so the moment B2a made the
list catalog-backed, every id the list serves -- every `ext_YYYYMMDD` -- would
404 `FLOOD_NOT_FOUND` on the exact click that is this feature's payoff. This
slice rewires the lookup and deletes the literal.

Three properties carry it, and each fails silently if written the obvious way:

* **one derivation, not two** (D12). The bridge resolves through
  `catalog_view`, the SAME module the list renders with. A second rendering of
  the served contract is how the list and the bridge begin to disagree about
  which events exist -- BLOCKER-1 arriving through the other door;
* **revision-scoped** (D12's three-part rule). The lookup sees exactly the
  generation the list serves: an id from a superseded generation must NOT
  resolve while that generation is not the served one, or the bridge hands out
  tiles for a card the picker does not show;
* **the curated override survives** (spec R3 S2). `mar_2015` carries an
  explicit `days_buffer: 30` in its seeded payload; relying on the epoch
  default at `router_gee_support.py` would coincidentally produce the same 30
  today and the wrong number the day the epoch rule moves.

Real Postgres and the REAL route throughout (`TestClient`): the `db` reaching
the impl is a claim about the signature FastAPI resolved through `_gee_async`,
which a direct call to the impl cannot see.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
from tests.new.geo.rainfall.curated_payloads import curated_payload

URL = "/api/v2/geo/gee/images/historic-floods"

SCOPE = {
    "source_id": "chirps-v3-final",
    "scope_kind": "provider_asset",
    "scope_id": "zona_cc_ampliada",
    "scope_version": BASELINE_ASSET_VERSION,
}

SEALED = {
    "climatology_span_start": "1991-01-01",
    "climatology_span_end": "2026-01-01",
    "window_lengths": [1, 3, 7],
    "gap_days": 1,
    "min_window_samples": 3650,
    "tier_percentiles": {"extrema": 99.75, "alta": 98.8},
    "constants_digest": "fixture-digest",
}


def _current_revision() -> str:
    from app.domains.geo.rainfall.detector import DETECTOR_REVISION

    return DETECTOR_REVISION


def _detected(
    db,
    *,
    tier="extrema",
    start=date(2015, 3, 12),
    end=None,
    peak=None,
    percentile=99.81,
    revision=None,
    event_key=None,
    created_at=None,
):
    """Persist one complete detected row and return it."""
    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    end = start if end is None else end
    peak = start if peak is None else peak
    prefix = {"extrema": "ext", "alta": "alt"}[tier]
    stamped = {} if created_at is None else {"created_at": created_at}
    row = RainfallExtremeEvent(
        **SCOPE,
        detector_revision=_current_revision() if revision is None else revision,
        provenance="detected",
        event_key=event_key or f"{prefix}_{start:%Y%m%d}",
        tier=tier,
        start_date=start,
        end_date=end,
        peak_date=peak,
        max_percentile=percentile,
        fired_windows={
            "d3": {"peak_end": peak.isoformat(), "peak_total_mm": 180.0, "percentile": percentile}
        },
        sealed_detection_params=SEALED,
        climatology_span_start=date(1991, 1, 1),
        climatology_span_end=date(2026, 1, 1),
        **stamped,
    )
    db.add(row)
    db.flush()
    return row


def _curated(db, *, event_key="mar_2015", day=date(2015, 3, 15), payload=None):
    """Persist one curated anchor exactly as `lluvia_ext_002` seeds it."""
    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    row = RainfallExtremeEvent(
        **SCOPE,
        detector_revision="curated",
        provenance="curated",
        event_key=event_key,
        tier=None,
        start_date=day,
        end_date=day,
        # The floor comes from `curated_payloads` (shared with the dispatcher
        # and serving fixtures); `mar_2015`'s imagery overrides apply only when
        # the caller supplies no payload of its own, so an explicit payload
        # never inherits fields its assertions never asked for.
        curated_payload=curated_payload(
            **(
                {"sensor": "landsat8", "max_cloud": 80, "days_buffer": 30}
                if payload is None
                else {}
            ),
            **(payload or {}),
        ),
    )
    db.add(row)
    db.flush()
    return row


class _FloodExplorer:
    """The GEE seam, recording what the bridge asked it for."""

    def __init__(self, image_result: dict[str, Any] | None = None):
        self.image_result = image_result or {"sensor": "Sentinel-2", "tile_url": "https://t/{z}"}
        self.image_calls: list[dict] = []
        self.sar_calls: list[dict] = []

    def get_image(self, **kwargs):
        self.image_calls.append(kwargs)
        return dict(self.image_result)

    def get_sentinel1_image(self, **kwargs):
        self.sar_calls.append(kwargs)
        return {"sensor": "Sentinel-1", "tile_url": "sar"}

    @property
    def call(self) -> dict:
        assert len(self.image_calls) == 1, f"expected one call, got {self.image_calls}"
        return self.image_calls[0]


@pytest.fixture
def explorer(monkeypatch):
    """`_ensure_gee` is looked up as a module global inside `_gee_async`'s
    closure, so it is resolved per request and monkeypatching the name is enough
    to keep Earth Engine out of the test while the REAL route runs."""
    obj = _FloodExplorer()
    monkeypatch.setattr(
        "app.domains.geo.router._ensure_gee",
        lambda: {"get_image_explorer": lambda: obj},
    )
    return obj


@pytest.fixture
def db_calls():
    """How many times FastAPI resolved `Depends(get_db)` for the request.

    Task 5.2's claim is about the signature `_gee_async` rebuilt, and the only
    honest way to observe it is from the wire: if `db` is not on the impl,
    FastAPI never resolves the dependency and this counter stays at zero.
    """
    return []


@pytest.fixture
def client(db, db_calls):
    """The REAL app, an operator identity, and the test's own transaction."""
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole
    from app.db.session import get_db
    from app.main import app

    def _override_get_db():
        db_calls.append(db)
        yield db

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(role=UserRole.OPERADOR)
    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    test_client.headers.update({"Host": "localhost"})
    yield test_client
    app.dependency_overrides.clear()


def _tiles(client, flood_id: str, visualization: str = "rgb"):
    return client.get(f"{URL}/{flood_id}", params={"visualization": visualization})


# ===========================================================================
# 5.1 -- a detected catalog id resolves end to end
# ===========================================================================


def test_a_detected_catalog_id_resolves_through_the_route(client, db, explorer):
    """5.1 (spec R3 S2, BLOCKER-1). Against the module-literal scan this is a
    404: `ext_20150312` was never in `HISTORIC_FLOODS` and never could be."""
    _detected(db)

    response = _tiles(client, "ext_20150312")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["flood_info"]["id"] == "ext_20150312"
    # The imagery target is the PEAK day, the one `catalog_view` serves as
    # `date` -- centring the search on a wet spell's first day points the sensor
    # at the day before the water arrived.
    assert explorer.call["target_date"] == date(2015, 3, 12)
    assert explorer.call["sensor"] == "sentinel2"
    assert explorer.call["mode"] == "composite"
    # No `days_buffer` on a detected record (D9's ceiling), so the epoch default
    # applies: a pre-2020 event gets the long buffer.
    assert explorer.call["days_buffer"] == 30
    assert explorer.call["max_cloud"] == 60


def test_the_bridge_serves_the_same_record_the_list_serves(client, db, explorer):
    """5.1, the structural half: ONE derivation. A second rendering would drift
    from the list's the first time either side gained a field."""
    _detected(db)

    served = _tiles(client, "ext_20150312").json()["flood_info"]
    listed = client.get(URL).json()["floods"][0]

    assert served == listed


# ===========================================================================
# 5.2 -- the `db` propagates through `_gee_async`, asserted at the wire
# ===========================================================================


def test_the_route_resolves_a_db_dependency_through_gee_async(client, db, explorer, db_calls):
    """5.2. `_gee_async` (`router.py:142-154`) rebuilds the signature filtering
    out ONLY `ensure_gee`, so `db: Session = Depends(get_db)` propagates and no
    new wrapper is needed. Asserted from the request, not by reading the
    wrapper: the claim is about FastAPI's resolved signature."""
    _detected(db)

    assert db_calls == [], "nothing resolved before the request"
    assert _tiles(client, "ext_20150312").status_code == 200
    assert db_calls == [db], "FastAPI never resolved Depends(get_db) for the bridge"


# ===========================================================================
# 5.3 -- the lookup is revision-scoped
# ===========================================================================


def test_an_id_from_a_superseded_generation_does_not_resolve(client, db, explorer):
    """5.3. A bridge that scanned every revision would hand out tiles for a card
    the list does not show."""
    old = datetime(2026, 1, 1, tzinfo=UTC)
    _detected(db, revision="rev-old", start=date(2011, 4, 3), created_at=old)
    _detected(db, start=date(2015, 3, 12))

    listed = {record["id"] for record in client.get(URL).json()["floods"]}
    assert listed == {"ext_20150312"}, "precondition: only the current generation is listed"

    response = _tiles(client, "ext_20110403")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FLOOD_NOT_FOUND"
    assert explorer.image_calls == [], "no provider call for an unresolved id"


def test_the_stale_generation_the_list_serves_is_the_one_the_bridge_resolves(client, db, explorer):
    """5.3, the other direction (D12 rule 2). With no rows at the current
    revision the list serves the previous generation labelled `stale`, and the
    bridge must resolve exactly those ids -- a lookup pinned to
    `DETECTOR_REVISION` would 404 every card the picker is showing."""
    _detected(
        db, revision="rev-old", start=date(2011, 4, 3), created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )

    body = client.get(URL).json()
    assert body["revision_state"] == "stale"
    assert [record["id"] for record in body["floods"]] == ["ext_20110403"]

    assert _tiles(client, "ext_20110403").status_code == 200


# ===========================================================================
# 5.4 -- the curated bridge path, with its explicit buffer
# ===========================================================================


def test_a_curated_anchor_resolves_by_id_with_its_seeded_overrides(client, db, explorer):
    """5.4 (spec R3 S2). `mar_2015` resolves exactly as it did off the literal,
    and its 30-day buffer comes from `curated_payload.days_buffer` -- seeded
    explicitly for this reason -- not from the epoch coincidence."""
    _curated(db)

    response = _tiles(client, "mar_2015")

    assert response.status_code == 200, response.text
    assert explorer.call["sensor"] == "landsat8"
    assert explorer.call["max_cloud"] == 80
    assert explorer.call["days_buffer"] == 30
    assert explorer.call["target_date"] == date(2015, 3, 15)


def test_the_curated_buffer_is_read_from_the_payload_not_from_the_epoch_rule(client, db, explorer):
    """5.4's real killer. The epoch default would say 15 for a post-2020 event;
    an anchor that seeds 25 must get 25."""
    _curated(
        db,
        event_key="sep_2025",
        day=date(2025, 9, 5),
        payload={"name": "Septiembre 2025", "severity": "media", "days_buffer": 25},
    )

    assert _tiles(client, "sep_2025").status_code == 200
    assert explorer.call["days_buffer"] == 25


def test_the_served_record_keeps_the_curated_id_not_the_row_uuid(client, db, explorer):
    """Mutant m5. The picker restores a selection by this id; a UUID here means
    every persisted selection stops restoring after the next detector run."""
    row = _curated(db)

    body = _tiles(client, "mar_2015").json()

    assert body["flood_info"]["id"] == "mar_2015"
    assert body["flood_info"]["id"] != str(row.id)
    assert body["flood_info"]["name"] == "Inundacion Marzo 2015"


def test_the_served_buffer_never_exceeds_the_frontend_ceiling(client, db, explorer):
    """`typeGuards.ts:406-411` rejects a restored selection whose `days_buffer`
    falls outside [1, 30], and rejection there is SILENT -- the selection simply
    stops restoring. A curated payload is hand-written data, so the ceiling is
    enforced backend-side rather than trusted."""
    _curated(
        db,
        event_key="feb_2017",
        day=date(2017, 2, 20),
        payload={"name": "Febrero 2017", "severity": "alta", "days_buffer": 45},
    )

    body = _tiles(client, "feb_2017").json()

    assert explorer.call["days_buffer"] == 30
    assert body["flood_info"]["days_buffer"] == 30


def test_the_served_buffer_never_falls_below_the_frontend_floor(client, db, explorer):
    """The OTHER end of the same `[1, 30]` window, pinned for the same reason.

    `typeGuards.ts:406-411` rejects `days_buffer: 0` exactly as silently as it
    rejects 45, and a zero-day buffer is also a search window with no days in
    it -- the provider would be asked for imagery on a single instant. A clamp
    written as `min(MAX, ...)` alone, or as `max(0, ...)`, passes every ceiling
    test in this file and ships the empty window.
    """
    _curated(
        db,
        event_key="feb_2017",
        day=date(2017, 2, 20),
        payload={"name": "Febrero 2017", "severity": "alta", "days_buffer": 0},
    )

    body = _tiles(client, "feb_2017").json()

    assert explorer.call["days_buffer"] == 1
    assert body["flood_info"]["days_buffer"] == 1


# ===========================================================================
# 5.4, the precedence the list already applies -- at the bridge
# ===========================================================================


def test_a_suppressed_detected_id_resolves_to_the_card_that_suppressed_it(client, db, explorer):
    """D8's precedence, at the BRIDGE.

    `feb_2017`'s rain fired on 02-18 while the anchor is dated 02-20, so the
    list serves ONE card -- the curated one -- and suppresses `ext_20170218`
    behind it. A bridge that resolved that id off the raw detected rows would
    hand back a record centred on a DIFFERENT date, with a different buffer and
    a different sensor than the card the picker rendered: two surfaces, one
    click, two answers. The suppressed id resolves to the SAME record the list
    serves.
    """
    _curated(
        db,
        event_key="feb_2017",
        day=date(2017, 2, 20),
        payload={
            "name": "Inundacion Febrero 2017",
            "severity": "alta",
            "sensor": "landsat8",
            "days_buffer": 20,
        },
    )
    _detected(db, start=date(2017, 2, 18))

    listed = client.get(URL).json()["floods"]
    assert [record["id"] for record in listed] == ["feb_2017"], (
        "precondition: the detected row is suppressed behind the curated card"
    )

    body = _tiles(client, "ext_20170218").json()

    assert body["flood_info"]["id"] == "feb_2017"
    assert body["flood_info"]["date"] == "2017-02-20", "the CURATED date, not the detected peak"
    assert body["flood_info"] == listed[0], "the same record, field for field"
    assert explorer.call["target_date"] == date(2017, 2, 20)
    assert explorer.call["sensor"] == "landsat8"
    assert explorer.call["days_buffer"] == 20


def test_a_detected_id_outside_the_tolerance_still_resolves_as_itself(client, db, explorer):
    """The other half of the same rule: only a SUPPRESSED id redirects.

    `ext_20170310` is 18 days from the anchor -- outside
    `CONFIRMATION_TOLERANCE_DAYS`, so the list gives it its own card and the
    bridge must keep resolving it to its own record. A redirect written as
    "any detected row while a curated anchor exists" would swallow it.
    """
    _curated(
        db,
        event_key="feb_2017",
        day=date(2017, 2, 20),
        payload={"name": "Inundacion Febrero 2017", "severity": "alta"},
    )
    _detected(db, start=date(2017, 3, 10))

    listed = {record["id"] for record in client.get(URL).json()["floods"]}
    assert listed == {"feb_2017", "ext_20170310"}, "precondition: two cards, nothing suppressed"

    body = _tiles(client, "ext_20170310").json()

    assert body["flood_info"]["id"] == "ext_20170310"
    assert body["flood_info"]["provenance"] == "detected"
    assert explorer.call["target_date"] == date(2017, 3, 10)


# ===========================================================================
# The error contract is unchanged
# ===========================================================================


def test_an_unknown_id_is_still_flood_not_found(client, db, explorer):
    """The existing contract, carried verbatim: a catalog id that does not exist
    is a 404 `FLOOD_NOT_FOUND`, never a 500."""
    _detected(db)

    response = _tiles(client, "no_existe")

    assert response.status_code == 404
    payload = response.json()["error"]
    assert payload["code"] == "FLOOD_NOT_FOUND"
    assert payload["details"] == {
        "resource_type": "historic_flood",
        "resource_id": "no_existe",
    }
    assert explorer.image_calls == []


def test_an_empty_catalog_is_a_not_found_rather_than_a_crash(client, db, explorer):
    """No generation at all (`revision_state: "empty"`) is the deploy-day state;
    the bridge answers the same 404 the list answers with an absence."""
    response = _tiles(client, "ext_20150312")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FLOOD_NOT_FOUND"
