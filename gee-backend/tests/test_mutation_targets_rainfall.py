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
    SPREADSHEET_FORMULA_PREFIXES,
    SnapshotContractError,
    analysis_request_fingerprint,
    metric_rows,
    metric_rows_csv,
    neutralize_spreadsheet_formula,
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
    uses: ``query``, ``add``, ``flush``, ``commit``, ``scalar``. No real DB.

    ``scalar`` backs THREE distinct ``select(...)``-based repository reads,
    called in this fixed order by ``queue_missing_analysis``: task 3.1's
    ``recent_done`` cooldown lookup, then LI2B-001/LI2B-003's
    ``repository.latest_terminal_attempt`` (the key's newest ``done``/
    ``failed`` row, which drives the failed and gate-refused cooldowns),
    then R2-003's ``repository.pending_row_for_key`` (the single "is there
    already a pending row for this key" check, replacing what used to be a
    ``db.query(...).filter_by(...).first()`` this fake answered via ``query``
    below). Positional, not query-inspecting -- good enough for this fake's
    one caller and its fixed call order; the defaults
    (``recent_done=None``/``terminal=None``/``existing=None``) keep every
    pre-existing test's behavior unchanged (no cooldown row, no terminal
    history, no reusable pending row -> the enqueue path runs as before).
    """

    def __init__(
        self,
        existing: Any | None = None,
        recent_done: Any | None = None,
        terminal: Any | None = None,
    ) -> None:
        self._existing = existing
        self._recent_done = recent_done
        self._terminal = terminal
        self._scalar_calls = 0
        self.added: list[Any] = []
        self.flushed = 0
        self.committed = 0

    def query(self, _model: Any) -> _FakeQuery:
        return _FakeQuery([self._existing] if self._existing is not None else [])

    def scalar(self, _query: Any) -> Any | None:
        self._scalar_calls += 1
        # 1st call: recent_done's cooldown lookup. 2nd: latest_terminal_attempt.
        # 3rd+: pending_row_for_key (queue_missing_analysis's pre-check, and
        # again after a simulated IntegrityError re-read -- neither existing
        # test drives that far).
        if self._scalar_calls == 1:
            return self._recent_done
        if self._scalar_calls == 2:
            return self._terminal
        return self._existing

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


class TestSpreadsheetFormulaNeutralization:
    """A CSV cell has no type, so the READER decides what it is.

    Excel and LibreOffice both evaluate a cell whose text starts with ``=``,
    ``+``, ``-``, ``@`` or a leading tab/CR on import, which is the CSV-injection
    class (LI3B-001). The xlsx export already refuses the same shape structurally
    (``cell.data_type = "s"``, export.py) -- the audit CSV is the MORE exposed of
    the two exports precisely because it has no such lever. One sanitizer, two
    consumers: the definition of "text a spreadsheet would execute" lives in one
    place so the two files can never disagree about the same value.
    """

    def test_every_owasp_trigger_prefix_is_neutralized(self) -> None:
        for hostile in ("=1+1", "+1", "-1", "@SUM(A1)", "\t=1+1", "\r=1+1"):
            assert neutralize_spreadsheet_formula(hostile) == f"'{hostile}"

    def test_benign_text_is_returned_verbatim(self) -> None:
        # Neutralizing indiscriminately would corrupt every unit, reason and
        # date the exports carry -- the guard must be invisible on real data.
        for benign in ("mm", "percentil", "quality_below_threshold", "2026-01-01", "", "0.5"):
            assert neutralize_spreadsheet_formula(benign) == benign

    def test_provider_fed_unit_reaches_the_csv_neutralized(self) -> None:
        # `unit` is the field the finding named: it is provider-fed and lands in
        # the file verbatim. A negative-looking unit is enough to make Excel
        # treat the cell as an expression.
        normalized = normalize_snapshot(
            _snapshot(annual={"a1": _metric_raw(unit="=cmd|'/c calc'!A1")}),
            expected_policy_revision="v1",
        )
        csv_row = next(csv.DictReader(StringIO(metric_rows_csv(metric_rows(normalized)))))
        assert csv_row["unit"] == "'=cmd|'/c calc'!A1"

    def test_the_json_envelope_is_what_makes_nested_evidence_inert(self) -> None:
        # `discrepancies` is provider-fed, so a hostile entry gets in. What
        # keeps the CELL inert is the JSON envelope, not the formula guard: the
        # encoded text always opens with `[` or `{`, which no spreadsheet reads
        # as an expression. This pins BOTH halves of that claim, because they
        # are what justify `_csv_cell` not guarding the encoded form (LI4-002).
        #
        # The previous version of this test asserted `not startswith("=")` on a
        # cell that opens with `[` by construction, so it passed whether or not
        # the guard ran and proved nothing about either.
        normalized = normalize_snapshot(
            _snapshot(annual={"a1": _metric_raw(discrepancies=["=1+1"])}),
            expected_policy_revision="v1",
        )
        cell = next(csv.DictReader(StringIO(metric_rows_csv(metric_rows(normalized)))))[
            "discrepancies"
        ]
        # 1. The envelope holds: the cell opens with a character no reader
        #    evaluates. Drop `json.dumps` and this is Python's repr instead.
        assert cell.startswith("[")
        assert not cell.startswith(SPREADSHEET_FORMULA_PREFIXES)
        # 2. …and the payload survives VERBATIM inside it. An export is
        #    evidence: quoting or stripping what the provider sent would be a
        #    worse defect than the one being guarded against.
        assert json.loads(cell) == ["=1+1"]

    def test_a_hostile_string_cell_is_still_neutralized_at_cell_level(self) -> None:
        # The counterpart to the test above, at the level `_csv_cell` actually
        # decides: a bare `str` has NO envelope, so it is the shape that still
        # needs the guard. `reason` is provider-adjacent and lands in the file
        # verbatim.
        normalized = normalize_snapshot(
            _snapshot(annual={"a1": _metric_raw(reason="=1+1", state="suppressed", value=None)}),
            expected_policy_revision="v1",
        )
        cell = next(csv.DictReader(StringIO(metric_rows_csv(metric_rows(normalized)))))["reason"]
        assert cell == "'=1+1"

    def test_numbers_are_never_quoted_into_text(self) -> None:
        # The CSV exists to be re-read as data. A negative FLOAT is a number,
        # not executable text, and prefixing it would break every consumer that
        # parses the column.
        normalized = normalize_snapshot(
            _snapshot(annual={"a1": _metric_raw(value=-3.5, coverage=1.0)}),
            expected_policy_revision="v1",
        )
        csv_row = next(csv.DictReader(StringIO(metric_rows_csv(metric_rows(normalized)))))
        assert csv_row["value"] == "-3.5"


# ===========================================================================
# service — the disclosure-time summary (lluvia-insights slice 2b, D4)
# ===========================================================================


def _post_policy_metric(name: str, **overrides: Any) -> dict[str, Any]:
    """What ``_normalize_metric`` actually hands the summary: the RAW build
    dict with ``value``/``state``/``reason`` overwritten by the policy
    outcome (``{**raw, ...}``, service.py). Build-time ``completeness`` and
    ``quality`` survive UNTOUCHED at 1.0 -- which is exactly the trap: a
    summary derived from completeness would call a policy-suppressed metric
    available."""
    payload: dict[str, Any] = {
        "metric": name,
        "value": 12.0,
        "unit": "mm",
        "state": "available",
        "reason": None,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"score": 1.0},
    }
    payload.update(overrides)
    return payload


class TestRainfallSummary:
    """Tasks 2b.1/2b.2/2b.4 (design.md D4 coherence invariant): the summary
    is assembled at DISCLOSURE time from post-``apply_metric_policy`` states,
    never from build-time completeness, so the narrative can never contradict
    the badges printed beside it."""

    def test_summary_never_describes_a_policy_suppressed_metric_as_available(self) -> None:
        """Spec: "Policy suppresses a metric the raw data would have
        supported"."""
        from app.domains.geo.rainfall.service import (
            SUMMARY_AVAILABLE_PREFIX,
            SUMMARY_MISSING_PREFIX,
            rainfall_summary,
        )

        summary = rainfall_summary(
            {
                "annual": {
                    "selected": _post_policy_metric("annual", value=204.0),
                    # Build-time completeness still reads 1.0; the policy
                    # suppressed it at disclosure.
                    "normal": _post_policy_metric(
                        "annual_normal",
                        value=None,
                        state="suppressed",
                        reason="coverage_below_threshold",
                    ),
                }
            }
        )

        assert "Normal 1991–2020 (suprimida: coverage_below_threshold)" in summary
        available, _, missing = summary.partition(SUMMARY_MISSING_PREFIX)
        assert available.startswith(SUMMARY_AVAILABLE_PREFIX)
        # The suppressed metric is named ONLY in the "sin dato" sentence, and
        # the served value (204.0) belongs to the metric that really has one.
        assert "Normal 1991–2020" not in available
        assert "Acumulado del año 204.0 mm" in available
        assert "204.0" not in missing

    @staticmethod
    def _sections(summary: str) -> dict[str, list[str]]:
        """``{bucket prefix: [entry, ...]}``. One sentence per bucket,
        entries separated by "; ". The sentence terminator is a period
        followed by a space or end-of-string, so a decimal point inside a
        value (204.0) never splits an entry."""
        import re

        from app.domains.geo.rainfall.service import (
            SUMMARY_AVAILABLE_PREFIX,
            SUMMARY_MISSING_PREFIX,
            SUMMARY_PARTIAL_PREFIX,
        )

        sections: dict[str, list[str]] = {}
        for prefix in (SUMMARY_AVAILABLE_PREFIX, SUMMARY_PARTIAL_PREFIX, SUMMARY_MISSING_PREFIX):
            match = re.search(rf"{re.escape(prefix)} (.*?)\.(?:\s|$)", summary)
            if match is not None:
                sections[prefix] = match.group(1).split("; ")
        return sections

    def test_summary_states_match_disclosed_metric_states(self) -> None:
        """Spec: "Summary and badges cannot disagree" -- every state the
        narrative names for a metric is that metric's own disclosed state."""
        from app.domains.geo.rainfall.service import (
            SUMMARY_AVAILABLE_PREFIX,
            SUMMARY_METRIC_LABELS,
            SUMMARY_MISSING_PREFIX,
            SUMMARY_PARTIAL_PREFIX,
            SUMMARY_STATE_LABELS,
            rainfall_summary,
        )

        groups = {
            "annual": {
                "selected": _post_policy_metric("annual", value=204.0),
                "normal": _post_policy_metric(
                    "annual_normal",
                    value=None,
                    state="suppressed",
                    reason="baseline_years_below_minimum",
                ),
                "percentile": _post_policy_metric(
                    "annual_percentile",
                    value=None,
                    state="unavailable",
                    reason="policy_revision_mismatch",
                ),
            },
            "antecedents": {
                "d7": _post_policy_metric("d7", value=14.0, state="partial"),
                "d90": _post_policy_metric(
                    "d90", value=None, state="suppressed", reason="antecedent_window_incomplete"
                ),
            },
        }
        summary = rainfall_summary(groups)
        sections = self._sections(summary)
        bucket_for_state = {
            "available": SUMMARY_AVAILABLE_PREFIX,
            "partial": SUMMARY_PARTIAL_PREFIX,
        }

        entries = [entry for section in sections.values() for entry in section]
        assert len(entries) == 5  # every disclosed metric is narrated exactly once

        for group in groups.values():
            for name, metric in group.items():
                label = SUMMARY_METRIC_LABELS[name]
                expected_bucket = bucket_for_state.get(metric["state"], SUMMARY_MISSING_PREFIX)
                matching = [
                    (prefix, entry)
                    for prefix, section in sections.items()
                    for entry in section
                    if entry.startswith(label)
                ]
                assert len(matching) == 1, (label, matching)
                prefix, entry = matching[0]
                # Membership in the "Disponibles" sentence IS the state
                # claim, so a suppressed metric cannot be narrated as served.
                assert prefix == expected_bucket, (label, prefix, expected_bucket)
                if metric["state"] in {"available", "partial"}:
                    # A metric with a value states it, and names no state
                    # word that could disagree with its own badge.
                    assert entry == f"{label} {metric['value']:.1f} {metric['unit']}"
                else:
                    # "no disponible" CONTAINS "disponible", so the state is
                    # pinned as the whole token, never as a substring search.
                    expected_state = SUMMARY_STATE_LABELS[metric["state"]]
                    assert entry == f"{label} ({expected_state}: {metric['reason']})"

    def test_summary_of_an_empty_envelope_claims_nothing(self) -> None:
        from app.domains.geo.rainfall.service import rainfall_summary

        assert rainfall_summary({}) == "Este análisis no divulga métricas."

    def test_summary_is_written_at_disclosure_and_overwrites_a_stale_one(self) -> None:
        """``normalize_snapshot`` OWNS the root ``summary`` key: a narrative
        that somehow reached the stored envelope is replaced by the one
        derived from the states actually being served, never merged with it."""
        normalized = normalize_snapshot(
            _snapshot(
                annual={"selected": _metric_raw(quality={"score": 0.1})},
                summary="una narrativa vieja que ya no describe lo servido",
            ),
            expected_policy_revision="v1",
        )
        assert normalized["annual"]["selected"]["reason"] == "quality_below_threshold"
        assert "una narrativa vieja" not in normalized["summary"]
        assert "quality_below_threshold" in normalized["summary"]


