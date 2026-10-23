"""Regression tests for the production boot gate (`_enforce_production_secrets`).

2026-10-23 audit (NUC-4): the Docker healthcheck refuses to resolve a Host in
production without ``HEALTHCHECK_HOST`` or a parseable ``API_BASE_URL``, exits 1
forever, and the container crash-loops a healthy app. The boot gate now refuses
to start in that same situation, reusing the healthcheck's own resolver so the
two checks cannot drift.
"""

import pytest

from app.config import Settings, _enforce_production_secrets

# Everything the gate checks besides the healthcheck host, valid by
# construction, so a failure in these tests points at the healthcheck rule.
# api_base_url intentionally left at its default ("") — the tests under
# scrutiny control it explicitly.
VALID_PRODUCTION = dict(
    environment="production",
    jwt_secret="a" * 64,
    cors_origins="https://frontend.example.com",
    frontend_url="https://frontend.example.com",
    debug=False,
    rate_limit_disabled=False,
    enable_docs=False,
    smtp_host="",
)


def test_production_without_healthcheck_host_or_api_base_url_refuses_to_start(
    monkeypatch,
):
    monkeypatch.delenv("HEALTHCHECK_HOST", raising=False)
    monkeypatch.delenv("API_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="HEALTHCHECK_HOST"):
        _enforce_production_secrets(Settings(**VALID_PRODUCTION))


def test_production_with_explicit_healthcheck_host_starts(monkeypatch):
    monkeypatch.setenv("HEALTHCHECK_HOST", "api.example.com")
    monkeypatch.delenv("API_BASE_URL", raising=False)

    _enforce_production_secrets(Settings(**VALID_PRODUCTION))


def test_production_with_parseable_api_base_url_starts(monkeypatch):
    monkeypatch.delenv("HEALTHCHECK_HOST", raising=False)
    # Set via the environment the way production wires it; pydantic-settings
    # lifts it into the Settings field the gate reads.
    monkeypatch.setenv("API_BASE_URL", "https://api.example.com")

    _enforce_production_secrets(Settings(**VALID_PRODUCTION))


def test_development_environment_never_enforces_the_gate(monkeypatch):
    monkeypatch.delenv("HEALTHCHECK_HOST", raising=False)
    monkeypatch.delenv("API_BASE_URL", raising=False)

    _enforce_production_secrets(Settings(**{**VALID_PRODUCTION, "environment": "development"}))
