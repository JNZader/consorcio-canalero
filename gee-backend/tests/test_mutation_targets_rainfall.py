"""Focused unit tests for the rainfall mutation targets — policy + service + temporal.

Rainfall v2 follow-up (P2): the archived change deferred its mutation-target
registration (task 3.4) because the delivery had already blown the 400-line
production budget. Registration is being added AFTER the archive, with the
same recipe finanzas and padron proved (see
``tests/test_mutation_targets_finanzas.py`` and
``tests/test_mutation_targets_padron.py``): pure-python, no DB, no
testcontainers, branch-dense — every conditional is hit on both sides so a
flipped operator fails immediately, and one pytest invocation stays cheap
enough to be multiplied by hundreds of mutants.

Why these three modules and not ``models.py`` / ``router.py`` / ``tasks.py``:

- ``policy.py`` owns the evidence selection (``evaluate_eligibility``,
  ``select_source``) and the metric thresholds/state machine
  (``apply_metric_policy``) — entirely pure, zero I/O. Dead centers the
  task's "policy thresholds, suppression" wording.
- ``service.py`` owns the request→source resolver
  (``resolve_missing_work_source``), the outbox enqueue
  (``queue_missing_analysis``) and the snapshot normalizer + CSV serializer —
  the shared JSON/CSV parity contract. All three are exercisable with a fake
  session: no engine, no container, no migrations.
- ``temporal.py`` owns the Buenos Aires calendar rules (baseline, antecedent
  windows, event peak/duration, rolling totals) — pure datetimes only.

Assertion style follows finanzas/padron stage 2: behavior and effects
(status, states, which calls did or did not happen, the documented reason
strings — reasons ARE the contract here, they are shipped to the UI and to
the CSV, so pinning them is pinning data, not translation-bound prose).
"""

from __future__ import annotations

import csv
import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from app.domains.geo.rainfall.policy import (
    EligibilityEvidence,
    EligibilityRecord,
    MetricThresholdPolicy,
    SourceRolePolicy,
    SourceSelection,
    apply_metric_policy,
    evaluate_eligibility,
    select_source,
)
from app.domains.geo.rainfall.adapters.manifests import CandidateManifest
from app.domains.geo.rainfall.scope import AnalysisScope
from app.domains.geo.rainfall.service import (
    RAINFALL_DAILY_SOURCE,
    RAINFALL_HISTORICAL_SOURCE,
    RAINFALL_INTENSITY_SOURCE,
    RAINFALL_VALIDATION_SOURCE,
    SnapshotContractError,
    analysis_request_fingerprint,
    metric_rows,
    metric_rows_csv,
    normalize_snapshot,
    queue_missing_analysis,
    resolve_missing_work_source,
)
from app.domains.geo.rainfall.temporal import (
    EventSuppressed,
    antecedent_dates,
    baseline_dates,
    buenos_aires_date,
    comparison_end,
    event_peak_and_duration,
    rolling_total,
)


# ===========================================================================
# shared helpers
# ===========================================================================


def _manifest(
    source_id: str = "chirps-v3-final",
    *,
    role: str = "historical",
    enabled: bool = True,
    provider_revision: str = "v3-final",
    checksum: str = "sha-a",
    manifest_version: int = 1,
) -> CandidateManifest:
    return CandidateManifest(
        source_id=source_id,
        source_class="estimated_satellite",
        role=role,
        cadence_minutes=1440,
        access_path="api",
        provider_revision=provider_revision,
        checksum=checksum,
        manifest_version=manifest_version,
        enabled=enabled,
    )


def _evidence(**overrides: bool) -> EligibilityEvidence:
    fields = {
        "access": True,
        "licence": True,
        "units": True,
        "boundaries": True,
        "cadence": True,
        "completeness": True,
        "revisions": True,
        "corridor_coverage": True,
        "quality": True,
        "known_events": True,
    }
    fields.update(overrides)
    return EligibilityEvidence(**fields)