# ===========================================================================
# compute.py — pure NRT-correction revision helpers (rainfall-materialization PR1)
# ===========================================================================


class TestRevisionFamilyAndCorrectionRevision:
    """PR1 task 1.2: ``revision_family``/``correction_revision`` round-trip.

    Pure, no I/O — the compute.py boundary rule (design.md "Technical
    Approach"). CHIRPS pins one revision string per source_id and restates
    values behind it (chirps.py:26-29); these two helpers are what lets a
    restated value become a *new* row instead of silently colliding on
    ``uq_rainfall_interval_revision``.
    """

    def test_revision_family_and_correction_revision_roundtrip(self) -> None:
        from app.domains.geo.rainfall.compute import correction_revision, revision_family

        assert revision_family("v3-nrt+r2") == "v3-nrt"
        assert correction_revision("v3-nrt", 2) == "v3-nrt+r2"
        assert revision_family(correction_revision("v3-nrt", 2)) == "v3-nrt"

    def test_revision_family_of_a_bare_family_revision_is_itself(self) -> None:
        from app.domains.geo.rainfall.compute import revision_family

        # No adapter has ever emitted a corrected slot yet — the family IS
        # the whole provider_revision string (chirps.py:26-29 live values).
        assert revision_family("v3-final") == "v3-final"
        assert revision_family("v3-nrt") == "v3-nrt"

    def test_correction_revision_first_and_second_ordinal(self) -> None:
        from app.domains.geo.rainfall.compute import correction_revision

        assert correction_revision("v3-nrt", 1) == "v3-nrt+r1"
        assert correction_revision("v3-nrt", 2) == "v3-nrt+r2"

    def test_correction_revision_rejects_non_positive_ordinal(self) -> None:
        from app.domains.geo.rainfall.compute import correction_revision

        with pytest.raises(ValueError, match="ordinal"):
            correction_revision("v3-nrt", 0)
        with pytest.raises(ValueError, match="ordinal"):
            correction_revision("v3-nrt", -1)


