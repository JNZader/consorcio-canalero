"""Pure evidence and no-blending selection policy."""

from dataclasses import dataclass

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
        )
        if selectable:
            return SourceSelection(source_id, position > 0, tuple(rejected))
        rejected.append(source_id)
    return SourceSelection(None, False, tuple(rejected))
