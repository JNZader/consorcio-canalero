"""Contract tests for the disabled-by-default Rainfall v2 evidence gate."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError


def _candidate(**overrides):
    from app.domains.geo.rainfall.adapters.manifests import CandidateManifest

    values = {
        "source_id": "imerg-v07",
        "source_class": "estimated_satellite",
        "role": "intensity",
        "cadence_minutes": 30,
        "access_path": "api",
        "provider_revision": "v07",
        "checksum": "fixture-checksum",
    }
    values.update(overrides)
    return CandidateManifest(**values)


def _passed_evidence(**overrides):
    from app.domains.geo.rainfall.policy import EligibilityEvidence

    values = {
        name: True
        for name in (
            "access",
            "licence",
            "units",
            "boundaries",
            "cadence",
            "completeness",
            "revisions",
            "corridor_coverage",
            "quality",
            "known_events",
        )
    }
    values.update(overrides)
    return EligibilityEvidence(**values)


def test_candidates_are_disabled_until_all_role_evidence_passes():
    from app.domains.geo.rainfall.policy import evaluate_eligibility

    assert evaluate_eligibility(_candidate(), _passed_evidence(units=False)).failed_criteria == (
        "units",
    )
    assert evaluate_eligibility(_candidate(), _passed_evidence()).eligible is True


def test_scraped_rendered_images_are_ineligible_even_when_other_evidence_passes():
    from app.domains.geo.rainfall.policy import evaluate_eligibility

    assert evaluate_eligibility(
        _candidate(access_path="rendered_image"), _passed_evidence()
    ).failed_criteria == ("scrape_rejected",)


def test_selection_requires_enabled_manifest_and_matching_role_without_blending():
    from app.domains.geo.rainfall.policy import EligibilityRecord, SourceRolePolicy, select_source

    preferred = _candidate(source_id="sinarame-rqpe", enabled=False)
    wrong_role = _candidate(source_id="imerg-v07", role="daily", enabled=True)
    policy = SourceRolePolicy("intensity", 1, "e1", (preferred.source_id, wrong_role.source_id))
    result = select_source(
        policy,
        {
            preferred.source_id: EligibilityRecord(preferred.source_id, "intensity", "e1", True),
            wrong_role.source_id: EligibilityRecord(wrong_role.source_id, "daily", "e1", True),
        },
        {preferred.source_id: preferred, wrong_role.source_id: wrong_role},
    )
    assert result.chosen_source_id is None
    assert result.rejected_source_ids == ("sinarame-rqpe", "imerg-v07")


def test_metric_result_rejects_missing_or_extra_evidence_metadata():
    from app.domains.geo.rainfall.schemas import MetricResult, Provenance

    now = datetime(2026, 1, 1, tzinfo=UTC)
    values = {
        "metric": "p30",
        "unit": "mm",
        "state": "available",
        "value": 1.0,
        "interval_start": now,
        "interval_end": now + timedelta(minutes=30),
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"verified": True},
        "discrepancies": (),
        "temporal_state": "final",
        "revision": "r1",
        "provenance": Provenance(
            source_id="fake",
            source_class="estimated_radar",
            method="fixture",
            nominal_resolution="1km",
            aggregation="sum",
            spatial_scope="zone",
            freshness=now,
            available_through=now,
        ),
        "fallback_used": False,
    }
    assert MetricResult(**values).coverage == 1.0
    with pytest.raises(ValidationError):
        MetricResult(**{key: value for key, value in values.items() if key != "quality"})
    with pytest.raises(ValidationError):
        MetricResult(**values, unexpected=True)


def test_source_batch_golden_contract_preserves_utc_cadence_coverage_revision_and_checksum():
    from app.domains.geo.rainfall.ports import SourceBatch, SourceInterval

    start = datetime(2024, 3, 20, 0, 0, tzinfo=UTC)
    intervals = tuple(
        SourceInterval(
            start + timedelta(minutes=30 * i),
            start + timedelta(minutes=30 * (i + 1)),
            value,
            "mm",
            "fake-r2",
        )
        for i, value in enumerate((12.0, 8.0))
    )
    batch = SourceBatch(
        "fake-radar",
        "zone",
        "zone-1",
        "v1",
        timedelta(minutes=30),
        intervals,
        1.0,
        1.0,
        {"known_event": "2024-03-20"},
        ("gauge_delta=0.2mm",),
        "sha256:known-event",
    )
    assert sum(item.value for item in batch.intervals) == 20.0
    assert batch.intervals[0].interval_end == batch.intervals[1].interval_start
    assert batch.checksum == "sha256:known-event"
    with pytest.raises(ValueError, match="cadence"):
        SourceBatch(
            "fake-radar",
            "zone",
            "zone-1",
            "v1",
            timedelta(minutes=30),
            (SourceInterval(start, start + timedelta(hours=1), 1.0, "mm", "fake-r2"),),
            1.0,
            1.0,
            {},
            (),
            "sha256:bad",
        )


def test_immutable_rows_reject_orm_update_and_delete_before_flush():
    from app.domains.geo.rainfall.models import (
        RainfallAnalysisRevision,
        RainfallIntervalValue,
        _prevent_rainfall_audit_mutation,
    )

    class SessionDouble:
        dirty: set[object]
        deleted: set[object]

    interval = RainfallIntervalValue(
        source_id="s",
        scope_kind="zone",
        scope_id="1",
        scope_version="v1",
        interval_start=datetime.now(UTC),
        interval_end=datetime.now(UTC) + timedelta(minutes=30),
        provider_revision="r1",
        value=1.0,
        unit="mm",
    )
    session = SessionDouble()
    session.dirty = {interval}
    session.deleted = set()
    with pytest.raises(ValueError, match="append-only"):
        _prevent_rainfall_audit_mutation(session, None, None)
    revision = RainfallAnalysisRevision(
        request_fingerprint="f", policy_revision="p", data_revision="d", snapshot={}
    )
    session.dirty = set()
    session.deleted = {revision}
    with pytest.raises(ValueError, match="append-only"):
        _prevent_rainfall_audit_mutation(session, None, None)


def test_checkpoint_identity_includes_scope_kind_and_version():
    from app.domains.geo.rainfall.models import RainfallBackfillCheckpoint

    columns = set(RainfallBackfillCheckpoint.__table__.columns)
    assert {"scope_kind", "scope_version", "completed_at"} <= {column.name for column in columns}


def test_eligibility_records_are_append_only_and_interval_lifecycle_is_separate():
    from app.domains.geo.rainfall.models import (
        RainfallIntervalLifecycle,
        RainfallSourceEligibility,
        _prevent_rainfall_audit_mutation,
    )

    class SessionDouble:
        dirty: set[object]
        deleted: set[object]

    eligibility = RainfallSourceEligibility(
        source_id="source",
        role="daily",
        evidence_revision="e1",
        eligible=True,
        criteria={},
        failed_criteria=[],
    )
    lifecycle = RainfallIntervalLifecycle(
        interval_value_id="00000000-0000-0000-0000-000000000001",
        event_type="superseded",
        expires_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    session = SessionDouble()
    session.dirty, session.deleted = {eligibility}, set()
    with pytest.raises(ValueError, match="append-only"):
        _prevent_rainfall_audit_mutation(session, None, None)
    assert lifecycle.event_type == "superseded"
    assert "superseded_at" not in {column.name for column in lifecycle.__table__.columns}


def test_selection_binds_eligibility_to_source_role_and_evidence_revision():
    from app.domains.geo.rainfall.policy import EligibilityRecord, SourceRolePolicy, select_source

    candidate = _candidate(source_id="imerg-v07", role="intensity", enabled=True)
    policy = SourceRolePolicy("intensity", 1, "e2", (candidate.source_id,))
    stale = EligibilityRecord(candidate.source_id, "intensity", "e1", True)
    mismatch = EligibilityRecord(candidate.source_id, "daily", "e2", True)
    valid = EligibilityRecord(candidate.source_id, "intensity", "e2", True)
    assert (
        select_source(
            policy, {candidate.source_id: stale}, {candidate.source_id: candidate}
        ).chosen_source_id
        is None
    )
    assert (
        select_source(
            policy, {candidate.source_id: mismatch}, {candidate.source_id: candidate}
        ).chosen_source_id
        is None
    )
    assert (
        select_source(
            policy, {candidate.source_id: valid}, {candidate.source_id: candidate}
        ).chosen_source_id
        == candidate.source_id
    )


@pytest.mark.parametrize(
    ("state", "value", "reason", "valid"),
    [
        ("available", None, None, False),
        ("available", 0.0, None, True),
        ("suppressed", 1.0, "policy", False),
        ("suppressed", None, None, False),
        ("suppressed", None, "policy", True),
        ("unavailable", None, "missing", True),
        ("partial", 0.0, None, True),
        ("partial", None, "incomplete", True),
    ],
)
def test_metric_result_enforces_state_value_reason_invariants(state, value, reason, valid):
    from app.domains.geo.rainfall.schemas import MetricResult, Provenance

    now = datetime(2026, 1, 1, tzinfo=UTC)
    values = dict(
        metric="p30",
        value=value,
        unit="mm",
        state=state,
        reason=reason,
        interval_start=now,
        interval_end=now + timedelta(minutes=30),
        coverage=1.0,
        completeness=1.0,
        quality={},
        discrepancies=(),
        temporal_state="final",
        revision="r1",
        provenance=Provenance(
            source_id="s",
            source_class="estimated_radar",
            method="m",
            nominal_resolution="1km",
            aggregation="sum",
            spatial_scope="zone",
            freshness=now,
            available_through=now,
        ),
        fallback_used=False,
    )
    if valid:
        assert MetricResult(**values).value == value
    else:
        with pytest.raises(ValidationError):
            MetricResult(**values)


def test_source_batch_and_adapter_include_stable_scope_identity():
    from app.domains.geo.rainfall.ports import RainfallSourceAdapter, SourceBatch, SourceInterval

    start = datetime(2024, 1, 1, tzinfo=UTC)
    interval = SourceInterval(start, start + timedelta(minutes=30), 1.0, "mm", "r1")
    batch = SourceBatch(
        "s", "zone", "zone-1", "v2", timedelta(minutes=30), (interval,), 1, 1, {}, (), "sum"
    )
    assert batch.scope_kind == "zone"
    assert batch.scope_version == "v2"
    assert "scope_kind" in RainfallSourceAdapter.fetch.__annotations__
    with pytest.raises(ValueError, match="scope"):
        SourceBatch("s", "", "zone-1", "", timedelta(minutes=30), (interval,), 1, 1, {}, (), "sum")