class TestSixDecimalEqualityBoundary:
    """PR1 task 1.4: the *same* rounding ``data_revision_for`` will hash
    (decision 3b) decides whether a restated value is a no-op or a
    correction — a difference too small to move the 6th decimal must never
    mint a ``rainfall_interval_lifecycle`` row claiming a correction the
    disclosure cannot show."""

    def test_six_decimal_equality_boundary(self) -> None:
        from app.domains.geo.rainfall.repository import _values_equal_at_6dp

        # Equal at 6 decimal places despite not being bit-identical.
        assert _values_equal_at_6dp(1.5000001, 1.5) is True
        # A restatement large enough to move the 6th decimal is NOT equal.
        assert _values_equal_at_6dp(1.500002, 1.5) is False

    def test_six_decimal_equality_is_symmetric(self) -> None:
        from app.domains.geo.rainfall.repository import _values_equal_at_6dp

        assert _values_equal_at_6dp(0.0, 0.0000001) is True
        assert _values_equal_at_6dp(0.0000001, 0.0) is True


# ===========================================================================
# policy.py — RAINFALL_METRIC_POLICY constants (rainfall-materialization PR2, task 2.8)
# ===========================================================================


class TestRainfallMetricPolicyConstants:
    """decision 5d: a frozen module constant, not a settings-driven read —
    the display path (service.py's ``_metric_policy``) rejects a revision
    mismatch, so the policy MUST be embedded in every snapshot rather than
    looked up live."""

    def test_rainfall_metric_policy_constants_shape(self) -> None:
        from app.domains.geo.rainfall.policy import (
            RAINFALL_METRIC_POLICY,
            RAINFALL_METRIC_POLICY_REVISION,
            MetricThresholdPolicy,
        )

        assert isinstance(RAINFALL_METRIC_POLICY_REVISION, str)
        assert RAINFALL_METRIC_POLICY_REVISION
        assert isinstance(RAINFALL_METRIC_POLICY, MetricThresholdPolicy)
        assert RAINFALL_METRIC_POLICY.revision == RAINFALL_METRIC_POLICY_REVISION
        assert RAINFALL_METRIC_POLICY.minimum_coverage_by_metric["annual"] == 0.8
        assert RAINFALL_METRIC_POLICY.minimum_quality_by_metric["annual"] == 0.8
        # A well-formed threshold policy the shared apply_metric_policy state
        # machine can actually evaluate (guards against a policy so broken
        # every snapshot's annual metric silently comes back suppressed).
        applied = apply_metric_policy(
            RAINFALL_METRIC_POLICY,
            "annual",
            value=10.0,
            coverage=0.9,
            quality_score=0.9,
            completeness=0.9,
        )
        assert applied.state == "available"
        assert applied.value == 10.0


# ===========================================================================
# compute.py — build_snapshot + data_revision_for (rainfall-materialization
# PR2, tasks 2.4-2.7)
# ===========================================================================


def _fixture_batch_evidence(**overrides: Any) -> dict[str, Any]:
    """Matches the JSON-safe shape tasks.py's ``_batch_result`` returns."""
    payload: dict[str, Any] = {
        "source_id": "chirps-v3-final",
        "scope_kind": "zone",
        "scope_id": "z1",
        "year": 2024,
        "intervals": 3,
        "persisted": 3,
        "superseded": 0,
        "provider_revision": "v3-final",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {
            "catalog_id": "UCSB-CHC/CHIRPS/V3/DAILY_RNL",
            "band": "precipitation",
            "reduction": "mean",
            "scale_m": 5500,
            "provider_revision": "v3-final",
        },
        "discrepancies": [],
        "checksum": "sha256:fixture",
    }
    payload.update(overrides)
    return payload


_ZONE_SCOPE = AnalysisScope(kind="zone", id="z1", version="v1", regional_estimate=False)


def _daily_intervals(*, start: date, values: list[float]) -> list[tuple[datetime, datetime, float]]:
    rows = []
    for offset, value in enumerate(values):
        day_start = datetime(start.year, start.month, start.day, tzinfo=UTC) + timedelta(
            days=offset
        )
        rows.append((day_start, day_start + timedelta(days=1), value))
    return rows


class TestBuildSnapshotEnvelope:
    """Task 2.4 (v1) / task 2a.7 (v2 slice 2a): root keys are a subset of
    SNAPSHOT_ROOT_KEYS. v1 shipped only annual.selected; slice 2a grows the
    envelope with annual.{normal,percentile} (design.md D4/D5) -- ALWAYS
    present, suppressed rather than omitted when no baseline is resolved --
    and antecedents.{d7,d30,d90} (design.md D6). Every metric carries the
    full extra="forbid" field set with quality["score"] in [0, 1]
    (decision 5b)."""

    def test_build_snapshot_envelope_contract(self) -> None:
        from app.domains.geo.rainfall.compute import build_snapshot
        from app.domains.geo.rainfall.service import SNAPSHOT_ROOT_KEYS

        now = datetime(2024, 6, 15, tzinfo=UTC)
        intervals = _daily_intervals(start=date(2024, 1, 1), values=[1.0, 2.0, 3.0])
        snapshot = build_snapshot(
            scope=_ZONE_SCOPE,
            year=2024,
            role="historical",
            source_id="chirps-v3-final",
            intervals=intervals,
            batch=_fixture_batch_evidence(),
            now=now,
        )

        assert set(snapshot) <= SNAPSHOT_ROOT_KEYS
        # No baseline was given (default None) -- normal/percentile are
        # PRESENT (never omitted from the envelope) but suppressed, task
        # 2a.7's baseline_scope_unmapped branch.
        assert set(snapshot["annual"]) == {"selected", "normal", "percentile"}
        assert set(snapshot["antecedents"]) == {"d7", "d30", "d90"}
        assert snapshot["annual"]["normal"]["state"] == "suppressed"
        assert snapshot["annual"]["normal"]["reason"] == "baseline_scope_unmapped"
        assert snapshot["annual"]["percentile"]["state"] == "suppressed"
        assert snapshot["annual"]["percentile"]["reason"] == "baseline_scope_unmapped"

        metric = snapshot["annual"]["selected"]
        expected_fields = {
            "metric",
            "value",
            "unit",
            "state",
            "reason",
            "interval_start",
            "interval_end",
            "coverage",
            "completeness",
            "quality",
            "discrepancies",
            "temporal_state",
            "revision",
            "provenance",
            "fallback_used",
        }
        assert set(metric) == expected_fields
        assert 0 <= metric["quality"]["score"] <= 1
        assert metric["value"] == 6.0
        assert metric["state"] == "available"

        provenance = metric["provenance"]
        assert provenance["source_id"] == "chirps-v3-final"
        assert provenance["spatial_scope"] == "zone"

        # Every new metric shares the SAME MetricResult field contract.
        for group_name, member_name in (
            ("annual", "normal"),
            ("annual", "percentile"),
            ("antecedents", "d7"),
            ("antecedents", "d30"),
            ("antecedents", "d90"),
        ):
            assert set(snapshot[group_name][member_name]) == expected_fields

    def test_build_snapshot_emits_no_summary_key(self) -> None:
        """Task 2b.3 (design.md D4): the narrative is assembled at
        DISCLOSURE time, from post-policy states. ``compute.py`` is pure and
        never applies policy, so any summary it emitted would describe
        states that may never be the ones served -- it must emit none."""
        from app.domains.geo.rainfall.compute import build_snapshot

        snapshot = build_snapshot(
            scope=_ZONE_SCOPE,
            year=2024,
            role="historical",
            source_id="chirps-v3-final",
            intervals=_daily_intervals(start=date(2024, 1, 1), values=[1.0, 2.0, 3.0]),
            batch=_fixture_batch_evidence(),
            now=datetime(2024, 6, 15, tzinfo=UTC),
            baseline={year: (10.0, 365, 365) for year in range(1991, 2021)},
        )
        assert "summary" not in snapshot

    def test_build_snapshot_raises_on_duplicate_interval_start(self) -> None:
        """Task 2.7: a duplicated slot is a broken invariant, not a sum —
        intervals_in_window's anti-join is supposed to guarantee at most one
        row per slot; a violation must be loud."""
        from app.domains.geo.rainfall.compute import build_snapshot

        start = datetime(2024, 1, 1, tzinfo=UTC)
        duplicated = [
            (start, start + timedelta(days=1), 1.0),
            (start, start + timedelta(days=1), 5.0),
        ]
        with pytest.raises(ValueError, match="duplicat"):
            build_snapshot(
                scope=_ZONE_SCOPE,
                year=2024,
                role="historical",
                source_id="chirps-v3-final",
                intervals=duplicated,
                batch=_fixture_batch_evidence(),
                now=datetime(2024, 6, 15, tzinfo=UTC),
            )


