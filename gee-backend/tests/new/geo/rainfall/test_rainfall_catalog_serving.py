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


def _payload(name, severity, **extra):
    """A minimal curated payload with the two fields the seed ALWAYS provides.

    `name` and `description` are not optional in the served contract: the
    frontend's `isHistoricFlood` drops a nameless record silently, so a payload
    missing either is a broken seed and the read model raises on it. Building
    them here keeps every fixture honest about that.
    """
    return {"name": name, "description": f"{name} -- descripcion curada", "severity": severity} | (
        extra
    )


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


def test_two_generations_written_in_one_transaction_break_the_tie_by_revision(client, db):
    """4.2, the tie the timestamp CANNOT break (WARNING, fix-forward).

    `created_at` defaults to `now()`, which in Postgres is TRANSACTION start
    time: two generations written inside ONE transaction share it to the
    microsecond. `max(created_at) DESC` alone then leaves the choice to the
    planner, and the picker would serve a different catalog on different days
    for the same rows. `detector_revision DESC` is the tie-break that makes the
    answer a property of the data -- untested until this test, and a mutant
    that flipped it to ASC survived the whole suite.
    """
    same_instant = datetime(2026, 1, 1, tzinfo=UTC)
    _detected(db, revision="rev-a", start=date(2001, 1, 5), created_at=same_instant)
    _detected(db, revision="rev-b", start=date(2002, 2, 6), created_at=same_instant)

    body = _body(client)

    assert body["revision_state"] == "stale"
    assert body["detector_revision"] == "rev-b"
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


def test_every_row_confirming_an_anchor_is_merged_not_served_as_a_second_card(client, db):
    """4.5, the case D8's precedence actually has to survive (CRITICAL, fix-forward).

    Both tiers hold rows for one storm BY CONSTRUCTION -- an `alta` span is a
    superset of the `extrema` spans inside it (`repository.EVENT_KEY_PREFIXES`
    exists precisely because both are persisted for the same days). Suppressing
    only the SINGLE nearest confirming row therefore leaves every other row of
    the same storm in the list, and the DEFAULT `extrema` response serves the
    curated `feb_2017` card AND `ext_20170219` as a second card for the same
    flood: exactly the r1 failure ("two cards for one flood") that D8's
    precedence exists to remove, arriving through the tier the caller did not
    even ask about.

    One card in BOTH tier views, and it is the CURATED one carrying the
    confirmation. The confirming row NAMED is the nearest across the whole
    served generation -- confirmation is derived against the generation, not
    against the filtered page -- so it is the same id under either tier.
    """
    _curated(
        db,
        event_key="feb_2017",
        day=date(2017, 2, 20),
        payload=_payload("Inundacion Febrero 2017", "alta"),
    )
    _detected(
        db,
        tier="alta",
        start=date(2017, 2, 16),
        end=date(2017, 2, 18),
        peak=date(2017, 2, 18),
        percentile=99.68,
    )
    _detected(
        db,
        tier="extrema",
        start=date(2017, 2, 19),
        end=date(2017, 2, 19),
        peak=date(2017, 2, 19),
        percentile=99.9,
    )

    for tier in ("extrema", "alta"):
        body = _body(client, tier=tier)

        assert [record["id"] for record in body["floods"]] == ["feb_2017"], tier
        record = body["floods"][0]
        assert record["confirmation"] == "detector_confirmed", tier
        assert record["confirmed_by"] == "ext_20170219", tier
        assert record["confirmation_offset_days"] == 1, tier
        assert record["name"] == "Inundacion Febrero 2017", tier
        assert body["total"] == 1, tier


def test_an_anchor_the_year_filter_excludes_suppresses_nothing(client, db):
    """The other edge of suppression, which the year filter opens.

    A curated anchor dated 2016-12-31 is confirmed by rain that fell on
    2017-01-02, two days away. Ask for 2017 and the anchor is NOT in the
    response -- its own dates are 2016 -- so suppressing its confirming row
    would delete the detector's only record of that storm from the very year
    the caller asked about: a 200 with an empty list and nothing anywhere to
    notice. Suppression only applies for anchors this response actually serves.
    """
    _curated(
        db,
        event_key="dic_2016",
        day=date(2016, 12, 31),
        payload=_payload("Inundacion Diciembre 2016", "alta"),
    )
    _detected(db, start=date(2017, 1, 2), end=date(2017, 1, 2), peak=date(2017, 1, 2))

    body = _body(client, year=2017)

    assert [record["id"] for record in body["floods"]] == ["ext_20170102"]
    assert body["absence"] is None

    both_years = _body(client)
    assert [record["id"] for record in both_years["floods"]] == ["dic_2016"], (
        "unfiltered, the anchor IS served and the same row is merged into it"
    )


