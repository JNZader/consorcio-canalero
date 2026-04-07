"""
Configuracion de la aplicacion.
Carga variables de entorno y define settings.
"""

import logging
from pydantic_settings import BaseSettings
from typing import Optional

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Configuracion de la aplicacion."""

    # Auth (JWT + OAuth)
    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION"
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    # Database (PostgreSQL + PostGIS)
    database_url: str = "postgresql://consorcio:consorcio_dev@localhost:5432/consorcio"
    database_echo: bool = False

    # Google Earth Engine
    gee_key_file_path: Optional[str] = None
    gee_service_account_key: Optional[str] = None
    gee_project_id: str = "cc10demayo"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Geo Worker tile service (internal URL within Docker network)
    geo_worker_tile_url: str = "http://geo-worker:8001"

    # Martin tile server (Vector Tiles)
    martin_internal_url: str = "http://martin:3000"  # Internal Docker network URL
    martin_public_url: str = ""  # Public-facing base URL for tile URL templates

    # Contact Information
    contact_phone: str = "+54 353 4000000"
    contact_email: str = "contacto@consorcio10demayo.gob.ar"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60

    # App
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    api_prefix: str = "/api/v2"
    debug: bool = False
    enable_docs: bool = True
    frontend_url: str = "http://localhost:5173"
    api_base_url: str = (
        ""  # Backend public URL (e.g. https://cc10demayo-api.javierzader.com)
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Retorna lista de origenes CORS permitidos."""
        origins = {
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        }

        if self.frontend_url:
            origins.add(self.frontend_url.strip().rstrip("/"))

        return sorted(origins)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        populate_by_name = True


# Instancia global de settings
settings = Settings()  # type: ignore[call-arg]

if not settings.martin_public_url:
    logger.warning(
        "MARTIN_PUBLIC_URL is not set. "
        "The /api/v2/public/layers/catalog endpoint will return tile URLs with an empty base. "
        "Set MARTIN_PUBLIC_URL to the public-facing Martin URL (e.g. https://tiles.example.com)."
    )
