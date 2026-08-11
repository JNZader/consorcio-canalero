"""Pure evidence and no-blending selection policy."""

from dataclasses import dataclass
from math import isfinite

from app.domains.geo.rainfall.adapters.manifests import CandidateManifest

REQUIRED_CRITERIA = (
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


@dataclass(frozen=True, slots=True)
class EligibilityEvidence:
    access: bool
    licence: bool
    units: bool
    boundaries: bool
    cadence: bool
    completeness: bool
    revisions: bool
    corridor_coverage: bool
    quality: bool
    known_events: bool


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    eligible: bool
    failed_criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EligibilityRecord:
    source_id: str
    role: str
    evidence_revision: str
    eligible: bool
    manifest_version: int
    provider_revision: str
    checksum: str


@dataclass(frozen=True, slots=True)
class SourceRolePolicy:
    role: str
    version: int
    evidence_revision: str
    ordered_source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceSelection:
    chosen_source_id: str | None
    fallback_used: bool
    rejected_source_ids: tuple[str, ...]


def evaluate_eligibility(
    candidate: CandidateManifest, evidence: EligibilityEvidence
) -> EligibilityResult:
    if candidate.access_path == "rendered_image":
        return EligibilityResult(False, ("scrape_rejected",))
    failures = tuple(name for name in REQUIRED_CRITERIA if not getattr(evidence, name))
    return EligibilityResult(not failures, failures)


def select_source(
    policy: SourceRolePolicy,
    eligibility_by_source_id: dict[str, EligibilityRecord],
    manifests_by_source_id: dict[str, CandidateManifest],
) -> SourceSelection:
    """Choose one enabled source only when current role/revision evidence agrees."""
    rejected: list[str] = []
    for position, source_id in enumerate(policy.ordered_source_ids):
        manifest = manifests_by_source_id.get(source_id)
        evidence = eligibility_by_source_id.get(source_id)
        selectable = (
            manifest is not None
            and manifest.enabled
            and manifest.role == policy.role
            and evidence is not None
            and evidence.eligible
            and evidence.source_id == source_id
            and evidence.role == policy.role
            and evidence.evidence_revision == policy.evidence_revision
            and evidence.manifest_version == manifest.manifest_version
            and evidence.provider_revision == manifest.provider_revision
            and evidence.checksum == manifest.checksum
        )
        if selectable:
            return SourceSelection(source_id, position > 0, tuple(rejected))
        rejected.append(source_id)
    return SourceSelection(None, False, tuple(rejected))


@dataclass(frozen=True, slots=True)
class MetricThresholdPolicy:
    """Versioned display thresholds; absent thresholds suppress rather than permit."""

    revision: str
    minimum_coverage_by_metric: dict[str, float]
    minimum_quality_by_metric: dict[str, float]
    duration_threshold: float | None


@dataclass(frozen=True, slots=True)
class PolicyMetricResult:
    value: float | None
    state: str
    reason: str | None


def _is_fraction(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(value)
        and 0 <= value <= 1
    )


def _valid_threshold_policy(policy: MetricThresholdPolicy) -> bool:
    return (
        all(_is_fraction(value) for value in policy.minimum_coverage_by_metric.values())
        and all(_is_fraction(value) for value in policy.minimum_quality_by_metric.values())
        and (
            policy.duration_threshold is None
            or (
                not isinstance(policy.duration_threshold, bool)
                and isinstance(policy.duration_threshold, (int, float))
                and isfinite(policy.duration_threshold)
                and policy.duration_threshold >= 0
            )
        )
    )


def apply_metric_policy(
    policy: MetricThresholdPolicy,
    metric: str,
    *,
    value: float | None,
    coverage: float,
    quality_score: float,
    completeness: float,
) -> PolicyMetricResult:
    """Evaluate one metric without allowing an unrelated failure to suppress it."""
    if not _valid_threshold_policy(policy):
        return PolicyMetricResult(None, "suppressed", "policy_threshold_invalid")
    minimum_coverage = policy.minimum_coverage_by_metric.get(metric)
    minimum_quality = policy.minimum_quality_by_metric.get(metric)
    if minimum_coverage is None or minimum_quality is None:
        return PolicyMetricResult(None, "suppressed", "policy_threshold_unset")
    if metric in {"duration", "peak"} and policy.duration_threshold is None:
        return PolicyMetricResult(None, "suppressed", "policy_threshold_unset")
    if coverage < minimum_coverage or completeness < minimum_coverage:
        return PolicyMetricResult(None, "suppressed", "coverage_below_threshold")
    if quality_score < minimum_quality:
        return PolicyMetricResult(None, "suppressed", "quality_below_threshold")
    if value is None:
        return PolicyMetricResult(None, "unavailable", "metric_value_unavailable")
    return PolicyMetricResult(value, "available", None)


# ---------------------------------------------------------------------------
# Rainfall v2 materialization display thresholds (design.md decision 5d)
# ---------------------------------------------------------------------------

# A frozen module constant, not settings-driven: service.py's `_metric_policy`
# rejects a revision mismatch (the display path reads the policy FROM the
# snapshot, not live), so the policy must be embedded in every snapshot at
# build time and mirrored into `rainfall_analysis_revision.policy_revision`.
# 0.8/0.8 are starting thresholds pending the domain lead's number (Open
# Questions); this same policy is also the write gate PR3's year-rollover
# finalization reuses verbatim (decision 9b) — the two consumers share one
# definition of "good enough to show".
#
# The bump is LOAD-BEARING, not cosmetic -- `data_revision` hashes
# source/family/scope/year/comparison_end/intervals only, so for a key whose
# evidence has not moved a corrected envelope would hit `persist_revision`'s
# ON CONFLICT DO NOTHING and never land. `policy_revision` is the second
# column of `uq_rainfall_analysis_snapshot`, so bumping it makes the corrected
# snapshot a distinct row instead of a discarded duplicate. Old rows stay
# self-consistent: the router normalizes each row with the row's OWN
# policy_revision, so no migration and no snapshot backfill --
# `router.read_analysis` serves them and enqueues a labelled refresh
# (`rainfall.analysis.policy_revision_stale`, workbook §2.1).
#
# History of this constant, newest first -- every entry is a build-time
# envelope change that had to REACH already-materialized keys:
#
# - `-insights-r2` (Ops.6, archive-report.md 2026-08-11 §10): the evidence
#   gate coupling `annual.percentile` to the selected year's own day
#   completeness (`compute._selected_metric_rankable`) is decided at BUILD
#   time, so it only reaches a reader through a NEW revision row. Without
#   this bump the correction is envelope-only: a key already materialized
#   under `-insights` with unmoved evidence keeps serving the biased rank
#   forever, and a completed year -- which neither scheduled sweep revisits
#   -- would never get another chance. The prod population at the time of
#   the bump was zero (all 8 insights revisions sat at selected completeness
#   1.0, so no served rank was actually biased); it is bumped anyway, as
#   cheap insurance for future ingest gaps and for other deployments.
# - `-insights` (lluvia-insights slice 2b, task 2b.6, design.md D3): bumped
#   from "rainfall-v2-2026-08" so the enriched envelope
#   (annual.normal/percentile + antecedents) could land on keys whose
#   evidence had not moved.
RAINFALL_METRIC_POLICY_REVISION = "rainfall-v2-2026-08-insights-r2"

# LI2A-003 (lluvia-insights slice 2b, design.md D4 note): annual_normal and
# annual_percentile carry `completeness = eligible baseline years / 30`, and
# their `quality["score"]` is that SAME number (D4) -- so any threshold above
# 20/30 silently dominates compute.MIN_BASELINE_YEARS, the sample-size floor
# that owns the distinct `baseline_years_below_minimum` reason D5 promises.
# At 0.9 the effective floor was 27 eligible years, and the whole reachable
# 20-26 band was served as `coverage_below_threshold`: a sample-size problem
# wearing a coverage label. Pinned here to exactly `MIN_BASELINE_YEARS / 30`
# -- the same float division `completeness` itself performs, so the boundary
# case compares equal rather than losing to a hand-rounded 0.6667 -- which
# makes the compute-level floor the binding gate and leaves this entry as the
# structural backstop it was meant to be. Written as a literal (not imported
# from compute.py, which imports THIS module) and pinned equal to it by
# `TestBaselineFloorBindsAtDisclosure`.
_BASELINE_SAMPLE_FRACTION = 20 / 30

# lluvia-insights slice 2a, task 2a.11 (design.md D4): five new metric
# entries -- annual_normal/annual_percentile (0.9/0.8, a reference
# climatology is not time-pressured, so it demands more than the
# in-progress "annual" year) and d7/d30/d90 (0.9/0.8 each, a floor above
# temporal.rolling_total's own exact-window refusal). Deliberately NO
# "summary" entry (D4): the report summary is a root-level Spanish string,
# not a MetricResult, and can never be policy_threshold_unset.
RAINFALL_METRIC_POLICY = MetricThresholdPolicy(
    revision=RAINFALL_METRIC_POLICY_REVISION,
    minimum_coverage_by_metric={
        "annual": 0.8,
        "annual_normal": _BASELINE_SAMPLE_FRACTION,
        "annual_percentile": _BASELINE_SAMPLE_FRACTION,
        "d7": 0.9,
        "d30": 0.9,
        "d90": 0.9,
    },
    minimum_quality_by_metric={
        "annual": 0.8,
        # Same fraction as the coverage entry above, and for the same
        # reason: `quality["score"]` for these two IS `completeness`, so a
        # higher value here would re-suppress the exact 20-26 band under
        # `quality_below_threshold` instead of `coverage_below_threshold`
        # -- the same misattribution, a different label (verified by probe).
        "annual_normal": _BASELINE_SAMPLE_FRACTION,
        "annual_percentile": _BASELINE_SAMPLE_FRACTION,
        "d7": 0.8,
        "d30": 0.8,
        "d90": 0.8,
    },
    duration_threshold=None,
)
