"""Repository layer for the geo domain."""

from app.domains.geo.geo_repository_catastro import (
    bulk_upsert_parcelas,
    get_afectados_by_flood_event,
    get_afectados_by_zona,
)
from app.domains.geo.geo_repository_events_rainfall import GeoRepositoryEventsRainfallMixin
from app.domains.geo.geo_repository_jobs_layers import GeoRepositoryJobsLayersMixin
from app.domains.geo.geo_repository_zoning_analysis import GeoRepositoryZoningAnalysisMixin


class GeoRepository(
    GeoRepositoryJobsLayersMixin,
    GeoRepositoryZoningAnalysisMixin,
    GeoRepositoryEventsRainfallMixin,
):
    """Data-access layer for geo jobs, layers, events, and rainfall."""
