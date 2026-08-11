"""Historical baseline persistence under the provider-asset scope key (D1).

Slice 1 of lluvia-insights: the baseline key is
``scope_kind="provider_asset"``, ``scope_id=<resolved asset>``,
``scope_version=BASELINE_ASSET_VERSION`` -- fixed, never a zoning version,
so a zone republication cannot orphan 30 years of evidence.
"""

from datetime import UTC, date, datetime, timedelta

import pytest


def test_provider_asset_scope_key_persists_and_reads_back(db):
    from app.domains.geo.rainfall.adapters.gee_client import (
        BASELINE_ASSET_VERSION,
        DEFAULT_ZONE_ASSET,
        asset_name_for,
    )
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import intervals_in_window, persist_intervals

    # The baseline key IS the resolved asset, unchanged by which scope kind
    # or id a caller resolved it from.
    asset = asset_name_for("provider_asset", DEFAULT_ZONE_ASSET)
    assert asset == DEFAULT_ZONE_ASSET

    start = datetime(1991, 1, 1, tzinfo=UTC)
    rows = [SourceInterval(start, start + timedelta(days=1), 12.5, "mm", "v3-final")]
    persisted = persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=rows,
    )
    assert persisted == {"inserted": 1, "unchanged": 0, "superseded": 0}

    readback = intervals_in_window(
        db,
        source_id="chirps-v3-final",
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        start=start,
        end=start + timedelta(days=1),
    )
    assert len(readback) == 1
    assert readback[0].value == 12.5
    assert readback[0].scope_kind == "provider_asset"
    assert readback[0].scope_version == BASELINE_ASSET_VERSION


def test_baseline_cumulatives_returns_per_year_totals(db):
    from sqlalchemy import text

    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import baseline_cumulatives, persist_intervals

    asset = "baseline-test-asset-per-year-totals"
    source_id = "chirps-v3-final"

    def _rows(year: int, values: list[float]) -> list[SourceInterval]:
        start = datetime(year, 3, 1, tzinfo=UTC)
        return [
            SourceInterval(
                start + timedelta(days=i), start + timedelta(days=i + 1), value, "mm", "v3-final"
            )
            for i, value in enumerate(values)
        ]

    values_by_year = {1991: [1.0, 2.0, 3.0], 1992: [4.0, 5.0], 1993: [0.5]}
    for year, values in values_by_year.items():
        persist_intervals(
            db,
            source_id=source_id,
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_rows(year, values),
        )

    # LI1-002 (review-ledger.md): a row landing exactly on the year
    # boundary (1991-01-01T00:00Z) is the case `date_part('year',
    # timestamptz)` mis-groups under a non-UTC session TZ -- Postgres
    # converts a `timestamptz` to the session's `TimeZone` setting BEFORE
    # extracting the field. Under America/Argentina/Buenos_Aires (UTC-3)
    # that instant is 1990-12-31T21:00 local, so the un-pinned expression
    # would file it under 1990 -- a year outside `expected_days_by_year`,
    # which is exactly the `KeyError` every real backfill row hits at
    # repository.py:305 (a real backfill always writes a Jan-1 row).
    boundary_value = 100.0
    boundary_start = datetime(1991, 1, 1, tzinfo=UTC)
    persist_intervals(
        db,
        source_id=source_id,
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=[
            SourceInterval(
                boundary_start, boundary_start + timedelta(days=1), boundary_value, "mm", "v3-final"
            )
        ],
    )
    values_by_year = {**values_by_year, 1991: [*values_by_year[1991], boundary_value]}

    # One cutoff date per baseline year, past every persisted row so they
    # all fall inside the window (matches temporal.baseline_dates' shape).
    dates = [date(year, 3, 10) for year in values_by_year]

    # Non-UTC session TZ, scoped to this test's transaction: the `db`
    # fixture wraps the whole test in one transaction that gets rolled
    # back afterward, and per Postgres semantics a plain `SET` issued
    # inside a transaction that later rolls back reverts with it -- this
    # cannot leak into other tests sharing the pooled connection. Only the
    # boundary row above can move: every other persisted row sits in
    # March, safely mid-year in both UTC and Buenos Aires local time.
    db.execute(text("SET TIME ZONE 'America/Argentina/Buenos_Aires'"))

    result = baseline_cumulatives(db, source_id=source_id, asset=asset, dates=dates)

    assert result.keys() == {1991, 1992, 1993}
    for year, values in values_by_year.items():
        total, matched, expected = result[year]
        assert total == pytest.approx(sum(values))  # matches a manual SQL sum
        assert matched == len(values)
        window_start = datetime(year, 1, 1, tzinfo=UTC)
        window_end = datetime(year, 3, 11, tzinfo=UTC)
        assert expected == (window_end - window_start).days


