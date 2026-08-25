"""The SERVED historic-floods contract, catalog-backed (lluvia-eventos-extremos, B2a).

This is the slice where the served list stops being three module literals and
becomes a read over `rainfall_extreme_event`. Everything that pins the served
contract lives here, because a served contract split across two merge windows
turns `main` red in between (tasks.md risk #2).

Four properties carry the slice, and each one fails SILENTLY if it is written
the obvious way:

* **the generation rule** (D12). An empty current generation serves the
  previous one, LABELLED stale, and never an empty list — the deploy-ordering
  hazard the hand-run CLI creates (deploy code -> run the detector -> flip to
  `current`). A handler that filtered on `DETECTOR_REVISION` alone would serve
  a blank picker with a 200 and no error anywhere;
* **read-time synthesis** (D10). `isHistoricFlood`
  (`useImageExplorerController.tsx:48-56`) requires `name: string` and drops
  any record without one — silently, with no error. A nameless detected row is
  therefore not a cosmetic defect, it is an invisible one;
* **the frontend-anchored severity map** (D9). `ImageExplorerInfoPanels.tsx`
  styles exactly `alta` -> red and `media` -> orange, everything else -> the
  palest yellow, so serving the true tier `extrema` on the wire paints the most
  extreme events the faintest colour available;
* **confirmation derived at read with a ±3-day tolerance** (spec R4, ratified
  2026-08-26). `feb_2017`'s rain fired on 02-18 and the curated anchor is dated
  02-20; a strict same-date rule hides a real confirmation behind a dating
  technicality, and a loose one confirms `mar_2015` from 8 days away.

Real Postgres and the REAL router throughout: every contract assertion goes
through `TestClient` against the registered route, because the claims are about
FastAPI's resolved signature, the response headers and the serialized payload —
none of which a direct call to the impl can see.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION

URL = "/api/v2/geo/gee/images/historic-floods"

SCOPE = {
    "source_id": "chirps-v3-final",
    "scope_kind": "provider_asset",
    "scope_id": "zona_cc_ampliada",
    "scope_version": BASELINE_ASSET_VERSION,
}

#: The sealed block a detected row carries. A literal, not a call into
#: `detector.DETECTION_CONSTANTS`: these are claims about what the API does with
#: a row, and a test that imports the value under test cannot fail when it moves.
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
    windows=None,
    span_end=date(2026, 1, 1),
    event_key=None,
    created_at=None,
):
    """Persist one complete detected row and return it.

    ``created_at`` is passed explicitly wherever a test compares two
    generations: the column defaults to `now()`, which in Postgres is
    TRANSACTION start time, so two generations written inside one test share it
    to the microsecond and "the most recent generation" would be decided by the
    planner rather than by the data.
    """
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
        fired_windows=windows
        or {"d3": {"peak_end": peak.isoformat(), "peak_total_mm": 180.0, "percentile": percentile}},
        sealed_detection_params=SEALED,
        climatology_span_start=date(1991, 1, 1),
        climatology_span_end=span_end,
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
        curated_payload=payload
        or {
            "name": "Inundacion Marzo 2015",
            "description": "Evento historico para revisar con Landsat 8/Landsat 7 y Sentinel-1",
            "severity": "alta",
            "sensor": "landsat8",
            "max_cloud": 80,
            "days_buffer": 30,
        },
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def client(db):
    """The REAL app, an operator identity, and the test's own transaction.

    `get_db` is overridden with the ambient `db` session rather than a factory
    so the rows a test plants — which live inside that session's uncommitted
    transaction — are the rows the handler reads.
    """
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole
    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(role=UserRole.OPERADOR)
    app.dependency_overrides[get_db] = lambda: db
    test_client = TestClient(app)
    test_client.headers.update({"Host": "localhost"})
    yield test_client
    app.dependency_overrides.clear()


def _body(client, **params):
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _by_id(body):
    return {record["id"]: record for record in body["floods"]}


# ===========================================================================
# 4.1 / 4.2 -- D12: which generation is served, and how it says so
# ===========================================================================


def test_the_current_generation_is_served_and_named(client, db):
    """4.1 (D12 rule 1)."""
    _detected(db)

    body = _body(client)

    assert body["revision_state"] == "current"
    assert body["detector_revision"] == _current_revision()
    assert [record["id"] for record in body["floods"]] == ["ext_20150312"]


def test_an_empty_current_generation_serves_the_previous_one_labelled_stale(client, db):
    """4.2 (D12 rule 2) -- the deploy-ordering hazard, and the whole reason the
    rule exists.

    A deploy that bumps `DETECTOR_REVISION` before an operator runs the
    detector leaves the current generation EMPTY. Serving nothing would be a
    blank picker with a 200 and nothing to notice; serving the previous
    generation labelled `stale` is the repo's own precedent
    (`policy.py:193-197` serves each row under its OWN revision).
    """
    _detected(db, revision="rainfall-extreme-v0-previous")

    body = _body(client)

    assert body["revision_state"] == "stale"
    assert body["detector_revision"] == "rainfall-extreme-v0-previous"
    assert [record["id"] for record in body["floods"]] == ["ext_20150312"]
    assert body["absence"] is None


def test_the_most_recent_non_empty_generation_wins_the_stale_fallback(client, db):
    """4.2, second half: "the previous generation" is the most RECENT one that
    has rows, not whichever the query happened to return first."""
    older = datetime(2026, 1, 1, tzinfo=UTC)
    _detected(db, revision="rev-older", start=date(2001, 1, 5), percentile=99.9, created_at=older)
    _detected(
        db,
        revision="rev-newer",
        start=date(2002, 2, 6),
        percentile=99.8,
        created_at=older + timedelta(days=30),
    )

    body = _body(client)

    assert body["revision_state"] == "stale"
    assert body["detector_revision"] == "rev-newer"
    assert [record["id"] for record in body["floods"]] == ["ext_20020206"]


def test_an_empty_catalog_is_labelled_empty_rather_than_current(client, db):
    """A catalog nobody has written yet has no generation to call current.

    Labelling it `current` would claim a generation exists and serve zero rows
    as a complete telling of the weather.
    """
    body = _body(client)

    assert body["revision_state"] == "empty"
    assert body["floods"] == []
    assert body["absence"]["reason"] == "incomplete_evidence"


# ===========================================================================
# 4.3 / 4.4 -- curated rows at every tier, and the default short list
# ===========================================================================


def test_curated_rows_are_served_under_every_tier_and_every_revision_state(client, db):
    """4.3 (D12 rule 3). Institutional memory is not detector output: hiding an
    anchor behind the default tier filter is the silent drop spec R4 forbids."""
    _curated(db)

    for params in ({}, {"tier": "extrema"}, {"tier": "alta"}):
        body = _body(client, **params)
        assert "mar_2015" in _by_id(body), params


def test_the_default_response_is_the_extrema_short_list(client, db):
    """4.4 (spec R3). `alta` is ~144 events against `extrema`'s ~36 (the
    measured calibration, 2026-08-26); serving it by default is a wall of
    cards."""
    _detected(db, tier="extrema", start=date(2015, 3, 12))
    _detected(db, tier="alta", start=date(2015, 3, 10))

    default = _body(client)
    explicit = _body(client, tier="alta")

    assert [record["id"] for record in default["floods"]] == ["ext_20150312"]
    assert [record["id"] for record in explicit["floods"]] == ["alt_20150310"]
    assert default["tier"] == "extrema"


def test_an_unknown_tier_is_refused_rather_than_silently_defaulted(client, db):
    """A typo'd tier that quietly returns the default serves a different
    question's answer under the caller's label."""
    assert client.get(URL, params={"tier": "extremaa"}).status_code == 422


# ===========================================================================
# 4.5 / 4.6 -- D8 precedence and the ±3-day confirmation derivation
# ===========================================================================


def test_a_confirmed_anchor_is_one_card_carrying_both_provenances(client, db):
    """4.5 (D8 precedence). r1 served the curated row AND the detected row into
    a picker with no dedup, i.e. two cards for one flood."""
    _curated(
        db,
        event_key="feb_2017",
        day=date(2017, 2, 20),
        payload={
            "name": "Inundacion Febrero 2017",
            "description": "Gran inundacion que afecto Bell Ville y zona rural",
            "severity": "alta",
            "sensor": "sentinel2",
        },
    )
    _detected(
        db,
        tier="alta",
        start=date(2017, 2, 16),
        end=date(2017, 2, 18),
        peak=date(2017, 2, 18),
        percentile=99.68,
    )

    body = _body(client, tier="alta")

    assert len(body["floods"]) == 1, "the detected row must not be served as a second card"
    record = body["floods"][0]
    assert record["id"] == "feb_2017"
    assert record["name"] == "Inundacion Febrero 2017"
    assert record["severity"] == "alta"
    assert record["date"] == "2017-02-20", "the anchor keeps its curated date"
    assert record["provenance"] == "detected"
    assert record["curated"] is True
    assert record["tier"] == "alta"
    assert record["max_percentile"] == pytest.approx(99.68)
    assert set(record["fired_windows"]) == {"d3"}
    assert record["confirmation"] == "detector_confirmed"
    assert record["confirmed_by"] == "alt_20170216"
    assert record["confirmation_offset_days"] == 2


def test_an_unconfirmed_anchor_is_still_served_and_flagged(client, db):
    """4.6 (spec R4 S2). `mar_2015`'s nearest detected event ends 8 days away;
    CHIRPS is blind to that local convective. The anchor stays, flagged."""
    _curated(db)
    _detected(db, tier="alta", start=date(2015, 3, 5), end=date(2015, 3, 7), peak=date(2015, 3, 6))

    body = _body(client, tier="alta")

    record = _by_id(body)["mar_2015"]
    assert record["confirmation"] == "not_confirmed"
    assert record["confirmed_by"] is None
    assert record["confirmation_label"] == "curated, not detector-confirmed"
    assert "alt_20150305" in _by_id(body), "the far-away detected row is its own card"


@pytest.mark.parametrize(
    ("offset_days", "confirmed"),
    [(0, True), (1, True), (3, True), (4, False), (8, False)],
)
def test_the_confirmation_tolerance_is_exactly_three_days(client, db, offset_days, confirmed):
    """4.6 (owner-ratified 2026-08-26). Both boundaries asserted: exactly three
    days confirms, four does not. A tolerance nobody pinned at its edges is a
    tolerance that can widen to "anything in the same month" unnoticed."""
    anchor = date(2017, 2, 20)
    fired = anchor - timedelta(days=offset_days)
    _curated(db, event_key="feb_2017", day=anchor, payload={"name": "a", "severity": "alta"})
    _detected(db, tier="alta", start=fired, end=fired, peak=fired)

    record = _by_id(_body(client, tier="alta"))["feb_2017"]

    assert (record["confirmation"] == "detector_confirmed") is confirmed
    assert (record["confirmed_by"] is not None) is confirmed


def test_confirmation_is_derived_at_read_and_never_stored(client, db):
    """4.6, the structural half. The catalog is append-only (`_IMMUTABLE_TYPES`),
    so storing confirmation would require the detector to UPDATE a curated row
    on every run — refused at flush — and the value would go stale the instant
    the served generation moved."""
    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    anchor = _curated(
        db, event_key="feb_2017", day=date(2017, 2, 20), payload={"name": "a", "severity": "alta"}
    )
    _detected(
        db, tier="alta", start=date(2017, 2, 18), end=date(2017, 2, 18), peak=date(2017, 2, 18)
    )

    assert _by_id(_body(client, tier="alta"))["feb_2017"]["confirmation"] == "detector_confirmed"

    db.expire_all()
    stored = db.get(RainfallExtremeEvent, anchor.id)
    assert set(stored.curated_payload) == {"name", "severity"}
    assert stored.tier is None and stored.max_percentile is None


# ===========================================================================
# 4.7 / 4.10 -- what the frontend actually requires of the record
# ===========================================================================


def test_a_served_detected_record_satisfies_is_historic_flood(client, db):
    """4.7 (D10 / CRITICAL-7). `isHistoricFlood` requires `id`, `name`, `date`,
    all strings, and drops anything else SILENTLY; the info panel renders
    `description` unconditionally. A detected row with no synthesized name does
    not render wrong — it disappears, with no error anywhere."""
    _detected(db, start=date(2015, 3, 12), end=date(2015, 3, 15), peak=date(2015, 3, 14))

    record = _body(client)["floods"][0]

    for field in ("id", "name", "date"):
        assert isinstance(record[field], str) and record[field], field
    assert record["name"] == "Lluvia extrema 12-15 de marzo 2015"
    assert record["description"].startswith("Ventanas que superaron el umbral:")
    assert "CHIRPS" in record["description"]
    assert record["date"] == "2015-03-14", "the imagery target is the peak day"


def test_the_wire_severity_stays_inside_the_palette_the_frontend_styles(client, db):
    """4.10 (D9). `extrema` on the wire renders the palest yellow available."""
    _detected(db, tier="extrema", start=date(2015, 3, 12))
    _detected(db, tier="alta", start=date(2016, 4, 2))

    extrema = _by_id(_body(client))["ext_20150312"]
    alta = _by_id(_body(client, tier="alta"))["alt_20160402"]

    assert extrema["severity"] == "alta" and extrema["tier"] == "extrema"
    assert alta["severity"] == "media" and alta["tier"] == "alta"
    assert "extrema" not in {extrema["severity"], alta["severity"]}


def test_curated_severity_is_served_verbatim(client, db):
    """4.10, second half (D8). `sep_2025` keeps `media` without implying a tier
    for a row that was never ranked."""
    _curated(
        db,
        event_key="sep_2025",
        day=date(2025, 9, 5),
        payload={"name": "Inundacion Septiembre 2025", "severity": "media"},
    )

    record = _by_id(_body(client))["sep_2025"]

    assert record["severity"] == "media"
    assert record["tier"] is None
    assert record["provenance"] == "curated"


# ===========================================================================
# 4.8 -- D11 disclosure: per-record vs root
# ===========================================================================


@pytest.mark.parametrize(
    ("end_day", "candidate", "note_fragment"),
    [
        (date(1994, 4, 9), False, "antes de 2015"),
        (date(2019, 4, 9), True, "Ventana dorada"),
        (date(2023, 4, 9), True, "Sentinel"),
    ],
)
def test_every_record_declares_its_imagery_candidacy(client, db, end_day, candidate, note_fragment):
    """4.8 (D11). The pre-2015 event is STILL SERVED — spec R5 S1 — it just
    says plainly that no useful image exists for it."""
    _detected(db, start=end_day, end=end_day, peak=end_day)

    record = _body(client)["floods"][0]

    assert record["imagery_candidate"] is candidate
    assert note_fragment in record["imagery_note"]
    assert record["dataset_disclosure"].startswith("CHIRPS")


@pytest.mark.parametrize(
    ("end_day", "candidate"),
    [(date(2014, 12, 31), False), (date(2015, 1, 1), True)],
)
def test_the_imagery_cutoff_sits_exactly_on_2015_01_01(client, db, end_day, candidate):
    """4.8, the BOUNDARY — added after the mutant sweep found it uncovered.

    The three-case candidacy test above uses 1994 / 2019 / 2023, which a cutoff
    moved anywhere inside 1995-2014 satisfies just as well: the mutant that
    slid it to 2010 survived the whole suite. The cutoff is a claim about
    SENSORS (Sentinel-2A from 2015, `explore.md:87-96`), so the day it changes
    on is the assertion, not a year comfortably on either side of it.
    """
    _detected(db, start=end_day, end=end_day, peak=end_day)

    assert _body(client)["floods"][0]["imagery_candidate"] is candidate


def test_the_curated_rows_carry_the_dataset_disclosure_too(client, db):
    """4.8 (spec R5): EVERY event, curated included."""
    _curated(db)

    assert _by_id(_body(client))["mar_2015"]["dataset_disclosure"].startswith("CHIRPS")


def test_the_response_root_declares_zone_only_coverage(client, db):
    """4.8, root half. `basin_coverage: false` is EXPLICIT because the basin
    scope is broken end to end (`gee_client.py:52-57`) and silence reads as
    support."""
    _detected(db)

    body = _body(client)

    assert body["coverage"] == {
        "scope_kind": "zone",
        "scope_id": "zona_cc_ampliada",
        "basin_coverage": False,
    }
    assert body["imagery_golden_window"] == {"start": "2017-01-01", "end": "2021-12-31"}
    assert body["catalog_span"] == {"start": "1991-01-01", "end": "2025-12-31"}


# ===========================================================================
# 4.9 -- R6: absence is never a bare success
# ===========================================================================


def test_a_year_with_no_qualifying_window_serves_a_reason(client, db):
    """4.9 (spec R6). And the curated rows are STILL served for that year, so
    the absence is about the detector's evidence and not about the response
    being blank."""
    _detected(db, start=date(2015, 3, 12))
    _curated(
        db,
        event_key="sep_2025",
        day=date(2025, 9, 5),
        payload={"name": "Inundacion Septiembre 2025", "severity": "media"},
    )

    body = _body(client, year=2025)

    assert body["absence"]["reason"] == "no_qualifying_window"
    assert body["absence"]["detail"]
    assert [record["id"] for record in body["floods"]] == ["sep_2025"]


def test_a_year_with_a_detected_event_carries_no_absence(client, db):
    _detected(db, start=date(2015, 3, 12))

    assert _body(client, year=2015)["absence"] is None


def test_no_synthetic_event_is_produced_for_an_empty_year(client, db):
    """4.9, the half that matters: absence is a REASON, never a placeholder row."""
    _detected(db, start=date(2015, 3, 12))

    body = _body(client, year=1998)

    assert body["floods"] == []
    assert body["total"] == 0
    assert body["absence"]["reason"] == "no_qualifying_window"


# ===========================================================================
# 4.11 / 4.12 -- the days_buffer ceiling, ordering and the uncapped total
# ===========================================================================


def test_a_detected_record_emits_no_days_buffer(client, db):
    """4.11 (D9's ceiling). `typeGuards.ts:406-411` rejects a restored selection
    whose `days_buffer` is `<1` or `>30`, so a buffer derived from a long wet
    spell's duration would emit `40` and break the restore path. The epoch
    default at `router_gee_support.py:502` applies instead."""
    _detected(db, start=date(2015, 3, 1), end=date(2015, 4, 20), peak=date(2015, 3, 14))

    record = _body(client)["floods"][0]

    assert "days_buffer" not in record


def test_a_curated_record_carries_its_explicit_days_buffer(client, db):
    """4.11's other half: `mar_2015`'s 30 is STORED (task 2.11), so the bridge
    does not depend on the epoch default coinciding with it."""
    _curated(db)

    record = _by_id(_body(client))["mar_2015"]

    assert record["days_buffer"] == 30
    assert record["sensor"] == "landsat8"
    assert record["max_cloud"] == 80


def test_the_page_is_ordered_by_strength_and_the_total_is_uncapped(client, db):
    """4.12. A `total` that equals `len(page)` is the bug this pins: it makes
    every page look like the last one."""
    for index in range(5):
        _detected(db, start=date(2000 + index, 5, 1), percentile=99.0 + index / 10)

    body = _body(client, limit=2)

    assert [record["id"] for record in body["floods"]] == ["ext_20040501", "ext_20030501"]
    assert body["total"] == 5
    assert body["limit"] == 2 and body["offset"] == 0

    page_two = _body(client, limit=2, offset=2)
    assert [record["id"] for record in page_two["floods"]] == ["ext_20020501", "ext_20010501"]
    assert page_two["total"] == 5


def test_the_limit_defaults_to_200_and_is_capped_at_500(client, db):
    _detected(db)

    assert _body(client)["limit"] == 200
    assert _body(client, limit=500)["limit"] == 500
    assert client.get(URL, params={"limit": 501}).status_code == 422


def test_curated_rows_are_pinned_ahead_of_the_detected_page(client, db):
    """An anchor that falls off page two of a 144-row `alta` list has been
    dropped by pagination, which spec R4 forbids as firmly as dropping it by
    filter."""
    for index in range(3):
        _detected(db, start=date(2000 + index, 5, 1), percentile=99.9)
    _curated(db)

    body = _body(client, limit=1)

    assert [record["id"] for record in body["floods"]] == ["mar_2015"]
    assert body["total"] == 4


# ===========================================================================
# 4.13 -- the cache header
# ===========================================================================


def test_the_response_is_privately_cached_for_five_minutes(client, db):
    """4.13. `public, max-age=86400` on a response gated by
    `Depends(_require_operator())` is both a shared-cache leak and a day-long
    staleness window after a detector run — harmless over three constants, not
    over a DB-backed filtered response."""
    _detected(db)

    response = client.get(URL)

    assert response.headers["cache-control"] == "private, max-age=300"


# ===========================================================================
# The literal survives this slice, by design
# ===========================================================================


def test_the_module_literal_is_dead_but_still_present_for_the_un_rewired_bridge(client, db):
    """B2a's deliberate sequencing note. `HISTORIC_FLOODS` is no longer read by
    the list handler, but `get_historic_flood_tiles_impl` still scans it; the
    symbol and everything bound to it die together in B2b. Deleting it here
    would drag the bridge, five dispatcher tests and the shape move into this
    slice — one ~1,100-line PR whose production component crosses 400."""
    from app.domains.geo import router_gee_support

    _detected(db)

    assert [flood["id"] for flood in router_gee_support.HISTORIC_FLOODS] == [
        "mar_2015",
        "feb_2017",
        "sep_2025",
    ]
    assert _body(client)["floods"][0]["id"] == "ext_20150312", "the list no longer reads it"