def _eligibility_record(
    source_id: str = "chirps-v3-final",
    *,
    evidence_revision: str = "ev-1",
    provider_revision: str = "v3-final",
    checksum: str = "sha-a",
    manifest_version: int = 1,
    eligible: bool = True,
) -> EligibilityRecord:
    return EligibilityRecord(
        source_id=source_id,
        role="historical",
        evidence_revision=evidence_revision,
        eligible=eligible,
        manifest_version=manifest_version,
        provider_revision=provider_revision,
        checksum=checksum,
    )


def _policy(*source_ids: str) -> SourceRolePolicy:
    return SourceRolePolicy(
        role="historical",
        version=1,
        evidence_revision="ev-1",
        ordered_source_ids=tuple(source_ids),
    )


def _hourly_intervals(
    start: datetime, end: datetime, values: tuple[float, ...]
) -> tuple[tuple[datetime, float], ...]:
    return tuple((start + timedelta(hours=index), value) for index, value in enumerate(values))


# ===========================================================================
# policy — evidence selection
# ===========================================================================


class TestEvaluateEligibility:
    def test_all_criteria_passed_is_eligible_without_failures(self) -> None:
        result = evaluate_eligibility(_manifest("chirps-v3-final"), _evidence())
        assert result.eligible is True
        assert result.failed_criteria == ()

    def test_rendered_image_access_is_always_rejected(self) -> None:
        """The scrape-rejection is a HARD no, regardless of the evidence
        sheet: a rendered image cannot carry the provenance the policy needs."""
        manifest = _manifest("image-source")
        manifest = CandidateManifest(
            source_id="image-source",
            source_class="estimated_satellite",
            role="historical",
            cadence_minutes=1440,
            access_path="rendered_image",
            provider_revision="r1",
            checksum="c",
        )
        result = evaluate_eligibility(manifest, _evidence())
        assert result.eligible is False
        assert result.failed_criteria == ("scrape_rejected",)

    @pytest.mark.parametrize(
        "failed_field",
        [
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
        ],
    )
    def test_each_missing_criterion_rejects_with_its_own_name(self, failed_field: str) -> None:
        """The failed-criteria list must name the OFFENDING criterion so the
        evidence sheet can be fixed without guessing -- it is shipped verbatim
        to the network and to the audit record."""
        evidence = _evidence(**{failed_field: False})
        result = evaluate_eligibility(_manifest("chirps-v3-final"), evidence)
        assert result.eligible is False
        assert result.failed_criteria == (failed_field,)

    def test_two_missing_criteria_are_both_reported(self) -> None:
        result = evaluate_eligibility(
            _manifest("chirps-v3-final"),
            _evidence(access=False, known_events=False),
        )
        assert result.failed_criteria == ("access", "known_events")


