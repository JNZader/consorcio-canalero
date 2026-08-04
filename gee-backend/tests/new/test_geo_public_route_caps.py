"""Caps on the PUBLIC geo routes (batch 4, T3 audit).

Two unauthenticated surfaces were reachable without any bound on the work they
could ask for:

* ``POST /api/v2/geo/basins/approved-zones/current/export-map-pdf`` — takes a
  base64 map capture plus legend rows straight into reportlab. No body limit,
  no image size limit, no list limits.
* ``GET /api/v2/geo/layers/{id}/tiles/{z}/{x}/{y}.png`` — the tile proxy, which
  the global rate limiter deliberately SKIPS (any path containing ``/tiles/``),
  with an unbounded ``z`` feeding a ``2 ** z`` downstream.

Service-free: the PDF builder is exercised directly, and the routes are driven
through ``TestClient`` with the DB dependency and branding stubbed out.
"""

from __future__ import annotations

import base64
import io
import os
import struct
import uuid
import zlib

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-geo-route-caps")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

EXPORT_PATH = "/api/v2/geo/basins/approved-zones/current/export-map-pdf"


def _png_bytes(width: int, height: int) -> bytes:
    """A PNG whose IHDR declares ``width x height``.

    Only the header has to be truthful: the pixel cap is checked from the
    declared dimensions, BEFORE anything decodes the raster.
    """
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def _chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return (
            struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def _data_url(png: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(png).decode()}"


def _lying_png_data_url(width: int, height: int) -> str:
    """A tiny PNG whose IHDR CLAIMS a huge size — the decompression-bomb shape."""
    small = _png_bytes(2, 2)
    ihdr_start = small.index(b"IHDR") + 4
    fake_ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    head = small[: ihdr_start - 8]
    tail = small[ihdr_start + 13 + 4 :]  # skip the original IHDR data AND its CRC
    body = b"IHDR" + fake_ihdr
    chunk = struct.pack(">I", 13) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    return _data_url(head + chunk + tail)


@pytest.fixture
def branding():
    from app.shared.pdf.base import BrandingInfo

    return BrandingInfo(
        nombre_organizacion="Consorcio Test",
        color_primario="#1a5276",
        logo_path=None,
    )


# ── builder-level caps ──────────────────────────────────────────────────────


def test_map_pdf_builder_rejects_an_image_over_the_pixel_cap(branding, monkeypatch) -> None:
    from app.config import settings
    from app.shared.pdf.builders_common import ImagenDemasiadoGrande
    from app.shared.pdf.builders_zoning import build_approved_zoning_map_pdf

    monkeypatch.setattr(settings, "geo_map_pdf_max_image_px", 100, raising=False)
    payload = {"title": "Mapa", "mapImageDataUrl": _data_url(_png_bytes(40, 40))}

    with pytest.raises(ImagenDemasiadoGrande):
        build_approved_zoning_map_pdf(payload, branding)


def test_map_pdf_builder_accepts_an_image_under_the_pixel_cap(branding) -> None:
    from app.shared.pdf.builders_zoning import build_approved_zoning_map_pdf

    payload = {"title": "Mapa", "mapImageDataUrl": _data_url(_png_bytes(8, 8))}

    result = build_approved_zoning_map_pdf(payload, branding)

    assert isinstance(result, io.BytesIO)
    assert result.getvalue()[:4] == b"%PDF"


def test_map_pdf_builder_caps_a_declared_bomb_before_decoding_it(branding) -> None:
    """The cap must be answered from the PNG HEADER.

    An 8000x8000 IHDR on two KB of payload is the decompression-bomb shape. If
    the guard ran after the raster was materialised, this would surface as an
    unreadable-image error (or worse, as the expansion itself) instead of the
    pixel cap.
    """
    from app.shared.pdf.builders_common import ImagenDemasiadoGrande
    from app.shared.pdf.builders_zoning import build_approved_zoning_map_pdf

    payload = {"title": "Mapa", "mapImageDataUrl": _lying_png_data_url(8000, 8000)}

    with pytest.raises(ImagenDemasiadoGrande):
        build_approved_zoning_map_pdf(payload, branding)


def test_map_pdf_builder_rejects_undecodable_image_bytes(branding) -> None:
    """Used to reach the generic 500 handler (and Sentry) from a public route."""
    from app.shared.pdf.builders_common import ImagenInvalida
    from app.shared.pdf.builders_zoning import build_approved_zoning_map_pdf

    payload = {
        "title": "Mapa",
        "mapImageDataUrl": f"data:image/png;base64,{base64.b64encode(b'not a png').decode()}",
    }

    with pytest.raises(ImagenInvalida):
        build_approved_zoning_map_pdf(payload, branding)


# ── route-level caps ────────────────────────────────────────────────────────


@pytest.fixture
def cliente(monkeypatch):
    from app.db.session import get_db
    from app.main import app
    from app.shared.pdf.base import BrandingInfo

    monkeypatch.setattr(
        "app.shared.pdf.get_branding",
        lambda _db: BrandingInfo(
            nombre_organizacion="Consorcio Test",
            color_primario="#1a5276",
            logo_path=None,
        ),
    )
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    yield client
    app.dependency_overrides.clear()


def test_export_map_pdf_still_serves_a_legitimate_capture(cliente) -> None:
    rs = cliente.post(
        EXPORT_PATH,
        json={"title": "Mapa", "mapImageDataUrl": _data_url(_png_bytes(8, 8))},
    )

    assert rs.status_code == 200, rs.text
    assert rs.headers["content-type"] == "application/pdf"


def _oversize_body() -> bytes:
    from app.config import settings

    relleno = b"A" * (settings.geo_map_pdf_max_body_bytes + 4096)
    return b'{"title":"Mapa","mapImageDataUrl":"data:image/png;base64,' + relleno + b'"}'


def _in_chunks(body: bytes, size: int = 65536):
    for i in range(0, len(body), size):
        yield body[i : i + size]


def test_export_map_pdf_rejects_a_body_over_the_cap(cliente) -> None:
    rs = cliente.post(
        EXPORT_PATH,
        content=_oversize_body(),
        headers={"content-type": "application/json"},
    )

    assert rs.status_code == 413, rs.text


def test_export_map_pdf_rejects_an_oversize_body_without_parsing_it(cliente, monkeypatch) -> None:
    """413 must happen BEFORE validation — the point of the guard is that the
    oversize body is never deserialized."""
    from app.domains.geo import router_common

    validaciones: list[object] = []
    original = router_common.ApprovedZonesMapPdfRequest.model_validate

    def _espia(cls, *args, **kwargs):
        validaciones.append(args[0] if args else None)
        return original(*args, **kwargs)

    monkeypatch.setattr(
        router_common.ApprovedZonesMapPdfRequest,
        "model_validate",
        classmethod(_espia),
    )

    rs = cliente.post(
        EXPORT_PATH,
        content=_oversize_body(),
        headers={"content-type": "application/json"},
    )

    assert rs.status_code == 413, rs.text
    assert validaciones == [], "the oversize body must never reach the model"


def test_export_map_pdf_rejects_a_chunked_body_over_the_cap(cliente) -> None:
    """REGRESSION (4R CRITICAL). A body streamed with ``Transfer-Encoding:
    chunked`` carries no ``Content-Length``, so the header check cannot fire and
    only the stream-counting branch stands between the caller and the handler.

    That branch was dead: declaring ``payload: ApprovedZonesMapPdfRequest`` on
    the route made FastAPI await ``request.body()`` before solving dependencies,
    so the guard always saw a cached ``_body`` and returned early. Measured on
    fastapi 0.135.2: an 8.4 MB chunked POST reached the handler. Parsing through
    ``Depends(parse_map_pdf_body)`` is what makes this 413 real.
    """
    rs = cliente.post(
        EXPORT_PATH,
        content=_in_chunks(_oversize_body()),
        headers={"content-type": "application/json"},
    )

    assert "content-length" not in {k.lower() for k in rs.request.headers}
    assert rs.status_code == 413, rs.text


def test_export_map_pdf_keeps_its_request_schema_in_openapi(cliente) -> None:
    """Parsing via a dependency hides the body from FastAPI's inference, so the
    schema is supplied by hand — assert it is there and self-contained.

    The schema comes from ``app.openapi()`` (the method, always available), NOT
    from ``GET /openapi.json``: that route is gated behind ``ENABLE_DOCS`` and
    is off by default in CI, where the HTTP fetch 404s and this test would die
    on a missing ``paths`` key while passing on any dev box with the flag on.
    """
    from app.main import app

    doc = app.openapi()
    operacion = doc["paths"]["/api/v2/geo/basins/approved-zones/current/export-map-pdf"]["post"]

    esquema = operacion["requestBody"]["content"]["application/json"]["schema"]
    assert esquema["properties"]["mapImageDataUrl"]
    definiciones = set(esquema.get("$defs", {}))

    refs = set()

    def _recorrer(nodo):
        if isinstance(nodo, dict):
            if isinstance(nodo.get("$ref"), str):
                refs.add(nodo["$ref"])
            for valor in nodo.values():
                _recorrer(valor)
        elif isinstance(nodo, list):
            for valor in nodo:
                _recorrer(valor)

    _recorrer(esquema)
    colgadas = [r for r in refs if r.removeprefix("#/$defs/") not in definiciones]
    assert not colgadas, f"dangling refs in the map-pdf requestBody: {colgadas}"


def test_export_map_pdf_sheds_load_when_every_slot_is_taken(cliente, monkeypatch) -> None:
    """The pixel cap bounds ONE request; the semaphore bounds how many of those
    are resident at once."""
    from app.domains.geo import router_common

    router_common.reset_map_pdf_slots()
    monkeypatch.setattr(router_common, "PDF_SEMAFORO_TIMEOUT_S", 0.01)
    slots = router_common.get_map_pdf_slots()
    tomados = []
    try:
        while slots.acquire(blocking=False):
            tomados.append(1)
        assert tomados, "the semaphore must start with at least one slot"

        rs = cliente.post(
            EXPORT_PATH,
            json={"title": "Mapa", "mapImageDataUrl": _data_url(_png_bytes(8, 8))},
        )

        assert rs.status_code == 503, rs.text
        assert rs.headers.get("Retry-After")
    finally:
        for _ in tomados:
            slots.release()
        router_common.reset_map_pdf_slots()


def test_export_map_pdf_rejects_too_many_legend_rows(cliente) -> None:
    from app.config import settings

    filas = [
        {"label": f"z{i}", "color": "#ff0000"}
        for i in range(settings.geo_map_pdf_max_legend_items + 1)
    ]

    rs = cliente.post(
        EXPORT_PATH,
        json={
            "title": "Mapa",
            "mapImageDataUrl": _data_url(_png_bytes(8, 8)),
            "zoneLegend": filas,
        },
    )

    assert rs.status_code == 422, rs.text


def test_export_map_pdf_rejects_a_declared_bomb_with_422_not_500(cliente) -> None:
    rs = cliente.post(
        EXPORT_PATH,
        json={"title": "Mapa", "mapImageDataUrl": _lying_png_data_url(8000, 8000)},
    )

    assert rs.status_code == 422, rs.text


# ── tile proxy: bounded z/x/y ───────────────────────────────────────────────


def _tile_url(z: int, x: int, y: int) -> str:
    return f"/api/v2/geo/layers/{uuid.uuid4()}/tiles/{z}/{x}/{y}.png"


def test_tile_proxy_rejects_an_absurd_zoom(cliente) -> None:
    """``z`` feeds ``2 ** z`` downstream — it can never be caller-chosen."""
    rs = cliente.get(_tile_url(1_000_000_000, 0, 0))

    assert rs.status_code == 422, rs.text


def test_tile_proxy_rejects_negative_coordinates(cliente) -> None:
    assert cliente.get(_tile_url(10, -1, 0)).status_code == 422


def test_tile_proxy_answers_204_outside_the_pyramid(cliente) -> None:
    """x/y past ``2 ** z`` is "no tile here", the same answer the upstream gives."""
    rs = cliente.get(_tile_url(2, 4, 0))

    assert rs.status_code == 204


def test_tile_proxy_accepts_the_deepest_supported_zoom(cliente) -> None:
    """z22 must stay reachable — the bound is a ceiling, not a narrowing."""
    from app.domains.geo.router_core import MAX_TILE_ZOOM

    rs = cliente.get(_tile_url(MAX_TILE_ZOOM, 0, 0))

    # No tile service is running in tests: the proxy degrades to 204, which
    # proves the request passed validation instead of being rejected as 422.
    assert rs.status_code == 204