class TestBuildSnapshotCoverageWindow:
    """Task 2.5: coverage/completeness/quality are recomputed over
    [year_start, min(comparison_end, last_interval_end)), not the raw fetch
    window — otherwise a current year in progress would report the
    completeness of a FULL year against a handful of published days."""

    def test_build_snapshot_bounds_coverage_window_to_available_through(self) -> None:
        from app.domains.geo.rainfall.compute import build_snapshot

        # 5 days published in a year that (per `now`) has run for far longer
        # than 5 days — completeness must be measured against the DISCLOSED
        # window, not the full year, or it would read near zero forever.
        now = datetime.now(UTC)
        current_year = now.year
        intervals = _daily_intervals(
            start=date(current_year, 1, 1), values=[1.0, 1.0, 1.0, 1.0, 1.0]
        )
        snapshot = build_snapshot(
            scope=_ZONE_SCOPE,
            year=current_year,
            role="daily",
            source_id="chirps-v3-sat",
            intervals=intervals,
            batch=_fixture_batch_evidence(
                source_id="chirps-v3-sat",
                provider_revision="v3-nrt",
                quality={
                    "catalog_id": "UCSB-CHC/CHIRPS/V3/DAILY_SAT",
                    "band": "precipitation",
                    "reduction": "mean",
                    "scale_m": 5500,
                    "provider_revision": "v3-nrt",
                },
            ),
            now=now,
        )
        metric = snapshot["annual"]["selected"]
        # available_through tracks the last PUBLISHED day, not the calendar
        # comparison_end (the provider is lagging behind `now` by design).
        assert metric["provenance"]["available_through"] == (
            datetime(current_year, 1, 6, tzinfo=UTC).isoformat()
        )
        assert metric["completeness"] == 1.0
        assert metric["coverage"] == 1.0
        assert metric["value"] == 5.0

    def test_build_snapshot_with_no_data_in_window_is_unavailable(self) -> None:
        from app.domains.geo.rainfall.compute import build_snapshot

        now = datetime(2024, 3, 1, tzinfo=UTC)
        snapshot = build_snapshot(
            scope=_ZONE_SCOPE,
            year=2024,
            role="daily",
            source_id="chirps-v3-sat",
            intervals=[],
            batch=_fixture_batch_evidence(intervals=0, persisted=0),
            now=now,
        )
        metric = snapshot["annual"]["selected"]
        assert metric["state"] == "unavailable"
        assert metric["value"] is None
        assert metric["reason"]
        assert metric["completeness"] == 0.0


class TestDataRevisionFor:
    """Task 2.6: content address stable across an unchanged (intervals,
    comparison_end) pair, and changes when comparison_end alone advances
    (decision 3b — this is what makes the daily revisit sweep mint a new
    revision even when the provider republished nothing new)."""

    def test_data_revision_for_stability_and_advance(self) -> None:
        from app.domains.geo.rainfall.compute import data_revision_for

        rows = [
            (datetime(2024, 1, 1, tzinfo=UTC), 1.5),
            (datetime(2024, 1, 2, tzinfo=UTC), 2.5),
        ]
        first = data_revision_for(
            "chirps-v3-final", "v3-final", _ZONE_SCOPE, 2024, date(2024, 1, 2), rows
        )
        same_again = data_revision_for(
            "chirps-v3-final", "v3-final", _ZONE_SCOPE, 2024, date(2024, 1, 2), list(rows)
        )
        assert first == same_again

        advanced = data_revision_for(
            "chirps-v3-final", "v3-final", _ZONE_SCOPE, 2024, date(2024, 1, 3), rows
        )
        assert advanced != first

        changed_value = data_revision_for(
            "chirps-v3-final",
            "v3-final",
            _ZONE_SCOPE,
            2024,
            date(2024, 1, 2),
            [(datetime(2024, 1, 1, tzinfo=UTC), 9.9), rows[1]],
        )
        assert changed_value != first

    def test_data_revision_for_is_order_independent(self) -> None:
        from app.domains.geo.rainfall.compute import data_revision_for

        rows = [
            (datetime(2024, 1, 1, tzinfo=UTC), 1.5),
            (datetime(2024, 1, 2, tzinfo=UTC), 2.5),
        ]
        forward = data_revision_for(
            "chirps-v3-final", "v3-final", _ZONE_SCOPE, 2024, date(2024, 1, 2), rows
        )
        reversed_order = data_revision_for(
            "chirps-v3-final",
            "v3-final",
            _ZONE_SCOPE,
            2024,
            date(2024, 1, 2),
            list(reversed(rows)),
        )
        assert forward == reversed_order


# ===========================================================================
# compute.py — fingerprint_lock_key + served_state + revision_write_decision
# (rainfall-materialization PR3, tasks 3.2/3.4/3.5)
# ===========================================================================


class TestFingerprintLockKey:
    """Task 3.2: the per-fingerprint advisory lock key (design.md
    "Serializing siblings"). No new column -- the fingerprint the outbox row
    already carries IS a lowercase sha256 hex digest (service.py:102-107);
    the key is the first 16 hex chars (8 bytes) read as an unsigned
    big-endian int, reinterpreted as PostgreSQL's signed bigint."""

    def test_fingerprint_lock_key_is_deterministic(self) -> None:
        from app.domains.geo.rainfall.compute import fingerprint_lock_key

        fp = "deadbeef" * 8
        assert fingerprint_lock_key(fp) == fingerprint_lock_key(fp)

    def test_fingerprint_lock_key_stays_inside_postgres_bigint_range(self) -> None:
        from app.domains.geo.rainfall.compute import fingerprint_lock_key

        for prefix in ("00" * 8, "ff" * 8, "7f" + "ff" * 7, "80" + "00" * 7):
            key = fingerprint_lock_key(prefix + "00" * 24)
            assert -(1 << 63) <= key < (1 << 63)

    def test_fingerprint_lock_key_wraps_a_high_first_bit_to_negative(self) -> None:
        """The wraparound branch: a digest whose first byte is >= 0x80 has
        its top bit set as an unsigned int -- reinterpreted as bigint, that
        maps to a NEGATIVE key."""
        from app.domains.geo.rainfall.compute import fingerprint_lock_key

        assert fingerprint_lock_key("8" + "0" * 63) < 0
        assert fingerprint_lock_key("7" + "0" * 63) >= 0

    def test_fingerprint_lock_key_matches_hand_computed_values(self) -> None:
        from app.domains.geo.rainfall.compute import fingerprint_lock_key

        # First 16 hex chars "0000000000000001" -> unsigned 1 -> signed 1.
        assert fingerprint_lock_key("0" * 15 + "1" + "0" * 48) == 1
        # First bit set: 0x8000000000000000 unsigned -> -2**63 signed (the
        # exact wraparound boundary).
        assert fingerprint_lock_key("8" + "0" * 63) == -(1 << 63)
        # All-ones prefix: 0xFFFFFFFFFFFFFFFF unsigned -> -1 signed.
        assert fingerprint_lock_key("f" * 16 + "0" * 48) == -1