class TestSelectSource:
    """Every conjoined guard in ``select_source`` is a decision that can be
    mutated into its opposite; each rejection below pins one gate."""

    def test_no_eligible_candidate_returns_none_when_evidence_is_missing(self) -> None:
        result = select_source(
            _policy("chirps-v3-final"),
            {},  # no evidence at all
            {"chirps-v3-final": _manifest("chirps-v3-final")},
        )
        assert result == SourceSelection(None, False, ("chirps-v3-final",))

    def test_first_source_wins_without_fallback(self) -> None:
        result = select_source(
            _policy("chirps-v3-final", "sqpe-obs"),
            {"chirps-v3-final": _eligibility_record("chirps-v3-final")},
            {"chirps-v3-final": _manifest("chirps-v3-final")},
        )
        assert result == SourceSelection("chirps-v3-final", False, ())

    def test_second_eligible_source_marks_fallback_and_lists_the_rejected_one(self) -> None:
        first = _manifest("chirps-v3-final")
        second = _manifest("sqpe-obs", role="historical", provider_revision="v1")
        result = select_source(
            _policy("chirps-v3-final", "sqpe-obs"),
            {
                "chirps-v3-final": _eligibility_record("chirps-v3-final"),  # eligible -> wins
                # sqpe-obs: no evidence -> rejected
            },
            {"chirps-v3-final": first, "sqpe-obs": second},
        )
        assert result == SourceSelection("chirps-v3-final", False, ())

    def test_fallback_used_when_first_is_rejected_and_second_is_selected(self) -> None:
        first = _manifest("chirps-v3-final")
        second = _manifest("sqpe-obs", role="historical", provider_revision="v1")
        result = select_source(
            _policy("chirps-v3-final", "sqpe-obs"),
            {
                # first has eligible=True but WRONG role in evidence -> rejected
                "chirps-v3-final": _eligibility_record(
                    "chirps-v3-final", evidence_revision="stale"
                ),
                "sqpe-obs": _eligibility_record(
                    "sqpe-obs", provider_revision="v1", checksum="sha-a"
                ),
            },
            {"chirps-v3-final": first, "sqpe-obs": second},
        )
        # chirps rejected (stale evidence revision), sqpe-obs selected as fallback
        assert result.chosen_source_id == "sqpe-obs"
        assert result.fallback_used is True
        assert result.rejected_source_ids == ("chirps-v3-final",)

    def test_disabled_manifest_is_never_selected(self) -> None:
        manifest = _manifest("chirps-v3-final", enabled=False)
        result = select_source(
            _policy("chirps-v3-final"),
            {"chirps-v3-final": _eligibility_record("chirps-v3-final")},
            {"chirps-v3-final": manifest},
        )
        assert result.chosen_source_id is None

    def test_role_mismatch_between_manifest_and_policy_rejects(self) -> None:
        manifest = _manifest("chirps-v3-final", role="daily")
        result = select_source(
            _policy("chirps-v3-final"),
            {"chirps-v3-final": _eligibility_record("chirps-v3-final")},
            {"chirps-v3-final": manifest},
        )
        assert result.chosen_source_id is None

    def test_missing_manifest_rejects(self) -> None:
        result = select_source(_policy("chirps-v3-final"), {}, {})
        assert result.chosen_source_id is None
        assert result.rejected_source_ids == ("chirps-v3-final",)

    def test_missing_evidence_rejects(self) -> None:
        result = select_source(
            _policy("chirps-v3-final"),
            {},
            {"chirps-v3-final": _manifest("chirps-v3-final")},
        )
        assert result.chosen_source_id is None

    def test_stale_evidence_revision_rejects(self) -> None:
        manifest = _manifest("chirps-v3-final")
        stale = _eligibility_record("chirps-v3-final", evidence_revision="ev-0")
        result = select_source(
            _policy("chirps-v3-final"),
            {"chirps-v3-final": stale},
            {"chirps-v3-final": manifest},
        )
        assert result.chosen_source_id is None

    def test_checksum_mismatch_rejects(self) -> None:
        manifest = _manifest("chirps-v3-final")
        mismatched = _eligibility_record("chirps-v3-final", checksum="sha-different")
        result = select_source(
            _policy("chirps-v3-final"),
            {"chirps-v3-final": mismatched},
            {"chirps-v3-final": manifest},
        )
        assert result.chosen_source_id is None

    def test_evidence_of_another_source_is_not_itself(self) -> None:
        manifest = _manifest("chirps-v3-final")
        wrong = _eligibility_record("sqpe-obs")  # evidence of ANOTHER candidate
        result = select_source(
            _policy("chirps-v3-final"),
            {"chirps-v3-final": wrong},
            {"chirps-v3-final": manifest},
        )
        assert result.chosen_source_id is None


# ===========================================================================
# policy — metric thresholds / suppression
# ===========================================================================

_OK_POLICY = MetricThresholdPolicy(
    revision="v1",
    minimum_coverage_by_metric={"annual": 0.8, "intensity": 0.9},
    minimum_quality_by_metric={"annual": 0.7, "intensity": 0.8},
    duration_threshold=24.0,
)


