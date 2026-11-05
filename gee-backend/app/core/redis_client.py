"""Shared Redis client options.

A client without ``socket_timeout`` blocks forever on a half-open connection.
That stall takes the rate limiter and the JSON cache with it (R1-003).
"""

from __future__ import annotations

REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS = 2.0
REDIS_SOCKET_TIMEOUT_SECONDS = 2.0


def redis_from_url_kwargs(
    *,
    decode_responses: bool,
    encoding: str | None = None,
) -> dict[str, object]:
    """Keyword arguments every ``Redis.from_url`` call in this app must pass."""
    kwargs: dict[str, object] = {
        "decode_responses": decode_responses,
        "socket_connect_timeout": REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS,
        "socket_timeout": REDIS_SOCKET_TIMEOUT_SECONDS,
    }
    if encoding is not None:
        kwargs["encoding"] = encoding
    return kwargs
