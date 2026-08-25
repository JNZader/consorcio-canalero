"""The policy-revision bump's re-materialization consequence (SDD S2b, tasks
4.2 and 4.3; spec MODIFIED "Policy Thresholds for New Metrics").

Real PostgreSQL, end to end through ``tasks._persist_analysis_revision`` and
the request path, because both halves of this contract are database
behaviours and neither survives a double:

* ``persist_revision`` writes with ``ON CONFLICT DO NOTHING`` keyed on
  ``(request_fingerprint, policy_revision, data_revision)``. ``data_revision``
  is a content address over the EVIDENCE (``compute.data_revision_for``) and
  does not hash the policy at all, so for every key whose evidence has not
  moved the enriched six-metric envelope collides with the row already there
  and is silently discarded -- unless ``RAINFALL_METRIC_POLICY_REVISION``
  moved, which is the whole reason S2a bumped it.
* the older row is a distinct row, not an overwrite: it keeps being served,
  normalized under its OWN ``policy_revision``, until its refresh lands.

Both tests therefore pin the ROW SET, not just the served payload.
"""

import json
import logging
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION, asset_name_for
from app.domains.geo.rainfall.models import RainfallAnalysisRevision, RainfallOutbox
from app.domains.geo.rainfall.ports import SourceInterval
from app.domains.geo.rainfall.repository import persist_intervals

# The value ``RAINFALL_METRIC_POLICY_REVISION`` carried before this change
# bumped it. A literal on purpose, and the same literal
# ``test_slice2b_resilience_fixes.py`` pins: reading it from the module would
# make it move WITH the bump and the test would then assert nothing.
_PREVIOUS_POLICY_REVISION = "rainfall-v2-2026-08"

_REFERENCE_KEYS = (
    "d7_normal",
    "d7_percentile",
    "d30_normal",
    "d30_percentile",
    "d90_normal",
    "d90_percentile",
)


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


def _batch(scope_id: str, *, year: int) -> dict:
    return {
        "source_id": "chirps-v3-sat",
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


def _fingerprint_for(scope: dict, year: int) -> str:
    from app.domains.geo.rainfall.service import analysis_request_fingerprint

    return analysis_request_fingerprint({"scope": scope, "year": year})


def _outbox_for(db, *, scope_id: str, year: int, fingerprint: str) -> RainfallOutbox:
    outbox = RainfallOutbox(
        source_id="chirps-v3-sat",
        role="daily",
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
    return outbox


def _seed_complete_evidence(db, *, scope_id: str, year: int, now: datetime) -> int:
    """Selected-year daily coverage plus a thirty-year daily baseline, both
    complete through ``now``'s comparison end.

    Complete on BOTH sides deliberately: this fixture has to make the six
    reference metrics genuinely AVAILABLE, because "a later snapshot carrying
    the antecedent reference metrics" is satisfied trivially by six suppressed
    placeholders -- the keys are always emitted (S2a deviation 2) -- and a
    test that accepted that would pass against a build whose reference never
    resolves.
    """
    asset = asset_name_for("zone", scope_id)
    days_needed = (
        datetime(now.year, now.month, now.day, tzinfo=UTC) - datetime(year, 1, 1, tzinfo=UTC)
    ).days + 1
    for baseline_year in range(1991, 2021):
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(date(baseline_year, 1, 1), days_needed, 5.0),
        )
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_rows(date(year, 1, 1), days_needed, 3.0, provider_revision="v3-nrt"),
    )
    db.flush()
    return days_needed


def _revision_rows(db, fingerprint: str) -> list[RainfallAnalysisRevision]:
    from sqlalchemy import select

    return list(
        db.scalars(
            select(RainfallAnalysisRevision)
            .where(RainfallAnalysisRevision.request_fingerprint == fingerprint)
            .order_by(RainfallAnalysisRevision.created_at)
        ).all()
    )


def _without_the_reference(snapshot: dict, revision: str) -> dict:
    """The same envelope as a build under *revision* would have produced:
    restamped, and WITHOUT the six reference keys, which did not exist then.

    Stripping matters. Leaving them in -- even suppressed -- would make task
    4.3's "does not present reference metrics it never carried" pass against
    a stored row that carries them, which is the one thing it exists to catch.
    """
    stripped = {
        **snapshot,
        "metric_policy": {**snapshot["metric_policy"], "revision": revision},
    }
    for group in ("annual", "antecedents"):
        stripped[group] = {
            name: {**metric, "revision": revision}
            for name, metric in snapshot[group].items()
            if name not in _REFERENCE_KEYS
        }
    return stripped


# ===========================================================================
# 4.2 — a key materialized under the previous revision re-serves the enriched
#       envelope, and the earlier row is RETAINED
# ===========================================================================