def _snapshot_with(
    *, source_id: str, temporal_state: str, **metric_overrides: Any
) -> dict[str, Any]:
    """Minimal well-formed snapshot for served_state/revision_write_decision
    unit tests -- only the fields those two pure readers touch."""
    metric: dict[str, Any] = {
        "metric": "annual",
        "value": 500.0,
        "coverage": 0.95,
        "completeness": 0.95,
        "quality": {"score": 0.95},
        "temporal_state": temporal_state,
        "provenance": {"source_id": source_id},
    }
    metric.update(metric_overrides)
    return {"annual": {"selected": metric}}


class TestServedState:
    """Task 3.4: reads (annual.selected.provenance.source_id,
    annual.selected.temporal_state) from a complete envelope, None when
    either is missing -- the ONE reader shared by stage-2 selection and the
    write gate (design.md "What served state means, and where it is read
    from")."""

    def test_served_state_reads_the_disclosed_pair(self) -> None:
        from app.domains.geo.rainfall.compute import served_state

        snapshot = _snapshot_with(source_id="chirps-v3-final", temporal_state="final")
        assert served_state(snapshot) == ("chirps-v3-final", "final")

    def test_served_state_is_none_when_provenance_is_missing(self) -> None:
        from app.domains.geo.rainfall.compute import served_state

        snapshot = {"annual": {"selected": {"temporal_state": "final"}}}
        assert served_state(snapshot) is None

    def test_served_state_is_none_when_temporal_state_is_missing(self) -> None:
        from app.domains.geo.rainfall.compute import served_state

        snapshot = {"annual": {"selected": {"provenance": {"source_id": "chirps-v3-final"}}}}
        assert served_state(snapshot) is None

    def test_served_state_is_none_when_annual_group_is_absent(self) -> None:
        from app.domains.geo.rainfall.compute import served_state

        assert served_state({}) is None


class TestRevisionWriteDecision:
    """Task 3.5: every branch of decision 9b's write gate."""

    def test_no_incumbent_writes(self) -> None:
        from app.domains.geo.rainfall.compute import revision_write_decision
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        candidate = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        assert revision_write_decision(None, candidate, RAINFALL_METRIC_POLICY) == "write"

    def test_incumbent_with_unreadable_served_state_writes(self) -> None:
        """A corrupt/pre-contract incumbent row -- unreadable, not final --
        must stay replaceable."""
        from app.domains.geo.rainfall.compute import revision_write_decision
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        candidate = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        assert revision_write_decision({}, candidate, RAINFALL_METRIC_POLICY) == "write"

    def test_same_source_id_writes(self) -> None:
        from app.domains.geo.rainfall.compute import revision_write_decision
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        incumbent = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        candidate = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        assert revision_write_decision(incumbent, candidate, RAINFALL_METRIC_POLICY) == "write"

    def test_provisional_candidate_over_final_incumbent_is_latched(self) -> None:
        from app.domains.geo.rainfall.compute import revision_write_decision
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        incumbent = _snapshot_with(source_id="chirps-v3-final", temporal_state="final")
        candidate = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        assert revision_write_decision(incumbent, candidate, RAINFALL_METRIC_POLICY) == "latched"

    def test_cross_source_available_writes(self) -> None:
        from app.domains.geo.rainfall.compute import revision_write_decision
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        incumbent = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        candidate = _snapshot_with(
            source_id="chirps-v3-final",
            temporal_state="final",
            coverage=0.9,
            completeness=0.9,
            quality={"score": 0.9},
        )
        assert revision_write_decision(incumbent, candidate, RAINFALL_METRIC_POLICY) == "write"

    def test_cross_source_below_coverage_is_gate_refused(self) -> None:
        from app.domains.geo.rainfall.compute import revision_write_decision
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        incumbent = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        candidate = _snapshot_with(
            source_id="chirps-v3-final",
            temporal_state="final",
            coverage=0.5,
            completeness=0.9,
            quality={"score": 0.9},
        )
        assert (
            revision_write_decision(incumbent, candidate, RAINFALL_METRIC_POLICY) == "gate_refused"
        )

    def test_cross_source_below_completeness_is_gate_refused(self) -> None:
        from app.domains.geo.rainfall.compute import revision_write_decision
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        incumbent = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        candidate = _snapshot_with(
            source_id="chirps-v3-final",
            temporal_state="final",
            coverage=0.9,
            completeness=0.5,
            quality={"score": 0.9},
        )
        assert (
            revision_write_decision(incumbent, candidate, RAINFALL_METRIC_POLICY) == "gate_refused"
        )

    def test_cross_source_below_quality_is_gate_refused(self) -> None:
        from app.domains.geo.rainfall.compute import revision_write_decision
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        incumbent = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        candidate = _snapshot_with(
            source_id="chirps-v3-final",
            temporal_state="final",
            coverage=0.9,
            completeness=0.9,
            quality={"score": 0.5},
        )
        assert (
            revision_write_decision(incumbent, candidate, RAINFALL_METRIC_POLICY) == "gate_refused"
        )

    def test_cross_source_null_value_is_gate_refused(self) -> None:
        """Adequate coverage/completeness/quality but a null value ->
        apply_metric_policy returns "unavailable", never "available" -> the
        gate refuses (design.md: "all three are refusals here")."""
        from app.domains.geo.rainfall.compute import revision_write_decision
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        incumbent = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        candidate = _snapshot_with(
            source_id="chirps-v3-final",
            temporal_state="final",
            coverage=0.9,
            completeness=0.9,
            quality={"score": 0.9},
            value=None,
        )
        assert (
            revision_write_decision(incumbent, candidate, RAINFALL_METRIC_POLICY) == "gate_refused"
        )

    def test_cross_source_coverage_equal_to_threshold_boundary_writes(self) -> None:
        """policy.py:166 is `<`, so equality PASSES -- the exact boundary
        task 3.5 must pin."""
        from app.domains.geo.rainfall.compute import revision_write_decision
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        incumbent = _snapshot_with(source_id="chirps-v3-sat", temporal_state="provisional")
        candidate = _snapshot_with(
            source_id="chirps-v3-final",
            temporal_state="final",
            coverage=0.8,
            completeness=0.8,
            quality={"score": 0.8},
        )
        assert revision_write_decision(incumbent, candidate, RAINFALL_METRIC_POLICY) == "write"


# ===========================================================================
# service.py — resolve_missing_work_source `now` seam (rainfall-materialization
# PR3, task 3.8)
# ===========================================================================