def test_a_confirmed_anchor_leaves_no_false_absence(client, db):
    """4.9 / spec R6 (WARNING, fix-forward). The absence is computed from the
    detected records that SURVIVE suppression, so a generation whose only
    qualifying row was merged into the curated card used to report
    `no_qualifying_window` -- a reason that is false, beside a non-empty list,
    while the evidence it denies is being served inside the card. R6's own
    wording: a false reason is worse than no field.

    A row suppressed INTO a card is still evidence the detector produced.
    """
    _curated(
        db,
        event_key="feb_2017",
        day=date(2017, 2, 20),
        payload=_payload("Inundacion Febrero 2017", "alta"),
    )
    _detected(
        db, tier="alta", start=date(2017, 2, 18), end=date(2017, 2, 18), peak=date(2017, 2, 18)
    )

    body = _body(client, tier="alta")

    assert [record["id"] for record in body["floods"]] == ["feb_2017"]
    assert body["floods"][0]["confirmation"] == "detector_confirmed"
    assert body["absence"] is None


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


@pytest.mark.parametrize("direction", [-1, 1], ids=["before-the-anchor", "after-the-anchor"])
@pytest.mark.parametrize(
    ("offset_days", "confirmed"),
    [(0, True), (1, True), (3, True), (4, False), (8, False)],
)
def test_the_confirmation_tolerance_is_exactly_three_days(
    client, db, offset_days, confirmed, direction
):
    """4.6 (owner-ratified 2026-08-26). Both boundaries asserted: exactly three
    days confirms, four does not. A tolerance nobody pinned at its edges is a
    tolerance that can widen to "anything in the same month" unnoticed.

    Both DIRECTIONS too. `confirmation_offset_days` has two symmetric branches
    -- the rain before the anchor and the rain after it -- and every fixture
    written for the real `feb_2017` case plants it BEFORE, which exercises one
    of them. The other branch could return a constant 0 (confirming anything
    dated after the anchor, at any distance) and the whole suite would stay
    green: measured, that mutant survived until this parametrization.
    """
    anchor = date(2017, 2, 20)
    fired = anchor + direction * timedelta(days=offset_days)
    _curated(db, event_key="feb_2017", day=anchor, payload=_payload("a", "alta"))
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
        db, event_key="feb_2017", day=date(2017, 2, 20), payload=_payload("a", "alta")
    )
    _detected(
        db, tier="alta", start=date(2017, 2, 18), end=date(2017, 2, 18), peak=date(2017, 2, 18)
    )

    assert _by_id(_body(client, tier="alta"))["feb_2017"]["confirmation"] == "detector_confirmed"

    db.expire_all()
    stored = db.get(RainfallExtremeEvent, anchor.id)
    assert set(stored.curated_payload) == {"name", "description", "severity"}
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


@pytest.mark.parametrize("missing", ["name", "description"])
def test_a_curated_payload_missing_its_prose_is_loud_rather_than_silent(missing):
    """4.7's other half. `payload.get("name")` answering `None` recreates the
    exact CRITICAL-7 failure the synthesis exists to remove: `isHistoricFlood`
    requires `name: string` and DROPS the record silently, so a curated anchor
    with a broken payload vanishes from the picker with a 200 and no error
    anywhere. The seed (`lluvia_ext_002`) provides both fields on all three
    anchors, so a payload without them is a violated assumption -- and a
    violated assumption should raise, not vanish a card.

    The ONE assertion in this file that does not go through `TestClient`, for a
    measured reason: `app.main`'s catch-all handler turns any exception into a
    500 and calls `logger.exception`, and under the dev structlog renderer that
    hands the traceback to `rich`, which pretty-prints the SQLAlchemy row in
    every frame's locals. Measured: the request had not returned after 60 s.
    The claim here is about the READ MODEL's refusal anyway, not about the
    status code that refusal is eventually rendered as.
    """
    from app.domains.geo.rainfall import catalog_view

    payload = _payload("Inundacion Marzo 2015", "alta")
    del payload[missing]
    anchor = SimpleNamespace(
        event_key="mar_2015",
        start_date=date(2015, 3, 15),
        end_date=date(2015, 3, 15),
        curated_payload=payload,
    )
    generation = SimpleNamespace(
        revision="curated", revision_state="empty", detected=(), curated=(anchor,)
    )

    with pytest.raises(ValueError, match=missing):
        catalog_view.build_catalog_response(generation)


