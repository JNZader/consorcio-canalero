"""Dependency-free liveness probe for backend container healthchecks."""

from __future__ import annotations

from collections.abc import Mapping
import http.client
import os
from urllib.parse import urlsplit

TRANSPORT_HOST = "127.0.0.1"
TRANSPORT_PORT = 8000
LIVE_PATH = "/live"
TIMEOUT_SECONDS = 5.0
_PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod", "staging"})


def _is_production(environment: str) -> bool:
    return environment.strip().lower() in _PRODUCTION_ENVIRONMENTS


def _api_base_url_hostname(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() not in {"http", "https"}:
            return None
        return parsed.hostname
    except ValueError:
        return None


def resolve_healthcheck_host(environ: Mapping[str, str]) -> str | None:
    """Resolve the explicit Host header without changing the TCP target."""
    explicit_host = environ.get("HEALTHCHECK_HOST", "").strip()
    if explicit_host:
        return explicit_host

    api_hostname = _api_base_url_hostname(environ.get("API_BASE_URL", ""))
    if api_hostname:
        return api_hostname

    if _is_production(environ.get("ENVIRONMENT", "")):
        return None
    return "localhost"


def probe_liveness(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether the loopback-only ``/live`` probe is healthy."""
    effective_environ = os.environ if environ is None else environ
    host_header = resolve_healthcheck_host(effective_environ)
    if host_header is None:
        return False

    connection: http.client.HTTPConnection | None = None
    try:
        connection = http.client.HTTPConnection(
            TRANSPORT_HOST,
            TRANSPORT_PORT,
            timeout=TIMEOUT_SECONDS,
        )
        connection.request("GET", LIVE_PATH, headers={"Host": host_header})
        response = connection.getresponse()
        return 200 <= response.status < 400
    except Exception:
        return False
    finally:
        if connection is not None:
            connection.close()


def main(environ: Mapping[str, str] | None = None) -> int:
    """Return the process exit status expected by Docker healthchecks."""
    return 0 if probe_liveness(environ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