class TestResolveMissingWorkSourceNowSeam:
    """Task 3.8: `now` feeds EXACTLY the `year == now.year` routing test and
    nothing else -- threaded IN from sweep stage 2's re-resolution; the
    request path (`queue_missing_analysis`) leaves it unset so a live
    request always routes on the real clock."""

    def test_now_seam_routes_current_year_to_daily(self) -> None:
        resolved = resolve_missing_work_source(None, 2024, now=datetime(2024, 6, 15, tzinfo=UTC))
        assert resolved["role"] == "daily"
        assert resolved["source_id"] == RAINFALL_DAILY_SOURCE

    def test_now_seam_routes_completed_year_to_historical(self) -> None:
        resolved = resolve_missing_work_source(None, 2024, now=datetime(2025, 1, 2, tzinfo=UTC))
        assert resolved["role"] == "historical"
        assert resolved["source_id"] == RAINFALL_HISTORICAL_SOURCE

    def test_now_none_falls_back_to_the_real_clock(self) -> None:
        current = datetime.now(UTC).year
        resolved = resolve_missing_work_source(None, current, now=None)
        assert resolved["role"] == "daily"


# ===========================================================================
# service.py — RAINFALL_VALIDATION_SOURCE matches the manifest
# (rainfall-materialization PR3, task 3.18)
# ===========================================================================


class TestValidationSourceMatchesManifest:
    def test_validation_identifier_matches_manifest(self) -> None:
        from app.domains.geo.rainfall.adapters.manifests import CANDIDATE_MANIFESTS

        manifest = next(m for m in CANDIDATE_MANIFESTS if m.role == "validation")
        assert RAINFALL_VALIDATION_SOURCE == manifest.source_id == "smn-gauge"


# ===========================================================================
# compute.py — weibull_percentile (lluvia-insights slice 2a, task 2a.1/D5)
# ===========================================================================


class TestWeibullPercentile:
    """Task 2a.1/D5: empirical Weibull plotting-position rank over the
    baseline PLUS the selected year (N = n+1); ties take the MEAN of their
    tied 1-based positions."""

    def test_lowest_and_highest_selected_value_bound_the_range_at_n30(self) -> None:
        from app.domains.geo.rainfall.compute import weibull_percentile

        baseline = [float(value) for value in range(1, 31)]  # 30 distinct baseline years
        lowest = weibull_percentile(baseline, 0.0)  # below every baseline year
        highest = weibull_percentile(baseline, 999.0)  # above every baseline year
        assert lowest == pytest.approx(100 * 1 / 32)
        assert highest == pytest.approx(100 * 31 / 32)
        assert 3.0 < lowest < 3.2
        assert 96.8 < highest < 97.0

    def test_median_selected_value_lands_exactly_at_the_middle(self) -> None:
        from app.domains.geo.rainfall.compute import weibull_percentile

        baseline = [float(value) for value in range(1, 31)]
        # No tie: 15.5 sits strictly between the 15th and 16th baseline
        # values, so it is unambiguously the combined sample's 16th (1-based).
        result = weibull_percentile(baseline, 15.5)
        assert result == pytest.approx(50.0)

    def test_tied_values_share_the_mean_position(self) -> None:
        from app.domains.geo.rainfall.compute import weibull_percentile

        # combined sorted: [10, 20, 20, 20] -- the THREE 20s (2 baseline +
        # the tied selected value) occupy 1-based positions 2, 3, 4 -- mean 3.
        baseline = [10.0, 20.0, 20.0]
        result = weibull_percentile(baseline, 20.0)
        assert result == pytest.approx(100 * 3 / (4 + 1))


# ===========================================================================
# compute.py — annual.normal/annual.percentile 20-year floor (lluvia-insights
# slice 2a, tasks 2a.3/2a.4/2a.5/D5)
# ===========================================================================


class TestNormalAndPercentileBaselineFloor:
    """Task 2a.3/2a.5: MIN_BASELINE_YEARS=20 is a SAMPLE-SIZE gate
    apply_metric_policy cannot express (it only sees fractions) -- below
    it, both metrics suppress with their own reason, distinct from any
    coverage/quality threshold outcome."""

    _COMPARISON_END = date(2026, 8, 7)  # not Feb 29 -> full 30-year family

    @staticmethod
    def _complete_baseline(years: range) -> dict[int, tuple[float, int, int]]:
        return {year: (10.0, 365, 365) for year in years}

    def test_19_eligible_years_suppresses_below_minimum(self) -> None:
        from app.domains.geo.rainfall.compute import _normal_and_percentile_metrics

        normal, percentile = _normal_and_percentile_metrics(
            baseline=self._complete_baseline(range(1991, 1991 + 19)),
            baseline_cutoff=self._COMPARISON_END,
            selected_value=12.0,
            selected_temporal_state="final",
            selected_source_id="chirps-v3-sat",
            nominal_resolution="1000m",
            scope=_ZONE_SCOPE,
            now=datetime(2026, 8, 7, 12, 0, tzinfo=UTC),
        )
        assert normal["state"] == "suppressed"
        assert normal["reason"] == "baseline_years_below_minimum"
        assert normal["value"] is None
        assert percentile["state"] == "suppressed"
        assert percentile["reason"] == "baseline_years_below_minimum"
        assert percentile["value"] is None

    def test_20_eligible_years_is_not_suppressed_by_the_floor(self) -> None:
        from app.domains.geo.rainfall.compute import _normal_and_percentile_metrics

        normal, percentile = _normal_and_percentile_metrics(
            baseline=self._complete_baseline(range(1991, 1991 + 20)),
            baseline_cutoff=self._COMPARISON_END,
            selected_value=12.0,
            selected_temporal_state="final",
            selected_source_id="chirps-v3-sat",
            nominal_resolution="1000m",
            scope=_ZONE_SCOPE,
            now=datetime(2026, 8, 7, 12, 0, tzinfo=UTC),
        )
        assert normal["state"] == "available"
        assert normal["reason"] is None
        assert normal["value"] == pytest.approx(10.0)
        assert percentile["state"] == "available"
        assert percentile["reason"] is None

    def test_selected_value_unavailable_suppresses_only_percentile(self) -> None:
        """Author counterexample self-check (Null/absence): the RANK needs
        a selected-year total to rank AGAINST; the normal (a pure baseline
        average) does not -- a resolved, eligible baseline still yields an
        `available` normal even when the selected year itself has no value."""
        from app.domains.geo.rainfall.compute import _normal_and_percentile_metrics

        normal, percentile = _normal_and_percentile_metrics(
            baseline=self._complete_baseline(range(1991, 2021)),
            baseline_cutoff=self._COMPARISON_END,
            selected_value=None,
            selected_temporal_state="provisional",
            selected_source_id="chirps-v3-sat",
            nominal_resolution="1000m",
            scope=_ZONE_SCOPE,
            now=datetime(2026, 8, 7, 12, 0, tzinfo=UTC),
        )
        assert normal["state"] == "available"
        assert normal["value"] == pytest.approx(10.0)
        assert percentile["state"] == "suppressed"
        assert percentile["reason"] == "annual_selected_value_unavailable"
        assert percentile["value"] is None


