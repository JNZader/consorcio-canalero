"""
Configuracion de la aplicacion.
Carga variables de entorno y define settings.
"""

from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional


class Settings(BaseSettings):
    """Configuracion de la aplicacion."""

    # Supabase - Soporta ambos formatos (nuevo 2025+ y legacy)
    supabase_url: str

    # Nuevo formato (2025+)
    supabase_publishable_key: Optional[str] = None
    supabase_secret_key: Optional[str] = None

    # Legacy formato (retrocompatibilidad)
    supabase_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None

    # JWT Secret
    supabase_jwt_secret: str = ""

    # Google Earth Engine
    gee_key_file_path: Optional[str] = None
    gee_service_account_key: Optional[str] = None
    gee_project_id: str = "cc10demayo"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Contact Information
    contact_phone: str = "+54 353 4000000"  # Phone number shown to users
    contact_email: str = "contacto@consorcio10demayo.gob.ar"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60

    # App
    cors_origins: str = (
        "http://localhost:4321,http://localhost:3000,http://localhost:5173"
    )
    api_prefix: str = "/api/v1"
    debug: bool = False
    frontend_url: str = "http://localhost:4321"

    @property
    def cors_origins_list(self) -> list[str]:
        """Retorna lista de origenes CORS permitidos."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def effective_publishable_key(self) -> str:
        """Retorna la publishable/anon key efectiva (nuevo o legacy)."""
        return self.supabase_publishable_key or self.supabase_key or ""

    @property
    def effective_secret_key(self) -> Optional[str]:
        """Retorna la secret/service_role key efectiva (nuevo o legacy)."""
        return self.supabase_secret_key or self.supabase_service_role_key

    @model_validator(mode="after")
    def validate_supabase_keys(self):
        """Validar que al menos una key de Supabase este configurada."""
        has_new = self.supabase_publishable_key is not None
        has_legacy = self.supabase_key is not None
        if not has_new and not has_legacy:
            raise ValueError(
                "Se requiere SUPABASE_PUBLISHABLE_KEY (nuevo) o SUPABASE_KEY (legacy)"
            )
        return self

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        populate_by_name = True


# Instancia global de settings
settings = Settings()  # type: ignore[call-arg]
