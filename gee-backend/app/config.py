"""
Configuracion de la aplicacion.
Carga variables de entorno y define settings.
"""

import logging
from pydantic_settings import BaseSettings
from typing import Optional

logger = logging.getLogger(__name__)

# Tokens / values we MUST refuse to start with when running outside of dev.
# Detected via a fail-fast check on application boot (see bottom of file).
INSECURE_DEFAULTS = {
    "jwt_secret": {"CHANGE-ME-IN-PRODUCTION", ""},
    "redis_password": {"changeme", ""},
}
MIN_JWT_SECRET_LENGTH = 64  # bytes — matches `openssl rand -hex 32` recommendation


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
    # ``redis_password`` is the bare password used by Coolify / docker-compose
    # for the Redis instance. Only read directly here for the fail-fast check
    # below; runtime code consumes the full ``redis_url`` (which embeds the
    # password in the URL form).
    redis_password: str = ""

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
    # Read once at boot — middleware references settings.rate_limit_disabled,
    # not os.getenv at request time. That way an in-process mutation of
    # the env var can't reopen the bypass after the fail-fast check below.
    rate_limit_disabled: bool = False

    # Error tracking (Sentry) — wired in app/main.py only when sentry_dsn
    # is non-empty. Leaving it empty silently disables the integration
    # (zero overhead, no network), which is the right default for dev
    # and for installs that don't want to ship errors off-box.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0  # 0.0 = no transaction tracing
    sentry_environment: str = ""  # falls back to settings.environment

    # Centralised logs (BetterStack / Logtail) — empty = disabled.
    # Wired in app/core/logging.py. When set, the LogtailHandler is
    # attached to the root logger so every structlog event also ships
    # off-box. Free tier: 1 GB/mes at logtail.com.
    betterstack_token: str = ""
    # Optional override for the ingest endpoint. BetterStack's EU vs US
    # regions have different hostnames; leave empty for the default.
    betterstack_host: str = ""

    # App
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    api_prefix: str = "/api/v2"
    debug: bool = False
    enable_docs: bool = True
    environment: str = "development"  # "production" | "staging" | "development"
    frontend_url: str = "http://localhost:5173"
    api_base_url: str = (
        ""  # Backend public URL (e.g. https://cc10demayo-api.javierzader.com)
    )

    # Photo upload storage (LocalPhotoStorage for now — drop-in swap to S3/MinIO).
    # The directory is mounted as a Docker volume in compose so files survive
    # container rebuilds. The public_base is what we prefix into `foto_url`
    # when persisting; `app.mount("/uploads", StaticFiles(...))` serves it.
    uploads_root: str = "/app/uploads"
    uploads_public_base: str = "/uploads"

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
settings = Settings()


def _is_production_env(environment: str) -> bool:
    """Treat ``staging`` as production for the safety checks."""
    return environment.lower() in {"production", "prod", "staging"}


def _enforce_production_secrets(s: Settings) -> None:
    """Refuse to start in production with placeholder secrets.

    Catches three high-impact misconfigurations the audit flagged:
      - ``JWT_SECRET`` left at ``"CHANGE-ME-IN-PRODUCTION"`` or too short.
      - ``REDIS_PASSWORD`` left at the well-known ``"changeme"``.
      - ``RATE_LIMIT_DISABLED`` set to a truthy value (rate-limit off is
        only acceptable in dev where the threat model is "me at my laptop").

    Any of these in production is an instant security incident; failing
    loud at startup is much safer than letting the app run with them.
    """
    if not _is_production_env(s.environment):
        return

    problems: list[str] = []

    # Trim whitespace BEFORE the length check — a value pasted into a
    # GUI env-var editor (Coolify, Dokku) commonly picks up a trailing
    # ``\n`` or ``\r`` that survives in the JWT signing key and breaks
    # interop. We also warn so the operator fixes the env, not just the
    # symptom.
    jwt_raw = s.jwt_secret
    jwt_trimmed = jwt_raw.strip()
    if jwt_trimmed != jwt_raw:
        logger.warning(
            "JWT_SECRET had leading/trailing whitespace; trimmed in memory. "
            "Update the env var to remove it — different transports trim "
            "differently and the mismatch will eventually bite."
        )
        s.jwt_secret = jwt_trimmed

    if s.jwt_secret in INSECURE_DEFAULTS["jwt_secret"]:
        problems.append(
            "JWT_SECRET is missing or set to the placeholder default; "
            "generate a 64+ byte random value (e.g. `openssl rand -hex 32`)."
        )
    else:
        # Count bytes, not chars — a 32-char unicode string can be much
        # less than 32 bytes of HMAC key material.
        secret_bytes = len(s.jwt_secret.encode("utf-8"))
        if secret_bytes < MIN_JWT_SECRET_LENGTH:
            problems.append(
                f"JWT_SECRET is too short ({secret_bytes} bytes); "
                f"must be at least {MIN_JWT_SECRET_LENGTH} bytes "
                "(use `openssl rand -hex 32` for 64-byte hex)."
            )

    if s.redis_password in INSECURE_DEFAULTS["redis_password"]:
        # Empty is allowed in environments where Redis isn't password-
        # protected at all (e.g. inside a private docker network and not
        # reachable externally) — but ``changeme`` is never OK.
        if s.redis_password == "changeme":
            problems.append(
                "REDIS_PASSWORD is set to the placeholder 'changeme'; "
                "rotate it to a real secret."
            )

    # ``s.rate_limit_disabled`` is parsed by pydantic-settings from the
    # env var (with "1"/"true"/"yes"/"on" → True). Reading the parsed
    # field instead of os.getenv keeps the boot-time check aligned with
    # what the middleware actually sees at runtime — no normalization
    # drift between the two code paths.
    if s.rate_limit_disabled:
        problems.append(
            "RATE_LIMIT_DISABLED is truthy in a production environment; "
            "unset it or set it to 'false'."
        )

    # CORS hardening — with credentials: 'include' on the OAuth flow, a
    # mis-set CORS_ORIGINS that includes localhost or the wildcard '*'
    # becomes a credentialed-CSRF foothold. Refuse to start.
    raw_cors = (settings.cors_origins or "").strip()
    if raw_cors == "" or "*" in raw_cors:
        problems.append(
            "CORS_ORIGINS is empty or contains '*' in production; "
            "set an explicit comma-separated list of frontend origins."
        )
    else:
        from urllib.parse import urlparse

        loopback_hosts = {"localhost", "127.0.0.1", "0.0.0.0"}
        for entry in s.cors_origins_list:
            parsed = urlparse(entry)
            hostname = (parsed.hostname or "").lower()
            # Exact match against the loopback names, plus the ``.localhost``
            # TLD (RFC 6761). Substring matches would reject legitimate
            # hosts like ``my-localhost-tunnel.example.com``.
            if hostname in loopback_hosts or hostname.endswith(".localhost"):
                problems.append(
                    f"CORS_ORIGINS contains a loopback host ({entry}) in "
                    "production; remove dev entries from the env var."
                )
                break

    if problems:
        message = (
            "Refusing to start with insecure configuration:\n  - "
            + "\n  - ".join(problems)
        )
        raise RuntimeError(message)


_enforce_production_secrets(settings)


if not settings.martin_public_url:
    logger.warning(
        "MARTIN_PUBLIC_URL is not set. "
        "The /api/v2/public/layers/catalog endpoint will return tile URLs with an empty base. "
        "Set MARTIN_PUBLIC_URL to the public-facing Martin URL (e.g. https://tiles.example.com)."
    )
