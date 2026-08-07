"""Versioned, disabled-by-default candidates for the validation spike."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CandidateManifest:
    source_id: str
    source_class: str
    role: str
    cadence_minutes: int
    access_path: str
    provider_revision: str
    checksum: str
    manifest_version: int = 1
    enabled: bool = False


CANDIDATE_MANIFESTS = (
    CandidateManifest(
        "chirps-v3-final",
        "estimated_satellite",
        "historical",
        1440,
        "api",
        "v3-final",
        "pending-spike",
    ),
    CandidateManifest(
        "sqpe-obs", "estimated_radar", "daily", 1440, "api", "pending", "pending-spike"
    ),
    CandidateManifest(
        "sinarame-rqpe", "estimated_radar", "intensity", 30, "api", "pending", "pending-spike"
    ),
    CandidateManifest(
        "imerg-v07", "estimated_satellite", "intensity", 30, "api", "v07", "pending-spike"
    ),
    CandidateManifest(
        "persiann", "estimated_satellite", "intensity", 30, "api", "pending", "pending-spike"
    ),
    CandidateManifest(
        "smn-gauge", "observed_station", "validation", 60, "api", "pending", "pending-spike"
    ),
)
