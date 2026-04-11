"""Repository layer for the geo domain."""

from app.domains.geo.geo_repository_jobs_layers import GeoRepositoryJobsLayersMixin


class GeoRepository(GeoRepositoryJobsLayersMixin):
    """Data-access layer for geo jobs and layers."""
