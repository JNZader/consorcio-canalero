"""Repository layer for the geo intelligence sub-module."""

from sqlalchemy import func

from app.domains.geo.geo_repository_catastro import (
    bulk_upsert_parcelas,
    get_afectados_by_flood_event,
    get_afectados_by_zona,
)
from app.domains.geo.intelligence.repository_composites import IntelligenceRepositoryCompositesMixin
from app.domains.geo.intelligence.repository_metrics import IntelligenceRepositoryMetricsMixin
from app.domains.geo.intelligence.repository_zones import IntelligenceRepositoryZonesMixin


class IntelligenceRepository(
    IntelligenceRepositoryZonesMixin,
    IntelligenceRepositoryMetricsMixin,
    IntelligenceRepositoryCompositesMixin,
):
    """Data-access layer for operational intelligence entities."""
