"""GEE initialization retries transient failures but latches permanent credential errors."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

import app.domains.geo.gee_service as gee_service


def _reset_init_state(monkeypatch, clock) -> None:
    monkeypatch.setattr(gee_service, "_gee_initialized", False)
    monkeypatch.setattr(gee_service, "_gee_init_error", None)
    monkeypatch.setattr(gee_service, "_gee_init_retry_at", 0.0, raising=False)
    monkeypatch.setattr(gee_service, "_gee_init_failures", 0, raising=False)
    monkeypatch.setattr(gee_service, "_gee_init_permanent_error", False, raising=False)
    monkeypatch.setattr(gee_service, "_monotonic", lambda: clock[0], raising=False)
    monkeypatch.setattr(gee_service, "GEE_INIT_RETRY_BASE_SECONDS", 5.0, raising=False)
    monkeypatch.setattr(gee_service.settings, "gee_key_file_path", None)
    monkeypatch.setattr(gee_service.settings, "gee_service_account_key", None)
    monkeypatch.setattr(gee_service, "_gee_credential_fingerprint", None, raising=False)


def test_transient_init_failure_retries_after_cooldown(monkeypatch) -> None:
    clock = [100.0]
    _reset_init_state(monkeypatch, clock)
    initialize = MagicMock(side_effect=[ConnectionError("network down"), None])
    monkeypatch.setattr(gee_service.ee, "Initialize", initialize)

    with pytest.raises(ValueError):
        gee_service._ensure_initialized()
    with pytest.raises(RuntimeError):
        gee_service._ensure_initialized()
    assert initialize.call_count == 1

    clock[0] += 5.1
    gee_service._ensure_initialized()
    assert initialize.call_count == 2
    assert gee_service.is_initialized() is True


def test_permanent_credential_failure_is_not_retried(monkeypatch) -> None:
    clock = [100.0]
    _reset_init_state(monkeypatch, clock)
    monkeypatch.setattr(
        gee_service.settings,
        "gee_service_account_key",
        '{"client_email":"broken@example.com","private_key":"invalid"}',
    )
    credentials = MagicMock(side_effect=ValueError("invalid credentials"))
    monkeypatch.setattr(gee_service.ee, "ServiceAccountCredentials", credentials)

    with pytest.raises(ValueError):
        gee_service._ensure_initialized()
    clock[0] += 600
    with pytest.raises(RuntimeError):
        gee_service._ensure_initialized()
    assert credentials.call_count == 1


def test_replacing_the_mounted_key_file_reinitializes(monkeypatch, tmp_path) -> None:
    """GEE-01: a new file at the same path drops the cached session."""
    clock = [100.0]
    _reset_init_state(monkeypatch, clock)
    key = tmp_path / "gee-service-account.json"
    key.write_text('{"client_email":"a@example.com"}')
    monkeypatch.setattr(gee_service.settings, "gee_key_file_path", str(key))
    credentials = MagicMock()
    initialize = MagicMock()
    reset = MagicMock()
    monkeypatch.setattr(gee_service.ee, "ServiceAccountCredentials", credentials)
    monkeypatch.setattr(gee_service.ee, "Initialize", initialize)
    monkeypatch.setattr(gee_service.ee, "Reset", reset)

    gee_service._ensure_initialized()
    assert initialize.call_count == 1
    assert reset.call_count == 0

    key.write_text('{"client_email":"b@example.com"}')
    stat = key.stat()
    os.utime(key, ns=(stat.st_mtime_ns + 1_000_000, stat.st_mtime_ns + 1_000_000))
    gee_service._ensure_initialized()

    assert reset.call_count == 1
    assert initialize.call_count == 2
    assert gee_service.is_initialized() is True