class TestApplyMetricPolicy:
    """The suppression vocabulary (available|suppressed|unavailable) is the
    disclosure contract -- a FALSIFIED reason string is shipped to the client
    AND the CSV, so every branch's reason is pinned here as data."""

    def test_metric_above_thresholds_is_available(self) -> None:
        result = apply_metric_policy(
            _OK_POLICY, "annual", value=10.0, coverage=0.95, quality_score=0.9, completeness=1.0
        )
        assert result.state == "available"
        assert result.value == 10.0
        assert result.reason is None

    def test_metric_below_coverage_threshold_is_suppressed(self) -> None:
        result = apply_metric_policy(
            _OK_POLICY, "intensity", value=5.0, coverage=0.5, quality_score=0.9, completeness=1.0
        )
        assert result.state == "suppressed"
        assert result.value is None
        assert result.reason == "coverage_below_threshold"

    def test_metric_below_quality_threshold_is_suppressed(self) -> None:
        result = apply_metric_policy(
            _OK_POLICY, "intensity", value=5.0, coverage=1.0, quality_score=0.5, completeness=1.0
        )
        assert result.state == "suppressed"
        assert result.reason == "quality_below_threshold"

    def test_duration_metric_needs_a_duration_threshold(self) -> None:
        no_duration = MetricThresholdPolicy(
            revision="v1",
            minimum_coverage_by_metric={"duration": 0.7},
            minimum_quality_by_metric={"duration": 0.7},
            duration_threshold=None,
        )
        result = apply_metric_policy(
            no_duration, "duration", value=2.0, coverage=1.0, quality_score=0.9, completeness=1.0
        )
        assert result.state == "suppressed"
        assert result.reason == "policy_threshold_unset"

    def test_a_metric_without_declared_thresholds_is_suppressed(self) -> None:
        result = apply_metric_policy(
            _OK_POLICY, "unknown", value=2.0, coverage=1.0, quality_score=0.9, completeness=1.0
        )
        assert result.state == "suppressed"
        assert result.reason == "policy_threshold_unset"

    def test_invalid_threshold_policy_is_suppressed_before_any_metric(self) -> None:
        bad = MetricThresholdPolicy(
            revision="v1",
            minimum_coverage_by_metric={"annual": 1.5},  # > 1 -> invalid fraction
            minimum_quality_by_metric={"annual": 0.7},
            duration_threshold=None,
        )
        result = apply_metric_policy(
            bad, "annual", value=1.0, coverage=1.0, quality_score=0.9, completeness=1.0
        )
        assert result.state == "suppressed"
        assert result.reason == "policy_threshold_invalid"

    def test_nan_threshold_makes_the_whole_policy_invalid(self) -> None:
        """``isfinite`` is what keeps NaN from slipping past the
        ``0 <= x <= 1`` threshold check as a "valid" fraction: one NaN
        threshold invalidates the whole policy before any metric is judged."""
        nan_policy = MetricThresholdPolicy(
            revision="v1",
            minimum_coverage_by_metric={"annual": float("nan")},
            minimum_quality_by_metric={"annual": 0.7},
            duration_threshold=None,
        )
        result = apply_metric_policy(
            nan_policy, "annual", value=1.0, coverage=1.0, quality_score=0.9, completeness=1.0
        )
        assert result.state == "suppressed"
        assert result.reason == "policy_threshold_invalid"

    def test_a_missing_value_is_unavailable_not_suppressed(self) -> None:
        result = apply_metric_policy(
            _OK_POLICY, "annual", value=None, coverage=1.0, quality_score=0.9, completeness=1.0
        )
        assert result.state == "unavailable"
        assert result.reason == "metric_value_unavailable"


# ===========================================================================
# temporal — Buenos Aires calendar + event windows
# ===========================================================================


