"""Production Uvicorn launcher with fail-closed proxy hostname resolution."""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
from collections.abc import Callable, Iterable

import uvicorn

HostnameResolver = Callable[[str], Iterable[str]]


class ProxyTrustConfigurationError(ValueError):
    """Raised when trusted proxy peers cannot be resolved narrowly."""


def _resolve_hostname(hostname: str) -> tuple[str, ...]:
    addresses = {
        item[4][0]
        for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        if item[0] in {socket.AF_INET, socket.AF_INET6}
    }
    return tuple(sorted(addresses))


def resolve_forwarded_allow_ips(
    configured: str,
    *,
    hostname_resolver: HostnameResolver = _resolve_hostname,
) -> list[str]:
    """Resolve IP/CIDR/hostname entries to Uvicorn trusted peer values."""
    tokens = [token.strip() for token in configured.split(",") if token.strip()]
    if not tokens:
        raise ProxyTrustConfigurationError("FORWARDED_ALLOW_IPS must not be empty")

    resolved: set[str] = set()
    for token in tokens:
        if token == "*":
            raise ProxyTrustConfigurationError("wildcard proxy trust is forbidden")

        if "/" in token:
            try:
                network = ipaddress.ip_network(token, strict=True)
            except ValueError as exc:
                raise ProxyTrustConfigurationError(
                    f"invalid trusted proxy network: {token}"
                ) from exc
            if network.prefixlen == 0:
                raise ProxyTrustConfigurationError("trusting an entire IP family is forbidden")
            resolved.add(str(network))
            continue

        try:
            resolved.add(str(ipaddress.ip_address(token)))
            continue
        except ValueError:
            pass

        try:
            addresses = tuple(hostname_resolver(token))
        except (OSError, ValueError) as exc:
            raise ProxyTrustConfigurationError(
                f"could not resolve trusted proxy hostname: {token}"
            ) from exc
        if not addresses:
            raise ProxyTrustConfigurationError(
                f"trusted proxy hostname returned no addresses: {token}"
            )
        for address in addresses:
            try:
                resolved.add(str(ipaddress.ip_address(address)))
            except ValueError as exc:
                raise ProxyTrustConfigurationError(
                    f"trusted proxy hostname returned an invalid address: {address}"
                ) from exc

    return sorted(resolved)


def main() -> None:
    try:
        trusted_peers = resolve_forwarded_allow_ips(
            os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
        )
    except ProxyTrustConfigurationError as exc:
        print(f"Invalid FORWARDED_ALLOW_IPS: {exc}", file=sys.stderr)
        raise SystemExit(78) from exc

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        workers=2,
        proxy_headers=True,
        forwarded_allow_ips=trusted_peers,
    )


if __name__ == "__main__":
    main()
