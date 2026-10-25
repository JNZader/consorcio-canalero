"""SEG-1 regression coverage: decoded-pixel cap + off-loop Pillow work.

Audit 2026-10-23 (`docs/auditorias/AUDITORIA_CONSORCIO_CANALERO_2026-10-23.md`,
finding SEG-1): the denuncia photo upload path bounded only the COMPRESSED
bytes (10 MB). A 10 MB JPEG can declare ~100-150 Mpx, and Pillow decoded it
twice (verify + re-encode) synchronously inside `async def save` — hundreds
of MB of RGB per request, on the event loop, for any authenticated citizen.
The repo already capped the same class of bomb on the map-PDF surface with
`geo_map_pdf_max_image_px`; these tests pin the mirrored fix for photos.
"""

from __future__ import annotations

import io
import struct
import threading
import zlib

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.shared import storage as storage_module
from app.shared.storage import LocalPhotoStorage


def _png_bytes(size: tuple[int, int], color: str = "steelblue") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def _lying_png_bytes(width: int, height: int) -> bytes:
    """PNG whose IHDR declares ``width x height`` on a tiny 8x8 payload.

    A few dozen bytes of real data carrying a giant declared raster is the
    decompression-bomb shape: the pixel count is only answerable from the
    HEADER, before any decode work.
    """
    data = bytearray(_png_bytes((8, 8)))
    data[16:24] = struct.pack(">II", width, height)
    data[29:33] = struct.pack(">I", zlib.crc32(bytes(data[12:29])) & 0xFFFFFFFF)
    return bytes(data)


def _gps_jpeg_bytes() -> bytes:
    """JPEG carrying an EXIF GPSInfo IFD (GPSLatitudeRef + GPSLatitude).

    Pillow 12 cannot serialize a nested GPS IFD from scratch (``Exif.tobytes``
    needs a file-backed Exif), so the TIFF blob is hand-packed:
    IFD0 -> GPSInfo IFD at offset 26 -> 3 RATIONALs at offset 56.
    """
    ifd0 = struct.pack("<H", 1)
    ifd0 += struct.pack("<HHII", 0x8825, 4, 1, 26)  # GPSInfo IFD pointer
    ifd0 += struct.pack("<I", 0)  # no next IFD
    gps = struct.pack("<H", 2)
    gps += struct.pack("<HHI4s", 0x0001, 2, 2, b"N\x00\x00\x00")  # GPSLatitudeRef
    gps += struct.pack("<HHII", 0x0002, 5, 3, 56)  # GPSLatitude: 3 RATIONALs
    gps += struct.pack("<I", 0)
    rationals = b"".join(struct.pack("<II", value, 1) for value in (12, 34, 0))
    tiff = b"II\x2a\x00\x08\x00\x00\x00" + ifd0 + gps + rationals
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color=(180, 30, 30)).save(
        buffer, format="JPEG", exif=b"Exif\x00\x00" + tiff
    )
    return buffer.getvalue()