def test_baseline_cumulatives_omits_years_with_no_persisted_rows(db):
    """A year with zero matched rows is absent, never a fabricated zero."""
    from app.domains.geo.rainfall.repository import baseline_cumulatives

    result = baseline_cumulatives(
        db,
        source_id="chirps-v3-final",
        asset="baseline-test-asset-empty",
        dates=[date(1991, 6, 1), date(1992, 6, 1)],
    )
    assert result == {}


def test_baseline_cumulatives_raises_on_a_duplicated_interval_slot(db):
    """LI2A-005 (slice 2b amendment A3): ``build_snapshot`` treats a
    duplicated ``interval_start`` as a broken invariant worth raising on,
    because ``intervals_in_window``'s anti-join is supposed to guarantee at
    most one non-superseded row per slot. ``baseline_cumulatives`` reads
    through the SAME anti-join and inherits the SAME invariant, but had no
    guard -- so a duplicate silently inflated BOTH ``total_mm`` and
    ``matched_days`` (the year still looked complete), quietly biasing
    ``annual.normal`` and every percentile ranked against it."""
    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
    from app.domains.geo.rainfall.models import RainfallIntervalValue
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import baseline_cumulatives, persist_intervals

    asset = "baseline-test-asset-duplicated-slot"
    source_id = "chirps-v3-final"
    day = datetime(1991, 5, 1, tzinfo=UTC)
    persist_intervals(
        db,
        source_id=source_id,
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=[SourceInterval(day, day + timedelta(days=1), 10.0, "mm", "v3-final")],
    )

    # A SECOND non-superseded row for the same slot. `uq_rainfall_interval_
    # revision` permits it (provider_revision is part of the key), and no
    # `rainfall_interval_lifecycle` row marks either side superseded -- the
    # exact residue of a correction whose supersession link never landed
    # (persist_intervals only records the link for ids RETURNING reports).
    db.add(
        RainfallIntervalValue(
            source_id=source_id,
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            interval_start=day,
            interval_end=day + timedelta(days=1),
            provider_revision="v3-final+r1",
            value=10.0,
            unit="mm",
        )
    )
    db.flush()

    with pytest.raises(ValueError, match="duplicat"):
        baseline_cumulatives(db, source_id=source_id, asset=asset, dates=[date(1991, 5, 2)])


def test_zoning_republication_does_not_orphan_baseline(db):
    """A zone's own scope_version bump (a republished zoning) is invisible
    to the baseline key: it is never part of it (1.2/1.4)."""
    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION, asset_name_for
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import baseline_cumulatives, persist_intervals

    asset_before = asset_name_for("zone", "any-zone-id")
    asset_after = asset_name_for("zone", "any-zone-id")
    assert asset_before == asset_after

    source_id = "chirps-v3-final"
    start = datetime(1995, 6, 1, tzinfo=UTC)
    persist_intervals(
        db,
        source_id=source_id,
        scope_kind="provider_asset",
        scope_id=asset_before,
        scope_version=BASELINE_ASSET_VERSION,
        rows=[SourceInterval(start, start + timedelta(days=1), 7.0, "mm", "v3-final")],
    )

    before = baseline_cumulatives(
        db, source_id=source_id, asset=asset_before, dates=[date(1995, 6, 5)]
    )
    # Simulate a zoning republication: the request scope's own version
    # bumps elsewhere, but the resolved asset -- and therefore the baseline
    # read -- is unaffected, because the read key never carried it.
    after = baseline_cumulatives(
        db, source_id=source_id, asset=asset_after, dates=[date(1995, 6, 5)]
    )

    assert before == after
    assert before[1995][0] == pytest.approx(7.0)