class TestBaselineFloorBindsAtDisclosure:
    """LI2A-003 (slice 2b amendment A2): ``MIN_BASELINE_YEARS`` was DEAD
    CODE at disclosure time. ``annual_normal``/``annual_percentile`` carry
    ``completeness = eligible_years / 30`` (and ``quality["score"]`` is the
    same number, D4), so a 0.9 threshold made the effective floor 27
    eligible years -- and in the reachable 20-26 band the served reason was
    ``coverage_below_threshold``, misattributing a sample-size shortfall as
    a coverage problem. Both thresholds are now ``MIN_BASELINE_YEARS / 30``,
    so the compute-level floor -- the one with the distinct reason D5
    promises -- is the binding gate."""

    _NOW = datetime(2024, 8, 7, 12, 0, tzinfo=UTC)

    @staticmethod
    def _normalized_annual(eligible_years: int) -> dict[str, Any]:
        from app.domains.geo.rainfall.compute import build_snapshot
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
        from app.domains.geo.rainfall.service import normalize_snapshot

        snapshot = build_snapshot(
            scope=_ZONE_SCOPE,
            year=2024,
            role="daily",
            source_id="chirps-v3-sat",
            intervals=_daily_intervals(start=date(2024, 1, 1), values=[5.0] * 220),
            batch=_fixture_batch_evidence(source_id="chirps-v3-sat"),
            now=TestBaselineFloorBindsAtDisclosure._NOW,
            # Every year complete, so the per-year 0.95 filter keeps all of
            # them: `eligible_years` is exactly the sample size under test.
            baseline={year: (10.0, 365, 365) for year in range(1991, 1991 + eligible_years)},
        )
        normalized = normalize_snapshot(
            snapshot, expected_policy_revision=RAINFALL_METRIC_POLICY_REVISION
        )
        return normalized["annual"]

    def test_19_years_suppresses_with_the_distinct_sample_size_reason(self) -> None:
        annual = self._normalized_annual(19)
        for name in ("normal", "percentile"):
            assert annual[name]["state"] == "suppressed", (name, annual[name])
            assert annual[name]["reason"] == "baseline_years_below_minimum", (name, annual[name])
            assert annual[name]["value"] is None, (name, annual[name])

    def test_21_years_is_served_instead_of_misreported_as_a_coverage_shortfall(self) -> None:
        annual = self._normalized_annual(21)
        for name in ("normal", "percentile"):
            # Pre-amendment this was suppressed `coverage_below_threshold`
            # (21/30 = 0.7 < 0.9) -- a sample-size shortfall wearing a
            # coverage label, for a sample the floor itself accepts.
            assert annual[name]["reason"] != "coverage_below_threshold", (name, annual[name])
            assert annual[name]["state"] == "available", (name, annual[name])
            assert annual[name]["value"] is not None, (name, annual[name])

    def test_exactly_the_floor_is_served_at_the_float_equality_boundary(self) -> None:
        """The threshold IS ``MIN_BASELINE_YEARS / 30`` -- the same float
        division ``completeness`` performs -- so the boundary case compares
        equal and passes. A hand-rounded 0.6667 would suppress it."""
        annual = self._normalized_annual(20)
        for name in ("normal", "percentile"):
            assert annual[name]["state"] == "available", (name, annual[name])

    def test_thresholds_track_the_compute_floor_rather_than_drifting_from_it(self) -> None:
        from app.domains.geo.rainfall.compute import MIN_BASELINE_YEARS
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY
        from app.domains.geo.rainfall.temporal import baseline_years_for

        baseline_years = len(baseline_years_for(date(2026, 8, 7)))  # 30, non-Feb-29
        expected = MIN_BASELINE_YEARS / baseline_years
        for metric in ("annual_normal", "annual_percentile"):
            assert RAINFALL_METRIC_POLICY.minimum_coverage_by_metric[metric] == expected
            # `quality["score"]` for these two IS `completeness` (D4), so a
            # higher quality threshold would re-suppress the same band under
            # a different reason.
            assert RAINFALL_METRIC_POLICY.minimum_quality_by_metric[metric] == expected

    def test_other_metrics_keep_their_own_thresholds(self) -> None:
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

        coverage = RAINFALL_METRIC_POLICY.minimum_coverage_by_metric
        quality = RAINFALL_METRIC_POLICY.minimum_quality_by_metric
        assert (coverage["annual"], quality["annual"]) == (0.8, 0.8)
        for window in ("d7", "d30", "d90"):
            assert (coverage[window], quality[window]) == (0.9, 0.8)


class TestPercentileFeb29SmallSample:
    """Task 2a.4/D5: February 29 has only 8 leap years in 1991-2020
    (temporal.baseline_years_for) -- structurally below MIN_BASELINE_YEARS,
    with no special-case code needed (spec: "February 29 rank on a small
    sample")."""

    def test_feb_29_baseline_has_only_8_leap_years_and_suppresses(self) -> None:
        from app.domains.geo.rainfall.compute import _normal_and_percentile_metrics
        from app.domains.geo.rainfall.temporal import baseline_years_for

        comparison_end = date(2028, 2, 29)
        leap_years = baseline_years_for(comparison_end)
        assert len(leap_years) == 8  # 1992, 1996, ..., 2020

        # Even a FULLY complete baseline for all 8 leap years cannot clear
        # MIN_BASELINE_YEARS=20.
        baseline = {year: (10.0, 366, 366) for year in leap_years}
        normal, percentile = _normal_and_percentile_metrics(
            baseline=baseline,
            baseline_cutoff=comparison_end,
            selected_value=11.0,
            selected_temporal_state="final",
            selected_source_id="chirps-v3-sat",
            nominal_resolution="1000m",
            scope=_ZONE_SCOPE,
            now=datetime(2028, 2, 29, 12, 0, tzinfo=UTC),
        )
        assert normal["state"] == "suppressed"
        assert normal["reason"] == "baseline_years_below_minimum"
        assert percentile["state"] == "suppressed"
        assert percentile["reason"] == "baseline_years_below_minimum"


# ===========================================================================
# compute.py — annual.normal/annual.percentile envelope shape (lluvia-insights
# slice 2a, task 2a.6/D5)
# ===========================================================================


class TestAnnualNormalAndPercentileEnvelopeShape:
    """Task 2a.6: normal/percentile carry provenance.source_id ==
    "chirps-v3-final" REGARDLESS of the selected year's own source
    (design.md D5), percentile's unit is "percentil" (not "%"), and both
    share the baseline envelope interval bounds (1991-01-01 -> last
    baseline comparison_end + 1 day)."""

    def test_normal_and_percentile_envelope_shape(self) -> None:
        from app.domains.geo.rainfall.compute import build_snapshot

        now = datetime(2024, 8, 7, 12, 0, tzinfo=UTC)
        intervals = _daily_intervals(start=date(2024, 1, 1), values=[5.0] * 220)
        baseline = {year: (10.0, 365, 365) for year in range(1991, 2021)}  # all 30 complete

        snapshot = build_snapshot(
            scope=_ZONE_SCOPE,
            year=2024,
            role="daily",
            source_id="chirps-v3-sat",  # the SELECTED year's own source -- daily/NRT
            intervals=intervals,
            batch=_fixture_batch_evidence(
                source_id="chirps-v3-sat",
                provider_revision="v3-nrt",
                quality={
                    "catalog_id": "UCSB-CHC/CHIRPS/V3/DAILY_SAT",
                    "band": "precipitation",
                    "reduction": "mean",
                    "scale_m": 5500,
                    "provider_revision": "v3-nrt",
                },
            ),
            now=now,
            baseline=baseline,
        )

        normal = snapshot["annual"]["normal"]
        percentile = snapshot["annual"]["percentile"]

        # NOT the selected year's chirps-v3-sat -- the baseline is always
        # Final, regardless of what sourced the selected year.
        assert normal["provenance"]["source_id"] == "chirps-v3-final"
        assert percentile["provenance"]["source_id"] == "chirps-v3-final"
        assert percentile["unit"] == "percentil"
        assert normal["unit"] == "mm"

        expected_start = datetime(1991, 1, 1, tzinfo=UTC).isoformat()
        expected_end = (datetime(2020, 8, 7, tzinfo=UTC) + timedelta(days=1)).isoformat()
        assert normal["interval_start"] == expected_start
        assert normal["interval_end"] == expected_end
        assert percentile["interval_start"] == expected_start
        assert percentile["interval_end"] == expected_end