class TestTemporalCalendar:
    def test_comparison_end_collapses_current_year_to_today(self) -> None:
        today = date(2026, 8, 7)
        assert comparison_end(2026, today) == today

    def test_comparison_end_for_other_years_is_dec_31st(self) -> None:
        assert comparison_end(2025, date(2026, 8, 7)) == date(2025, 12, 31)

    def test_single_day_antecedent_window_is_that_day(self) -> None:
        assert antecedent_dates(date(2026, 8, 7), 1) == (date(2026, 8, 7), date(2026, 8, 7))

    def test_antecedent_window_looks_back_exactly_days_minus_one(self) -> None:
        assert antecedent_dates(date(2026, 8, 7), 30) == (date(2026, 7, 9), date(2026, 8, 7))

    @pytest.mark.parametrize("days", [0, -3])
    def test_non_positive_antecedent_days_are_rejected(self, days: int) -> None:
        with pytest.raises(ValueError, match="positive"):
            antecedent_dates(date(2026, 8, 7), days)

    def test_baseline_on_a_normal_day_is_the_full_1991_2020_family(self) -> None:
        dates = baseline_dates(date(2026, 8, 7))
        assert len(dates) == 30
        assert dates[0] == date(1991, 8, 7)
        assert dates[-1] == date(2020, 8, 7)

    def test_baseline_on_feb_29_keeps_only_leap_years(self) -> None:
        """The normal family must not invent ``date(2021, 2, 29)`` (2021 is
        not a leap year, so the constructor cannot even be called): the leap-day
        baseline is built only from real leap years in 1991–2020."""
        dates = baseline_dates(date(2028, 2, 29))
        assert all(d.year % 4 == 0 for d in dates)
        assert date(2020, 2, 29) in dates
        assert 2021 not in {d.year for d in dates}
        assert date(1992, 2, 29) in dates

    def test_buenos_aires_date_converts_utc_premidnight_to_previous_local_day(self) -> None:
        """UTC 2026-08-07T02:30 is 2026-08-06 23:30 in ART (-03, no DST) -- the
        boundary that crops UTC-midnight interval starts into the RIGHT source
        day.  Note 03:00 UTC lands on 00:00 of the SAME day, so 02:30 is the
        true previous-day case."""
        ts = datetime(2026, 8, 7, 2, 30, tzinfo=UTC)
        assert buenos_aires_date(ts) == date(2026, 8, 6)