def test_a_key_materialized_under_the_previous_revision_gains_the_reference_metrics(
    db, monkeypatch
):
    """4.2 (spec MODIFIED S2). Two builds of the SAME evidence, one under each
    policy revision, must produce TWO rows -- and the newer one must carry the
    six reference metrics as available values.

    Fixture shape, stated because it reads oddly: the first
    ``_persist_analysis_revision`` call is a DRY RUN, not an assertion. Its
    ``persist_revision`` is intercepted so nothing is written, which is how
    the test learns the ``data_revision`` this evidence hashes to without
    re-implementing ``compute.data_revision_for`` inside a test (a copy would
    then pass by agreeing with itself). A dry run rather than a
    write-then-delete because ``RainfallAnalysisRevision`` is append-only by
    a ``before_flush`` guard (models.py) -- deleting the probe row would mean
    disabling a production invariant to set up a test.

    The pre-bump row is then written with that exact ``data_revision``, and
    that identity is the load-bearing part: it is precisely the "evidence has
    not moved" case where ``persist_revision``'s ``ON CONFLICT DO NOTHING``
    would discard the enriched envelope if the policy revision had not moved
    with it.
    """
    from uuid import uuid4

    from app.domains.geo.rainfall import repository, tasks
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
    from app.domains.geo.rainfall.repository import persist_revision
    from app.domains.geo.rainfall.service import normalize_snapshot

    scope_id = "zone-s2b-rematerialization"
    year = 2025
    now = datetime(year, 4, 15, 12, 0, tzinfo=UTC)
    _seed_complete_evidence(db, scope_id=scope_id, year=year, now=now)

    scope = {"kind": "zone", "id": scope_id, "version": "v1"}
    fingerprint = _fingerprint_for(scope, year)
    outbox = _outbox_for(db, scope_id=scope_id, year=year, fingerprint=fingerprint)

    dry_run: dict = {}

    def _capture(_db, *, request_fingerprint, policy_revision, data_revision, snapshot):
        dry_run.update(
            request_fingerprint=request_fingerprint,
            policy_revision=policy_revision,
            data_revision=data_revision,
            snapshot=snapshot,
        )
        return uuid4()

    monkeypatch.setattr(repository, "persist_revision", _capture)
    probe = tasks._persist_analysis_revision(
        db, outbox_id=str(outbox.id), batch=_batch(scope_id, year=year), now=now
    )
    monkeypatch.undo()

    assert probe["decision"] == "write"
    assert dry_run["policy_revision"] == RAINFALL_METRIC_POLICY_REVISION
    assert dry_run["request_fingerprint"] == fingerprint
    data_revision = probe["data_revision"]
    probe_snapshot = dry_run["snapshot"]
    assert _revision_rows(db, fingerprint) == []

    # The pre-bump world: one row, previous revision, same evidence.
    persist_revision(
        db,
        request_fingerprint=fingerprint,
        policy_revision=_PREVIOUS_POLICY_REVISION,
        data_revision=data_revision,
        snapshot=_without_the_reference(probe_snapshot, _PREVIOUS_POLICY_REVISION),
    )
    db.flush()
    assert len(_revision_rows(db, fingerprint)) == 1

    # The refresh the stale-poll path schedules is processed.
    result = tasks._persist_analysis_revision(
        db, outbox_id=str(outbox.id), batch=_batch(scope_id, year=year), now=now
    )
    assert result["decision"] == "write"
    assert result["data_revision"] == data_revision, (
        "the evidence must not move between the two builds, or this test stops "
        "being about the policy bump"
    )

    db.flush()
    db.expire_all()
    rows = _revision_rows(db, fingerprint)

    # (a) The earlier revision is RETAINED, not overwritten.
    assert len(rows) == 2
    assert [row.policy_revision for row in rows] == [
        _PREVIOUS_POLICY_REVISION,
        RAINFALL_METRIC_POLICY_REVISION,
    ]
    older, newer = rows
    assert older.data_revision == newer.data_revision
    for key in _REFERENCE_KEYS:
        assert key not in older.snapshot["antecedents"], key

    # (b) The later snapshot carries the reference metrics, with values.
    normalized = normalize_snapshot(
        newer.snapshot, expected_policy_revision=RAINFALL_METRIC_POLICY_REVISION
    )
    antecedents = normalized["antecedents"]
    for key in _REFERENCE_KEYS:
        metric = antecedents[key]
        assert metric["state"] == "available", (key, metric)
        assert metric["value"] is not None, (key, metric)
        assert metric["reason"] is None, (key, metric)
        assert metric["revision"] == RAINFALL_METRIC_POLICY_REVISION, (key, metric)

    # The normals are the baseline's own 5.0 mm/day over their window: the
    # value is checked, not merely its presence, so a build that emitted the
    # key with an arbitrary number cannot pass.
    assert antecedents["d7_normal"]["value"] == pytest.approx(7 * 5.0)
    assert antecedents["d30_normal"]["value"] == pytest.approx(30 * 5.0)
    assert antecedents["d90_normal"]["value"] == pytest.approx(90 * 5.0)

    # The three antecedent TOTALS are unchanged across the bump -- the same
    # evidence, so the same millimetres. Only the reference is new.
    for window in ("d7", "d30", "d90"):
        assert (
            newer.snapshot["antecedents"][window]["value"]
            == older.snapshot["antecedents"][window]["value"]
        ), window