# ===========================================================================
# compute.py — cross-source baseline caveat (lluvia-insights slice 2b,
# tasks 2b.9/2b.10/2b.11, design.md D5 / LIB-003)
# ===========================================================================


class TestCrossSourceBaselineCaveat:
    """A current-year comparison ranks an NRT-sourced total against a
    Final-sourced baseline -- a methodological caveat the reader cannot infer
    from the numbers, and one the baseline has no channel of its own to carry
    (it comes from a SQL aggregate, so there is no adapter batch to inherit
    ``discrepancies`` from). ``build_snapshot`` therefore emits a fixed entry
    into normal's and percentile's OWN ``discrepancies``, and only where the
    caveat is actually true."""

    _CAVEAT = "cross_source_baseline=chirps-v3-final_vs_chirps-v3-sat"
    _NOW = datetime(2024, 8, 7, 12, 0, tzinfo=UTC)

    @classmethod
    def _snapshot_for(cls, source_id: str, provider_revision: str) -> dict[str, Any]:
        from app.domains.geo.rainfall.compute import build_snapshot

        return build_snapshot(
            scope=_ZONE_SCOPE,
            year=2024,
            role="daily" if source_id != "chirps-v3-final" else "historical",
            source_id=source_id,
            intervals=_daily_intervals(start=date(2024, 1, 1), values=[5.0] * 220),
            batch=_fixture_batch_evidence(source_id=source_id, provider_revision=provider_revision),
            now=cls._NOW,
            baseline={year: (10.0, 365, 365) for year in range(1991, 2021)},
        )

    def test_caveat_is_present_for_an_nrt_selected_year(self) -> None:
        snapshot = self._snapshot_for("chirps-v3-sat", "v3-nrt")

        for name in ("normal", "percentile"):
            metric = snapshot["annual"][name]
            assert metric["discrepancies"] == [self._CAVEAT], (name, metric["discrepancies"])
            # It belongs to the two metrics it biases, not to the selected
            # year (whose own discrepancies stay the adapter batch's).
            assert metric["state"] == "available", (name, metric)
        assert self._CAVEAT not in snapshot["annual"]["selected"]["discrepancies"]

    def test_caveat_is_absent_when_both_sides_are_final(self) -> None:
        snapshot = self._snapshot_for("chirps-v3-final", "v3-final")

        for name in ("normal", "percentile"):
            assert snapshot["annual"][name]["discrepancies"] == [], name

    def test_caveat_survives_policy_normalization_into_the_served_metric(self) -> None:
        """design.md D5: ``discrepancies`` is carried through
        ``_normalize_metric``'s ``{**raw, ...}`` passthrough, so the caveat
        reaches the JSON, the audit CSV rows and the xlsx sheet -- not only
        the panel."""
        from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION

        normalized = normalize_snapshot(
            self._snapshot_for("chirps-v3-sat", "v3-nrt"),
            expected_policy_revision=RAINFALL_METRIC_POLICY_REVISION,
        )
        served = {row["metric"]: row for row in metric_rows(normalized)}
        assert served["annual_normal"]["discrepancies"] == [self._CAVEAT]
        assert served["annual_percentile"]["discrepancies"] == [self._CAVEAT]


# ===========================================================================
# compute.py — antecedents.{d7,d30,d90} cross-year window (lluvia-insights
# slice 2a, task 2a.9/D6)
# ===========================================================================


class TestAntecedentCrossYearWindow:
    """Task 2a.9/D6: d7/d30/d90 end at the CLIPPED disclosure end
    ``min(comparison_end_exclusive, last_interval_end)`` -- not at the raw
    calendar ``comparison_end`` (D6 anchor amendment, LI2A-002) -- and may
    read into the PRIOR year; a gap anywhere in the window suppresses with
    its own reason, never a short sum. The fixtures below publish data
    through the comparison date, so the two anchors coincide here; the
    lagging case has its own real-PG coverage in
    ``test_rainfall_insights_metrics.py``."""

    _COMPARISON_END_EXCLUSIVE = datetime(2025, 1, 21, tzinfo=UTC)  # comparison_end = Jan 20, 2025
    _NOW = datetime(2025, 1, 20, 12, 0, tzinfo=UTC)

    def test_d90_sums_across_the_year_boundary_when_complete(self) -> None:
        from app.domains.geo.rainfall.compute import build_snapshot

        window_start_date = (self._COMPARISON_END_EXCLUSIVE - timedelta(days=90)).date()
        assert window_start_date.year == 2024  # genuinely crosses the year boundary
        intervals = _daily_intervals(start=window_start_date, values=[1.0] * 90)

        snapshot = build_snapshot(
            scope=_ZONE_SCOPE,
            year=2025,
            role="daily",
            source_id="chirps-v3-sat",
            intervals=intervals,
            batch=_fixture_batch_evidence(source_id="chirps-v3-sat"),
            now=self._NOW,
        )
        d90 = snapshot["antecedents"]["d90"]
        assert d90["state"] == "available"
        assert d90["value"] == pytest.approx(90.0)
        assert d90["reason"] is None

        # LI2A-001: D6's "annual.selected provably unaffected by the widened
        # read" claim, pinned by assertion rather than by argument. Of the 90
        # daily rows (2024-10-23 .. 2025-01-20) only the 20 in 2025 are inside
        # build_snapshot's own `in_window` filter, at completeness 1.0
        # (window_end == last_interval_end == 2025-01-21).
        selected = snapshot["annual"]["selected"]
        assert selected["state"] == "available"
        assert selected["value"] == pytest.approx(20.0)
        assert selected["completeness"] == pytest.approx(1.0)

    def test_d90_suppresses_on_a_gap_in_the_prior_year_tail(self) -> None:
        from app.domains.geo.rainfall.compute import build_snapshot

        window_start_date = (self._COMPARISON_END_EXCLUSIVE - timedelta(days=90)).date()
        full = _daily_intervals(start=window_start_date, values=[1.0] * 90)
        gapped = full[:30] + full[31:]  # drop one day -- a hole in the prior-year tail

        snapshot = build_snapshot(
            scope=_ZONE_SCOPE,
            year=2025,
            role="daily",
            source_id="chirps-v3-sat",
            intervals=gapped,
            batch=_fixture_batch_evidence(source_id="chirps-v3-sat"),
            now=self._NOW,
        )
        d90 = snapshot["antecedents"]["d90"]
        assert d90["state"] == "suppressed"
        assert d90["value"] is None
        assert d90["reason"] == "antecedent_window_incomplete"

        # d7 -- entirely within the complete tail -- must stay unaffected by
        # d90's own gap.
        d7 = snapshot["antecedents"]["d7"]
        assert d7["state"] == "available"
        assert d7["value"] == pytest.approx(7.0)

        # LI2A-001: the dropped 2024-11-22 row is a PRIOR-year slot, so
        # annual.selected keeps the same 20 current-year days at 1.0 and the
        # same completeness as the ungapped sibling test above -- the D6
        # widening is provably invisible to it in both directions.
        selected = snapshot["annual"]["selected"]
        assert selected["state"] == "available"
        assert selected["value"] == pytest.approx(20.0)
        assert selected["completeness"] == pytest.approx(1.0)
