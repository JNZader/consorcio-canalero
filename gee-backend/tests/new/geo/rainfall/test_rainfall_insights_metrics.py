"""Integration coverage for slice 2a's new metrics (real PG): every new
metric has a policy threshold (D4), normal/percentile share the SAME
comparison_end annual.selected discloses (D4/D5), and antecedents.d90
suppresses -- not short-sums -- on an incomplete prior-year tail (D6).

Lluvia insights slice 2a: annual.normal/percentile + antecedents.d7/d30/d90.
"""

import hashlib
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION, asset_name_for
from app.domains.geo.rainfall.models import RainfallOutbox
from app.domains.geo.rainfall.ports import SourceInterval
from app.domains.geo.rainfall.repository import RainfallRepository, persist_intervals


def _daily_rows(
    start: date, count: int, value: float, *, provider_revision: str = "v3-final"
) -> list[SourceInterval]:
    rows = []
    for offset in range(count):
        day = start + timedelta(days=offset)
        day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        rows.append(
            SourceInterval(day_start, day_start + timedelta(days=1), value, "mm", provider_revision)
        )
    return rows


def _build_outbox_and_batch(
    db, *, scope_id: str, year: int, source_id: str = "chirps-v3-sat", role: str = "daily"
):
    fingerprint = hashlib.sha256(f"fp-{scope_id}-{year}".encode()).hexdigest()
    outbox = RainfallOutbox(
        source_id=source_id,
        role=role,
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        year=year,
        work_labels=["analysis_missing"],
        interval_start=datetime(year, 1, 1, tzinfo=UTC),
        interval_end=datetime(year + 1, 1, 1, tzinfo=UTC),
        status="pending",
        request_fingerprint=fingerprint,
    )
    db.add(outbox)
    db.flush()
    batch = {
        "source_id": source_id,
        "scope_kind": "zone",
        "scope_id": scope_id,
        "year": year,
        "intervals": 0,
        "persisted": 0,
        "superseded": 0,
        "provider_revision": "v3-nrt",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": "v3-nrt"},
        "discrepancies": [],
        "checksum": f"sha256:fixture-{scope_id}",
    }
    return outbox, batch, fingerprint