def test_persist_analysis_revision_resolves_mapped_baseline_and_passes_it_through(db, monkeypatch):
    """1.8's actual GREEN behavior for a MAPPED scope: build_snapshot
    receives the resolved repository.baseline_cumulatives dict, not just
    the unmapped-basin baseline=None branch (proven separately above)."""
    import hashlib

    from app.domains.geo.rainfall import compute, tasks
    from app.domains.geo.rainfall.adapters.gee_client import (
        BASELINE_ASSET_VERSION,
        asset_name_for,
    )
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import persist_intervals

    captured: dict = {}
    real_build_snapshot = compute.build_snapshot

    def spy_build_snapshot(**kwargs):
        captured.update(kwargs)
        return real_build_snapshot(**kwargs)

    monkeypatch.setattr(compute, "build_snapshot", spy_build_snapshot)

    scope_id = "zone-mapped-baseline-wiring"
    asset = asset_name_for("zone", scope_id)

    baseline_start = datetime(1991, 3, 10, tzinfo=UTC)
    persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=[
            SourceInterval(
                baseline_start, baseline_start + timedelta(days=1), 9.0, "mm", "v3-final"
            )
        ],
    )

    selected_start = datetime(2024, 6, 1, tzinfo=UTC)
    persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=[
            SourceInterval(
                selected_start, selected_start + timedelta(days=1), 1.0, "mm", "v3-final"
            )
        ],
    )
    db.flush()

    fingerprint = hashlib.sha256(b"fp-mapped-baseline-wiring").hexdigest()
    outbox = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=datetime(2024, 1, 1, tzinfo=UTC),
        interval_end=datetime(2025, 1, 1, tzinfo=UTC),
        status="pending",
        request_fingerprint=fingerprint,
    )
    db.add(outbox)
    db.flush()

    batch = {
        "source_id": "chirps-v3-final",
        "scope_kind": "zone",
        "scope_id": scope_id,
        "year": 2024,
        "intervals": 1,
        "persisted": 1,
        "superseded": 0,
        "provider_revision": "v3-final",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": "v3-final"},
        "discrepancies": [],
        "checksum": "sha256:fixture-mapped-baseline-wiring",
    }

    # Comparison_end lands in mid-September Buenos Aires local time either
    # way (no UTC/local day-boundary ambiguity), well after the persisted
    # 1991-03-10 baseline row.
    now = datetime(2024, 9, 15, 12, 0, tzinfo=UTC)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    assert "baseline" in captured
    assert captured["baseline"] is not None
    assert 1991 in captured["baseline"]
    total, matched, _expected = captured["baseline"][1991]
    assert total == pytest.approx(9.0)
    assert matched == 1


def test_unmapped_basin_raises_unknown_provider_scope():
    """Regression pin for the precondition tasks._persist_analysis_revision
    (1.8) relies on: an unmapped basin's own asset resolution raises,
    rather than silently reducing over the wrong geometry."""
    from app.domains.geo.rainfall.adapters.gee_client import UnknownProviderScope, asset_name_for

    with pytest.raises(UnknownProviderScope, match="no GEE asset mapped"):
        asset_name_for("basin", "an-unmapped-basin-id")


def test_persist_analysis_revision_suppresses_baseline_for_unmapped_basin(db):
    """1.8: an unmapped basin's asset-resolution failure must not become a
    build crash (design.md D1) -- build_snapshot receives baseline=None and
    the revision still writes normally."""
    import hashlib

    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import RainfallRepository, persist_intervals

    def _daily_intervals(*, start_day: int, values: list[float]) -> list[SourceInterval]:
        rows = []
        for offset, value in enumerate(values):
            start = datetime(2024, 1, start_day + offset, tzinfo=UTC)
            rows.append(SourceInterval(start, start + timedelta(days=1), value, "mm", "v3-final"))
        return rows

    fingerprint = hashlib.sha256(b"fp-unmapped-basin").hexdigest()

    rows = _daily_intervals(start_day=1, values=[1.0, 2.0, 3.0])
    persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="basin",
        scope_id="unmapped-basin-77",
        scope_version="v1",
        rows=rows,
    )
    db.flush()

    outbox = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="basin",
        scope_id="unmapped-basin-77",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=datetime(2024, 1, 1, tzinfo=UTC),
        interval_end=datetime(2025, 1, 1, tzinfo=UTC),
        status="pending",
        request_fingerprint=fingerprint,
    )
    db.add(outbox)
    db.flush()

    batch = {
        "source_id": "chirps-v3-final",
        "scope_kind": "basin",
        "scope_id": "unmapped-basin-77",
        "year": 2024,
        "intervals": 3,
        "persisted": 3,
        "superseded": 0,
        "provider_revision": "v3-final",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": "v3-final"},
        "discrepancies": [],
        "checksum": "sha256:fixture-unmapped-basin",
    }

    result = tasks._persist_analysis_revision(
        db, outbox_id=str(outbox.id), batch=batch, now=datetime(2024, 6, 15, tzinfo=UTC)
    )

    assert result["decision"] == "write"
    assert result["revision_id"] is not None

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    assert revision.snapshot["annual"]["selected"]["state"] == "available"