def _upload(data: bytes, content_type: str = "image/png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename="photo.png",
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.asyncio
async def test_photo_over_the_pixel_cap_is_rejected(tmp_path, monkeypatch) -> None:
    """RED-CHECK: a valid image inside the 10 MB byte cap but over the pixel
    cap must be rejected with a 400 naming the limit, not decoded twice."""
    from app.config import settings

    monkeypatch.setattr(settings, "denuncia_photo_max_image_px", 100, raising=False)
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")

    with pytest.raises(HTTPException) as exc_info:
        await storage.save(_upload(_png_bytes((40, 40))), "denuncias/abc")

    assert exc_info.value.status_code == 400
    assert "píxeles" in exc_info.value.detail
    assert "40x40" in exc_info.value.detail
    assert list((tmp_path / "denuncias").glob("*")) == []


@pytest.mark.asyncio
async def test_declared_pixel_bomb_is_capped_from_the_header(tmp_path) -> None:
    """75 bytes of payload declaring 7000x7000 (= 49 Mpx) must trip the
    DEFAULT 40 Mpx cap from the IHDR header — before any decode."""
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")

    with pytest.raises(HTTPException) as exc_info:
        await storage.save(_upload(_lying_png_bytes(7000, 7000)), "denuncias/abc")

    assert exc_info.value.status_code == 400
    assert "7000x7000" in exc_info.value.detail


@pytest.mark.asyncio
async def test_header_over_pillows_own_bomb_error_maps_to_400(tmp_path) -> None:
    """Pillow hard-rejects headers declaring > ~179 Mpx at open() with
    DecompressionBombError (an Exception, NOT an OSError). It must map to
    the pixel-cap 400 instead of escaping storage as a 500."""
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")

    with pytest.raises(HTTPException) as exc_info:
        await storage.save(_upload(_lying_png_bytes(20000, 20000)), "denuncias/abc")

    assert exc_info.value.status_code == 400
    assert "píxeles" in exc_info.value.detail


@pytest.mark.asyncio
async def test_under_cap_photo_is_saved_with_exif_gps_stripped(tmp_path) -> None:
    """Behavior pin: an under-cap JPEG saves, decodes at the original
    dimensions, and its EXIF GPS coordinates do not survive."""
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")

    url = await storage.save(_upload(_gps_jpeg_bytes(), content_type="image/jpeg"), "denuncias/abc")

    assert url == "/uploads/denuncias/abc.jpg"
    saved = Image.open(io.BytesIO((tmp_path / "denuncias/abc.jpg").read_bytes()))
    assert saved.size == (32, 32)
    assert saved.format == "JPEG"
    gps = saved.getexif().get_ifd(0x8825)
    assert 0x0001 not in gps  # GPSLatitudeRef
    assert 0x0002 not in gps  # GPSLatitude


@pytest.mark.asyncio
async def test_pillow_validation_runs_off_the_event_loop(tmp_path, monkeypatch) -> None:
    """RED-CHECK: the Pillow decode/re-encode must run in the worker
    threadpool, never on the event-loop thread."""
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")
    loop_thread = threading.get_ident()
    worker_threads: list[int] = []
    real = storage_module._validate_and_strip_exif

    def spy(content: bytes, declared_mime: str) -> bytes:
        worker_threads.append(threading.get_ident())
        return real(content, declared_mime)

    monkeypatch.setattr(storage_module, "_validate_and_strip_exif", spy)

    url = await storage.save(_upload(_png_bytes((8, 8))), "denuncias/abc")

    assert url == "/uploads/denuncias/abc.png"
    assert worker_threads and worker_threads[0] != loop_thread


@pytest.mark.asyncio
async def test_concurrent_pipelines_beyond_the_slot_bound_get_503(tmp_path, monkeypatch) -> None:
    """RSK1-001 (SEG-1 review): the pixel cap bounds ONE request; the slot
    bound caps how many pipelines run at once. With one slot, a second
    save while the first is mid-flight must answer 503 + Retry-After
    immediately (non-blocking acquire — the loop never waits), and the
    queue must recover once the slot frees."""
    import asyncio
    import threading

    from app.config import settings
    from app.shared import storage as storage_mod

    monkeypatch.setattr(settings, "denuncia_photo_max_concurrency", 1)
    storage_mod.reset_photo_slots()
    try:
        storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")

        gate = threading.Event()
        release = threading.Event()
        real_strip = storage_mod._validate_and_strip_exif

        def gated_strip(data: bytes, content_type: str) -> bytes:
            gate.set()
            release.wait(timeout=5)
            return real_strip(data, content_type)

        monkeypatch.setattr(storage_mod, "_validate_and_strip_exif", gated_strip)

        first = asyncio.create_task(storage.save(_upload(_png_bytes((8, 8))), "denuncias/first"))
        await asyncio.to_thread(gate.wait, timeout=5)  # pipeline 1 is mid-flight

        with pytest.raises(HTTPException) as exc_info:
            await storage.save(_upload(_png_bytes((8, 8))), "denuncias/second")
        assert exc_info.value.status_code == 503
        assert exc_info.value.headers["Retry-After"] == "2"

        release.set()
        saved = await first
        assert saved.endswith("first.png")

        # Slot freed: the next save goes through.
        recovered = await storage.save(_upload(_png_bytes((8, 8))), "denuncias/third")
        assert recovered.endswith("third.png")
    finally:
        release.set()
        storage_mod.reset_photo_slots()
