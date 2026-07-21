"""Version-compatible helpers for security contracts over FastAPI routes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol

from fastapi import APIRouter
from fastapi.routing import APIRoute


class EffectiveAPIRoute(Protocol):
    """APIRoute surface after inherited router context is applied."""

    path: str
    dependant: Any


def iter_effective_api_routes(router: APIRouter) -> Iterator[EffectiveAPIRoute]:
    """Yield API routes with their effective prefixes and dependencies.

    FastAPI 0.138+ keeps included routers lazy and exposes public
    ``iter_route_contexts`` objects that proxy the effective route surface.
    Older supported releases flatten included routers directly into
    ``router.routes``, so direct ``APIRoute`` iteration is sufficient there.
    """
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:
        for route in router.routes:
            if isinstance(route, APIRoute):
                yield route
        return

    for route_context in iter_route_contexts(router.routes):
        if isinstance(route_context.route, APIRoute):
            yield route_context