def test_curated_severity_is_served_verbatim(client, db):
    """4.10, second half (D8). `sep_2025` keeps `media` without implying a tier
    for a row that was never ranked."""
    _curated(
        db,
        event_key="sep_2025",
        day=date(2025, 9, 5),
        payload=_payload("Inundacion Septiembre 2025", "media"),
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


def test_the_catalog_span_is_the_served_rows_span_not_the_module_constants(client, db):
    """4.8, root half (WARNING, fix-forward). The span read off
    `DETECTOR_CLIMATOLOGY_*` is the span the CODE currently holds, not the one
    the served rows were ranked against -- so a stale generation served after a
    constants bump announces a span its own rows never saw, contradicting
    `event_from_row`'s docstring and every synthesized description underneath
    (those DO read the row).
    """
    _detected(
        db,
        revision="rev-narrow",
        start=date(2001, 1, 5),
        span_end=date(2021, 1, 1),
    )

    body = _body(client)

    assert body["revision_state"] == "stale"
    assert body["catalog_span"] == {"start": "1991-01-01", "end": "2020-12-31"}
    assert "1991-2020" in body["floods"][0]["description"], "the row's own prose agrees"


def test_a_generation_holding_two_spans_refuses_to_name_one(db):
    """The span is uniform within a generation BY CONSTRUCTION (D5 seals one
    constants block per `detector_revision`, and `persist_events` refuses a row
    that disagrees at an existing identity). Two spans therefore mean the
    catalog is broken in a way no single `catalog_span` can describe -- and
    picking either one would put a number at the response root that half the
    cards underneath contradict. Asserted at the read model for the same reason
    as the curated-payload refusal above.
    """
    from app.domains.geo.rainfall import catalog_view

    def _row(span_end):
        # `alta` rows under the default `extrema` request: the span claim is
        # about the GENERATION, so it has to be refused even when not one row
        # of it reaches the page the caller asked for.
        return SimpleNamespace(
            tier="alta",
            start_date=date(2001, 1, 5),
            end_date=date(2001, 1, 5),
            climatology_span_start=date(1991, 1, 1),
            climatology_span_end=span_end,
        )

    generation = SimpleNamespace(
        revision="rev-mixed",
        revision_state="current",
        detected=(_row(date(2021, 1, 1)), _row(date(2026, 1, 1))),
        curated=(),
    )

    with pytest.raises(ValueError, match="different climatology spans"):
        catalog_view.build_catalog_response(generation)


def test_an_empty_catalog_announces_no_span_at_all(client, db):
    """The other half: with no generation there is no ranked span, and naming
    the module's constants would claim a catalog that does not exist."""
    _curated(db)

    body = _body(client)

    assert body["revision_state"] == "empty"
    assert body["catalog_span"] is None


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
        payload=_payload("Inundacion Septiembre 2025", "media"),
    )

    body = _body(client, year=2025)

    assert body["absence"]["reason"] == "no_qualifying_window"
    assert body["absence"]["detail"]
    assert [record["id"] for record in body["floods"]] == ["sep_2025"]


@pytest.mark.parametrize("year", [2015, 2016])
def test_a_year_straddling_event_is_served_under_both_of_its_years(client, db, year):
    """4.9, the case a `start_date.year == year` filter silently loses.

    A wet spell that runs 28-dic to 03-ene belongs to BOTH years for a caller
    asking "what happened in 2016": filtering on the start year alone would
    drop it from 2016 with a 200 and an absence reason claiming the detector
    found nothing.
    """
    _detected(db, start=date(2015, 12, 28), end=date(2016, 1, 3), peak=date(2015, 12, 31))

    body = _body(client, year=year)

    assert [record["id"] for record in body["floods"]] == ["ext_20151228"]
    assert body["absence"] is None


def test_a_detected_record_declares_whether_its_span_was_clipped(client, db):
    """4.8, the derived flag (`DetectedEvent.clipped_at_span_end`). An event
    reaching the frozen span's LAST day may have been cut by the span rather
    than by the weather, and the served record has to say so -- derived from
    the span sealed ON the row, never stored, because the same days under a
    wider span in a later revision are a different row.
    """
    _detected(
        db,
        start=date(2025, 12, 29),
        end=date(2025, 12, 31),
        peak=date(2025, 12, 30),
        span_end=date(2026, 1, 1),
        percentile=99.9,
    )
    _detected(db, start=date(2015, 3, 12), span_end=date(2026, 1, 1), percentile=99.8)

    served = _by_id(_body(client))

    assert served["ext_20251229"]["clipped_at_span_end"] is True
    assert served["ext_20150312"]["clipped_at_span_end"] is False


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
# The literal is gone
# ===========================================================================

# RETIRED IN B2b, as designed. `test_the_module_literal_is_dead_but_still
# _present_for_the_un_rewired_bridge` pinned B2a's deliberate sequencing note:
# the list had stopped reading `HISTORIC_FLOODS` but the imagery bridge still
# scanned it, so the symbol had to survive exactly one merge window. B2b rewired
# the bridge and deleted the symbol in the same commit, which is what that note
# promised. Its successor is `test_rainfall_catalog_bridge.py`, where the bridge
# resolves ids against this same catalog.
