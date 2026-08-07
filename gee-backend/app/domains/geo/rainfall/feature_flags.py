"""Per-deployment feature flags for Rainfall v2 source-role activation."""

from dataclasses import dataclass
from typing import Any

RAINFALL_SOURCE_ROLES = ("historical", "daily", "intensity", "validation")


@dataclass(frozen=True, slots=True)
class RainfallFeatureFlags:
    historical: bool = False
    daily: bool = False
    intensity: bool = False
    validation: bool = False

    def is_enabled(self, role: str) -> bool:
        return getattr(self, role, False)

    def __getitem__(self, role: str) -> bool:
        return self.is_enabled(role)


def get_rainfall_feature_flags(settings_blob: dict[str, Any]) -> RainfallFeatureFlags:
    """Read source-role activation flags from a settings value blob."""
    raw = settings_blob.get("rainfall_feature_flags") if isinstance(settings_blob, dict) else None
    if not isinstance(raw, dict):
        raw = {}
    resolved: dict[str, bool] = {}
    for role in RAINFALL_SOURCE_ROLES:
        value = raw.get(role)
        resolved[role] = isinstance(value, bool) and value
    return RainfallFeatureFlags(**resolved)
