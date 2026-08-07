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
