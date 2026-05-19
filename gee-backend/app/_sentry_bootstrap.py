"""Sentry bootstrap — runs BEFORE ``app.config`` is imported.

The production fail-fast in ``app/config.py`` raises ``RuntimeError`` at
module-import time if env vars are mis-configured (placeholder JWT,
wildcard CORS, etc.). When that happens it's the highest-impact error
the operator can hit, and it must NOT be invisible to Sentry — but the
config module hasn't loaded yet, so we can't rely on
``settings.sentry_dsn`` to initialise the SDK.

This module reads ``SENTRY_DSN`` straight from ``os.environ`` and
initialises Sentry as soon as it is imported. ``app/main.py`` imports
it as the very first line. If the DSN is unset, this is a no-op.
"""

from __future__ import annotations

import os


def _bootstrap() -> None:
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        # SDK not installed in this environment (e.g. minimal test image).
        return

    environment = (
        os.environ.get("SENTRY_ENVIRONMENT", "").strip()
        or os.environ.get("ENVIRONMENT", "").strip()
        or "development"
    )
    sample_raw = os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0").strip() or "0"
    try:
        traces_sample_rate = float(sample_raw)
    except ValueError:
        traces_sample_rate = 0.0

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        # PII off — matches the rest of the codebase (auth tokens
        # redacted, producer names stripped from public assets).
        send_default_pii=False,
    )


_bootstrap()
