"""Rank-and-persist shortlist of GEE scenes for extreme-rainfall events.

No Earth Engine in this module: the ranker is a pure function of metadata,
and persist/GET talk only to Postgres. The CLI injects a lister.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.domains.geo.rainfall.imagery_shortlist import (
    CLOUD_BASIS,
    SCORER_REVISION,
    SceneHit,
    load_candidates,
    rank_scenes,
    replace_candidates,
    shortlist_payload,
)


PEAK = date(2015, 3, 14)


def test_clear_s2_on_peak_beats_cloudy_s2_and_outranks_out_of_window() -> None:
    ranked = rank_scenes(
        PEAK,
        [
            SceneHit("sentinel2", "S2_CLEAR", PEAK, 5.0),
            SceneHit("sentinel2", "S2_CLOUDY", PEAK, 70.0),
            SceneHit("sentinel2", "S2_LATE", date(2015, 4, 10), 5.0),
        ],
    )

    assert [row.scene_id for row in ranked] == ["S2_CLEAR", "S2_CLOUDY"]
    assert ranked[0].rank == 1
    assert ranked[0].score > ranked[1].score


def test_sar_beats_very_cloudy_optical_on_the_same_day() -> None:
    ranked = rank_scenes(
        PEAK,
        [
            SceneHit("sentinel2", "S2_SOUP", PEAK, 90.0),
            SceneHit("sentinel1", "S1_VV", PEAK, None),
        ],
    )

    assert ranked[0].scene_id == "S1_VV"
    assert ranked[0].cloud_pct is None


def test_pre_event_optical_is_kept_but_loses_to_post_event() -> None:
    ranked = rank_scenes(
        PEAK,
        [
            SceneHit("sentinel2", "BEFORE", date(2015, 3, 13), 10.0),
            SceneHit("sentinel2", "AFTER", date(2015, 3, 15), 10.0),
        ],
    )

    assert [row.scene_id for row in ranked] == ["AFTER", "BEFORE"]


def test_unknown_optical_cloud_does_not_outrank_known_clear() -> None:
    ranked = rank_scenes(
        PEAK,
        [
            SceneHit("sentinel2", "UNKNOWN", PEAK, None),
            SceneHit("sentinel2", "CLEAR", PEAK, 8.0),
        ],
    )

    assert ranked[0].scene_id == "CLEAR"


def test_top_n_caps_at_three() -> None:
    hits = [SceneHit("sentinel2", f"S{i}", PEAK, float(i)) for i in range(8)]
    ranked = rank_scenes(PEAK, hits)
    assert [row.rank for row in ranked] == [1, 2, 3]
    assert len(ranked) == 3


def test_replace_candidates_is_a_new_generation(db) -> None:
    first = rank_scenes(PEAK, [SceneHit("sentinel2", "OLD", PEAK, 5.0)])
    replace_candidates(db, "ext_20150314", first)
    db.flush()

    second = rank_scenes(
        PEAK,
        [
            SceneHit("sentinel1", "NEW_S1", PEAK, None),
            SceneHit("sentinel2", "NEW_S2", PEAK, 12.0),
        ],
    )
    replace_candidates(db, "ext_20150314", second)
    db.flush()

    loaded = load_candidates(db, "ext_20150314")
    assert [row.scene_id for row in loaded] == ["NEW_S1", "NEW_S2"]
    assert all(row.scorer_revision == SCORER_REVISION for row in loaded)
    assert all(row.cloud_basis == CLOUD_BASIS for row in loaded)


def test_shortlist_payload_is_jsonable() -> None:
    ranked = rank_scenes(PEAK, [SceneHit("sentinel2", "S2_CLEAR", PEAK, 5.0)])
    body = shortlist_payload("ext_20150314", ranked)
    assert body["event_id"] == "ext_20150314"
    assert body["scorer_revision"] == SCORER_REVISION
    assert body["cloud_basis"] == "scene_metadata"
    assert body["candidates"][0]["sensor"] == "sentinel2"
    assert body["candidates"][0]["scene_date"] == "2015-03-14"
    assert body["candidates"][0]["visualization"] == "rgb"


def test_cli_run_for_one_event_uses_the_injected_lister(db) -> None:
    from app.domains.geo.rainfall.imagery_shortlist_cli import shortlist_event

    event = SimpleNamespace(
        id="ext_20150314",
        date="2015-03-14",
        peak_date="2015-03-14",
        imagery_candidate=True,
    )

    def fake_lister(sensor: str, start: date, end: date) -> list[SceneHit]:
        if sensor == "sentinel2":
            return [SceneHit("sentinel2", "S2", PEAK, 6.0)]
        if sensor == "sentinel1":
            return [SceneHit("sentinel1", "S1", PEAK, None)]
        return []

    written = shortlist_event(db, event, list_scenes=fake_lister)
    db.flush()
    assert [row.scene_id for row in written] == ["S2", "S1"]


def test_cli_skips_pre2015_non_candidates(db) -> None:
    from app.domains.geo.rainfall.imagery_shortlist_cli import shortlist_event

    event = SimpleNamespace(
        id="ext_19940101",
        date="1994-01-01",
        peak_date="1994-01-01",
        imagery_candidate=False,
    )
    written = shortlist_event(db, event, list_scenes=lambda *_a, **_k: [_ for _ in ()])
    assert written == []
    assert load_candidates(db, "ext_19940101") == []


CANDIDATES_URL = "/api/v2/geo/gee/images/historic-floods/{flood_id}/candidates"


def _curated_anchor(db, event_key: str = "mar_2015") -> None:
    from app.domains.geo.rainfall.models import RainfallExtremeEvent
    from tests.new.geo.rainfall.curated_payloads import curated_payload

    db.add(
        RainfallExtremeEvent(
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id="zona_cc_ampliada",
            scope_version="v1",
            detector_revision="curated",
            provenance="curated",
            event_key=event_key,
            start_date=date(2015, 3, 15),
            end_date=date(2015, 3, 15),
            curated_payload=curated_payload(
                name="Inundacion Marzo 2015",
                description="x",
                severity="alta",
                sensor="landsat8",
                max_cloud=80,
                days_buffer=30,
            ),
        )
    )
    db.flush()


@pytest.fixture
def operator_client(db):
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole
    from app.db.session import get_db
    from app.main import app

    def _override_get_db():
        yield db

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(role=UserRole.OPERADOR)
    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    yield client
    app.dependency_overrides.clear()


def test_candidates_route_is_401_without_auth() -> None:
    from app.main import app

    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    response = client.get(CANDIDATES_URL.format(flood_id="mar_2015"))
    assert response.status_code == 401


def test_candidates_route_404_when_event_missing(operator_client) -> None:
    response = operator_client.get(CANDIDATES_URL.format(flood_id="nope"))
    assert response.status_code == 404


def test_candidates_route_empty_when_cli_has_not_run(operator_client, db) -> None:
    _curated_anchor(db)
    response = operator_client.get(CANDIDATES_URL.format(flood_id="mar_2015"))
    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == "mar_2015"
    assert body["candidates"] == []
    assert body["cloud_basis"] == "scene_metadata"


def test_candidates_route_returns_persisted_shortlist(operator_client, db) -> None:
    _curated_anchor(db)
    ranked = rank_scenes(date(2015, 3, 15), [SceneHit("sentinel2", "S2", date(2015, 3, 15), 4.0)])
    replace_candidates(db, "mar_2015", ranked)
    db.flush()

    response = operator_client.get(CANDIDATES_URL.format(flood_id="mar_2015"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidates"][0]["scene_id"] == "S2"
    assert body["candidates"][0]["rank"] == 1
