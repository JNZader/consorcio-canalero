"""Repository layer for the geo domain."""

from app.domains.geo.geo_repository_jobs_layers import GeoRepositoryJobsLayersMixin
from app.domains.geo.geo_repository_zoning_analysis import (
    GeoRepositoryZoningAnalysisMixin,
)


class GeoRepository(
    GeoRepositoryJobsLayersMixin,
    GeoRepositoryZoningAnalysisMixin,
):
    """Data-access layer for geo jobs, layers, and approved zoning."""
