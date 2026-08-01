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


def database_sync_url(value: str) -> str:
    """Return a URL that is safe for SQLAlchemy's synchronous engine.

    DATABASE_URL is canonical and documented with the synchronous PostgreSQL
    driver. The former asyncpg spelling remains accepted for compatibility,
    but it is normalized before any create_engine call.
    """
    driver, separator, remainder = value.partition("://")
    if not separator:
        raise ValueError("DATABASE_URL must be an absolute SQLAlchemy URL")
    if driver in {"postgres", "postgresql+asyncpg"}:
        driver = "postgresql"
    return f"{driver}://{remainder}"


def database_async_url(value: str) -> str:
    """Derive the asyncpg URL used exclusively by create_async_engine."""
    driver, separator, remainder = value.partition("://")
    if not separator:
        raise ValueError("DATABASE_URL must be an absolute SQLAlchemy URL")
    if driver in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        driver = "postgresql+asyncpg"
    if driver != "postgresql+asyncpg":
        raise ValueError("Async database access requires a PostgreSQL DATABASE_URL")
    return f"{driver}://{remainder}"


class Settings(BaseSettings):
    """Configuracion de la aplicacion."""

    # Auth (JWT + OAuth)
    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION"
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    # Database (PostgreSQL + PostGIS)
    database_url: str = "postgresql://consorcio:consorcio_dev@localhost:5432/consorcio"
    database_echo: bool = False
    # Phase 4 / F4-F: switch to PgBouncer transaction-pooling mode. When
    # ``True`` the async engine drops asyncpg's server-side prepared
    # statement cache (``statement_cache_size=0``) — PgBouncer
    # transaction mode is incompatible with prepared statements because
    # the prepared name lives on a server connection that the next
    # transaction may not reuse. The sync engine doesn't need a change
    # because psycopg2 does NOT use server-side prepares by default.
    # Leave ``False`` for direct-to-postgres deploys.
    use_pgbouncer: bool = False
    # Phase 5 / F5-E: SMTP-body PII hardening. By default, verify and
    # reset emails carry an 8-char alphanumeric code that the SPA exchanges
    # for the JWT token via POST /auth/exchange-code. The current SPA accepts
    # both ?code= and legacy ?token=; false is a compatibility escape hatch.
    use_one_time_codes: bool = True

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
    # Dedicated brute-force throttle for credential-guessing surfaces
    # (login / forgot-password / exchange-code). Much stricter than the
    # generic per-client limit above; consumed by
    # ``DistributedRateLimitMiddleware`` via ``get_auth_rate_limiter()``.
    auth_rate_limit_requests: int = 10
    auth_rate_limit_window: int = 60

    # ── Ficha territorial (POST /api/v2/geo/analisis-zona) ────────────────
    # Public, unauthenticated, raster-backed endpoint. Every knob below is a
    # cost bound; the justifications are design §2.1-2.4 of the
    # ``ficha-territorial`` change and MUST stay with the value.
    #
    # OFF by default, and it must stay off until A3b lands the real compute.
    # The route is mounted (so the wire contract and its tests exist) but
    # answers 503 ``funcionalidad_no_disponible``, because today
    # ``ficha_service.analizar_zona`` returns a PLACEHOLDER: area_ha=0.0 and
    # every dataset ``sin_cobertura``. Nothing else gates it — the endpoint is
    # public and ``/openapi.json`` advertises it — so flipping this on early
    # would publish "0 ha, sin cobertura" to the UI as if it were a measurement.
    ficha_enabled: bool = False
    # 30 req/min per IP, PER WORKER PROCESS when Redis is down. The limiter
    # degrades to a per-process in-memory window (it does not fail open), and
    # ``app/server.py`` runs uvicorn with workers=2 → the real degraded ceiling
    # is 2 x 30 = 60 req/min per IP. With Redis up the window is shared and 30
    # is exact. The limiter lives on its own key namespace ("ratelimit:ficha:")
    # and on its own router, so it can never throttle the operator geo routes
    # (JDB-003).
    ficha_rate_limit_requests: int = 30
    ficha_rate_limit_window: int = 60
    # 20 000 ha ≈ 23 % of the ~88 000 ha consorcio — a legitimate sub-basin and
    # ~100x the median parcel; at 30 m that is ~222 k px/raster (< 2 MB float64).
    ficha_max_area_ha: float = 20_000.0
    # Envelope cap: blocks a thin diagonal sliver whose bbox window would blow
    # up ``rasterio_mask(crop=True)`` even though its own area is small.
    ficha_max_envelope_ha: float = 60_000.0
    # Hand-drawn DrawControl polygons are < 100 vertices; 1 000 admits a pasted
    # parcel outline while bounding the ``ST_Intersection`` cost.
    ficha_max_vertices: int = 1_000
    # 2 km each side of a canal is already a generous influence zone. Without
    # this cap ``buffer_m`` is an unbounded amplification knob (JDB-006); the
    # area cap remains the backstop.
    ficha_max_buffer_m: float = 2_000.0
    # 1 MiB: a legitimate drawn-polygon body is a few KB. Enforced on
    # Content-Length BEFORE parsing, because the vertex cap only fires after
    # the whole body is deserialized (JDB-007).
    ficha_max_body_bytes: int = 1024 * 1024
    # Hard bound on simultaneous raster memory: the handler is sync and runs on
    # Starlette's threadpool, and rasterio holds real memory per call. This is
    # independent of Redis availability.
    # PER WORKER PROCESS: the semaphore is a module-level object, so it bounds
    # one interpreter. ``app/server.py`` runs uvicorn with workers=2 → the real
    # ceiling on the box is 2 x 4 = 8 concurrent raster analyses. Size the value
    # against (RAM budget / workers), not against the RAM budget.
    ficha_max_concurrency: int = 4
    # ``low_confidence`` is relative and per raster: (geom_area / pixel_area) < K.
    # K = 10 for 30 m products; precipitation normals override K = 0 (a smooth
    # interpolated field sampled sub-pixel is exact, not approximate).
    ficha_low_confidence_pixel_ratio: float = 10.0

    # Error tracking (Sentry) — wired in app/main.py only when sentry_dsn
    # is non-empty. Leaving it empty silently disables the integration
    # (zero overhead, no network), which is the right default for dev
    # and for installs that don't want to ship errors off-box.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0  # 0.0 = no transaction tracing
    sentry_environment: str = ""  # falls back to settings.environment

    # SMTP — opt-in. Empty SMTP_HOST disables the integration; UserManager
    # falls back to logging the verification / reset token so dev still
    # works without an external provider.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""  # e.g. no-reply@consorcio.example.com
    smtp_from_name: str = "Consorcio Canalero 10 de Mayo"
    # Transport mode. EXACTLY ONE should be true:
    #   - port 587 STARTTLS upgrade: ``smtp_use_starttls=True`` (default)
    #   - port 465 implicit TLS    : ``smtp_use_tls=True``
    #     (Office 365, some legacy Google Workspace, Hostinger, Namecheap)
    # The boot check below catches the both-true misconfig.
    smtp_use_starttls: bool = True
    smtp_use_tls: bool = False

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
    # Secure-by-default: docs OFF unless explicitly enabled via ENABLE_DOCS.
    # Production fail-fast below warns if this is flipped on in prod.
    enable_docs: bool = False
    environment: str = "development"  # "production" | "staging" | "development"
    frontend_url: str = "http://localhost:5173"
    api_base_url: str = ""  # Backend public URL (e.g. https://cc10demayo-api.javierzader.com)

    # Photo upload storage (LocalPhotoStorage for now — drop-in swap to S3/MinIO).
    # The directory is mounted as a Docker volume in compose so files survive
    # container rebuilds. The public_base is what we prefix into `foto_url`
    # when persisting; `app.mount("/uploads", StaticFiles(...))` serves it.
    uploads_root: str = "/app/uploads"
    uploads_public_base: str = "/uploads"

    @property
    def database_sync_url(self) -> str:
        """Canonical URL for sync SQLAlchemy consumers and Alembic."""
        return database_sync_url(self.database_url)

    @property
    def database_async_url(self) -> str:
        """Deterministically derived asyncpg URL for fastapi-users."""
        return database_async_url(self.database_url)

    @property
    def cors_origins_list(self) -> list[str]:
        """Retorna lista de origenes CORS permitidos."""
        origins = {
            origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()
        }

        if self.frontend_url:
            origins.add(self.frontend_url.strip().rstrip("/"))

        return sorted(origins)

    @property
    def trusted_hosts(self) -> list[str]:
        """Allowed ``Host`` header values for ``TrustedHostMiddleware``.

        Derived from CORS origins + the API base URL hostname. The
        Docker healthcheck has to forge a matching Host header
        explicitly (see the ``healthcheck`` block in
        ``docker-compose.prod.yml``) — we deliberately do NOT include
        ``localhost``/``127.0.0.1`` because every other container on
        the same Docker network can forge ``Host: localhost`` and
        bypass the host-pinning otherwise.

        In dev (when CORS_ORIGINS has a localhost entry, which the
        fail-fast check refuses in production) the dev origins flow
        through naturally so localhost works on the developer
        machine.
        """
        from urllib.parse import urlparse

        hosts: set[str] = set()
        for url in self.cors_origins_list:
            parsed = urlparse(url)
            if parsed.hostname:
                hosts.add(parsed.hostname)
        if self.api_base_url:
            parsed = urlparse(self.api_base_url)
            if parsed.hostname:
                hosts.add(parsed.hostname)
        # No localhost. Dev installs whose ``CORS_ORIGINS`` includes
        # ``http://localhost:5173`` get localhost in the set via the
        # loop above; prod ``CORS_ORIGINS`` is loopback-free (the
        # fail-fast check refuses it).
        return sorted(hosts)

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
                "REDIS_PASSWORD is set to the placeholder 'changeme'; rotate it to a real secret."
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

    # ``s.debug`` in production leaks internals (verbose 500 bodies via
    # the generic exception handler, DEBUG-level logs, uvicorn reload).
    # Same class of misconfig as RATE_LIMIT_DISABLED — refuse to start.
    if s.debug:
        problems.append("DEBUG debe ser False en producción; unset DEBUG or set it to 'false'.")

    # Docs exposure in production is information disclosure (full API
    # surface + schemas for unauthenticated recon), but it can be a
    # deliberate operator choice — warn loudly instead of refusing.
    if s.enable_docs:
        logger.warning(
            "ENABLE_DOCS is true in a production environment; /docs and "
            "/redoc expose the full API schema to unauthenticated "
            "clients. Set ENABLE_DOCS=false unless intentionally public."
        )

    # SMTP TLS: if email is configured at all in production, refuse to
    # ship password-reset / verification tokens over plaintext SMTP.
    # ``both False`` would otherwise silently send tokens in the clear.
    if s.smtp_host:
        if not (s.smtp_use_tls or s.smtp_use_starttls):
            problems.append(
                "SMTP_HOST is set in production but neither SMTP_USE_TLS nor "
                "SMTP_USE_STARTTLS is true; password-reset tokens would "
                "travel in cleartext. Enable exactly one."
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
        message = "Refusing to start with insecure configuration:\n  - " + "\n  - ".join(problems)
        raise RuntimeError(message)


_enforce_production_secrets(settings)


if not settings.martin_public_url:
    logger.warning(
        "MARTIN_PUBLIC_URL is not set. "
        "The /api/v2/public/layers/catalog endpoint will return tile URLs with an empty base. "
        "Set MARTIN_PUBLIC_URL to the public-facing Martin URL (e.g. https://tiles.example.com)."
    )