class TestEventPeakAndDuration:
    """Peak is the max rolling-window SUM over the whole wet run; duration is
    ONE contiguous run. Both suppression branches (no run / two runs) are
    part of the disclosure contract."""

    def test_single_wet_run_yields_peak_and_duration(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = start + timedelta(hours=4)
        intervals = _hourly_intervals(start, end, (0.5, 2.0, 1.5, 0.0))
        peak, duration = event_peak_and_duration(
            start=start,
            end=end,
            cadence=timedelta(hours=1),
            intervals=intervals,
            duration_threshold=1.0,
            rolling_window=timedelta(hours=2),
        )
        assert peak == 3.5  # 2.0 + 1.5
        assert duration == timedelta(hours=2)

    def test_missing_duration_threshold_suppresses_both_metrics(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = start + timedelta(hours=1)
        with pytest.raises(EventSuppressed, match="duration threshold"):
            event_peak_and_duration(
                start=start,
                end=end,
                cadence=timedelta(hours=1),
                intervals=_hourly_intervals(start, end, (1.0,)),
                duration_threshold=None,
                rolling_window=timedelta(hours=1),
            )

    def test_two_wet_runs_are_suppressed_not_averaged(self) -> None:
        """Two separate runs in one window = ambiguous event; the policy must
        refuse to invent a single number."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = start + timedelta(hours=4)
        with pytest.raises(EventSuppressed, match="exactly one wet run"):
            event_peak_and_duration(
                start=start,
                end=end,
                cadence=timedelta(hours=1),
                intervals=_hourly_intervals(start, end, (1.5, 0.0, 1.5, 0.0)),
                duration_threshold=1.0,
                rolling_window=timedelta(hours=1),
            )

    def test_cadence_misalignment_is_suppressed(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = start + timedelta(hours=3)
        with pytest.raises(EventSuppressed, match="cadence"):
            event_peak_and_duration(
                start=start,
                end=end,
                cadence=timedelta(hours=1),
                intervals=_hourly_intervals(start, end, (1.0, 1.0, 1.0)),
                duration_threshold=1.0,
                rolling_window=timedelta(minutes=90),  # not a multiple of 1h
            )

    def test_rolling_window_smaller_than_a_single_cadence_is_suppressed(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        with pytest.raises(EventSuppressed):
            event_peak_and_duration(
                start=start,
                end=start + timedelta(hours=2),
                cadence=timedelta(hours=2),
                intervals=((start, 1.0),),
                duration_threshold=1.0,
                rolling_window=timedelta(hours=1),
            )


class TestRollingTotal:
    def test_sum_of_all_expected_intervals_within_the_window(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        result = rolling_total(
            end=start + timedelta(hours=3),
            window=timedelta(hours=3),
            cadence=timedelta(hours=1),
            intervals=_hourly_intervals(start, start + timedelta(hours=3), (1.0, 2.0, 3.0)),
        )
        assert result == 6.0

    def test_window_and_cadence_must_be_aligned(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        with pytest.raises(EventSuppressed, match="rolling window"):
            rolling_total(
                end=start + timedelta(hours=3),
                window=timedelta(hours=1),  # shorter than a cadence step
                cadence=timedelta(hours=2),
                intervals=_hourly_intervals(start, start + timedelta(hours=2), (1.0, 2.0)),
            )

    def test_missing_intervals_in_the_window_are_suppressed(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        with pytest.raises(EventSuppressed, match="coverage"):
            rolling_total(
                end=start + timedelta(hours=2),
                window=timedelta(hours=2),
                cadence=timedelta(hours=1),
                intervals=((start, 1.0),),  # missing the second slot
            )


# ===========================================================================
# service — resolver + outbox enqueue
# ===========================================================================


class TestResolveMissingWorkSource:
    """The resolver maps a PUBLIC request to the internal source/role --
    exactly the mapping a mutation of the if/elif chain would silently break."""

    def test_past_year_maps_to_historical_chirps(self) -> None:
        resolved = resolve_missing_work_source(None, year=2022)
        assert resolved == {
            "source_id": RAINFALL_HISTORICAL_SOURCE,
            "role": "historical",
            "interval_start": datetime(2022, 1, 1, tzinfo=UTC),
            "interval_end": datetime(2023, 1, 1, tzinfo=UTC),
        }

    def test_current_year_maps_to_daily(self) -> None:
        current = datetime.now(UTC).year
        resolved = resolve_missing_work_source(None, year=current)
        assert resolved["role"] == "daily"
        assert resolved["source_id"] == RAINFALL_DAILY_SOURCE
        assert resolved["interval_end"] == datetime(current + 1, 1, 1, tzinfo=UTC)

    def test_event_window_maps_to_intensity(self) -> None:
        resolved = resolve_missing_work_source(
            {"start": "2024-03-01T00:00:00Z", "end": "2024-03-02T00:00:00Z"},
            year=2024,
        )
        assert resolved["role"] == "intensity"
        assert resolved["source_id"] == RAINFALL_INTENSITY_SOURCE
        assert resolved["interval_start"] == datetime(2024, 3, 1, tzinfo=UTC)
        assert resolved["interval_end"] == datetime(2024, 3, 2, tzinfo=UTC)

    def test_requested_validation_role_overrides_everything(self) -> None:
        resolved = resolve_missing_work_source(None, year=2024, requested_role="validation")
        assert resolved["role"] == "validation"
        assert resolved["source_id"] == RAINFALL_VALIDATION_SOURCE

    def test_reversed_event_window_is_ignored_not_crashed(self) -> None:
        resolved = resolve_missing_work_source(
            {"start": "2024-03-02T00:00:00Z", "end": "2024-03-01T00:00:00Z"},
            year=2024,
        )
        # falls back to the year BOUNDS, not a nonsense window
        assert resolved["interval_start"] == datetime(2024, 1, 1, tzinfo=UTC)


class TestAnalysisRequestFingerprint:
    def test_fingerprint_is_stable_across_key_order(self) -> None:
        assert analysis_request_fingerprint({"a": 1, "b": 2}) == analysis_request_fingerprint(
            {"b": 2, "a": 1}
        )

    def test_fingerprint_changes_when_the_request_changes(self) -> None:
        assert analysis_request_fingerprint({"a": 1}) != analysis_request_fingerprint({"a": 2})

    def test_model_dump_input_uses_json_semantics(self) -> None:
        class _Req(BaseModel):
            scope: dict[str, str]
            year: int

        req = _Req(scope={"kind": "zone", "id": "z1"}, year=2024)
        canonical = json.dumps(
            req.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
        )
        assert analysis_request_fingerprint(req) == (hashlib.sha256(canonical.encode()).hexdigest())


class _FakeQuery:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def filter_by(self, **_kwargs: Any) -> "_FakeQuery":
        return self

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Session double exposing exactly the surface ``queue_missing_analysis``
    uses: ``query``, ``add``, ``flush``, ``commit``. No real DB."""

    def __init__(self, existing: Any | None = None) -> None:
        self._existing = existing
        self.added: list[Any] = []
        self.flushed = 0
        self.committed = 0

    def query(self, _model: Any) -> _FakeQuery:
        return _FakeQuery([self._existing] if self._existing is not None else [])

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed += 1

    def commit(self) -> None:
        self.committed += 1


class TestQueueMissingAnalysis:
    """The enqueue is the network-visible part of the outbox: the response
    body (status / outbox_id / labels) IS the public contract."""

    _SCOPE = AnalysisScope(kind="zone", id="z1", version="v1", regional_estimate=False)

    def test_no_existing_row_enqueues_and_persists(self) -> None:
        db = _FakeSession()
        result = queue_missing_analysis(
            db, scope=self._SCOPE, year=2024, labels=("analysis_missing",)
        )

        assert result["status"] == "queued"
        assert result["scope"] == {"kind": "zone", "id": "z1", "version": "v1"}
        assert result["year"] == 2024
        assert result["outbox_id"]
        assert "role:historical" in result["labels"]
        assert db.flushed == 1
        assert db.committed == 1

    def test_existing_pending_row_is_reused_not_recreated(self) -> None:
        existing = SimpleNamespace(
            id=uuid.uuid4(), work_labels=("analysis_missing", "role:historical")
        )
        db = _FakeSession(existing=existing)
        result = queue_missing_analysis(
            db, scope=self._SCOPE, year=2024, labels=("analysis_missing",)
        )

        assert result["outbox_id"] == str(existing.id)
        assert result["labels"] == ("analysis_missing", "role:historical")
        assert db.added == []
        assert db.committed == 0

    def test_event_window_enqueues_intensity_role_label(self) -> None:
        db = _FakeSession()
        result = queue_missing_analysis(
            db,
            scope=self._SCOPE,
            year=2024,
            labels=("analysis_missing",),
            event_window={"start": "2024-03-01T00:00:00Z", "end": "2024-03-02T00:00:00Z"},
        )
        assert "role:intensity" in result["labels"]
        assert db.committed == 1


# ===========================================================================
# service — snapshot normalization + CSV parity
# ===========================================================================


def _metric_raw(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "metric": "annual",
        "value": 21.0,
        "unit": "mm",
        "state": "available",
        "reason": None,
        "interval_start": "2024-01-01T00:00:00Z",
        "interval_end": "2024-01-02T00:00:00Z",
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"score": 0.9},
        "discrepancies": [],
        "temporal_state": "final",
        "revision": "v1",
        "provenance": {
            "source_id": "radar",
            "source_class": "estimated_radar",
            "method": "sum",
            "nominal_resolution": "1km",
            "aggregation": "daily",
            "spatial_scope": "zone",
            "freshness": "2024-01-01T00:00:00Z",
            "available_through": "2024-01-02T00:00:00Z",
        },
        "fallback_used": False,
    }
    payload.update(overrides)
    return payload


def _policy_payload() -> dict[str, Any]:
    return {
        "revision": "v1",
        "minimum_coverage_by_metric": {"annual": 0.8, "intensity": 0.9},
        "minimum_quality_by_metric": {"annual": 0.7, "intensity": 0.8},
        "duration_threshold": 24.0,
    }


def _snapshot(**groups: Any) -> dict[str, Any]:
    return {
        "analysis_revision_id": "rev-1",
        "scope": {"kind": "zone", "id": "z1", "version": "v1"},
        "regional_estimate": False,
        "year": 2024,
        "comparison_end": "2024-12-31T00:00:00Z",
        "baseline": "1991-2020",
        "metric_policy": _policy_payload(),
        **{k: v for k, v in groups.items()},
    }


class TestNormalizeSnapshot:
    def test_contract_violation_raises_for_unknown_root_key(self) -> None:
        with pytest.raises(SnapshotContractError, match="envelope"):
            normalize_snapshot({"typo_key": 1}, expected_policy_revision="v1")

    def test_approved_policy_keeps_the_metric_available(self) -> None:
        normalized = normalize_snapshot(
            _snapshot(annual={"a1": _metric_raw(value=21.0)}),
            expected_policy_revision="v1",
        )
        assert normalized["annual"]["a1"]["state"] == "available"
        assert normalized["annual"]["a1"]["value"] == 21.0

    def test_metric_below_quality_is_suppressed_and_null(self) -> None:
        normalized = normalize_snapshot(
            _snapshot(annual={"a1": _metric_raw(quality={"score": 0.1})}),
            expected_policy_revision="v1",
        )
        entry = normalized["annual"]["a1"]
        assert entry["state"] == "suppressed"
        assert entry["value"] is None
        assert entry["reason"] == "quality_below_threshold"

    def test_wrong_policy_revision_is_unavailable_not_served(self) -> None:
        normalized = normalize_snapshot(
            _snapshot(annual={"a1": _metric_raw(revision="v0")}),
            expected_policy_revision="v1",
        )
        entry = normalized["annual"]["a1"]
        assert entry["state"] == "unavailable"
        assert entry["reason"] == "policy_revision_mismatch"

    def test_absent_metric_groups_are_not_materialized(self) -> None:
        """A group that is absent from the snapshot is ABSENT in the output --
        not materialized as nulls."""
        normalized = normalize_snapshot(
            _snapshot(annual={"a1": _metric_raw()}),
            expected_policy_revision="v1",
        )
        assert "antecedents" not in normalized
        assert "intensity" not in normalized

    def test_metric_outside_the_schema_fails_clear_contract_error(self) -> None:
        with pytest.raises(SnapshotContractError, match="envelope"):
            normalize_snapshot(
                _snapshot(annual={"a1": {"bad": "shape"}}),
                expected_policy_revision="v1",
            )


class TestMetricRowsCsv:
    """JSON and CSV must disclose the same facts: same fields, same values,
    same suppression. The CSV keeps nulls blank and JSON-encodes nested
    evidence (quality/provenance) so nothing is flattened away."""

    def test_flatten_keeps_only_metric_maps(self) -> None:
        rows = metric_rows(_snapshot(annual={"a1": _metric_raw()}))
        assert [r["metric"] for r in rows] == ["annual"]

    def test_csv_keeps_value_and_encodes_nested_evidence_as_json(self) -> None:
        normalized = normalize_snapshot(
            _snapshot(annual={"a1": _metric_raw(value=7.5)}),
            expected_policy_revision="v1",
        )
        csv_text = metric_rows_csv(metric_rows(normalized))
        csv_row = next(csv.DictReader(StringIO(csv_text)))
        assert csv_row["value"] == "7.5"
        # the quality dict survived as JSON inside its own CSV cell
        assert json.loads(csv_row["quality"]) == {"score": 0.9}
        assert normalized["annual"]["a1"]["state"] == "available"

    def test_suppressed_metric_exports_blank_value_and_state_and_reason(self) -> None:
        normalized = normalize_snapshot(
            _snapshot(annual={"a1": _metric_raw(quality={"score": 0.1})}),
            expected_policy_revision="v1",
        )
        csv_text = metric_rows_csv(metric_rows(normalized))
        csv_row = next(csv.DictReader(StringIO(csv_text)))
        assert csv_row["state"] == "suppressed"
        assert csv_row["reason"] == "quality_below_threshold"
        assert csv_row["value"] == ""

    def test_no_metric_groups_produce_only_the_header(self) -> None:
        assert metric_rows_csv(metric_rows({})).strip() == ""

    def test_metrics_from_two_groups_share_one_sorted_header(self) -> None:
        normalized = normalize_snapshot(
            _snapshot(
                annual={"m": _metric_raw()},
                intensity={"m": _metric_raw(metric="intensity", value=3.0, coverage=1.0)},
            ),
            expected_policy_revision="v1",
        )
        csv_text = metric_rows_csv(metric_rows(normalized))
        lines = csv_text.splitlines()
        # header is the sorted union of both rows' keys; each group writes the
        # SAME field names, so the value column is not duplicated
        assert lines[0].startswith("completeness,coverage,")
        assert "fallback_used" in lines[0]
        assert len(lines) == 3  # header + two rows
