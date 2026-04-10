"""Repository layer for the geo intelligence sub-module."""

from app.domains.geo.intelligence.repository_composites import (
    IntelligenceRepositoryCompositesMixin,
)
from app.domains.geo.intelligence.repository_metrics import (
    IntelligenceRepositoryMetricsMixin,
)
from app.domains.geo.intelligence.repository_zones import (
    IntelligenceRepositoryZonesMixin,
)


class IntelligenceRepository(
    IntelligenceRepositoryZonesMixin,
    IntelligenceRepositoryMetricsMixin,
    IntelligenceRepositoryCompositesMixin,
):
    """Data-access layer for operational intelligence entities."""