def test_no_metric_suppressed_as_policy_threshold_unset(db):
    """2a.12 (spec: "Complete analysis has no unthresholded metric") --
    full-coverage analysis: every new metric is available, none suppressed
    as policy_threshold_unset."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
    from app.domains.geo.rainfall.service import normalize_snapshot

    scope_id = "zone-2a12-full-coverage"
    asset = asset_name_for("zone", scope_id)
    year = 2025

    # comparison_end = Apr 15 (day 105 of a non-leap year) -- far enough
    # into the year that antecedents.d90's window ([Jan 11, Apr 16)) stays
    # entirely inside it, keeping the fixture footprint small.
    now = datetime(year, 4, 15, 12, 0, tzinfo=UTC)
    comparison_end_exclusive = datetime(year, 4, 16, tzinfo=UTC)
    days_needed = (comparison_end_exclusive - datetime(year, 1, 1, tzinfo=UTC)).days

    # All 30 baseline years, complete through the SAME month/day -- well
    # above MIN_BASELINE_YEARS=20, and completeness=1.0 clears the 0.8
    # quality threshold (D4) with margin.
    for baseline_year in range(1991, 2021):
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(date(baseline_year, 1, 1), days_needed, 5.0),
        )

    # The selected zone/year: full daily coverage through comparison_end.
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_rows(date(year, 1, 1), days_needed, 3.0, provider_revision="v3-nrt"),
    )
    db.flush()

    outbox, batch, fingerprint = _build_outbox_and_batch(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    normalized = normalize_snapshot(
        revision.snapshot, expected_policy_revision=RAINFALL_METRIC_POLICY_REVISION
    )

    checked = {
        "annual.normal": normalized["annual"]["normal"],
        "annual.percentile": normalized["annual"]["percentile"],
        "antecedents.d7": normalized["antecedents"]["d7"],
        "antecedents.d30": normalized["antecedents"]["d30"],
        "antecedents.d90": normalized["antecedents"]["d90"],
    }
    for name, metric in checked.items():
        assert metric["reason"] != "policy_threshold_unset", (name, metric)
        assert metric["state"] == "available", (name, metric)


def test_normal_and_percentile_share_selected_comparison_end(db):
    """2a.13: annual.normal/percentile's baseline windows are cut off at
    EXACTLY the same comparison_end date annual.selected discloses -- data
    persisted AFTER that date must not leak into the baseline average."""
    from app.domains.geo.rainfall import tasks

    scope_id = "zone-2a13-shared-cutoff"
    asset = asset_name_for("zone", scope_id)
    year = 2025
    now = datetime(year, 1, 20, 12, 0, tzinfo=UTC)  # comparison_end = Jan 20
    # Jan 20 is BEFORE Feb 29 in every calendar -- the cutoff day-count is
    # exactly 20 for every baseline year regardless of which are leap
    # years, so a single constant is genuinely correct here (unlike a
    # later-month cutoff, which would need a per-year leap adjustment).
    cutoff_days = 20  # Jan 1 .. Jan 20 inclusive

    for baseline_year in range(1991, 2021):
        # Cutoff-window data (counted) ...
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(date(baseline_year, 1, 1), cutoff_days, 5.0),
        )
        # ... + a deliberately huge tail AFTER the cutoff date, which must
        # NOT be counted if normal genuinely shares annual.selected's cutoff.
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(date(baseline_year, 1, 1) + timedelta(days=cutoff_days), 5, 1000.0),
        )

    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_rows(date(year, 1, 1), cutoff_days, 3.0, provider_revision="v3-nrt"),
    )
    db.flush()

    outbox, batch, fingerprint = _build_outbox_and_batch(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    snapshot = revision.snapshot

    assert snapshot["comparison_end"] == date(year, 1, 20).isoformat()
    normal = snapshot["annual"]["normal"]
    # Exactly the cutoff-window sum -- the post-cutoff 1000.0/day tail did
    # NOT leak into the baseline average.
    assert normal["value"] == pytest.approx(5.0 * cutoff_days)
    assert normal["state"] == "available"


def test_d90_suppressed_with_reason_when_prior_year_incomplete(db):
    """2a.14: comparison_end early in the year makes d90's window reach
    into the PRIOR year (D6); if that prior-year tail is incomplete, d90
    suppresses with its own reason -- never a short sum -- while d7 (fully
    inside the current year) stays available."""
    from app.domains.geo.rainfall import tasks

    scope_id = "zone-2a14-prior-year-gap"
    year = 2025
    now = datetime(year, 1, 20, 12, 0, tzinfo=UTC)  # comparison_end = Jan 20, 2025

    # This year's own data: complete Jan 1 - Jan 20.
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_rows(date(year, 1, 1), 20, 1.0, provider_revision="v3-nrt"),
    )
    # Prior year's tail: d90's window needs ~Oct 23, 2024 .. Dec 31, 2024
    # (the D6-widened read reaches back to Oct 3, 2024); persist a generous
    # over-cover of it, EXCEPT one day -- a genuine gap inside the window.
    prior_tail = _daily_rows(date(year - 1, 10, 1), 92, 1.0, provider_revision="v3-final")
    del prior_tail[45]  # Nov 15, 2024 -- squarely inside the needed window
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=prior_tail,
    )
    db.flush()

    outbox, batch, fingerprint = _build_outbox_and_batch(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    snapshot = revision.snapshot

    d90 = snapshot["antecedents"]["d90"]
    assert d90["state"] == "suppressed"
    assert d90["value"] is None
    assert d90["reason"] == "antecedent_window_incomplete"

    d7 = snapshot["antecedents"]["d7"]
    assert d7["state"] == "available"
    assert d7["value"] == pytest.approx(7.0)
