"""Shared streaming request body size cap dependency."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request
from starlette.requests import ClientDisconnect


def make_body_limit_dependency(max_bytes_getter: Callable[[], int]):
    """Build a FastAPI dependency that enforces a pre-parse byte ceiling."""

    async def enforce_body_limit(request: Request) -> None:
        max_bytes = max_bytes_getter()
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                declared_len = int(declared)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Content-Length invalido") from exc
            if declared_len < 0:
                raise HTTPException(status_code=400, detail="Content-Length invalido")
            if declared_len > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"El cuerpo excede el limite permitido ({max_bytes} bytes)",
                )

        if hasattr(request, "_body"):
            if len(request._body) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"El cuerpo excede el limite permitido ({max_bytes} bytes)",
                )
            return

        chunks: list[bytes] = []
        total = 0
        try:
            async for chunk in request.stream():
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"El cuerpo excede el limite permitido ({max_bytes} bytes)",
                    )
                chunks.append(chunk)
        except ClientDisconnect:
            raise HTTPException(status_code=499, detail="Cliente desconectado") from None

        request._body = b"".join(chunks)

    return enforce_body_limit