# ===========================================================================
# 4.3 — an old snapshot polled BEFORE its refresh lands is served under its
#       own revision and invents nothing
# ===========================================================================


def test_a_stale_snapshot_is_served_under_its_own_revision_without_the_reference(db, caplog):
    """4.3 (spec MODIFIED S3): the stored row is served, normalized against
    the policy revision it was WRITTEN under, and it must not appear to carry
    metrics that revision never produced.

    Normalizing it against the CURRENT revision instead would raise
    ``SnapshotContractError`` and 503 the read for every un-refreshed key in
    the deployment -- which is why ``read_analysis`` passes
    ``expected_policy_revision=stored_policy_revision`` rather than the
    module constant.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.auth import require_admin_or_operator
    from app.db.session import get_db
    from app.domains.geo.rainfall.compute import build_snapshot
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
    from app.domains.geo.rainfall.repository import persist_revision
    from app.domains.geo.rainfall.router import router
    from app.domains.geo.rainfall.scope import AnalysisScope

    scope_id = "zone-s2b-stale-serves-its-own"
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)
    rows = _daily_rows(date(year, 1, 1), 51, 3.0, provider_revision="v3-nrt")
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=rows,
    )
    db.flush()

    built = build_snapshot(
        scope=AnalysisScope(kind="zone", id=scope_id, version="v1", regional_estimate=False),
        year=year,
        role="daily",
        source_id="chirps-v3-sat",
        intervals=[(row.interval_start, row.interval_end, row.value) for row in rows],
        batch={
            "source_id": "chirps-v3-sat",
            "provider_revision": "v3-nrt",
            "unit": "mm",
            "cadence_seconds": 86400.0,
            "coverage": 1.0,
            "completeness": 1.0,
            "quality": {"scale_m": 5500, "provider_revision": "v3-nrt"},
            "discrepancies": [],
            "checksum": f"sha256:fixture-{scope_id}",
        },
        now=now,
    )
    scope = {"kind": "zone", "id": scope_id, "version": "v1"}
    fingerprint = _fingerprint_for(scope, year)
    persist_revision(
        db,
        request_fingerprint=fingerprint,
        policy_revision=_PREVIOUS_POLICY_REVISION,
        data_revision="b" * 64,
        snapshot=_without_the_reference(built, _PREVIOUS_POLICY_REVISION),
    )
    db.flush()

    app = FastAPI()
    app.dependency_overrides[require_admin_or_operator] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    app.include_router(router)

    caplog.set_level(logging.INFO, logger="rainfall")
    response = TestClient(app).post("/rainfall/analyses", json={"scope": scope, "year": year})

    assert response.status_code == 200
    body = response.json()

    # Served under its OWN revision, top to bottom.
    assert body["metric_policy"]["revision"] == _PREVIOUS_POLICY_REVISION
    assert RAINFALL_METRIC_POLICY_REVISION != _PREVIOUS_POLICY_REVISION
    for metric in body["antecedents"].values():
        assert metric["revision"] == _PREVIOUS_POLICY_REVISION, metric

    # And it invents nothing: the six keys it never carried are absent, not
    # synthesised as suppressed placeholders by the read path.
    for key in _REFERENCE_KEYS:
        assert key not in body["antecedents"], key
    assert set(body["antecedents"]) == {"d7", "d30", "d90"}

    # The healing refresh is scheduled exactly once, and it is labelled for
    # what it is, so an operator can tell a policy sweep from a data gap.
    from sqlalchemy import select

    queued = list(
        db.scalars(
            select(RainfallOutbox)
            .where(RainfallOutbox.scope_id == scope_id)
            .where(RainfallOutbox.status == "pending")
        ).all()
    )
    assert len(queued) == 1
    assert "policy_revision_stale" in queued[0].work_labels

    stale = next(
        json.loads(record.message.split(" ", 1)[1])
        for record in caplog.records
        if record.name == "rainfall"
        and record.message.startswith("rainfall.analysis.policy_revision_stale ")
    )
    assert stale["served_policy_revision"] == _PREVIOUS_POLICY_REVISION
    assert stale["current_policy_revision"] == RAINFALL_METRIC_POLICY_REVISION
