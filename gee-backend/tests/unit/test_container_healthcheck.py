"""Unit contracts for the dependency-free container liveness probe."""

from __future__ import annotations

from typing import Any

import pytest


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status


def _install_connection(
    monkeypatch: pytest.MonkeyPatch,
    healthcheck: Any,
    *,
    status: int = 204,
    error: Exception | None = None,
) -> list[Any]:
    instances: list[Any] = []

    class FakeConnection:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            self.transport = (host, port, timeout)
            self.request_args: tuple[str, str, dict[str, str]] | None = None
            self.closed = False
            instances.append(self)

        def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
            self.request_args = (method, path, headers)
            if error is not None:
                raise error

        def getresponse(self) -> _Response:
            return _Response(status)

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(healthcheck.http.client, "HTTPConnection", FakeConnection)
    return instances


def test_probe_connects_only_to_loopback_and_sends_explicit_host(monkeypatch) -> None:
    from app import healthcheck

    instances = _install_connection(monkeypatch, healthcheck)

    assert healthcheck.probe_liveness(
        {
            "ENVIRONMENT": "production",
            "HEALTHCHECK_HOST": "api.health.example",
            "API_BASE_URL": "https://ignored.example/api",
        }
    )

    assert len(instances) == 1
    connection = instances[0]
    assert connection.transport == ("127.0.0.1", 8000, 5.0)
    assert connection.request_args == (
        "GET",
        "/live",
        {"Host": "api.health.example"},
    )
    assert connection.closed is True


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        (
            {
                "HEALTHCHECK_HOST": " explicit.example ",
                "API_BASE_URL": "https://ignored.example:8443/api",
            },
            "explicit.example",
        ),
        ({"API_BASE_URL": "https://Api.Example:8443/api/v2"}, "api.example"),
        ({"API_BASE_URL": "http://[2001:db8::5]:8000/live"}, "2001:db8::5"),
        ({"ENVIRONMENT": "development", "API_BASE_URL": "http://[broken"}, "localhost"),
        ({"ENVIRONMENT": "production", "API_BASE_URL": "http://[broken"}, None),
    ],
)
def test_host_precedence_and_url_parsing(environment: dict[str, str], expected: str | None) -> None:
    from app import healthcheck

    assert healthcheck.resolve_healthcheck_host(environment) == expected


@pytest.mark.parametrize("environment", ["production", "prod", "staging", "STAGING"])
def test_production_without_explicit_or_api_host_fails_closed(
    monkeypatch, environment: str
) -> None:
    from app import healthcheck

    instances = _install_connection(monkeypatch, healthcheck)
    env = {"ENVIRONMENT": environment}

    assert healthcheck.resolve_healthcheck_host(env) is None
    assert healthcheck.probe_liveness(env) is False
    assert healthcheck.main(env) == 1
    assert instances == []


def test_development_without_config_uses_localhost_host_header(monkeypatch) -> None:
    from app import healthcheck

    instances = _install_connection(monkeypatch, healthcheck, status=200)
    env = {"ENVIRONMENT": "development"}

    assert healthcheck.resolve_healthcheck_host(env) == "localhost"
    assert healthcheck.main(env) == 0
    assert instances[0].request_args == ("GET", "/live", {"Host": "localhost"})
    assert instances[0].closed is True


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [(200, 0), (302, 0), (399, 0), (199, 1), (400, 1), (503, 1)],
)
def test_only_200_through_399_are_healthy(monkeypatch, status: int, expected_exit: int) -> None:
    from app import healthcheck

    instances = _install_connection(monkeypatch, healthcheck, status=status)

    assert (
        healthcheck.main({"ENVIRONMENT": "production", "HEALTHCHECK_HOST": "api.example"})
        == expected_exit
    )
    assert instances[0].closed is True


def test_connection_error_fails_closed_and_closes_connection(monkeypatch) -> None:
    from app import healthcheck

    instances = _install_connection(
        monkeypatch,
        healthcheck,
        error=ConnectionError("connection refused"),
    )

    assert (
        healthcheck.probe_liveness({"ENVIRONMENT": "production", "HEALTHCHECK_HOST": "api.example"})
        is False
    )
    assert instances[0].closed is True
